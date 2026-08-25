from pathlib import Path

from reasoning.graph_visualization import export_main_graph


def test_export_main_graph_uses_real_topology(tmp_path: Path) -> None:
    output = export_main_graph(tmp_path / "nested" / "main-graph.mmd")
    mermaid = output.read_text(encoding="utf-8")

    assert output.exists()
    assert "query_understanding" in mermaid
    assert "computation_execution" in mermaid
    assert "core_verification" in mermaid
    assert "answer_verification" in mermaid
