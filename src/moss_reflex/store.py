"""Append-only, permission-restricted JSONL episode storage."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path

from moss_reflex.episode import Episode


class EpisodeStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "episodes.jsonl"

    def append(self, episode: Episode) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        line = json.dumps(episode.to_dict(), separators=(",", ":"), ensure_ascii=False) + "\n"
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
        finally:
            os.close(descriptor)
        with suppress(OSError):
            self.path.chmod(0o600)

    def iter_episodes(self, start: int = 0) -> Iterator[Episode]:
        if not self.path.exists():
            return
        valid_index = 0
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        episode = Episode.from_dict(value)
                        if valid_index >= start:
                            yield episode
                        valid_index += 1
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

    def count(self) -> int:
        return sum(1 for _ in self.iter_episodes())

    def stats(self) -> dict[str, object]:
        outcomes: dict[str, int] = {}
        errors: dict[str, int] = {}
        tools: dict[str, int] = {}
        total = 0
        for episode in self.iter_episodes():
            total += 1
            outcomes[episode.outcome] = outcomes.get(episode.outcome, 0) + 1
            errors[episode.error_class] = errors.get(episode.error_class, 0) + 1
            tools[episode.tool_name] = tools.get(episode.tool_name, 0) + 1
        return {
            "episodes": total,
            "outcomes": dict(sorted(outcomes.items())),
            "error_classes": dict(sorted(errors.items())),
            "tools": dict(sorted(tools.items())),
            "path": str(self.path),
        }
