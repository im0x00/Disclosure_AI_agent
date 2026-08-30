import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from reasoning.core.core_models import ComputationIntent, VerificationIssue
from reasoning.core.evidence_adapters import (
    binding_evidence_payload,
    evidence_reference_pairs,
)
from reasoning.retrieval.models import RetrievalSearchResult

from .executor import ComputationExecutor
from .models import (
    ComputationPlan,
    ComputationPlanningResult,
    ComputationResult,
    DSLVersion,
    Operand,
    OperandBindingResult,
    Primitive,
)

_PLANNER_SYSTEM_PROMPT = """You compile a financial-disclosure computation into a safe DSL.
Return a plan only when the requested computation is expressible with the listed primitives and
operand references. Otherwise return unsupported_reason. Never calculate the final value yourself.

DSL rules:
- Expressions are constant, reference, or operation nodes.
- A reference name must be one of the supplied operand_id values.
- filter, group_by, sort, and distinct callbacks may reference item and index.
- item.path reads a field from the current collection item.
- Build derived metrics by composing primitives; do not invent operation names.
- Use DSL version {version}.

Allowed primitives: {primitives}
"""

_BINDER_SYSTEM_PROMPT = """Bind validated retrieval evidence to required computation operands.
Use only the supplied operand_id values and evidence references. Extract a value only when the
evidence text directly supports it. Preserve unit, period, and scope when present. Put every
unresolved requirement in missing_operand_ids. Never infer or invent a value.
"""


class OperandBindingService:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    async def bind(
        self,
        intent: ComputationIntent,
        retrieval_results: tuple[RetrievalSearchResult, ...],
    ) -> OperandBindingResult:
        binder = self.llm.with_structured_output(
            OperandBindingResult,
            method="json_schema",
        )
        evidence_payload = binding_evidence_payload(retrieval_results)
        raw_result = await binder.ainvoke(
            [
                SystemMessage(content=_BINDER_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Computation intent:\n{intent.model_dump_json()}\n\n"
                        f"Retrieval evidence:\n{json.dumps(evidence_payload, ensure_ascii=False)}"
                    )
                ),
            ]
        )
        binding = (
            raw_result
            if isinstance(raw_result, OperandBindingResult)
            else OperandBindingResult.model_validate(raw_result)
        )
        return self._enforce_evidence_binding(intent, retrieval_results, binding)

    @staticmethod
    def _enforce_evidence_binding(
        intent: ComputationIntent,
        retrieval_results: tuple[RetrievalSearchResult, ...],
        binding: OperandBindingResult,
    ) -> OperandBindingResult:
        required = {requirement.operand_id for requirement in intent.required_operands}
        allowed_references = evidence_reference_pairs(retrieval_results)
        valid_operands = tuple(
            operand
            for operand in binding.operands
            if operand.operand_id in required
            and operand.evidence_refs
            and all(
                (reference.document_id, reference.grain_id) in allowed_references
                for reference in operand.evidence_refs
            )
        )
        bound = {operand.operand_id for operand in valid_operands}
        missing = tuple(sorted(required - bound))
        return OperandBindingResult(
            operands=valid_operands,
            missing_operand_ids=missing,
        )


class ComputationPlanningService:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    async def plan(
        self,
        question: str,
        operands: tuple[Operand, ...],
        feedback: tuple[VerificationIssue, ...] = (),
    ) -> ComputationPlanningResult:
        planner = self.llm.with_structured_output(
            ComputationPlanningResult,
            method="json_schema",
        )
        system_prompt = _PLANNER_SYSTEM_PROMPT.format(
            version=DSLVersion.V1,
            primitives=", ".join(primitive.value for primitive in Primitive),
        )
        operand_payload = [
            operand.model_dump(mode="json", exclude={"evidence_refs"}) for operand in operands
        ]
        feedback_payload = [item.model_dump(mode="json") for item in feedback]
        raw_result = await planner.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=(
                        f"Question:\n{question}\n\n"
                        "Validated operands:\n"
                        f"{json.dumps(operand_payload, ensure_ascii=False)}\n\n"
                        f"Previous verification issues:\n"
                        f"{json.dumps(feedback_payload, ensure_ascii=False)}"
                    )
                ),
            ]
        )
        if isinstance(raw_result, ComputationPlanningResult):
            return raw_result
        return ComputationPlanningResult.model_validate(raw_result)


class ComputationService:
    """Node-independent facade for compiling and executing a computation plan."""

    def __init__(self, executor: ComputationExecutor | None = None) -> None:
        self.executor = executor or ComputationExecutor()

    def compute(
        self,
        plan: ComputationPlan,
        operands: tuple[Operand, ...],
    ) -> ComputationResult:
        return self.executor.execute(plan, operands)
