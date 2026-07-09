# Phase 12E2 Repeated Hard Trials Variance Evidence

## Scope

- manual `second_model` and `third_model` repeated hard-trial runs
- compact prompt profile only
- captured output ingestion plus offline variance evaluation
- fixture replay only
- no Codex-launched model calls
- no real browser execution

## Evidence summary

- operator ran all 18 repeated hard trials
- `third_model`: 9/9 passed, stable plan true
- `second_model`: 6/9 passed, approval scenario failed 3/3 with `missing_expected_text`
- top-level evaluator status: `completed_with_failures`
- outputs_total: `18`
- outputs_present: `18`
- outputs_missing: `0`
- outputs_ingested: `15`
- outputs_rejected: `3`
- dry_runs_succeeded: `18`
- dry_runs_failed: `0`
- fixture_runs_succeeded: `15`
- fixture_runs_failed: `3`
- actions_attempted_total: `63`
- actions_succeeded_total: `63`
- actions_failed_total: `0`
- expected_results_total: `78`
- expected_results_passed_total: `63`
- expected_results_failed_total: `15`
- finish_reason: `stop` for all trials
- model_execution: `false`
- real_browser_execution: `false`
- playwright_execution: `false`
- browser_opened: `false`

## Corrected evaluator evidence

- commit `773a49c` fixed the variance evaluator pass-rate semantics and added the `scenario_summaries` alias.
- corrected evaluator output was produced by rerunning the existing 18 variance outputs with `--execute-fixture` only.
- corrected pass rates:
  - `second_model` `pass_rate_fixture`: `0.667`
  - `second_model` `pass_rate_validation`: `1.0`
  - `third_model` `pass_rate_fixture`: `1.0`
  - `third_model` `pass_rate_validation`: `1.0`
- scenario-level outcome:
  - `second_model` `hard_policy_disambiguation`: `3/3` fixture succeeded, `stable_plan` true
  - `second_model` `hard_ticket_priority_crosscheck`: `3/3` fixture succeeded, `stable_plan` true
  - `second_model` `hard_approval_policy_match`: `0/3` fixture succeeded, `3/3` failed, `missing_expected_text`, `stable_plan` false
  - `third_model` `hard_policy_disambiguation`: `3/3` fixture succeeded, `stable_plan` true
  - `third_model` `hard_ticket_priority_crosscheck`: `3/3` fixture succeeded, `stable_plan` true
  - `third_model` `hard_approval_policy_match`: `3/3` fixture succeeded, `stable_plan` true
- this closes Phase 12E evidence collection unless more trials are explicitly requested.

## What this proves

- repeated captured planner outputs can be ingested, validated, dry-run accepted, and replayed offline
- `third_model` is materially more stable than `second_model` under the calibrated hard-trial harness
- the variance packet now clearly distinguishes model stability without any live browser or model execution by Codex

## What this does not prove

- not production browser automation
- not a live autonomous LLM loop
- not real browser execution
- not guarded Playwright evidence for this packet
- not a recommendation to change the approval prompt here
- not a production recommendation

## Relation to prior evidence

- Phase 12D established the calibrated hard discrimination packet.
- Phase 12E1 added the repeated hard-trials variance scaffolding.
- Phase 12E2 records the first repeated-trial evidence that clearly differentiates `third_model` stability from `second_model` on the calibrated hard packet.
- The evidence remains offline fixture replay only and manual operator model-call only.
