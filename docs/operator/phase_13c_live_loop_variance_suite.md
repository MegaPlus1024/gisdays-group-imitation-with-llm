# Phase 13C Live Loop Variance Suite

## Scope

- repeated offline live-loop trials for the three hard Phase 13 scenarios
- guarded local-model backend only
- `third_model` as the default planner alias
- explicit operator opt-in required for model calls
- no real browser or Playwright from Codex

## Safe refusal smoke

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop_variance_suite.py `
  --config configs/autonomous_runtime/browser_live_loop_variance_suite.example.json
```

This should refuse with `allow_model_calls_required` unless the operator explicitly adds `--allow-model-calls`.

## Operator run

```powershell
.\.venv\Scripts\python.exe scripts/run_autonomous_browser_live_loop_variance_suite.py `
  --config configs/autonomous_runtime/browser_live_loop_variance_suite.example.json `
  --allow-model-calls `
  --model-alias third_model `
  --model-endpoint http://127.0.0.1:8082/v1/chat/completions
```

## Notes

- the suite repeats the same three hard scenarios and records trial summaries plus route/goal stability signals
- trace paths, if present, should stay relative
- generated summaries are evidence only and should not be committed
- this is not a production browser automation path
