# Phase 13D Live Loop Playwright Replay

## Purpose

Phase 13D prepares a guarded Playwright replay suite that consumes successful Phase 13C live-loop traces and replays their executed browser actions against local/fixture/loopback content only.

Phase 13D1 fixes the artifact handoff so the variance suite persists per-trial trace files at the paths recorded in its summary, and the replay loader tolerates common PowerShell JSON encodings.

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
