# Phase 14 Multi-model Benchmark

## Summary

Phase 14 is an optional post-completion expansion for the already completed controlled read-only prototype.

It adds a reusable multi-model benchmark packet/evaluator for the existing five stateful read-only planner scenarios. The packet prepares repeated request files for multiple configured model aliases, and the evaluator classifies captured outputs per model without launching models, browser, Playwright, Chromium, or a local server.

By default, the example benchmark config targets `second_model` and `third_model`.

Phase 14B records the first real operator-run result from that benchmark infrastructure. The model calls were manual operator runs against local endpoints for `second_model` and `third_model`. After capture, the evaluator remained offline, fixture-only, and read-only.

Phase 14C extends the optional benchmark registry/config layer so future post-completion comparisons can also include `fourth_model` and `fifth_model` without changing the original TZ completion status.

## What was added

- `src/agent/autonomous_browser_stateful_readonly_planner_multimodel_benchmark.py`
- `scripts/build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet.py`
- `scripts/run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator.py`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_multimodel_benchmark.example.json`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_multimodel_benchmark_extended.example.json`

## Optional benchmark candidates

- `fourth_model`
  - intended family: Mistral Small 3.2 24B Instruct 2506
  - quantization: `Q4_K_M`
  - local path: `models/gguf/fourth_model.gguf`
  - suggested local port: `8083`
  - role: strong non-Qwen challenger
- `fifth_model`
  - intended family: Gemma 3 27B IT
  - quantization: `Q4_K_M`
  - local path: `models/gguf/fifth_model.gguf`
  - suggested local port: `8084`
  - role: large non-Qwen and non-Mistral challenger

These are optional post-completion benchmark candidates only. No Phase 14 benchmark result is claimed for them yet.

## Packet behavior

- request layout is nested by `model_alias / scenario_id / trial_label`
- request count is `models_total x scenarios_total x trials_per_scenario`
- request/output paths remain relative
- packet generation is fixture-only and offline
- execution flags stay false:
  - `model_execution`
  - `real_browser_execution`
  - `playwright_execution`
  - `browser_opened`
- the extended example config uses 4 aliases over 5 scenarios x 3 trials = `60` packet requests

## Evaluator behavior

The evaluator keeps per-model and combined metrics separate:

- `outputs_present` vs `outputs_missing`
- `validation_accepted` vs `validation_rejected`
- `workflows_succeeded` vs `workflows_failed`
- `pass_rate_overall`
- `validation_acceptance_rate`
- deterministic `best_model_by_pass_rate`
- `fully_successful_models`
- `missing_output_models`

Missing outputs are reported as structured benchmark results, not tracebacks.

## Phase 14B first real result

### Top-level result

- `status: completed_with_failures`
- `error_code: fixture_resolution_failed`
- `models_total: 2`
- `best_model_by_pass_rate: third_model`
- `fully_successful_models: ["third_model"]`
- `missing_output_models: {}`
- `no_runtime_execution: true`
- `fixture_only: true`
- `model_execution: false`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`

This is the first real captured benchmark result for the optional Phase 14 comparison layer. It shows a clear separation between the stronger final planner candidate and the weaker baseline without changing prompts or relaxing the evaluator.

### Per-model metrics

#### `second_model`

- `model_path: models/gguf/second_model.gguf`
- `outputs_total: 15`
- `outputs_present: 15`
- `outputs_missing: 0`
- `outputs_ingested: 12`
- `outputs_rejected: 3`
- `validation_accepted: 12`
- `validation_rejected: 3`
- `workflows_succeeded: 0`
- `workflows_failed: 15`
- `pass_rate_overall: 0.0`
- `validation_acceptance_rate: 0.8`
- `finish_reason_counts: {"stop": 15}`
- `failure_class_counts: {"model_failed_task": 15}`

#### `third_model`

- `model_path: models/gguf/third_model.gguf`
- `outputs_total: 15`
- `outputs_present: 15`
- `outputs_missing: 0`
- `outputs_ingested: 15`
- `outputs_rejected: 0`
- `validation_accepted: 15`
- `validation_rejected: 0`
- `workflows_succeeded: 15`
- `workflows_failed: 0`
- `pass_rate_overall: 1.0`
- `validation_acceptance_rate: 1.0`
- `finish_reason_counts: {"stop": 15}`
- `failure_class_counts: {"none": 15}`

## Qualitative interpretation

### `second_model`

`second_model` remains a useful baseline, but this first real Phase 14B benchmark shows that it is not reliable enough for the final stateful read-only planner role.

Observed weaknesses from the captured outputs:

- it often emits schema-shaped JSON without preserving the full required route/action structure
- `stateful_approval_policy_crosscheck` outputs sometimes collapsed to a single action where the workflow expected a multi-step route
- `stateful_policy_search_marker_review` used placeholder-like fact values such as `workspace_policy_anchor` and `workspace_policy_marker` instead of visible fixture text
- `stateful_ticket_priority_digest` sometimes produced incomplete facts or wrong marker/source-step assignments
- `stateful_policy_ticket_crosscheck` was closer after previous prompt hardening, but it still did not complete the full workflow set successfully

This note is comparative only. Phase 14B does not tune prompts to make `second_model` pass, and it does not relax the evaluator.

### `third_model`

`third_model` produced the first fully successful real benchmark result for this post-completion comparison layer:

- all 15 captured outputs were present
- all 15 were validation-accepted
- all 15 workflows succeeded
- pass rate was `1.0`

That result is still controlled, fixture-only, and offline after capture. It is evidence of stronger repeated read-only planning in this bounded benchmark, not a production-readiness claim.

## Operator note

- In PowerShell, per-model summaries use the field name `alias`, not `model_alias`.
- Example inspection command:

```powershell
Get-Content artifacts\autonomous_runtime_planner_summaries\stateful_readonly_planner_multimodel_benchmark\benchmark_evaluator_summary.json -Raw |
  ConvertFrom-Json |
  Select-Object -ExpandProperty model_summaries |
  Select-Object alias, outputs_total, outputs_present, validation_accepted, workflows_succeeded, pass_rate_overall
```

- This is a docs note only. The evaluator schema is not changed here.

## Scope and limits

- optional post-completion research expansion only
- does not change the final TZ completion claim
- does not launch models from Codex
- does not execute browser actions
- does not add new real browser or Playwright evidence
- does not claim production readiness
- GGUF files are local-only artifacts and must not be committed
- generated packet/output artifacts remain operator evidence and must not be committed

## Recommended use

Use this benchmark layer when comparing repeated captured stateful planner outputs across multiple local aliases while keeping the workflow offline, fixture-backed, and read-only.

If resource pressure is high, run the larger benchmark candidates one at a time and compare them through the Phase 14 harness rather than trying to keep all local model servers active simultaneously.
