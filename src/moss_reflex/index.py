"""Local Moss session lifecycle, snapshot recovery, and recency-ranked recall."""

from __future__ import annotations

import asyncio
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moss import DocumentInfo, MossClient, QueryOptions

from moss_reflex.episode import Episode
from moss_reflex.paths import git_root, repo_dir, session_name
from moss_reflex.store import EpisodeStore

_FILTER_FIELDS = {"repo", "language", "error_class", "tool_name", "outcome", "timestamp"}
_FILTER_OPERATORS = {"$eq", "$in"}


def compile_filters(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compile friendly field filters to Moss's condition representation."""

    if value is None or value == {}:
        return None
    if not isinstance(value, dict):
        raise ValueError("filters must be an object")
    if "$and" in value:
        items = value["$and"]
        if not isinstance(items, list) or not items:
            raise ValueError("$and must contain a non-empty list")
        return {"$and": [compile_filters(item) for item in items]}
    if set(value) == {"field", "condition"}:
        field = value["field"]
        condition = value["condition"]
        if field not in _FILTER_FIELDS or not isinstance(condition, dict):
            raise ValueError("invalid field condition")
        if len(condition) != 1 or next(iter(condition)) not in _FILTER_OPERATORS:
            raise ValueError("only $eq and $in conditions are supported")
        return value
    compiled: list[dict[str, Any]] = []
    for field, condition in value.items():
        if field not in _FILTER_FIELDS:
            raise ValueError(f"unsupported filter field: {field}")
        resolved = condition if isinstance(condition, dict) else {"$eq": condition}
        if len(resolved) != 1 or next(iter(resolved)) not in _FILTER_OPERATORS:
            raise ValueError("only $eq and $in conditions are supported")
        operator, operand = next(iter(resolved.items()))
        if operator == "$in" and not isinstance(operand, list):
            raise ValueError("$in requires a list")
        compiled.append({"field": field, "condition": resolved})
    return compiled[0] if len(compiled) == 1 else {"$and": compiled}


def _metadata(episode: Episode) -> dict[str, str]:
    return {
        "repo": episode.repo,
        "language": episode.language,
        "error_class": episode.error_class,
        "tool_name": episode.tool_name,
        "outcome": episode.outcome,
        "timestamp": episode.timestamp,
    }


def _document(episode: Episode) -> DocumentInfo:
    searchable = "\n".join(
        (
            f"error class: {episode.error_class}",
            f"tool: {episode.tool_name}",
            f"context: {episode.normalized_context}",
            f"action: {episode.action}",
            f"outcome: {episode.outcome}",
        )
    )
    return DocumentInfo(
        id=episode.id,
        text=searchable,
        metadata=_metadata(episode),
        payload=json.dumps(episode.to_dict(), separators=(",", ":"), ensure_ascii=False),
    )


class ReflexIndex:
    """A lazy, process-local SessionIndex backed by append-only episodes."""

    def __init__(self, root: Path | None = None, *, half_life_days: float = 30.0) -> None:
        self.root = git_root(root)
        self.directory = repo_dir(self.root)
        self.store = EpisodeStore(self.directory)
        self.snapshot_base = self.directory / "snapshot"
        self.manifest_path = self.directory / "snapshot-manifest.json"
        self.half_life_days = half_life_days
        self._session: Any = None
        self._lock = asyncio.Lock()

    def _credentials(self) -> tuple[str, str]:
        project_id = os.environ.get("MOSS_PROJECT_ID", "").strip()
        project_key = os.environ.get("MOSS_PROJECT_KEY", "").strip()
        if not project_id or not project_key:
            raise RuntimeError("set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in the environment")
        return project_id, project_key

    async def open(self) -> Any:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            project_id, project_key = self._credentials()
            client = MossClient(project_id, project_key)
            session = await client.session(
                index_name=session_name(self.root), model_id="moss-minilm"
            )
            self._session = session
            try:
                await self._restore_or_rebuild()
            except Exception:
                self._session = None
                raise
            return session

    def _manifest(self) -> dict[str, Any]:
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    async def _clear(self) -> None:
        docs = await self._session.get_docs()
        for start in range(0, len(docs), 256):
            await self._session.delete_docs([doc.id for doc in docs[start : start + 256]])

    async def _restore_or_rebuild(self) -> None:
        expected = self.store.count()
        manifest = self._manifest()
        restored = False
        session_path = self.snapshot_base / self._session.name
        if session_path.exists() and manifest.get("session_name") == self._session.name:
            try:
                loaded = await asyncio.to_thread(
                    self._session._inner.load_from_disk, str(self.snapshot_base)
                )
                restored = loaded == manifest.get("indexed") and loaded <= expected
            except Exception:
                restored = False
        if not restored:
            await self._clear()
            await self._add(list(self.store.iter_episodes()))
            await self._save(expected)
            return
        indexed = int(manifest.get("indexed", 0))
        pending = list(self.store.iter_episodes(start=indexed))
        if pending:
            await self._add(pending)
            await self._save(expected)

    async def _add(self, episodes: list[Episode]) -> None:
        for start in range(0, len(episodes), 64):
            await self._session.add_docs([_document(item) for item in episodes[start : start + 64]])

    async def _save(self, indexed: int) -> None:
        self.snapshot_base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if indexed:
            await asyncio.to_thread(self._session._inner.save_to_disk, str(self.snapshot_base))
        manifest = {"session_name": self._session.name, "indexed": indexed, "version": 1}
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.manifest_path)

    async def sync(self) -> int:
        await self.open()
        async with self._lock:
            expected = self.store.count()
            indexed = int(self._manifest().get("indexed", 0))
            if indexed > expected or self._session.doc_count != indexed:
                await self._clear()
                await self._add(list(self.store.iter_episodes()))
                await self._save(expected)
                return expected
            pending = list(self.store.iter_episodes(start=indexed))
            if pending:
                await self._add(pending)
                await self._save(expected)
            return expected

    async def rebuild(self) -> int:
        await self.open()
        async with self._lock:
            await self._clear()
            episodes = list(self.store.iter_episodes())
            await self._add(episodes)
            await self._save(len(episodes))
            return len(episodes)

    async def recall(
        self,
        query: str,
        *,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        if k < 1 or k > 50:
            raise ValueError("k must be between 1 and 50")
        await self.sync()
        if self._session.doc_count == 0:
            return []
        options = QueryOptions(top_k=min(max(k * 4, 12), 100), filter=compile_filters(filters))
        result = await self._session.query(query, options)
        now = datetime.now(timezone.utc)
        ranked: list[dict[str, Any]] = []
        for hit in result.docs:
            try:
                payload = json.loads(hit.payload) if hit.payload else {}
                timestamp = datetime.fromisoformat(payload["timestamp"])
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                payload = {"id": hit.id, "context": hit.text}
                timestamp = now
            age_days = max(0.0, (now - timestamp).total_seconds() / 86_400)
            recency = math.exp(-math.log(2) * age_days / self.half_life_days)
            semantic = float(hit.score)
            combined = 0.85 * semantic + 0.15 * recency
            ranked.append(
                {
                    "score": round(combined, 6),
                    "semantic_score": round(semantic, 6),
                    "recency_weight": round(recency, 6),
                    "episode": payload,
                }
            )
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        return ranked[:k]
