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

## Phase 13B11 note

- repaired local-model live-loop runs now carry explicit repair provenance in the summary trace, including `repair_applied`, `original_error_code`, and `repair_error_code`
- successful repaired steps are counted as successful repairs from the final trace, while invalid repair outputs still fail safely before any browser execution
- this keeps the diagnostics structured without changing the guarded, fixture-backed default behavior

## Phase 13B14 note

- the hard policy disambiguation flow now names the policy-page anchors and visible click targets, then steers the model toward `done`, `browser_extract_text`, or `browser_snapshot` once the live policy source page is reached
- current-page click targets are preflighted before fixture execution, so invisible clicks now stop as `model_output_click_target_not_visible` instead of falling through to `browser_click_target_not_found`
- repair counters remain cumulative at the summary level, and the summary now exposes explicit total aliases to make that cumulative meaning unambiguous

## Phase 13B15 note

- the live loop now has an explicit fixture-backed completion policy, so `hard_policy_disambiguation` stops with `status: succeeded` and `stop_reason: goal_satisfied` once the Workspace Policy page is reached with the required anchors
- the completion decision is auditable in trace metadata via `goal_satisfied`, `completion_policy_id`, `matched_completion_criteria`, `matched_url`, and `matched_text_anchors`
- the policy is fixture-local only; it does not add browser launch capability, real Playwright execution, or Codex-launched model execution

## Phase 13B16 note

- the completion policy is now scoped strictly by current `scenario_id`, so `hard_policy_disambiguation` is the only scenario backed by completion criteria for now
- `hard_ticket_priority_crosscheck` and `hard_approval_policy_match` no longer inherit policy completion from the policy scenario; they should continue normally until `done`, `max_steps`, or a real rejection/failure
- `goal_satisfied` is only valid when the matched criteria scenario id matches the live loop `scenario_id`
- this remains fixture-backed only and does not add browser launch capability or Codex-launched model execution

## Phase 13B17 note

- B16 fixed the false-positive leakage, and the final all-three hard-scenario run now has policy success plus ticket/approval runs that continue until `max_steps_reached` with their fixture checks passing
- B17 adds scenario-scoped completion criteria and compact guidance for `hard_ticket_priority_crosscheck` and `hard_approval_policy_match`
- the ticket scenario now keys off `tickets/1`, while the approval scenario keys off the approval flow and the `portal/approval-match` evidence page
- this remains fixture-backed only and does not add browser launch capability or Codex-launched model execution

## Phase 13B18 note

- B17 got the policy and ticket scenarios to `goal_satisfied` / valid scoped criteria, while approval still needed a stronger guard because the model followed visible but irrelevant links
- B18 adds scenario-relevant click-target constraints and repair guidance so `hard_approval_policy_match` can reject `Workspace policy` and steer toward `Approvals queue` / `Policy match review` as appropriate
- the guard stays scenario-scoped, fixture-backed, and does not add browser/Playwright execution from Codex

## Phase 13B19 note

- B18 solved the approval drift, and the remaining hard-ticket failure came from using the Ticket Board listing sentence as `expected_text` for the `Ticket 1` click
- B19 tightens ticket board guidance and repair so `expected_text` must come from the destination page anchor, with `Ticket 1 - Quarterly Access Review` as the preferred anchor
- this stays fixture-backed, scenario-scoped, and does not add browser/Playwright execution from Codex

## Phase 13B20 note

- final guarded local-model evidence now shows all three hard scenarios succeeding under the offline fixture live loop: policy on `docs/policy`, ticket on `tickets/1`, and approval on `portal/approval-match`
- the operator rerun after `90d9491` used `third_model`, with the policy scenario already stable from `163afed`, the ticket scenario repaired to the destination anchor, and the approval scenario reaching `Approvals queue` and `Policy match review` before goal satisfaction
- the final evidence is documented in `docs/status/phase_13b_guarded_local_model_live_loop_final_evidence.md`
- this remains fixture-backed only and does not add browser/Playwright execution from Codex

## Phase 13C note

- Phase 13C adds `docs/status/phase_13c_live_loop_variance_suite.md` and `docs/operator/phase_13c_live_loop_variance_suite.md` for repeated guarded local-model fixture live-loop trials
- the variance suite reuses the guarded live loop, repeats the three hard scenarios, and keeps `third_model` behind explicit `--allow-model-calls`
- route stability and matched-URL stability are tracked across repeated trials, but Codex still does not launch a model, browser, or Playwright here

## Phase 13C final note

- the final Phase 13C operator evidence shows 9/9 successful repeated trials across the three hard scenarios, with stable routes and stable matched URLs
- policy finished without repair, while ticket and approval each used bounded repair successfully on every trial
- the evidence remains fixture-backed only and does not add browser launch capability or Codex-launched model execution

## Phase 13D note

- Phase 13D prepares a guarded Playwright replay suite for the successful Phase 13C live-loop traces; Codex verified the refusal and dry-run paths only
- the new replay preparation keeps replay inputs local, fixture-backed, and scenario-scoped, and it does not launch Playwright or Chromium from Codex
- the operator later remains responsible for any real guarded Playwright replay run against local fixtures only

