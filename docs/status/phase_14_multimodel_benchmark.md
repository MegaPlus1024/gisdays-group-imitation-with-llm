# Phase 14 Multi-model Benchmark

## Summary

Phase 14 is an optional post-completion expansion for the already completed controlled read-only prototype.

It adds a reusable multi-model benchmark packet/evaluator for the existing five stateful read-only planner scenarios. The packet prepares repeated request files for multiple configured model aliases, and the evaluator classifies captured outputs per model without launching models, browser, Playwright, Chromium, or a local server.

By default, the example benchmark config targets `second_model` and `third_model`.

## What was added

- `src/agent/autonomous_browser_stateful_readonly_planner_multimodel_benchmark.py`
- `scripts/build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet.py`
- `scripts/run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator.py`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_multimodel_benchmark.example.json`

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

## Scope and limits

- optional post-completion research expansion only
- does not change the final TZ completion claim
- does not launch models from Codex
- does not execute browser actions
- does not add new real browser or Playwright evidence
- does not claim production readiness
- generated packet/output artifacts remain operator evidence and must not be committed

## Recommended use

Use this benchmark layer when comparing repeated captured stateful planner outputs across multiple local aliases while keeping the workflow offline, fixture-backed, and read-only.
