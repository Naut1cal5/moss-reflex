from __future__ import annotations

import stat
from pathlib import Path

from moss_reflex.episode import Episode
from moss_reflex.store import EpisodeStore


def episode(identifier: str = "one") -> Episode:
    return Episode(
        id=identifier,
        timestamp="2026-01-01T00:00:00+00:00",
        repo="repo",
        session_id="session",
        context="raw",
        action="run tests",
        outcome="failure",
        raw_trace="raw",
        normalized_context="normalized",
    )


def test_store_is_append_only_and_private(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path)
    store.append(episode("one"))
    store.append(episode("two"))

    assert [item.id for item in store.iter_episodes()] == ["one", "two"]
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert store.stats()["episodes"] == 2


def test_store_skips_a_corrupt_line(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path)
    store.append(episode())
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")
    assert store.count() == 1
