from argparse import ArgumentParser
from pathlib import Path
from typing import cast

from reasoning.computing.services import (
    ComputationPlanningService,
    ComputationService,
    OperandBindingService,
)
from reasoning.core_verification import CoreVerificationService
from reasoning.generate_answer.services import ResponseGenerationService
from reasoning.query_understanding.services import QueryUnderstandingService
from reasoning.retrieval.services import RetrievalService

from .graph import GraphDependencies, build_graph

DEFAULT_OUTPUT = Path("docs/main-graph.mmd")


def export_main_graph(output: Path = DEFAULT_OUTPUT) -> Path:
    """Build the real graph topology and export it as versionable Mermaid source."""

    graph = build_graph(_visualization_dependencies())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        graph.get_graph(xray=True).draw_mermaid(),
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = ArgumentParser(description="Export the disclosure AI main graph as Mermaid.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output path (default: {DEFAULT_OUTPUT})",
    )
    arguments = parser.parse_args()
    output = export_main_graph(arguments.output)
    print(output)


def _visualization_dependencies() -> GraphDependencies:
    """Create non-executable dependencies; graph rendering never invokes a node."""

    unused = object()
    return GraphDependencies(
        query_understanding=cast(QueryUnderstandingService, unused),
        retrieval=cast(RetrievalService, unused),
        operand_binding=cast(OperandBindingService, unused),
        computation_planning=cast(ComputationPlanningService, unused),
        computation=cast(ComputationService, unused),
        core_verification=cast(CoreVerificationService, unused),
        answer_generation=cast(ResponseGenerationService, unused),
    )


if __name__ == "__main__":
    main()
