"""Claude Code hook ingestion with deterministic outcome labels."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moss_reflex.episode import Episode
from moss_reflex.normalize import normalize_trace
from moss_reflex.paths import git_root, repo_dir, repo_hash
from moss_reflex.store import EpisodeStore

_ERROR_CLASS = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception|Failure))\b")
_EXIT_TEXT = re.compile(r"(?:exit(?:ed)?(?:\s+with)?(?:\s+code)?|status)\s*[:=]?\s*(-?\d+)", re.I)
_FAILED_PATTERNS = (
    re.compile(r"(?<!\d)(\d+)\s+failed\b", re.I),
    re.compile(r"(?:failures?|errors?)\s*[:=]\s*(\d+)", re.I),
    re.compile(r"Tests:\s*(\d+)\s+failed", re.I),
)
_PASSED_PATTERNS = (
    re.compile(r"(?<!\d)(\d+)\s+passed\b", re.I),
    re.compile(r"Tests:.*?(\d+)\s+passed", re.I),
)
_EXTENSIONS = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".go": "go",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return _stringify(response)
    ordered = ("stderr", "stdout", "error", "content", "output", "message")
    pieces = [_stringify(response[key]) for key in ordered if response.get(key) not in (None, "")]
    return "\n".join(pieces) if pieces else _stringify(response)


def _find_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in keys:
                return item
        for item in value.values():
            found = _find_value(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_value(item, keys)
            if found is not None:
                return found
    return None


def exit_code(response: Any, text: str) -> int | None:
    value = _find_value(response, {"exit_code", "exitcode", "return_code", "returncode"})
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    match = _EXIT_TEXT.search(text)
    if match:
        return int(match.group(1))
    is_error = _find_value(response, {"is_error", "iserror"})
    return 1 if is_error is True else None


def test_counts(text: str) -> tuple[int | None, int | None]:
    failed = next(
        (int(match.group(1)) for pattern in _FAILED_PATTERNS if (match := pattern.search(text))),
        None,
    )
    passed = next(
        (int(match.group(1)) for pattern in _PASSED_PATTERNS if (match := pattern.search(text))),
        None,
    )
    return failed, passed


def error_class(text: str) -> str:
    match = _ERROR_CLASS.search(text)
    if match:
        return match.group(1)
    lowered = text.lower()
    for needle, label in (
        ("borrow checker", "BorrowCheckError"),
        ("command not found", "CommandNotFound"),
        ("module not found", "ModuleNotFound"),
        ("no such file or directory", "FileNotFound"),
        ("type mismatch", "TypeMismatch"),
        ("compilation failed", "CompilationFailure"),
    ):
        if needle in lowered:
            return label
    return "none"


def _file_path(tool_input: Any) -> str:
    value = _find_value(tool_input, {"file_path", "filepath", "path"})
    return str(value) if isinstance(value, (str, Path)) else ""


def _language(file_path: str, action: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix in _EXTENSIONS:
        return _EXTENSIONS[suffix]
    lowered = action.lower()
    for executable, language in (
        ("pytest", "python"),
        ("python", "python"),
        ("cargo", "rust"),
        ("go test", "go"),
        ("npm", "javascript"),
        ("pnpm", "javascript"),
        ("tsc", "typescript"),
    ):
        if executable in lowered:
            return language
    return "unknown"


def _diff_digest(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--no-ext-diff", "--binary", "--", "."],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


class HookCapture:
    def __init__(self, root: Path) -> None:
        self.root = git_root(root)
        self.directory = repo_dir(self.root)
        self.store = EpisodeStore(self.directory)
        self.state_dir = self.directory / "hook-state"
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _state_path(self, session_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)[:120]
        return self.state_dir / f"{safe or 'unknown'}.json"

    def _lock_state(self, session_id: str) -> int:
        lock_path = self._state_path(session_id).with_suffix(".lock")
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        if os.name == "nt":
            msvcrt: Any = importlib.import_module("msvcrt")

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            fcntl: Any = importlib.import_module("fcntl")

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    @staticmethod
    def _unlock_state(descriptor: int) -> None:
        if os.name == "nt":
            msvcrt: Any = importlib.import_module("msvcrt")

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            fcntl: Any = importlib.import_module("fcntl")

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    def _load_state(self, session_id: str) -> dict[str, Any]:
        path = self._state_path(session_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, session_id: str, state: dict[str, Any]) -> None:
        path = self._state_path(session_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    def capture(self, hook_event: str, data: dict[str, Any]) -> Episode:
        session_id = str(data.get("session_id") or data.get("sessionId") or "unknown")
        lock = self._lock_state(session_id)
        try:
            return self._capture_locked(hook_event, data, session_id)
        finally:
            self._unlock_state(lock)

    def _capture_locked(
        self, hook_event: str, data: dict[str, Any], session_id: str
    ) -> Episode:
        state = self._load_state(session_id)
        tool_name = str(data.get("tool_name") or data.get("toolName") or hook_event)
        tool_input = data.get("tool_input", data.get("toolInput", {}))
        response = data.get("tool_response", data.get("toolResponse"))
        if response is None and data.get("error") is not None:
            response = {
                "error": data.get("error"),
                "is_error": True,
                "is_interrupt": data.get("is_interrupt", False),
            }
        response_text = _response_text(response)

        if hook_event.lower() == "stop":
            response_text = response_text or str(state.get("last_context", "session stopped"))
            tool_input = {"reason": data.get("stop_hook_active", "agent stop")}

        action = f"{tool_name}: {_stringify(tool_input)}"
        code = exit_code(response, response_text)
        failed, passed = test_counts(response_text)
        previous_failed = state.get("failed_tests")
        current_diff = _diff_digest(self.root)
        history = [item for item in state.get("diff_history", []) if isinstance(item, str)]
        reverted = bool(
            current_diff
            and history
            and current_diff != history[-1]
            and current_diff in history[:-1]
        )

        if hook_event.lower() == "stop":
            outcome = (
                "unresolved"
                if isinstance(previous_failed, int) and previous_failed > 0
                else "completed"
            )
        elif reverted:
            outcome = "reverted"
        elif isinstance(previous_failed, int) and failed is not None and failed < previous_failed:
            outcome = "resolved" if failed == 0 else "improved"
        elif isinstance(previous_failed, int) and failed is not None and failed > previous_failed:
            outcome = "regressed"
        elif (code is not None and code != 0) or (failed is not None and failed > 0):
            outcome = "failure"
        elif code == 0 or failed == 0:
            outcome = "success"
        else:
            outcome = "observed"

        timestamp = datetime.now(timezone.utc).isoformat()
        path = _file_path(tool_input)
        digest_source = f"{timestamp}\0{session_id}\0{tool_name}\0{action}\0{response_text}"
        episode = Episode(
            id=hashlib.sha256(digest_source.encode()).hexdigest()[:24],
            timestamp=timestamp,
            repo=repo_hash(self.root),
            session_id=session_id,
            context=response_text,
            action=action,
            outcome=outcome,
            raw_trace=response_text,
            normalized_context=normalize_trace(response_text, self.root),
            language=_language(path, action),
            error_class=error_class(response_text),
            tool_name=tool_name,
            file_path=path,
            exit_code=code,
            test_before=previous_failed if isinstance(previous_failed, int) else None,
            test_after=failed,
            details={"passed_tests": passed, "hook_event": hook_event},
        )
        self.store.append(episode)

        if failed is not None:
            state["failed_tests"] = failed
        state["last_context"] = response_text
        state["last_outcome"] = outcome
        if current_diff:
            history.append(current_diff)
            state["diff_history"] = history[-32:]
        self._save_state(session_id, state)
        return episode


def capture_stdin(hook_event: str, stdin_text: str) -> Episode:
    if os.environ.get("MOSS_REFLEX_DISABLED") == "1":
        raise RuntimeError("capture disabled by MOSS_REFLEX_DISABLED")
    value = json.loads(stdin_text or "{}")
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    cwd = value.get("cwd") or Path.cwd()
    return HookCapture(Path(str(cwd))).capture(hook_event, value)
