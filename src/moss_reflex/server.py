"""stdio MCP surface for procedural recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from moss_reflex.index import ReflexIndex


def build_server(root: Path | None = None) -> FastMCP:
    server = FastMCP("moss-reflex")
    index = ReflexIndex(root)

    @server.tool()
    async def recall_similar_situations(
        query: str,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Recall similar past coding situations, actions, raw traces, and outcomes."""

        return await index.recall(query, k=k, filters=filters)

    @server.tool()
    def reflex_stats() -> dict[str, object]:
        """Summarize locally captured episodes without contacting an LLM."""

        return index.store.stats()

    return server


def run_server(root: Path | None = None) -> None:
    build_server(root).run(transport="stdio")
