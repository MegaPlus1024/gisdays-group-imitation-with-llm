# Phase 12B Third Model Initial Evidence

## Scope

- operator-run `third_model` planner output capture
- compact local planner prompt
- captured output ingestion
- offline fixture replay
- first successful evidence for the stronger comparison candidate

## Evidence summary

- packet / evaluator path: `artifacts/autonomous_runtime_summaries/model_comparison_packet`
- schema_version: `autonomous_browser_model_comparison_evaluator_summary_v1`
- status: `completed_with_missing_outputs`
- outputs_total: `9`
- outputs_present: `3`
- outputs_missing: `6`
- outputs_ingested: `3`
- outputs_rejected: `0`
- dry_runs_succeeded: `3`
- dry_runs_failed: `0`
- fixture_runs_succeeded: `3`
- fixture_runs_failed: `0`
- actions_attempted_total: `14`
- actions_succeeded_total: `14`
- actions_failed_total: `0`
- expected_results_total: `14`
- expected_results_passed_total: `14`
- expected_results_failed_total: `0`
- model_execution: `false`
- real_browser_execution: `false`
- playwright_execution: `false`
- browser_opened: `false`
- no_runtime_execution: `true`

### Third model scenario results

- `browser_intranet_policy_research`
  - plan_id: `local_planner_policy_fixture_plan_v1`
  - actions: `3`
  - actions_attempted/succeeded/failed: `3/3/0`
  - expected_results_passed/failed/total: `3/0/3`
  - prompt_tokens: `314`
  - completion_tokens: `188`
  - total_tokens: `502`
  - finish_reason: `stop`
  - extraction_status: `accepted`
  - validation_status: `accepted`
  - dry_run_status: `accepted`
  - fixture_execution_status: `succeeded`
- `browser_ticket_triage_review`
  - actions: `4`
  - actions_attempted/succeeded/failed: `4/4/0`
  - expected_results_passed/failed/total: `4/0/4`
  - prompt_tokens: `447`
  - completion_tokens: `243`
  - total_tokens: `690`
  - finish_reason: `stop`
  - extraction_status: `accepted`
  - validation_status: `accepted`
  - dry_run_status: `accepted`
  - fixture_execution_status: `succeeded`
- `browser_approval_form_review`
  - actions: `7`
  - actions_attempted/succeeded/failed: `7/7/0`
  - expected_results_passed/failed/total: `7/0/7`
  - prompt_tokens: `558`
  - completion_tokens: `354`
  - total_tokens: `912`
  - finish_reason: `stop`
  - extraction_status: `accepted`
  - validation_status: `accepted`
  - dry_run_status: `accepted`
  - fixture_execution_status: `succeeded`

## What this proves

- `third_model` can produce a valid `autonomous_browser_plan_v1` under the compact prompt.
- captured output ingestion accepts the real operator-generated JSON.
- the validator accepts the captured plan output.
- the autonomous dry-run bridge accepts the validated plan.
- fixture-backed replay succeeds for 3 actions in the policy-family scenario and for the broader repeated-trials packet.
- 14/14 actions and 14/14 expected checks passed across the ingested third-model outputs.

## What this does not prove

- not real browser execution
- not guarded Playwright execution for the model-generated plan
- not an autonomous live LLM loop
- not production browser automation
- not general web browsing
- not a production readiness claim
- only one manually run comparison packet with three captured outputs
- only compact prompt profile
- Codex did not launch the model
- first_model and second_model outputs were absent in this capture set and are reported as missing by the evaluator
- raw runtime artifacts are ignored and were not committed

## Relation to prior evidence

- Phase 9 remains the separate guarded Playwright/Chromium local-fixture evidence line.
- Phase 10.6 remains the first single local planner output evidence line.
- Phase 10.8 remains the repeated local planner trials evidence line.
- Phase 12B adds the first successful `third_model` planner-output evidence line, still offline and replay-only.
- Phase 12C compares `second_model` and `third_model` on the same compact harness and documents the tie in `docs/status/phase_12_model_comparison_baseline.md`.
