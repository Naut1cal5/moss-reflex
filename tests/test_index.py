from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from moss_reflex.episode import Episode
from moss_reflex.index import ReflexIndex
from moss_reflex.paths import repo_dir
from moss_reflex.store import EpisodeStore


class FakeInner:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def save_to_disk(self, base: str) -> None:
        directory = Path(base) / self.session.name
        directory.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "id": doc.id,
                "text": doc.text,
                "metadata": doc.metadata,
                "payload": doc.payload,
            }
            for doc in self.session.docs.values()
        ]
        (directory / "session.json").write_text(json.dumps(records), encoding="utf-8")

    def load_from_disk(self, base: str) -> int:
        records = json.loads((Path(base) / self.session.name / "session.json").read_text())
        self.session.docs = {
            item["id"]: SimpleNamespace(**item)
            for item in records
        }
        return len(records)


class FakeSession:
    def __init__(self, name: str) -> None:
        self.name = name
        self.docs: dict[str, Any] = {}
        self._inner = FakeInner(self)

    @property
    def doc_count(self) -> int:
        return len(self.docs)

    async def add_docs(self, docs: list[Any]) -> tuple[int, int]:
        added = sum(doc.id not in self.docs for doc in docs)
        for doc in docs:
            self.docs[doc.id] = doc
        return added, len(docs) - added

    async def get_docs(self) -> list[Any]:
        return list(self.docs.values())

    async def delete_docs(self, ids: list[str]) -> int:
        deleted = 0
        for identifier in ids:
            deleted += self.docs.pop(identifier, None) is not None
        return deleted

    async def query(self, query: str, options: Any) -> Any:
        del query, options
        hits = [
            SimpleNamespace(
                id=doc.id,
                text=doc.text,
                payload=doc.payload,
                score=0.9 - position * 0.1,
            )
            for position, doc in enumerate(self.docs.values())
        ]
        return SimpleNamespace(docs=hits)


class FakeClient:
    calls = 0

    def __init__(self, project_id: str, project_key: str) -> None:
        assert project_id == "project"
        assert project_key == "key"

    async def session(self, index_name: str, model_id: str) -> FakeSession:
        assert model_id == "moss-minilm"
        FakeClient.calls += 1
        return FakeSession(index_name)


def make_episode(identifier: str, timestamp: str, raw: str) -> Episode:
    return Episode(
        id=identifier,
        timestamp=timestamp,
        repo="repo",
        session_id="session",
        context=raw,
        action="replace bad import",
        outcome="resolved",
        raw_trace=raw,
        normalized_context="ModuleNotFoundError package import",
        language="python",
        error_class="ModuleNotFoundError",
        tool_name="Bash",
    )


@pytest.fixture
def fake_moss(monkeypatch, tmp_path: Path) -> None:
    FakeClient.calls = 0
    monkeypatch.setattr("moss_reflex.index.MossClient", FakeClient)
    monkeypatch.setenv("MOSS_PROJECT_ID", "project")
    monkeypatch.setenv("MOSS_PROJECT_KEY", "key")
    monkeypatch.setenv("MOSS_REFLEX_HOME", str(tmp_path / "memory"))


async def test_recall_returns_verbatim_payload_and_persists_snapshot(
    git_repo: Path, fake_moss: None
) -> None:
    store = EpisodeStore(repo_dir(git_repo))
    raw = "Traceback\nModuleNotFoundError: package"
    store.append(make_episode("one", "2026-07-14T00:00:00+00:00", raw))
    index = ReflexIndex(git_repo)

    results = await index.recall("missing package", k=1, filters={"language": {"$eq": "python"}})

    assert results[0]["episode"]["raw_trace"] == raw
    assert results[0]["episode"]["outcome"] == "resolved"
    assert index.manifest_path.exists()
    assert (index.snapshot_base / index._session.name / "session.json").exists()
    assert FakeClient.calls == 1


async def test_corrupt_snapshot_rebuilds_from_jsonl(git_repo: Path, fake_moss: None) -> None:
    store = EpisodeStore(repo_dir(git_repo))
    store.append(make_episode("one", "2026-07-14T00:00:00+00:00", "raw"))
    first = ReflexIndex(git_repo)
    await first.open()
    snapshot = first.snapshot_base / first._session.name / "session.json"
    snapshot.write_text("corrupt", encoding="utf-8")

    second = ReflexIndex(git_repo)
    count = await second.sync()

    assert count == 1
    assert second._session.doc_count == 1
    assert json.loads(snapshot.read_text(encoding="utf-8"))[0]["id"] == "one"
