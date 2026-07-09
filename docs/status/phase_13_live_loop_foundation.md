# Phase 13A Live Loop Foundation

## Scope

- offline scripted live-loop foundation for autonomous browser planning
- observe -> planner -> validate -> fixture-execute -> observe cycle
- local fixture-backed execution only
- trace capture and compact JSON CLI output

## Evidence summary

- schema_version: `autonomous_browser_live_loop_summary_v1`
- loop_backend: `offline_fixture`
- planner_backend: `scripted`
- max_steps: `8`
- steps_attempted: `4`
- actions_attempted: `3`
- actions_succeeded: `3`
- actions_failed: `0`
- expected_results_passed: `3`
- expected_results_failed: `0`
- observations_total: `4`
- stop_reason: `planner_signaled_done`
- error_code: `null`
- model_execution: `false`
- real_browser_execution: `false`
- playwright_execution: `false`
- browser_opened: `false`
- no_runtime_execution: `true`

## What this proves

- a planner backend abstraction can drive a bounded offline browser loop one step at a time
- scripted planner steps can be validated and replayed against local fixtures
- the loop keeps browser execution offline while still producing a structured trace
- repeated-action and invalid-step guards are available before any real browser path

## What this does not prove

- not a live model-driven loop
- not real browser execution
- not guarded Playwright execution
- not production browser automation
- not autonomous agent deployment
- not a recommendation to use this path in production

## Relation to earlier phases

- Phase 12E documents repeated local planner trials evidence for captured model outputs.
- Phase 13A builds the offline live-loop scaffold that can later host a guarded model planner adapter.
- The guarded Playwright suite evidence from Phase 9 remains the separate real-browser benchmark.

## Phase 13B note

- `docs/operator/phase_13b_guarded_local_model_live_loop.md` records the guarded local-model adapter commands and refusal-by-default smoke path.
- Phase 13B keeps the live loop fixture-backed by default and does not add real browser or Codex-launched model execution.

## Phase 13B3 note

- the guarded local-model planner diagnostics now preserve safe structured error codes for non-local endpoints and local HTTP failures
- the first operator-side live-model attempt can now fail safely with structured JSON instead of a generic traceback, while still not launching browser or Playwright from Codex

## Phase 13B4 note

- the operator retry with `http://127.0.0.1:8082/v1` proved the local model request reaches llama-server
- the retry returned `browser_search`, which Phase 13B now rejects as `model_output_unsupported_action` before fixture execution
- endpoint normalization now accepts both `/v1` and full `/v1/chat/completions` inputs without duplicating the path
- Codex still does not launch browser or Playwright here
