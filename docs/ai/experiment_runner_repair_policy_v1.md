# Experiment Runner Repair Policy v1

## 1. Purpose

Small local models can produce structurally valid but incomplete actions. The first real `first_model` dry run showed exactly that: the model selected `read_file` but omitted the required `parameters.path`.

Repair policy gives the same model one controlled opportunity to correct a recoverable parse or validation failure. This is useful for experiments because it measures both first-attempt quality and recoverability without pretending the initial failure did not happen.

## 2. What Repair Does

When enabled with `--repair-attempts 1`, the runner performs:

```text
initial prompt
-> raw output
-> parse and validation
-> if recoverable parse/validation failure:
     build strict repair prompt
     call same model again
     parse and validate repaired output
-> if accepted:
     execute repaired action
     update history
     continue
-> if still invalid:
     stop with explicit after-repair reason
```

The repair prompt includes the exact rejection reason, previous raw output, allowed action schemas, required parameters, and role constraints.

## 3. What Repair Does Not Do

- It does not repair the action in code.
- It does not auto-fill missing parameters.
- It does not hide the initial failure.
- It does not rewrite the first attempt as successful.
- It does not expand shell allowlists or safety boundaries.
- It does not make a bad response good retroactively.

## 4. Metrics

Repair policy separates:

- `initial_parse_success_count`: first-attempt JSON/contract parse success.
- `initial_validation_accept_count`: first-attempt registry/role/safety acceptance.
- `repair_attempt_count`: total repair attempts.
- `repair_parse_success_count`: repair attempts that parsed.
- `repair_validation_accept_count`: repair attempts accepted by validation.
- `repaired_step_count`: steps recovered by repair.
- `unrecovered_failure_count`: steps still failed after repair or without repair.
- `final_validation_accept_count`: final accepted steps after repair policy.
- `execution_success_count`: final actions that executed successfully.

This makes first-attempt valid-action rate and final valid-action rate distinct.

## 5. Artifacts

Repair-enabled runs write:

- `attempts.jsonl`: every initial and repair attempt with prompt kind, raw output, parse/validation status, issues, latency, and errors.
- `raw_model_outputs.jsonl`: raw output per attempt with `attempt_index` and `attempt_type`.
- `validation_results.jsonl`: validation result per parsed attempt.
- `selected_actions.jsonl`: final accepted action only, if one exists.
- `errors.jsonl`: initial failure remains recorded even if repair succeeds.
- `steps.jsonl`: includes `repair_attempt_count`, `final_attempt_index`, `repaired`, and `initial_failure_preserved`.
- `model_behavior_result.json`: includes repair summary metrics in `metadata.repair_summary`.

## 6. Fair Comparison Rule

All models in a comparison must use the same repair policy. Comparing one model with repair enabled against another model without repair enabled would mix model quality with harness behavior.

Recommended comparison settings:

```text
--repair-attempts 1
--repair-on-parse-failure
--repair-on-validation-failure
```

## 7. Example Command

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py `
  --mode local `
  --model-id first_model `
  --models-config configs\evaluation_models.json `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\model_behavior\results\office_worker_first_model_run_002_repair_v1 `
  --run-id office_worker_first_model_run_002_repair_v1 `
  --execute-actions `
  --max-steps 5 `
  --repair-attempts 1 `
  --force
```
