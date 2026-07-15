"""Fail when repository source references disallowed remote-index operations or keys."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "__pycache__", "dist", "build"}
DISALLOWED = tuple(
    "".join(parts)
    for parts in (("create", "_index"), ("push", "_index"), ("load", "_index"))
)
KEY_PATTERN = re.compile(r"moss_[A-Za-z0-9_-]{20,}")


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(ROOT)
        for token in DISALLOWED:
            if token in text:
                findings.append(f"{relative}: contains disallowed operation {token!r}")
        if KEY_PATTERN.search(text):
            findings.append(f"{relative}: contains a Moss-shaped credential")
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("local-only and credential scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
