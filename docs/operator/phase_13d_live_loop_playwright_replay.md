# Phase 13D Live Loop Playwright Replay Operator Notes

## Prerequisites

- Phase 13C variance-suite artifacts exist
- the replay inputs are local fixture-backed traces only
- explicit `--allow-real-browser` and `--allow-playwright` guards are required for the non-dry-run path
- Codex should use the dry-run or refusal path only
- Phase 13D1 fixed the variance-suite handoff so replay sees the per-trial trace files at the summary-recorded relative paths

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
