# Consolidated Behavioral Analysis v1

Publication note: historical artifact ids are preserved. Current user-facing setup uses `second_model` for the second local model.

## Purpose

This report-facing analysis converts repeated-trials artifacts into behavioral conclusions required by the TZ: action quality, role compliance, coherence, diversity, repetition/template behavior, execution failures, model limitations, and latency/resource observations.

No models are started for this step. No new trials are run.

## Input Artifacts

Repeated-trials root:

`experiments/model_behavior/repeated_trials/office_worker_two_model_repair_n3_v1`

Models:

- `first_model`
- `qwen2_5_3b_instruct_q4_k_m`

## Methodology

The analysis reads trial folders through the existing artifact loader and groups evidence into:

- role compliance;
- coherence and history usage;
- diversity and template behavior;
- failure modes;
- resource and latency observations.

The protocol remains the same as the repeated-trials run: same scenario, role/profile, registry, evaluator, repair policy, execute-actions mode, and safety policy.

## Summary Table

| Model | Behavioral profile |
|---|---|
| `first_model` | Repair-dependent, poor first-attempt validity, but capable of executing repaired read actions. Shows narrow repeated behavior and weak history/coherence. |
| `qwen2_5_3b_instruct_q4_k_m` | Strong contract validity and lower latency, but repeatedly targets missing `docs/notes.txt`, resulting in zero execution success. |

## Role Compliance Analysis

Both models primarily selected file actions, which are compatible with the office-worker scenario. No shell-heavy behavior was observed. `first_model` triggered workspace safety failures when trying to write outside the experiment workspace; this is a safety failure, not a fabricated role violation. `qwen2_5_3b_instruct_q4_k_m` repeatedly read a missing file, which is poor environment awareness but not itself a role-template violation.

## Coherence And History Usage Analysis

`first_model` repeatedly recovered to `read_file docs/ai/model_registry.md` but did not show meaningful history use. `qwen2_5_3b_instruct_q4_k_m` showed apparent history usage in reasons, but repeated the same failed `docs/notes.txt` action, so history mention did not become useful adaptation.

## Diversity And Template Behavior Analysis

Both models show template-like behavior in this scenario. The dominant repeated action is `read_file`; the dominant parameters differ by model:

- `first_model`: `docs/ai/model_registry.md`;
- `qwen2_5_3b_instruct_q4_k_m`: `docs/notes.txt`.

This indicates low action-family diversity and repeated same-parameter patterns.

## Failure Mode Analysis

`first_model`:

- recurring missing required parameter on initial attempts;
- repair recovers two actions per trial;
- final unrecovered failure is `write_path_outside_workspace`;
- stop reason repeats as `validation_failed_after_repair`.

`qwen2_5_3b_instruct_q4_k_m`:

- JSON/action contract is valid from first attempt;
- execution repeatedly fails with `file_not_found`;
- stop reason repeats as `Reached max_consecutive_failures limit.`

## Resource/Latency Interpretation

The 3B model is faster in the observed repeated trials by mean selection latency. These are lightweight per-run observations and must not be interpreted as CPU-only capacity or benchmark results.

## Limitations

- One scenario only.
- Three trials per model only.
- No multi-agent run.
- No benchmark or capacity estimate.
- Browser is simulated-only.
- Office activity is stub/file-based.
- Results should not be used as final model recommendation.

## Next Step

Add at least one more scenario, preferably developer project maintenance or student research/report generation, then run N=3 or N=5 per model with the same protocol and compute cross-scenario aggregates.

## Second Scenario Follow-Up

The developer project maintenance scenario has been run as the second behavioral evidence point:

`docs/ai/developer_project_maintenance_trials_v1.md`

Artifacts:

- repeated trials: `experiments/model_behavior/repeated_trials/developer_project_maintenance_two_model_repair_n3_v1`
- consolidated analysis: `experiments/model_behavior/analysis/developer_project_maintenance_two_model_behavioral_analysis_v1`

This follow-up should be used together with the office-worker analysis for the next cross-scenario aggregate comparison.

## Cross-Scenario Analysis Follow-Up

The office-worker and developer-maintenance behavioral analyses have been combined into:

`experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1`

Report-facing document:

`docs/ai/cross_scenario_behavioral_analysis_v1.md`

The cross-scenario result keeps the recommendation status at `not_ready_for_final_recommendation`: it is enough to compare behavioral tendencies across two scenarios, but it still lacks resource/capacity evaluation and multi-agent capacity evidence.
