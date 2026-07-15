from pathlib import Path

from moss_reflex.server import build_server


def test_server_exposes_only_the_public_memory_tools(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOSS_REFLEX_HOME", str(tmp_path / "memory"))
    names = {tool.name for tool in build_server(tmp_path)._tool_manager.list_tools()}
    assert names == {"recall_similar_situations", "reflex_stats"}
