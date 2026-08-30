import asyncio
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Literal, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from reasoning.computing.nodes import (
    create_computation_execution_node,
    create_computation_planning_node,
    create_operand_binding_node,
)
from reasoning.computing.services import (
    ComputationPlanningService,
    ComputationService,
    OperandBindingService,
)
from reasoning.core.core_models import RuntimeFailure, VerificationAction
from reasoning.core.core_state import DisclosureAIInput, DisclosureAIOutput, DisclosureAIState
from reasoning.core.core_verification import CoreVerificationService, create_core_verification_node
from reasoning.generate_answer.nodes import (
    create_answer_verification_node,
    create_cannot_answer_node,
    create_clarification_node,
    create_final_answer_node,
)
from reasoning.generate_answer.services import ResponseGenerationService
from reasoning.llm import LLMRegistry
from reasoning.query_understanding.nodes import (
    create_query_safety_guard_node,
    create_query_understanding_node,
)
from reasoning.query_understanding.services import (
    QuerySafetyGuardService,
    QueryUnderstandingService,
)
from reasoning.retrieval import RetrievalSearchBackend
from reasoning.retrieval.batch_service import RetrievalBatchService
from reasoning.retrieval.nodes import (
    create_retrieval_plan_node,
    create_retrieval_search_node,
)
from reasoning.retrieval.retrieval import RetrievalQueryCompiler, RetrievalQueryConfig
from reasoning.retrieval.services import RetrievalService
from reasoning.runtime_retry import is_transient_error


@dataclass(frozen=True)
class GraphDependencies:
    query_safety: QuerySafetyGuardService
    query_understanding: QueryUnderstandingService
    retrieval: RetrievalService
    operand_binding: OperandBindingService
    computation_planning: ComputationPlanningService
    computation: ComputationService
    core_verification: CoreVerificationService
    answer_generation: ResponseGenerationService


@dataclass(frozen=True)
class RuntimeNodeRetryPolicy:
    max_attempts: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must not be negative")


@dataclass(frozen=True)
class AnswerRepairPolicy:
    max_generation_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_generation_attempts < 1:
            raise ValueError("max_generation_attempts must be at least 1")


