# Phase 13C Live Loop Variance Suite

## Summary

Phase 13C adds an offline, fixture-backed repeated live-loop variance suite for the guarded local-model planner path. It reuses the existing live-loop core, repeats the three hard Phase 13 scenarios, and is designed to be run by an operator only when `--allow-model-calls` is passed explicitly.

## Scope

- repeated trials for `hard_policy_disambiguation`
- repeated trials for `hard_ticket_priority_crosscheck`
- repeated trials for `hard_approval_policy_match`
- `third_model` as the default local planner candidate
- guarded `local_model` backend only
- no real browser or Playwright execution from Codex

## Evidence model

The suite summary is intended to carry:

- `schema_version`: `autonomous_browser_live_loop_variance_suite_summary_v1`
- `suite_id`
- `status`
- `error_code`
- `model_alias`
- `planner_backend`
- `trial_count_per_scenario`
- `scenarios_total`
- `trials_total`
- `trials_succeeded`
- `trials_failed`
- `trials_rejected`
- `pass_rate_overall`
- `model_execution_attempted`
- `model_execution_completed`
- `real_browser_execution`
- `playwright_execution`
- `browser_opened`
- `no_runtime_execution`
- `allow_model_calls`
- `limitations`
- `scenario_summaries`
- `trial_summaries`

Per-trial summaries are expected to retain scenario identifiers, trial labels, action counts, repair counts, matched URLs, completion-criteria provenance, and relative trace paths when present. Scenario summaries are expected to track trial totals, pass rates, error-code collections, matched URLs, route fingerprints, and route/matched-url stability.

## What this adds

- a bounded variance layer over the existing guarded live loop
- repeated offline evidence for the same hard scenarios instead of a single-trial snapshot
- route/goal stability checks across repeated trials
- refusal-by-default behavior unless the operator explicitly allows model calls

## Limitations

- fixture-only local browser model, not production automation
- explicit operator opt-in is still required for local model calls
- no real browser, Playwright, or external network from Codex
- only the three hard scenarios are covered by default
- generated summaries are evidence artifacts and should not be committed
- this is not a security evaluation or a production recommendation

## Operator command

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop_variance_suite.py `
  --config configs/autonomous_runtime/browser_live_loop_variance_suite.example.json `
  --allow-model-calls `
  --model-alias third_model `
  --model-endpoint http://127.0.0.1:8082/v1/chat/completions
```

The default config refuses safely without `--allow-model-calls`.
