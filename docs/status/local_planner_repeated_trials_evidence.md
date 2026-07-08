# Repeated Local Planner Trials Evidence

## Scope

- manual `second_model` repeated planner trials
- compact prompt
- captured output ingestion suite
- offline fixture replay

## Evidence summary

- model: `second_model`
- prompt profile: compact local planner prompt
- trials captured: `3`
- outputs_total: `3`
- outputs_ingested: `3`
- outputs_rejected: `0`
- dry_runs_succeeded: `3`
- dry_runs_failed: `0`
- fixture_runs_succeeded: `3`
- fixture_runs_failed: `0`
- actions_attempted_total: `9`
- actions_succeeded_total: `9`
- actions_failed_total: `0`
- expected_results_total: `9`
- expected_results_passed: `9`
- expected_results_failed: `0`
- replay_mode: `fixture_execution`
- real_browser_execution: `false`
- model_execution during ingestion: `false`
- no_runtime_execution: `true`
- suite status: `succeeded`
- suite schema_version: `autonomous_browser_planner_output_ingestion_suite_summary_v1`
- suite_id: `browser_local_planner_repeated_trials_packet_v1_ingestion_suite_v1`

This confirms that three manually captured `second_model` planner outputs were extracted, validated, dry-run accepted, and replayed through offline fixture execution successfully.

## What this proves

- repeated `second_model` outputs can conform to `autonomous_browser_plan_v1` under the compact prompt;
- the ingestion suite can process 3 captured outputs;
- the validator accepted 3/3;
- dry-run accepted 3/3;
- fixture replay succeeded 3/3;
- 9/9 actions and 9/9 expected checks passed.

## What this does not prove

- not Codex-launched model execution
- not live model-loop autonomy
- not real browser execution
- not guarded Playwright execution for a model-generated plan
- not production browser automation
- offline fixture replay only
- only one scenario family / 3 similar trials
- only compact prompt profile
- no production hardening claim

## Relation to Phase 9 and Phase 10

- Phase 9: guarded Playwright suite real browser fixture evidence.
- Phase 10.6: first single local planner output evidence in `docs/status/local_planner_output_evidence.md`.
- Phase 10.8: repeated local planner output evidence, still offline fixture replay.