def build_graph(
    dependencies: GraphDependencies,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    runtime_retry_policy: RuntimeNodeRetryPolicy | None = None,
    answer_repair_policy: AnswerRepairPolicy | None = None,
) -> CompiledStateGraph[DisclosureAIState, None, DisclosureAIInput, DisclosureAIOutput]:
    retry_policy = runtime_retry_policy or RuntimeNodeRetryPolicy()
    repair_policy = answer_repair_policy or AnswerRepairPolicy()
    graph = StateGraph(
        DisclosureAIState,
        input_schema=DisclosureAIInput,
        output_schema=DisclosureAIOutput,
    )
    # LangGraph's overloads cannot express partial TypedDict node views over a larger state.
    add_node = cast(Any, graph.add_node)
    add_node(
        "query_safety_guard",
        _with_runtime_retry(
            "query_safety_guard",
            create_query_safety_guard_node(dependencies.query_safety),
            retry_policy,
        ),
    )
    add_node(
        "query_understanding",
        _with_runtime_retry(
            "query_understanding",
            create_query_understanding_node(dependencies.query_understanding),
            retry_policy,
        ),
    )
    add_node(
        "clarification",
        _with_runtime_retry(
            "clarification",
            create_clarification_node(dependencies.answer_generation),
            retry_policy,
        ),
    )
    add_node(
        "retrieval_plan",
        _with_runtime_retry(
            "retrieval_plan",
            create_retrieval_plan_node(dependencies.retrieval),
            retry_policy,
        ),
    )
    add_node(
        "retrieval_search",
        _with_runtime_retry(
            "retrieval_search",
            create_retrieval_search_node(dependencies.retrieval),
            retry_policy,
        ),
    )
    add_node(
        "operand_binding",
        _with_runtime_retry(
            "operand_binding",
            create_operand_binding_node(dependencies.operand_binding),
            retry_policy,
        ),
    )
    add_node(
        "computation_planning",
        _with_runtime_retry(
            "computation_planning",
            create_computation_planning_node(dependencies.computation_planning),
            retry_policy,
        ),
    )
    add_node(
        "computation_execution",
        create_computation_execution_node(dependencies.computation),
    )
    add_node(
        "core_verification",
        _with_runtime_retry(
            "core_verification",
            create_core_verification_node(dependencies.core_verification),
            retry_policy,
        ),
    )
    add_node(
        "final_answer",
        _with_runtime_retry(
            "final_answer",
            create_final_answer_node(dependencies.answer_generation),
            retry_policy,
        ),
    )
    add_node(
        "cannot_answer",
        create_cannot_answer_node(),
    )
    add_node(
        "answer_verification",
        create_answer_verification_node(),
    )

    graph.add_edge(START, "query_safety_guard")
    graph.add_conditional_edges(
        "query_safety_guard",
        _route_after_query_safety_guard,
        {
            "query_understanding": "query_understanding",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "query_understanding",
        _route_after_understanding,
        {
            "clarification": "clarification",
            "retrieval": "retrieval_plan",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "clarification",
        _route_after_clarification,
        {
            "query_understanding": "query_understanding",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "retrieval_plan",
        _route_after_retrieval_plan,
        {
            "retrieval_search": "retrieval_search",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "retrieval_search",
        _route_after_retrieval,
        {
            "bind_operands": "operand_binding",
            "verify": "core_verification",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "operand_binding",
        _route_after_binding,
        {
            "plan_computation": "computation_planning",
            "verify": "core_verification",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "computation_planning",
        _route_after_computation_planning,
        {
            "execute": "computation_execution",
            "verify": "core_verification",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "computation_execution",
        _route_after_computation_execution,
        {
            "core_verification": "core_verification",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "core_verification",
        _route_after_core_verification,
        {
            VerificationAction.PASS: "final_answer",
            VerificationAction.RETRY_RETRIEVAL: "retrieval_plan",
            VerificationAction.RETRY_COMPUTATION: "computation_planning",
            VerificationAction.RETRY_UNDERSTANDING: "query_understanding",
            VerificationAction.CANNOT_ANSWER: "cannot_answer",
            "runtime_failure": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "final_answer",
        _route_after_final_answer,
        {
            "answer_verification": "answer_verification",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_conditional_edges(
        "answer_verification",
        lambda state: _route_after_answer_verification(state, repair_policy),
        {
            "end": END,
            "repair_answer": "final_answer",
            "cannot_answer": "cannot_answer",
        },
    )
    graph.add_edge("cannot_answer", END)
    return graph.compile(checkpointer=checkpointer, name="disclosure-ai-main")


def _route_after_query_safety_guard(
    state: DisclosureAIState,
) -> Literal["query_understanding", "cannot_answer"]:
    if _has_runtime_failure(state):
        return "cannot_answer"
    return "query_understanding" if state["query_safety"].is_safe else "cannot_answer"


def _route_after_understanding(
    state: DisclosureAIState,
) -> Literal["clarification", "retrieval", "cannot_answer"]:
    if _has_runtime_failure(state):
        return "cannot_answer"
    understanding = state["query_understanding"]
    return "clarification" if understanding.needs_clarification else "retrieval"


def _route_after_clarification(
    state: DisclosureAIState,
) -> Literal["query_understanding", "cannot_answer"]:
    return "cannot_answer" if _has_runtime_failure(state) else "query_understanding"


def _route_after_retrieval_plan(
    state: DisclosureAIState,
) -> Literal["retrieval_search", "cannot_answer"]:
    return "cannot_answer" if _has_runtime_failure(state) else "retrieval_search"


def _route_after_retrieval(
    state: DisclosureAIState,
) -> Literal["bind_operands", "verify", "cannot_answer"]:
    if _has_runtime_failure(state):
        return "cannot_answer"
    return "bind_operands" if state.get("computation_intent") is not None else "verify"


def _route_after_binding(
    state: DisclosureAIState,
) -> Literal["plan_computation", "verify", "cannot_answer"]:
    if _has_runtime_failure(state):
        return "cannot_answer"
    binding = state["operand_binding"]
    return "verify" if binding.missing_operand_ids else "plan_computation"


def _route_after_computation_planning(
    state: DisclosureAIState,
) -> Literal["execute", "verify", "cannot_answer"]:
    if _has_runtime_failure(state):
        return "cannot_answer"
    planning = state["computation_planning"]
    return "execute" if planning.plan is not None else "verify"


def _route_after_computation_execution(
    state: DisclosureAIState,
) -> Literal["core_verification", "cannot_answer"]:
    return "cannot_answer" if _has_runtime_failure(state) else "core_verification"


def _route_after_core_verification(
    state: DisclosureAIState,
) -> VerificationAction | Literal["runtime_failure"]:
    if _has_runtime_failure(state):
        return "runtime_failure"
    return state["core_verification"].action


def _route_after_final_answer(
    state: DisclosureAIState,
) -> Literal["answer_verification", "cannot_answer"]:
    return "cannot_answer" if _has_runtime_failure(state) else "answer_verification"


def _route_after_answer_verification(
    state: DisclosureAIState,
    policy: AnswerRepairPolicy,
) -> Literal["end", "repair_answer", "cannot_answer"]:
    verification = state["answer_verification"]
    if verification.status.value == "pass":
        return "end"
    if state.get("answer_generation_attempts", 0) < policy.max_generation_attempts:
        return "repair_answer"
    return "cannot_answer"


def _has_runtime_failure(state: DisclosureAIState) -> bool:
    return state.get("runtime_failure") is not None


def _with_runtime_retry(
    node_name: str,
    node: Any,
    policy: RuntimeNodeRetryPolicy,
) -> Any:
    async def wrapped(state: DisclosureAIState) -> dict[str, Any]:
        last_error: Exception | None = None
        attempts = 0
        for attempt in range(1, policy.max_attempts + 1):
            attempts = attempt
            try:
                result = node(state)
                if isawaitable(result):
                    result = await result
                return cast(dict[str, Any], result)
            except GraphBubbleUp:
                raise
            except Exception as error:
                last_error = error
                if not is_transient_error(error) or attempt >= policy.max_attempts:
                    break
                delay = min(
                    policy.base_delay_seconds * (2 ** (attempt - 1)),
                    policy.max_delay_seconds,
                )
                await asyncio.sleep(delay)
        assert last_error is not None
        return {
            "runtime_failure": RuntimeFailure(
                node=node_name,
                attempts=attempts,
                error_type=type(last_error).__name__,
            )
        }

    return wrapped


def create_main_graph(
    *,
    llms: LLMRegistry,
    search_backend: RetrievalSearchBackend,
    retrieval_query_config: RetrievalQueryConfig,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    runtime_retry_policy: RuntimeNodeRetryPolicy | None = None,
    answer_repair_policy: AnswerRepairPolicy | None = None,
) -> CompiledStateGraph[DisclosureAIState, None, DisclosureAIInput, DisclosureAIOutput]:
    dependencies = GraphDependencies(
        query_safety=QuerySafetyGuardService(llm=llms.default),
        query_understanding=QueryUnderstandingService(llm=llms.default),
        retrieval=RetrievalService(
            llm=llms.default,
            batch_service=RetrievalBatchService(
                query_compiler=RetrievalQueryCompiler(retrieval_query_config),
                search_backend=search_backend,
            ),
        ),
        operand_binding=OperandBindingService(llm=llms.reasoning),
        computation_planning=ComputationPlanningService(llm=llms.reasoning),
        computation=ComputationService(),
        core_verification=CoreVerificationService(llm=llms.reasoning),
        answer_generation=ResponseGenerationService(llm=llms.generation),
    )
    return build_graph(
        dependencies,
        checkpointer=checkpointer or InMemorySaver(),
        runtime_retry_policy=runtime_retry_policy,
        answer_repair_policy=answer_repair_policy,
    )
