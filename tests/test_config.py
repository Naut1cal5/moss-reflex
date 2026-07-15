from __future__ import annotations

import json
from pathlib import Path

from moss_reflex.config import configure_project


def test_configure_project_merges_and_is_idempotent(tmp_path: Path) -> None:
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text(
        json.dumps({"permissions": {"allow": ["Read"]}, "hooks": {"PostToolUse": []}}),
        encoding="utf-8",
    )

    configure_project(tmp_path)
    configure_project(tmp_path)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert settings["permissions"] == {"allow": ["Read"]}
    assert len(settings["hooks"]["PostToolUse"]) == 1
    assert len(settings["hooks"]["PostToolUseFailure"]) == 1
    assert len(settings["hooks"]["Stop"]) == 1
    assert mcp["mcpServers"]["moss-reflex"] == {
        "command": "moss-reflex",
        "args": ["serve"],
    }
