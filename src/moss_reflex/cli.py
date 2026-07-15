"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from moss_reflex.capture import capture_stdin
from moss_reflex.config import configure_project
from moss_reflex.index import ReflexIndex
from moss_reflex.paths import git_root, repo_dir
from moss_reflex.server import run_server
from moss_reflex.store import EpisodeStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="moss-reflex", description="Procedural memory for coding agents"
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init", help="install Claude Code hooks and MCP config")
    subcommands.add_parser("serve", help="run the stdio MCP server")
    subcommands.add_parser("stats", help="show local episode statistics")
    subcommands.add_parser("replay", help="rebuild the local Moss snapshot from JSONL")
    hook = subcommands.add_parser("hook", help=argparse.SUPPRESS)
    hook.add_argument("event", choices=("post-tool-use", "post-tool-use-failure", "stop"))
    return result


async def _replay(root: Path) -> int:
    return await ReflexIndex(root).rebuild()


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = git_root()
    if args.command == "init":
        settings, mcp_config = configure_project(root)
        print(f"Configured {settings}")
        print(f"Configured {mcp_config}")
        print("Export MOSS_PROJECT_ID and MOSS_PROJECT_KEY before starting Claude Code.")
        return 0
    if args.command == "serve":
        run_server(root)
        return 0
    if args.command == "stats":
        print(json.dumps(EpisodeStore(repo_dir(root)).stats(), indent=2))
        return 0
    if args.command == "replay":
        count = asyncio.run(_replay(root))
        print(f"Re-embedded {count} local episodes")
        return 0
    if args.command == "hook":
        events = {
            "post-tool-use": "PostToolUse",
            "post-tool-use-failure": "PostToolUseFailure",
            "stop": "Stop",
        }
        try:
            capture_stdin(events[args.event], sys.stdin.read())
        except Exception as error:
            print(f"moss-reflex capture warning: {error}", file=sys.stderr)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
