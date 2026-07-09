# Phase 12C Model Comparison Baseline

## Scope

- operator-run comparison packet for `second_model` and `third_model`
- compact browser-planner prompts
- captured output ingestion
- offline fixture replay
- baseline comparison only, not a winner declaration

## Evidence summary

- schema_version: `autonomous_browser_model_comparison_evaluator_summary_v1`
- status: `completed_with_missing_outputs`
- error_code: `missing_captured_outputs`
- models_total: `3`
- outputs_total: `9`
- outputs_present: `6`
- outputs_missing: `3`
- outputs_ingested: `6`
- outputs_rejected: `0`
- dry_runs_succeeded: `6`
- fixture_runs_succeeded: `6`
- actions_attempted_total: `28`
- actions_succeeded_total: `28`
- actions_failed_total: `0`
- expected_results_passed_total: `28`
- expected_results_failed_total: `0`
- real_browser_execution: `false`
- playwright_execution: `false`
- browser_opened: `false`
- model_execution during evaluator: `false`

### Model breakdown

#### first_model

- outputs_present: `0`
- outputs_missing: `3`
- not part of the active comparison baseline

#### second_model

- outputs_present: `3`
- outputs_ingested: `3`
- outputs_rejected: `0`
- dry_runs_succeeded: `3`
- fixture_runs_succeeded: `3`
- actions_succeeded_total: `14`
- actions_failed_total: `0`
- expected_results_passed_total: `14`
- expected_results_failed_total: `0`
- finish_reason: `stop` for all 3 outputs

#### third_model

- outputs_present: `3`
- outputs_ingested: `3`
- outputs_rejected: `0`
- dry_runs_succeeded: `3`
- fixture_runs_succeeded: `3`
- actions_succeeded_total: `14`
- actions_failed_total: `0`
- expected_results_passed_total: `14`
- expected_results_failed_total: `0`
- finish_reason: `stop` for all 3 outputs

## Per-scenario token comparison

### policy_family

- second_model: prompt_tokens `310`, completion_tokens `185`, total_tokens `495`
- third_model: prompt_tokens `314`, completion_tokens `188`, total_tokens `502`

### ticket_triage

- second_model: prompt_tokens `443`, completion_tokens `238`, total_tokens `681`
- third_model: prompt_tokens `447`, completion_tokens `243`, total_tokens `690`

### approval_review

- second_model: prompt_tokens `554`, completion_tokens `350`, total_tokens `904`
- third_model: prompt_tokens `558`, completion_tokens `354`, total_tokens `912`

## What this proves

- `second_model` and `third_model` tie on the current compact controlled prompts.
- both models achieve 3/3 ingestion, 3/3 validation/dry-run, 3/3 fixture replay, and 14/14 expected checks.
- `third_model` is compatible and stable in the current harness.
- the evaluator remained offline and did not open a real browser.

## What this does not prove

- not that `third_model` is better than `second_model`
- not a production recommendation
- not real browser execution
- not guarded Playwright execution for these model outputs
- not an autonomous live LLM loop
- not broad scenario discrimination
- not a claim that the current packet is sufficiently hard to rank models reliably
- only compact prompts and one controlled comparison packet

## Conclusion

This packet is non-discriminating for model quality on the current compact tasks. The functional outcome is a tie between `second_model` and `third_model`, so more complex prompts, repeated trials, or less compressed planning tasks are needed before preferring `third_model` as the default planner.

## Relation to prior evidence

- Phase 12B records the first successful `third_model` planner-output evidence in `docs/status/phase_12_third_model_initial_evidence.md`.
- Phase 12C adds the baseline comparison over `second_model` and `third_model` using the same harness.
- Phase 9 remains the separate guarded Playwright/Chromium local-fixture evidence line.

