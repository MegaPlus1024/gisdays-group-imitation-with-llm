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

## Phase 13B5 note

- the local-model live loop now rejects first-step `browser_click`, `browser_extract_text`, and `browser_snapshot` actions when no page is open yet, using `live_action_requires_open_page`
- `browser_open_url` remains the first accepted action in the no-page state, so the scenario start URL can be opened before any click or extract step
- the guard stays fixture-backed and does not launch browser, Playwright, or a live model loop from Codex

## Phase 13B7 note

- the first local-model action can now reach fixture execution as `browser_open_url`, and the failure has moved to invented `expected_text` on the opened start page instead of the initial no-page guard
- the live-model prompt now carries exact visible start-page anchors such as `Office Intranet Home`, `Workspace policy`, and the local policy review search marker so the model can choose a real substring for `expected_text`
- a safe preflight can reject obviously invented start-page `expected_text` values before fixture execution when the target page is already known from local fixtures
- Codex still does not launch browser, Playwright, Chromium, or a model here

## Phase 13B8 note

- the live-model prompt now also carries destination-page anchors for visible local `browser_click` targets, so `expected_text` can be grounded in the page reached by the click rather than the current page text
- the guarded live loop can now preflight click actions against the resolved destination fixture page and reject invented destination anchors before fixture execution
- this remains fixture-backed guidance only; it does not add production browser automation or Codex-launched model execution

## Phase 13B9 note

- the local-model live loop now adds goal-relevant link guidance for the hard policy disambiguation scenario, so the home page should favor `Workspace policy` instead of `Ticket board`
- click actions now preflight `expected_url` against the resolved destination fixture URL and reject invented paths like `/ticket_board` before fixture execution
- the run still remains offline and fixture-backed; no browser, Playwright, or Codex-launched model execution is added

## Phase 13B10 note

- `expected_text` is now enforced as one exact visible substring, so semicolon-joined or newline-joined anchor lists are rejected with `model_output_expected_text_not_atomic`
- malformed `expected_url` values such as placeholder `http<absolute_path>` inputs are rejected with `model_output_invalid_expected_url` before any destination-mismatch check
- the hard policy disambiguation prompt now calls out the exact `Workspace policy` destination and the exact `https://local.intranet/docs/policy` expected URL, but Codex still does not launch browser or Playwright here
