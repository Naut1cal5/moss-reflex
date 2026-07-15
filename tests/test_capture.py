from __future__ import annotations

from pathlib import Path

from moss_reflex.capture import HookCapture


def test_capture_labels_test_delta_without_an_llm(
    git_repo: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MOSS_REFLEX_HOME", str(tmp_path / "memory"))
    capture = HookCapture(git_repo)
    raw = f'File "{git_repo}/example.py", line 99, in test_value\nAssertionError: nope\n2 failed'

    failed = capture.capture(
        "PostToolUse",
        {
            "session_id": "abc",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "tool_response": {"stderr": raw, "exit_code": 1},
        },
    )
    resolved = capture.capture(
        "PostToolUse",
        {
            "session_id": "abc",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "tool_response": {"stdout": "8 passed, 0 failed", "exit_code": 0},
        },
    )

    assert failed.outcome == "failure"
    assert failed.error_class == "AssertionError"
    assert failed.raw_trace == raw
    assert str(git_repo) not in failed.normalized_context
    assert resolved.outcome == "resolved"
    assert resolved.test_before == 2
    assert resolved.test_after == 0


def test_capture_detects_applied_then_reverted_diff(
    git_repo: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MOSS_REFLEX_HOME", str(tmp_path / "memory"))
    capture = HookCapture(git_repo)
    base = {"session_id": "diff", "tool_name": "Edit", "tool_response": {"exit_code": 0}}
    capture.capture("PostToolUse", {**base, "tool_input": {"file_path": "example.py"}})
    (git_repo / "example.py").write_text("value = 2\n", encoding="utf-8")
    capture.capture("PostToolUse", {**base, "tool_input": {"file_path": "example.py"}})
    (git_repo / "example.py").write_text("value = 1\n", encoding="utf-8")

    reverted = capture.capture(
        "PostToolUse", {**base, "tool_input": {"file_path": "example.py"}}
    )

    assert reverted.outcome == "reverted"


def test_capture_reads_current_failure_event_shape(
    git_repo: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MOSS_REFLEX_HOME", str(tmp_path / "memory"))

    episode = HookCapture(git_repo).capture(
        "PostToolUseFailure",
        {
            "session_id": "failure-event",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "error": "Command exited with non-zero status code 1",
            "is_interrupt": False,
        },
    )

    assert episode.outcome == "failure"
    assert episode.exit_code == 1
    assert episode.raw_trace == "Command exited with non-zero status code 1"
