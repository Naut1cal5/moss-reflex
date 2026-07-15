"""Normalize volatile trace tokens without destroying diagnostic structure."""

from __future__ import annotations

import re
from pathlib import Path

_TIMESTAMP = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?Z?|\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\b"
)
_HEX_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{6,}\b")
_OFFSET = re.compile(r"(?<=\w)\+0x[0-9a-fA-F]+\b")
_PY_LINE = re.compile(r'(File\s+"[^"]+",\s+line\s+)\d+')
_GENERIC_LINE = re.compile(r"(?<![\w.-])(?:line|ln)\s+\d+", re.IGNORECASE)
_COLON_LINE = re.compile(r"(?P<path>(?:[\w.-]+/)*[\w.-]+\.[A-Za-z0-9]+):\d+(?::\d+)?")
_ABS_PATH = re.compile(r"(?<![\w.-])(?:/[\w.@+~-]+){2,}")
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\(?:[^\s:\"]+\\)*[^\s:\"]+")


def _relative_path(value: str, root: Path | None) -> str:
    cleaned = value.replace("\\", "/")
    if root is not None:
        prefix = str(root.resolve()).replace("\\", "/").rstrip("/") + "/"
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :]
    parts = [part for part in cleaned.split("/") if part]
    return "/".join(parts[-3:]) if len(parts) > 3 else "/".join(parts)


def normalize_trace(trace: str, root: Path | None = None) -> str:
    """Remove run-specific values while retaining exception and frame semantics."""

    value = trace.replace("\r\n", "\n")
    value = _TIMESTAMP.sub("<timestamp>", value)
    value = _OFFSET.sub("+<offset>", value)
    value = _HEX_ADDRESS.sub("<address>", value)
    value = _PY_LINE.sub(r"\g<1><line>", value)
    value = _GENERIC_LINE.sub("line <line>", value)
    value = _COLON_LINE.sub(lambda match: f"{match.group('path')}:<line>", value)
    value = _WINDOWS_PATH.sub(lambda match: _relative_path(match.group(0), root), value)
    value = _ABS_PATH.sub(lambda match: _relative_path(match.group(0), root), value)
    return value.strip()
