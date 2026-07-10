# Phase 13D Live Loop Playwright Replay

## Purpose

Phase 13D prepares a guarded Playwright replay suite that consumes successful Phase 13C live-loop traces and replays their executed browser actions against local/fixture/loopback content only.

Phase 13D1 fixes the artifact handoff so the variance suite persists per-trial trace files at the paths recorded in its summary, and the replay loader tolerates common PowerShell JSON encodings.
Phase 13D2 fixes the live-loop replay trace-to-backend handoff so selected action names stay canonical, replay plans validate as `autonomous_browser_plan_v1`, and pre-browser guarded failures carry sanitized validation diagnostics.
Phase 13D3 fixes the generated guarded Playwright operator config shape so the existing operator receives the exact schema it expects, and backend config paths appear in replay diagnostics.

## Input and output

- input: `artifacts/autonomous_runtime_summaries/live_loop_variance_suite.summary.json`
- trace root: `artifacts/autonomous_runtime_summaries/live_loop_variance_suite`
- expected trace shape: `artifacts/autonomous_runtime_summaries/live_loop_variance_suite/<scenario_id>/trial_XX/autonomous_browser_live_loop_trace.json`
- output: `autonomous_browser_live_loop_playwright_replay_summary_v1`

The replay summary is intended to track:

- suite and replay backend identifiers
- trace discovery and selection counts
- per-trace and per-scenario replay summaries
- action counts, expected-result counts, matched URLs, and final replay URLs
- safety flags such as `real_browser_execution`, `playwright_execution`, `browser_opened`, and `no_runtime_execution`

## Safety gates

- the default CLI/config path refuses safely without explicit real-browser guards
- dry-run mode validates and discovers traces without launching Playwright
- only local/fixture/loopback hosts are allowed
- `browser_search` and external web browsing are not part of this replay preparation path
- Phase 13D2 keeps the real guarded replay path bounded; it improves config/action handoff and diagnostics without launching Playwright from Codex
- Phase 13D3 fixes the remaining pre-browser config validation barrier without changing the refusal boundary

## Refusal and dry-run behavior

- refusal returns a compact JSON summary with a clear `error_code`
- dry-run keeps `real_browser_execution: false`, `playwright_execution: false`, and `browser_opened: false`
- Codex verifies refusal and dry-run paths only

## Operator command for the later guarded real run

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop_playwright_replay.py `
  --config configs\autonomous_runtime\browser_live_loop_playwright_replay.example.json `
  --allow-real-browser `
  --allow-playwright `
  --output-dir artifacts\autonomous_runtime_summaries\live_loop_playwright_replay
```

## Limitations

- fixture-only replay preparation, not production browser automation
- local model calls are not part of this phase
- Codex does not launch Playwright or Chromium here
- generated replay artifacts are evidence-only and should not be committed
- this is not a security evaluation or a production recommendation
- D2 confirms the dry-run path already succeeded and the earlier real guarded failure was a pre-browser config/action handoff issue
- D3 confirms the remaining real guarded failure was a generated operator-config shape issue, not a browser launch

## Final success evidence

Phase 13C input evidence:

- `status: succeeded`
- `trials_total: 9`
- `trials_succeeded: 9`
- `trials_failed: 0`
- `trials_rejected: 0`
- `pass_rate_overall: 1.0`
- `trace_count: 9`

Phase 13D dry-run evidence:

- `status: succeeded`
- `input_trace_count: 3`
- `selected_trace_count: 3`
- `traces_succeeded: 3`
- `traces_failed: 0`
- `actions_attempted_total: 8`
- `expected_results_passed_total: 8`
- `expected_results_failed_total: 0`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`

Final real guarded Playwright replay evidence:

- `status: succeeded`
- `error_code: null`
- `replay_backend: playwright`
- `input_trace_count: 3`
- `selected_trace_count: 3`
- `traces_replayed: 3`
- `traces_succeeded: 3`
- `traces_failed: 0`
- `traces_rejected: 0`
- `actions_attempted_total: 8`
- `actions_succeeded_total: 8`
- `actions_failed_total: 0`
- `expected_results_passed_total: 8`
- `expected_results_failed_total: 0`
- `real_browser_execution: true`
- `playwright_execution: true`
- `browser_opened: true`
- `real_network_traffic: false`
- `fixture_only: true`

Per-scenario replay summary:

| scenario_id | status | stop_reason | actions | expected checks | matched_url | real_browser_execution | playwright_execution | browser_opened |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hard_policy_disambiguation` | succeeded | goal_satisfied | 2/2 | 2/2 | `https://local.intranet/docs/policy` | true | true | true |
| `hard_ticket_priority_crosscheck` | succeeded | goal_satisfied | 3/3 | 3/3 | `https://local.intranet/tickets/1` | true | true | true |
| `hard_approval_policy_match` | succeeded | goal_satisfied | 3/3 | 3/3 | `https://local.intranet/portal/approval-match` | true | true | true |

Safety boundaries:

- real browser execution happened only under the operator's explicit guarded replay path
- no external network traffic was observed
- the replay still used local fixture routes only
- no model calls were needed during Phase 13D replay itself
- this remains a replay milestone, not production browser automation

Limitations:

- only the first successful trace for each of the three hard scenarios was replayed
- the evidence is fixture-backed and local only
- this is not a general web browsing benchmark
- this is not a security evaluation or production recommendation
- generated replay artifacts are evidence only and should not be committed

Interpretation:

- Phase 13D now proves that successful guarded local-model live-loop traces can be replayed through a real guarded Playwright/Chromium backend against local fixture routes
- the bridge is: `third_model` local-model live loop -> persisted fixture traces -> dry-run replay validation -> guarded Playwright execution
- Phase 13C provided the trace set, Phase 13D dry-run validated it, and the final guarded replay succeeded on all three scenarios
