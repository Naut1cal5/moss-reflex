"""Non-destructive Claude Code hook and MCP configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_POST_COMMAND = "moss-reflex hook post-tool-use"
_FAILURE_COMMAND = "moss-reflex hook post-tool-use-failure"
_STOP_COMMAND = "moss-reflex hook stop"


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _has_command(entries: Any, command: str) -> bool:
    if not isinstance(entries, list):
        return False
    return any(
        isinstance(group, dict)
        and any(
            isinstance(hook, dict) and hook.get("command") == command
            for hook in group.get("hooks", [])
        )
        for group in entries
    )


def configure_project(root: Path) -> tuple[Path, Path]:
    settings_path = root / ".claude" / "settings.json"
    settings = _read_object(settings_path)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(".claude/settings.json hooks must be an object")
    post = hooks.setdefault("PostToolUse", [])
    failure = hooks.setdefault("PostToolUseFailure", [])
    stop = hooks.setdefault("Stop", [])
    if not isinstance(post, list) or not isinstance(failure, list) or not isinstance(stop, list):
        raise ValueError("existing Claude hook groups must be lists")
    if not _has_command(post, _POST_COMMAND):
        post.append({"matcher": "*", "hooks": [{"type": "command", "command": _POST_COMMAND}]})
    if not _has_command(failure, _FAILURE_COMMAND):
        failure.append(
            {"matcher": "*", "hooks": [{"type": "command", "command": _FAILURE_COMMAND}]}
        )
    if not _has_command(stop, _STOP_COMMAND):
        stop.append({"hooks": [{"type": "command", "command": _STOP_COMMAND}]})
    _write_object(settings_path, settings)

    mcp_path = root / ".mcp.json"
    mcp_config = _read_object(mcp_path)
    servers = mcp_config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(".mcp.json mcpServers must be an object")
    servers["moss-reflex"] = {"command": "moss-reflex", "args": ["serve"]}
    _write_object(mcp_path, mcp_config)
    return settings_path, mcp_path
