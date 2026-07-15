from pathlib import Path

from moss_reflex.normalize import normalize_trace


def test_normalize_trace_preserves_semantics_and_removes_volatility(tmp_path: Path) -> None:
    trace = (
        f'2026-07-14T21:22:01.123Z File "{tmp_path}/pkg/service.py", line 418, in run\n'
        "ValueError: bad value at 0x7ffee12abc99 helper+0x4f\n"
        "pkg/other.py:91:7: type mismatch"
    )

    result = normalize_trace(trace, tmp_path)

    assert "2026-07-14" not in result
    assert "418" not in result
    assert "0x7ffee12abc99" not in result
    assert str(tmp_path) not in result
    assert "pkg/service.py" in result
    assert "ValueError" in result
    assert "in run" in result
    assert "pkg/other.py:<line>" in result
