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
