# Phase 13E Read-Only Stateful Workflows Operator Notes

## What to run

Use the scripted fixture-only suite:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_workflow_suite.py `
  --config configs\autonomous_runtime\browser_stateful_readonly_workflow_suite.example.json
```

No model, llama-server, browser, Chromium, or Playwright is needed for E1.

## Expected summary fields

The suite summary should report:

- `status`
- `error_code`
- `scenarios_total`
- `scenarios_succeeded`
- `scenarios_failed`
- `scenarios_rejected`
- `workflows_total`
- `workflows_succeeded`
- `actions_attempted_total`
- `actions_succeeded_total`
- `facts_collected_total`
- `evidence_items_total`
- `failure_class_counts`
- `scenario_summaries`

Each scenario summary should include relative `state_path`, `trace_path`, and `summary_path` values.

## How to inspect the artifacts

- `state_path` contains the JSON-serialized workflow state
- `trace_path` contains the step-by-step trace entries
- `summary_path` contains the per-scenario summary

The state should show collected facts, evidence items, visited URLs, and the final answer. The trace should show step outcomes, expected-text checks, and the failure class when a step is rejected or fails.

## Failure class guide

- `scenario_policy_rejected` means a scripted step asked for a disallowed action
- `script_error` means the scripted workflow itself was malformed
- `fixture_error` means the local fixture resolution or fixture-backed action failed
- `validation_error` means the rendered page did not satisfy the expected check
- `model_failed_task` is reserved for a workflow that reaches the end but still cannot produce a final answer

## Boundaries

- read-only only
- local fixtures only
- no external network
- no Codex-launched model or browser is needed for this phase
- generated artifacts are evidence only and should not be committed
