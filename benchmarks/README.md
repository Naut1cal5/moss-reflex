# Benchmark harness

`run_benchmark.py` executes the same task twice: once with memory disabled and once with
memory enabled. It does not invent results or require a paid model. You supply the coding-agent
runner you want to evaluate.

The runner receives these environment variables:

- `MOSS_REFLEX_BENCH_MODE`: `off` on the first run, `on` on the second.
- `MOSS_REFLEX_BENCH_RUN`: `1` or `2`.
- `MOSS_REFLEX_BENCH_TASK`: absolute path to the same task or fixture.
- `MOSS_REFLEX_BENCH_RESULT`: path where the runner must write JSON.

The result JSON contract is:

```json
{"resolved": true, "tool_calls": 14, "tokens": 18200}
```

Example:

```bash
python benchmarks/run_benchmark.py \
  --task benchmarks/tasks/recurring-import-error.md \
  --runner './your-agent-adapter'
```

The report records both raw measurements and second-run deltas. Keep the agent, model, prompt,
repository revision, and task identical between runs; only the memory mode should change.
