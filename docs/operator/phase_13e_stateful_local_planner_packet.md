# Phase 13E2a Stateful Local Planner Packet Operator Notes

## What to run

Rebuild the packet after updating the prompt/schema hardening:

```powershell
.\.venv\Scripts\python.exe scripts\build_autonomous_browser_stateful_readonly_planner_packet.py `
  --config configs\autonomous_runtime\browser_stateful_readonly_planner_packet.example.json
```

Then inspect the generated prompt and schema docs in the packet output directory.

If you want to recheck the offline evaluator shape, use:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_planner_evaluator.py `
  --packet-dir artifacts\autonomous_runtime_planner_packets\stateful_readonly_planner
```

## What changed in E2a

- the prompt now includes a strict JSON skeleton with `action_name` and `parameters`
- `browser_click` guidance now points at `parameters.target_text`
- the schema doc now names forbidden aliases like `action`, `tool`, `id`, `text`, and `content`
- evaluator diagnostics now name the missing shape fields more clearly

## Safety boundary

- strict validation remains strict
- no alias normalization is enabled by default
- no models, browser, Playwright, Chromium, or llama-server are launched by Codex
- generated packet artifacts are evidence only and should not be committed

## Phase 13E2b follow-up

- `final_answer.confidence` is optional; if present, use exactly `low`, `medium`, or `high`
- the evaluator will now report `truncated_model_output` if `response.json` says `finish_reason: length`
- the packet config raises `max_tokens` to `1800` for the next capture pass

## Phase 13E2c follow-up

- the approval prompt now includes an explicit required-facts skeleton and says not to omit `approval_decision_note`
- `missing_required_fact_keys` diagnostics now include required, present, and missing key lists plus a hint
- strict validation still stays strict and does not repair missing facts

## Final success expectations

- the final evaluator summary should show `status: succeeded` and `error_code: null`
- `model_execution: false` in the evaluator summary is expected because the evaluator does not call the model
- `real_browser_execution: false`, `playwright_execution: false`, and `browser_opened: false` are expected for the offline evaluator path
- `actions_succeeded` may remain `0` when no real executor or browser is run; the important values are the packet outputs, validation, dry-run, fixture replay, and workflow counts

## How to inspect the final accepted summaries

- open the packet output directory and review the generated request/response summaries for the five scenarios
- confirm each scenario shows `validation_accepted`, `dry_runs_succeeded`, `fixture_runs_succeeded`, and `workflows_succeeded`
- confirm the approval scenario includes `approval_decision_note` in the accepted facts and no `missing_required_fact_keys`

## Troubleshooting notes

- the initial strict-schema failure was `missing_action_field`
- the intermediate hardening pass exposed `invalid_confidence` and truncation handling
- the approval-specific omission was `approval_decision_note`; once that prompt was tightened, the evaluator accepted all five outputs
- strict validation remains strict and should not be relaxed for missing facts or aliases
