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
