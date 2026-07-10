# Phase 13B Guarded Local Model Live Loop

## Scope

- guarded local-model planner adapter for the offline live loop
- observe -> local model proposes one next action -> validate -> fixture execute -> observe -> repeat
- local fixture-backed execution only
- manual operator model endpoint only

## Safe refusal smoke

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop.py `
  --config configs\autonomous_runtime\browser_live_loop_local_model.example.json
```

This path should refuse with `allow_model_calls_required` unless the operator explicitly enables model calls.

## Diagnostics notes

- non-local endpoints are rejected with `non_local_model_endpoint`
- local HTTP transport failures surface as `model_http_request_failed`
- local HTTP status errors surface as `model_http_status_error`
- malformed or truncated model responses surface as `model_response_invalid_json`, `model_response_missing_choices`, `model_response_missing_content`, `model_output_no_json_object`, or `model_output_invalid_action` depending on the failure shape
- these codes stay structured and safe for operator troubleshooting and do not imply production readiness

## Phase 13B4 note

- `--model-endpoint` may be either `http://127.0.0.1:8082/v1` or the full `http://127.0.0.1:8082/v1/chat/completions`; the planner normalizes both to the same chat-completions target
- if the model emits `browser_search`, `browser_submit`, `browser_type`, or any other unsupported action, the live loop rejects it as `model_output_unsupported_action` before fixture execution
- do not add web/search support for Phase 13B; retry only after the prompt and guard patch

## Phase 13B5 note

- when the current observation has no opened page yet, the live loop now rejects first-step `browser_click`, `browser_extract_text`, and `browser_snapshot` actions with `live_action_requires_open_page`
- `browser_open_url` remains the valid first action in that state, so the operator should open the scenario start URL before expecting click or extract behavior
- this is still fixture-backed operator guidance only; it does not add browser launch capability or production readiness

## Phase 13B7 note

- if `browser_open_url` succeeds but the run stops with `expected_text_missing` or `model_output_expected_text_not_visible`, the model invented a start-page anchor instead of reusing visible fixture text
- for the current policy scenario, valid first-page anchors include `Office Intranet Home`, `Workspace policy`, and `Search marker: fixture-backed result for local policy review.`
- retry with an exact visible substring from the start page, not a welcome phrase, and keep the run fixture-backed only

## Phase 13B8 note

- for `browser_click`, `expected_text` should come from the destination page reached by the clicked target, not from the page the model is currently reading
- for the current policy scenario, a click on `Workspace policy` should ground `expected_text` in destination-page anchors such as `Workspace Policy`, `Allowed activity`, and `Search marker: fixture-backed result for workspace policy review.`
- the guarded live loop can now reject invented click-destination anchors before fixture execution, while still staying fixture-backed and non-production

## Phase 13B9 note

- if a click stops with `model_output_expected_url_not_matching_destination`, the model invented or misread the destination URL and should use the exact resolved fixture URL instead
- for `hard_policy_disambiguation`, the relevant home-page link is `Workspace policy -> https://local.intranet/docs/policy`
- `Ticket board` remains visible, but it is not the policy-source link for this goal

## Phase 13B10 note

- `model_output_expected_text_not_atomic` means the model joined multiple anchors into one `expected_text`; use one exact visible substring instead
- `model_output_invalid_expected_url` means the model emitted a malformed, non-local, or placeholder `expected_url`; the `Workspace policy` click must use `https://local.intranet/docs/policy`
- this is still fixture-backed operator guidance only; it does not add browser launch capability or production readiness

## Phase 13B11 note

- repaired live-loop runs now preserve repair provenance in the summary trace with `repair_applied`, `original_error_code`, and `repair_error_code`
- successful repair attempts are counted from the actual repaired execution trace, while invalid repair outputs still stop safely before fixture execution
- these diagnostics stay structured for operator troubleshooting and do not change the guarded default behavior

## Phase 13B14 note

- once the Workspace Policy page is reached, the prompt now says the policy-source goal is satisfied and should prefer `done`, `browser_extract_text`, or `browser_snapshot` over another click
- the visible click-target preflight now rejects invisible clicks before fixture execution with `model_output_click_target_not_visible`, which keeps `browser_click_target_not_found` out of the normal known-page flow
- summary repair counters are cumulative, and the new `*_total` aliases make that cumulative meaning explicit for troubleshooting

## Phase 13B15 note

- if the configured completion policy is enabled, `hard_policy_disambiguation` now stops as `succeeded` with `stop_reason: goal_satisfied` as soon as the Workspace Policy page is reached with the required anchors
- `goal_satisfied` is recorded in the trace metadata together with `completion_policy_id`, `matched_completion_criteria`, `matched_url`, and `matched_text_anchors`
- if the live loop still ends with `max_steps_reached` while every expected check passed, the completion policy is missing or disabled; this remains fixture-backed operator guidance only

## Phase 13B16 note

- the completion policy is now scoped strictly to the current `scenario_id`; only `hard_policy_disambiguation` has completion criteria right now
- `hard_ticket_priority_crosscheck` and `hard_approval_policy_match` should not inherit `goal_satisfied` from the policy scenario
- `goal_satisfied` is valid only when `matched_completion_criteria.scenario_id` equals the live loop `scenario_id`; if a mismatch is detected, the run fails safely with `completion_policy_scenario_mismatch`
- if other scenarios do not yet have completion criteria, `done`, `max_steps`, or ordinary failure/rejection is the expected outcome

## Phase 13B17 note

- B16 removed the false positive, and the final three hard-scenario run now has `hard_policy_disambiguation` succeeding while the ticket and approval scenarios stay scoped to their own criteria
- ticket completion should cite `tickets/1` plus the quarterly access review / priority / role anchors, and approval completion should cite the approval flow plus `portal/approval-match` evidence anchors
- the ticket scenario should start from `Ticket board`, then `Ticket 1`; the approval scenario should start from `Approvals queue`, then `Policy match review`
- `Workspace policy` alone should not satisfy either ticket or approval completion unless the scenario explicitly configures that, which it does not here

## Phase 13B18 note

- `model_output_irrelevant_click_target` means the click target was visible but not relevant to the current scenario goal
- for `hard_approval_policy_match` from home, the expected next click is `Approvals queue`; from the approvals page, the expected next click is `Policy match review`
- the relevance guard rejects irrelevant visible clicks before fixture execution and repairs them toward the scenario-specific target instead of letting the run drift through `Workspace policy`

## Phase 13B19 note

- `model_output_expected_text_not_visible` on `hard_ticket_priority_crosscheck` now means the model used the Ticket Board listing sentence instead of a destination-page anchor for the `Ticket 1` click
- for that ticket repair, the expected destination anchor should be `Ticket 1 - Quarterly Access Review` rather than the board listing sentence
- the repair stays one JSON object, no prose, and remains fixture-backed only

## Guarded operator run

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop.py `
  --config configs\autonomous_runtime\browser_live_loop_local_model.example.json `
  --planner-backend local_model `
  --allow-model-calls `
  --model-endpoint http://127.0.0.1:8082/v1 `
  --model-alias third_model `
  --scenario-id browser_live_loop_local_model_policy_review_v1 `
  --output-dir artifacts\autonomous_runtime_summaries\browser_live_loop_local_model
```

## Limitations

- Codex does not launch models, llama-server, browser, Playwright, Chromium, or a local server here
- this is not production browser automation
- this does not claim autonomous live LLM-loop readiness
- third_model is treated as an operator-provided local GGUF planner candidate
