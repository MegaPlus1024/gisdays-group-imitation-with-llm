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

## Final evidence

Top-level suite summary:

- `suite_id`: `phase_13c_guarded_local_model_live_loop_variance`
- `status`: `succeeded`
- `model_alias`: `third_model`
- `planner_backend`: `local_model`
- `trial_count_per_scenario`: `3`
- `scenarios_total`: `3`
- `trials_total`: `9`
- `trials_succeeded`: `9`
- `trials_failed`: `0`
- `trials_rejected`: `0`
- `pass_rate_overall`: `1.0`
- `model_execution_attempted`: `true`
- `model_execution_completed`: `true`
- `real_browser_execution`: `false`
- `playwright_execution`: `false`
- `browser_opened`: `false`
- `no_runtime_execution`: `true`

Scenario outcomes:

| scenario_id | status | trials | pass_rate | actions | expected checks | matched_url | route_stable | matched_url_stable |
|---|---|---:|---:|---:|---:|---|---|---|
| `hard_policy_disambiguation` | `succeeded` | 3 | 1.0 | 6/6 | 6/0 | `https://local.intranet/docs/policy` | true | true |
| `hard_ticket_priority_crosscheck` | `succeeded` | 3 | 1.0 | 9/9 | 9/0 | `https://local.intranet/tickets/1` | true | true |
| `hard_approval_policy_match` | `succeeded` | 3 | 1.0 | 9/9 | 9/0 | `https://local.intranet/portal/approval-match` | true | true |

Repair summary:

- policy scenario: no repairs required
- ticket scenario: repairs were required and succeeded on every trial; the observed original error code was `model_output_irrelevant_click_target`
- approval scenario: repairs were required and succeeded on every trial; the observed original error code was `model_output_irrelevant_click_target`
- total repair attempts: `12`
- total repair attempts succeeded: `12`
- total repair attempts failed: `0`

Route stability summary:

- `hard_policy_disambiguation`: stable matched URL and stable route fingerprint
- `hard_ticket_priority_crosscheck`: stable matched URL and stable route fingerprint
- `hard_approval_policy_match`: stable matched URL and stable route fingerprint
- the final repeated-trial evidence shows no cross-trial drift in the successful routes

Safety boundaries:

- fixture-only local browser model
- no real browser or Playwright execution from Codex
- no external network activity
- local model calls require explicit operator opt-in
- generated runtime summaries are evidence artifacts and should not be committed

Limitations:

- only three hard scenarios are covered
- only three trials per scenario were run for this evidence set
- this is not production browser automation
- this is not a production recommendation
- completion policies are configured fixture criteria, not universal task success

Next recommended phase:

- broaden the variance suite only if additional fixture-backed scenarios or more trials are needed for research coverage
- keep the guarded operator flow and refusal-by-default behavior intact
