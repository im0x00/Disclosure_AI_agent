from dataclasses import dataclass
from typing import Any, Literal, cast

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
from reasoning.generate_answer.nodes import (
    create_answer_verification_node,
    create_cannot_answer_node,
    create_clarification_node,
    create_final_answer_node,
)
from reasoning.generate_answer.services import ResponseGenerationService
from reasoning.query_understanding.nodes import create_query_understanding_node
from reasoning.query_understanding.services import QueryUnderstandingService
from reasoning.retrieval.nodes import (
    create_retrieval_plan_node,
    create_retrieval_search_node,
)
from reasoning.retrieval.services import RetrievalService

from .core_models import VerificationAction
from .core_state import DisclosureAIInput, DisclosureAIOutput, DisclosureAIState
from .core_verification import CoreVerificationService, create_core_verification_node


@dataclass(frozen=True)
class GraphDependencies:
    query_understanding: QueryUnderstandingService
    retrieval: RetrievalService
    operand_binding: OperandBindingService
    computation_planning: ComputationPlanningService
    computation: ComputationService
    core_verification: CoreVerificationService
    answer_generation: ResponseGenerationService


def build_graph(
    dependencies: GraphDependencies,
) -> CompiledStateGraph[DisclosureAIState, None, DisclosureAIInput, DisclosureAIOutput]:
    graph = StateGraph(
        DisclosureAIState,
        input_schema=DisclosureAIInput,
        output_schema=DisclosureAIOutput,
    )
    # LangGraph's overloads cannot express partial TypedDict node views over a larger state.
    add_node = cast(Any, graph.add_node)
    add_node(
        "query_understanding",
        create_query_understanding_node(dependencies.query_understanding),
    )
    add_node(
        "clarification",
        create_clarification_node(dependencies.answer_generation),
    )
    add_node(
        "retrieval_plan",
        create_retrieval_plan_node(dependencies.retrieval),
    )
    add_node(
        "retrieval_search",
        create_retrieval_search_node(dependencies.retrieval),
    )
    add_node(
        "operand_binding",
        create_operand_binding_node(dependencies.operand_binding),
    )
    add_node(
        "computation_planning",
        create_computation_planning_node(dependencies.computation_planning),
    )
    add_node(
        "computation_execution",
        create_computation_execution_node(dependencies.computation),
    )
    add_node(
        "core_verification",
        create_core_verification_node(dependencies.core_verification),
    )
    add_node(
        "final_answer",
        create_final_answer_node(dependencies.answer_generation),
    )
    add_node(
        "cannot_answer",
        create_cannot_answer_node(),
    )
    add_node(
        "answer_verification",
        create_answer_verification_node(),
    )

    graph.add_edge(START, "query_understanding")
    graph.add_conditional_edges(
        "query_understanding",
        _route_after_understanding,
        {
            "clarification": "clarification",
            "retrieval": "retrieval_plan",
        },
    )
    graph.add_edge("retrieval_plan", "retrieval_search")
    graph.add_conditional_edges(
        "retrieval_search",
        _route_after_retrieval,
        {
            "bind_operands": "operand_binding",
            "verify": "core_verification",
        },
    )
    graph.add_conditional_edges(
        "operand_binding",
        _route_after_binding,
        {
            "plan_computation": "computation_planning",
            "verify": "core_verification",
        },
    )
    graph.add_conditional_edges(
        "computation_planning",
        _route_after_computation_planning,
        {
            "execute": "computation_execution",
            "verify": "core_verification",
        },
    )
    graph.add_edge("computation_execution", "core_verification")
    graph.add_conditional_edges(
        "core_verification",
        _route_after_core_verification,
        {
            VerificationAction.PASS: "final_answer",
            VerificationAction.RETRY_RETRIEVAL: "retrieval_plan",
            VerificationAction.RETRY_COMPUTATION: "computation_planning",
            VerificationAction.RETRY_UNDERSTANDING: "query_understanding",
            VerificationAction.CANNOT_ANSWER: "cannot_answer",
        },
    )
    graph.add_edge("clarification", "answer_verification")
    graph.add_edge("final_answer", "answer_verification")
    graph.add_edge("cannot_answer", "answer_verification")
    graph.add_edge("answer_verification", END)
    return graph.compile(name="disclosure-ai-main")


def _route_after_understanding(
    state: DisclosureAIState,
) -> Literal["clarification", "retrieval"]:
    understanding = state["query_understanding"]
    return "clarification" if understanding.needs_clarification else "retrieval"


def _route_after_retrieval(
    state: DisclosureAIState,
) -> Literal["bind_operands", "verify"]:
    return "bind_operands" if state.get("computation_intent") is not None else "verify"


def _route_after_binding(
    state: DisclosureAIState,
) -> Literal["plan_computation", "verify"]:
    binding = state["operand_binding"]
    return "verify" if binding.missing_operand_ids else "plan_computation"


def _route_after_computation_planning(
    state: DisclosureAIState,
) -> Literal["execute", "verify"]:
    planning = state["computation_planning"]
    return "execute" if planning.plan is not None else "verify"


def _route_after_core_verification(state: DisclosureAIState) -> VerificationAction:
    return state["core_verification"].action
