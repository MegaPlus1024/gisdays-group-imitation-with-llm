# Phase 13E3 Stateful Planner Materialization

This phase adds a materializer for accepted stateful read-only planner outputs.

## What it does

- reads an existing planner packet directory
- reuses packet/evaluator parsing and validation
- materializes accepted outputs into workflow state, trace, and summary artifacts
- writes a compact top-level materializer summary

## Suggested local commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_autonomous_browser_stateful_readonly_planner_materializer.py
.\.venv\Scripts\python.exe scripts\materialize_autonomous_browser_stateful_readonly_planner_outputs.py --packet-dir artifacts\autonomous_runtime_planner_packets\stateful_readonly_planner --output-dir artifacts\autonomous_runtime_summaries\stateful_readonly_planner_materialized
```

## Troubleshooting

- Missing packet manifest or packet summary files should return a structured failure summary.
- Missing captured raw outputs should be reported as missing outputs, not as rejected content.
- Invalid planner output should still be rejected by the existing evaluator path.
- `source_response_path` should not leak into the workflow-summary artifact shape.

## Safety boundaries

- no model calls
- no browser or Playwright execution
- no external network access
- no GGUF modification
- no generated artifacts committed

## Notes

- The implementation is intentionally offline and fixture-backed.
- The packet/evaluator validation logic is reused so behavior stays strict.
