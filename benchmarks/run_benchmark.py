#!/usr/bin/env python3
"""Run one failing task with procedural memory disabled, then enabled."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runner", required=True, help="agent command; receives benchmark env vars"
    )
    parser.add_argument("--task", required=True, type=Path, help="task description or fixture path")
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    return parser.parse_args()


def run_once(command: str, task: Path, mode: str, run_number: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="moss-reflex-bench-") as temporary:
        result_path = Path(temporary) / "result.json"
        environment = os.environ.copy()
        environment.update(
            {
                "MOSS_REFLEX_BENCH_MODE": mode,
                "MOSS_REFLEX_BENCH_RUN": str(run_number),
                "MOSS_REFLEX_BENCH_TASK": str(task.resolve()),
                "MOSS_REFLEX_BENCH_RESULT": str(result_path),
            }
        )
        started = time.perf_counter()
        completed = subprocess.run(shlex.split(command), env=environment, check=False)
        elapsed = time.perf_counter() - started
        if not result_path.exists():
            raise RuntimeError(
                "runner did not write MOSS_REFLEX_BENCH_RESULT with resolved/tool_calls/tokens"
            )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        required = {"resolved", "tool_calls", "tokens"}
        if not isinstance(result, dict) or not required.issubset(result):
            raise RuntimeError(f"runner result must contain {sorted(required)}")
        result.update({"mode": mode, "run": run_number, "seconds": round(elapsed, 3)})
        result["process_exit_code"] = completed.returncode
        return result


def main() -> int:
    args = parse_args()
    baseline = run_once(args.runner, args.task, "off", 1)
    memory = run_once(args.runner, args.task, "on", 2)
    report = {
        "task": str(args.task),
        "baseline": baseline,
        "memory": memory,
        "delta": {
            "tool_calls": memory["tool_calls"] - baseline["tool_calls"],
            "tokens": memory["tokens"] - baseline["tokens"],
            "seconds": round(memory["seconds"] - baseline["seconds"], 3),
        },
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("mode     resolved  tool calls  tokens  seconds")
    for result in (baseline, memory):
        print(
            f"{result['mode']:<8} {str(result['resolved']):<9} "
            f"{result['tool_calls']:<11} {result['tokens']:<7} {result['seconds']}"
        )
    print(f"wrote {args.output}")
    return 0 if baseline["resolved"] and memory["resolved"] else 1


if __name__ == "__main__":
    sys.exit(main())
