# Phase 13D Live Loop Playwright Replay Operator Notes

## Prerequisites

- Phase 13C variance-suite artifacts exist
- the replay inputs are local fixture-backed traces only
- explicit `--allow-real-browser` and `--allow-playwright` guards are required for the non-dry-run path
- Codex should use the dry-run or refusal path only
- Phase 13D1 fixed the variance-suite handoff so replay sees the per-trial trace files at the summary-recorded relative paths
- Phase 13D2 fixes the replay trace/action handoff so canonical `action_name` values reach the guarded backend and pre-browser validation failures surface sanitized diagnostics
- Phase 13D3 fixes the generated guarded operator-config shape and writes the backend config next to each replay plan
- Phase 13D4 fixes the first real guarded Playwright replay barrier: clicks must target a clickable element, wait for navigation, and validate the post-click page rather than staying on the home page
- post-click expected-text checks now use the rendered destination page, and nested operator summaries carry the real browser flags that top-level aggregation reads
- Codex still does not launch browser, Playwright, Chromium, or a model for this path

## Phase 13D5 note

- Phase 13D5 fixes manifest-backed route mapping for extensionless logical URLs and grounds replay-plan `expected_text` in visible body anchors instead of title-only strings
- the fixture server now serves `/docs/policy`, `/tickets`, `/tickets/1`, `/portal/approvals`, and `/portal/approval-match` through the manifest-backed route map
- Codex still does not launch browser, Playwright, Chromium, or a model for this path

## Dry-run command

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop_playwright_replay.py `
  --config configs\autonomous_runtime\browser_live_loop_playwright_replay.example.json `
  --dry-run
```

Expected dry-run properties:

- `status: succeeded`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`
- trace paths remain relative
- no Playwright or Chromium launch from Codex

## Refusal command

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop_playwright_replay.py `
  --config configs\autonomous_runtime\browser_live_loop_playwright_replay.example.json
```

Expected refusal properties:

- `status: refused`
- `error_code: allow_real_browser_required`
- `no_runtime_execution: true`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`

## Later guarded real run

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop_playwright_replay.py `
  --config configs\autonomous_runtime\browser_live_loop_playwright_replay.example.json `
  --allow-real-browser `
  --allow-playwright `
  --output-dir artifacts\autonomous_runtime_summaries\live_loop_playwright_replay
```

## Failure diagnostics

- `allow_real_browser_required` means the non-dry-run path is still guarded
- `allow_playwright_required` means the Playwright guard is still missing
- `trace_not_found` and `trace_json_malformed` point to input trace problems
- `unsafe_trace_path` means a non-relative or otherwise unsafe path was rejected
- `file_url_not_allowed` means a replay input tried to escape the fixture-only boundary
- `config_validation_failed` can still appear before browser launch, but the replay trace diagnostics now carry the sanitized validation cause
- `backend_config_path` now points at the generated operator config next to the replay plan

## Final success note

- Phase 13C input evidence completed successfully before replay:
  - `status: succeeded`
  - `trials_total: 9`
  - `trials_succeeded: 9`
  - `pass_rate_overall: 1.0`
- Phase 13D dry-run completed successfully before guarded execution:
  - `status: succeeded`
  - `input_trace_count: 3`
  - `selected_trace_count: 3`
  - `traces_succeeded: 3`
  - `actions_attempted_total: 8`
  - `expected_results_passed_total: 8`
  - `real_browser_execution: false`
  - `playwright_execution: false`
  - `browser_opened: false`
- final guarded replay completed successfully:
  - `status: succeeded`
  - `error_code: null`
  - `traces_replayed: 3`
  - `traces_succeeded: 3`
  - `actions_attempted_total: 8`
  - `actions_succeeded_total: 8`
  - `expected_results_passed_total: 8`
  - `real_browser_execution: true`
  - `playwright_execution: true`
  - `browser_opened: true`
  - `real_network_traffic: false`
  - `fixture_only: true`

### How to read `replay_final_url`

- `replay_final_url` is the local fixture-served URL reached by the guarded Playwright run
- for these traces it should be a `127.0.0.1:8765` fixture URL, not an external site
- the logical URL remains the policy/ticket/approval fixture URL from the trace, while the final replay URL reflects the local server mapping

### Operational reminders

- if the Phase 13C traces already exist, Phase 13D replay does not need a model or llama-server run
- Phase 13C traces must exist before replay; Phase 13D consumes persisted traces only
- the final replay evidence is a guarded local fixture result, not production automation