## Phase 13D1 note

- Phase 13D1 fixes the variance-suite handoff so per-trial trace files are persisted at the summary-recorded relative paths, and the replay loader tolerates common PowerShell JSON encodings

## Phase 13D2 note

- Phase 13D2 fixes the live-loop replay trace/action handoff so canonical `action_name` values survive into the guarded backend, replay plans validate as `autonomous_browser_plan_v1`, and pre-browser failures keep sanitized validation diagnostics
- dry-run already succeeded; the earlier real guarded failure was a pre-browser config/action handoff issue, not a browser launch

## Phase 13D3 note

- Phase 13D3 fixes the generated guarded Playwright operator config shape and records the generated backend config path in replay diagnostics
- the remaining guarded replay failure was a config-shape mismatch before browser launch, not a real Playwright run

## Phase 13D4 note

- Phase 13D4 fixes the first real guarded Playwright replay runtime barrier: click/navigation semantics, post-click expected-text checks, and top-level summary aggregation
- D3 reached the guarded backend with `browser_opened: true`, but click navigation stayed on the home page and the nested operator summaries carried the real browser flags that the top-level summary initially missed
- Codex still did not launch browser, Playwright, Chromium, or a model for this documentation step

## Phase 13D5 note

- Phase 13D5 fixes manifest-backed route mapping for extensionless logical URLs and replaces title-only replay anchors with visible body anchors from the local fixtures

## Phase 13D final note

- Phase 13D final evidence succeeded for all three hard scenarios in the guarded Playwright replay path
- Phase 13C provided the nine successful local-model fixture traces, Phase 13D dry-run validated three selected traces, and the final guarded Playwright replay succeeded with `real_browser_execution: true` and `real_network_traffic: false`
- the final replay remained fixture-only and local, and Codex did not need to launch a model, browser, or Playwright to document the milestone
- D4 had reached real Playwright/Chromium, but `/docs/policy`, `/tickets`, and `/portal/approvals` still returned 404 from the fixture server because the browser followed the raw logical routes
- Codex still did not launch browser, Playwright, Chromium, or a model for this documentation step

## Phase 13E note

- Phase 13E adds the read-only stateful workflow foundation in `docs/status/phase_13e_readonly_stateful_workflows.md` and `docs/operator/phase_13e_readonly_stateful_workflows.md`
- the new layer stays fixture-only, scripted, and read-only while it records state, facts, evidence, and final answers for local intranet workflows
- no model, browser, or Playwright launch is needed from Codex to document or run the scripted E1 path
- Phase 13E2a hardens the companion local-planner packet prompt/schema and evaluator diagnostics after the first `third_model` E2 run exposed strict output-contract mismatches
- Phase 13E2b aligns the confidence enum and truncated-output diagnostics after the follow-up `third_model` E2 run narrowed the remaining failures to `invalid_confidence` and one truncated response
- Phase 13E2c tightens the approval required-fact prompt and missing-key diagnostics after the follow-up `third_model` E2 run reached 4/5 accepted workflows and failed only on the approval required-fact omission
- Phase 13E2 is now successful: the final `third_model` stateful read-only planner pass accepted all 5/5 outputs and 5/5 workflows in the fixture-only evaluator

## Phase 13E3 note

- Phase 13E3 materializes the accepted stateful planner outputs into workflow state, trace, and workflow-summary artifacts in `docs/status/phase_13e_stateful_planner_materialization.md`.
- the materializer reuses the strict packet/evaluator parsing and validation path, and it stays offline and fixture-backed
- missing captured outputs remain a handled failure mode, not a crash path

## Phase 13E4 note

- Phase 13E4 adds a repeated stateful read-only planner variance suite in `docs/status/phase_13e_stateful_planner_variance.md` and `docs/operator/phase_13e_stateful_planner_variance.md`

## Phase 13E4c note

- Phase 13E4c aligns the stateful planner variance prompts, fixture-workflow comparison mode, and click-target diagnostics after an earlier replay that accepted all 15 outputs by schema but failed all 15 workflows.
- The stateful packet now separates overview, hardboard, and policy citation guidance more clearly, and the evaluator/workflow traces keep the source-output and visible-target context attached to failures.
- the new suite prepares three trials for each of the five stateful scenarios under `third_model`, then reuses the offline evaluator and materializer paths
- the commands and runtime config stay fixture-backed, read-only, and safe for BOM-prefixed JSON inputs

## Phase 13E4d note

- Phase 13E4d narrows the remaining alignment gap after the E4c diagnostics: fixture-span comparison is now case-folded, the evaluator preserves model-output citation ids in diagnostics, and the ticket-priority prompt explicitly tells the model to reopen the hardboard before Ticket 8.
- this is still fixture-backed, read-only, and does not add browser/Playwright execution from Codex

## Phase 13E4e note

- Phase 13E4e tightens the remaining stateful variance fact anchoring after the E4d diagnostics: the policy-ticket prompt now says to copy the exact workspace policy marker without inventing admin approval language, and the ticket-priority prompt now says to copy Ticket 8 requester tier exactly as `office worker`.
- this is still fixture-backed, read-only, and does not add browser/Playwright execution from Codex
