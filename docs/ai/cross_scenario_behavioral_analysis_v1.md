# Cross-Scenario Behavioral Analysis v1

## 1. Purpose

This document summarizes the cross-scenario behavioral evidence for two local LLM models. It addresses the TZ requirement to compare local models by action selection quality, role fit, coherence, diversity, repetitive/template behavior, execution failures, and latency/resource observations across more than one role/scenario.

Primary artifact folder:

`experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1`

## 2. Inputs

| scenario | behavioral analysis | repeated trials |
|---|---|---|
| `office_worker` | `experiments/model_behavior/analysis/office_worker_two_model_behavioral_analysis_v1` | `experiments/model_behavior/repeated_trials/office_worker_two_model_repair_n3_v1` |
| `developer_project_maintenance` | `experiments/model_behavior/analysis/developer_project_maintenance_two_model_behavioral_analysis_v1` | `experiments/model_behavior/repeated_trials/developer_project_maintenance_two_model_repair_n3_v1` |

Models:

- `first_model`
- `qwen2_5_3b_instruct_q4_k_m`

Protocol:

- local mode;
- execute-actions enabled;
- `max_steps=5`;
- `repair_attempts=1`;
- N=3 trials per model per scenario;
- same runner, registry, repair policy, safety policy, and evaluator as the repeated-trials artifacts.

Total evidence base: 12 real local-model trajectories.

## 3. Cross-Scenario Summary

| model_id | scenarios | trials | mean initial validity | mean final validity | mean execution success | mean normal score | mean diversity | mean repetition | mean history usage | mean selection latency ms | scenario sensitivity |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `first_model` | 2 | 6 | 0.0 | 0.333334 | 0.5 | 0.215 | 0.583333 | 0.8625 | 0.25 | 753.749333 | `high` |
| `qwen2_5_3b_instruct_q4_k_m` | 2 | 6 | 1.0 | 1.0 | 0.0 | 0.0 | 0.458334 | 0.8625 | 0.75 | 489.095667 | `medium` |

## 4. Main Findings

- `qwen2_5_3b_instruct_q4_k_m` is consistently stronger on initial/final action-contract validity and observed latency.
- `first_model` is repair-dependent, but it achieved useful execution in the office-worker scenario; it failed to do so in the developer scenario.
- Both models show weak sequence coherence and template-like repetition.
- `first_model` has a stable failure pattern: `validation_failed_after_repair`.
- `qwen2_5_3b_instruct_q4_k_m` has stable contract validity but scenario-specific execution failures: `file_not_found` in office-worker and `unsafe_path` in developer maintenance.
- The evidence supports a provisional behavioral comparison, but not a final recommended configuration.

## 5. Metric Winners

| metric | winner |
|---|---|
| Contract validity | `qwen2_5_3b_instruct_q4_k_m` |
| Final validity after repair | `qwen2_5_3b_instruct_q4_k_m` |
| Execution success | `first_model` |
| Normal activity score | `first_model` |
| Diversity score | `first_model` |
| Lower template/repetition flag count | `first_model` |
| History usage score | `qwen2_5_3b_instruct_q4_k_m` |
| Lower selection latency | `qwen2_5_3b_instruct_q4_k_m` |
| Failure stability | `qwen2_5_3b_instruct_q4_k_m` |
| Overall evidence leader | `not_available` |

No final winner is declared because the evidence is mixed and still lacks resource/capacity and multi-agent measurements.

## 6. Stable and Scenario-Specific Failure Patterns

| model_id | stable failure patterns | scenario-specific failure patterns |
|---|---|---|
| `first_model` | `validation_failed_after_repair: 6` | none detected |
| `qwen2_5_3b_instruct_q4_k_m` | none detected | office-worker: `file_not_found: 6`; developer: `unsafe_path: 3` |

Additional aggregate counts from the generated artifact:

- `first_model`: `missing_required_parameter_count=6`, `repair_attempt_count=12`, `repair_success_count=6`, `unrecovered_failure_count=6`.
- `qwen2_5_3b_instruct_q4_k_m`: `file_not_found_count=6`, `max_consecutive_failures_count=3`, `execution_error_count=9`, `unrecovered_failure_count=9`.

## 7. Scenario Sensitivity

`first_model` is high sensitivity:

- final validity drops from 0.666667 in office-worker to 0.0 in developer maintenance;
- execution success drops from 1.0 to 0.0;
- normal activity drops from 0.43 to 0.0;
- the same broad repair-related failure pattern remains.

`qwen2_5_3b_instruct_q4_k_m` is medium sensitivity:

- initial/final validity remains 1.0 in both scenarios;
- execution success remains 0.0;
- failure mode changes from missing file to unsafe path;
- latency remains lower than `first_model` in both scenarios.

## 8. Recommendation Readiness

Status: `not_ready_for_final_recommendation`.

Satisfied evidence criteria:

- at least two scenarios completed;
- repeated trials per model;
- behavioral analysis exists;
- more than one role/scenario;
- lightweight latency observations exist.

Missing evidence:

- full resource benchmark;
- multi-agent capacity estimate;
- real browser/office automation;
- enough scenario diversity for a final recommended configuration.

Provisional findings:

- `qwen2_5_3b_instruct_q4_k_m` is the stronger model for JSON/action-contract validity and latency.
- `first_model` can produce useful execution after repair in one scenario, but is contract-weak and scenario-sensitive.
- Both models fail the stronger behavioral requirements around coherence, adaptation, and non-template activity.

## 9. Replay Command

```powershell
.\.venv\Scripts\python.exe scripts\compare_cross_scenario_behavior.py `
  --scenario-analysis office_worker=experiments\model_behavior\analysis\office_worker_two_model_behavioral_analysis_v1=experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --scenario-analysis developer_project_maintenance=experiments\model_behavior\analysis\developer_project_maintenance_two_model_behavioral_analysis_v1=experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --out-dir experiments\model_behavior\cross_scenario\office_worker_developer_two_model_cross_scenario_v1 `
  --label office_worker_developer_two_model_cross_scenario_v1 `
  --force
```

## 10. What This Proves

- The repeated local-model experiment infrastructure works across two scenarios.
- Behavioral differences between models are measurable from persisted artifacts.
- The repair policy materially affects final validity and must remain fixed for fair comparison.
- Failure modes are model- and scenario-dependent.

## 11. What This Does Not Prove

- It does not prove production readiness.
- It does not prove multi-agent capacity.
- It does not identify a final best model.
- It does not validate real browser or office automation.
- It does not provide CPU/RAM capacity estimates.

## 12. Next Step

Run resource/capacity evaluation and define the multi-agent capacity formula. After that, combine behavioral evidence with resource data in the final management report.

## 13. Resource/Capacity Follow-Up

Resource/capacity evaluation has been added as the next evidence layer:

`experiments/model_behavior/resources/resource_capacity_v1`

Report-facing document:

`docs/ai/resource_capacity_evaluation_v1.md`

Standalone formula:

`docs/ai/multi_agent_capacity_formula.md`

The resource layer provides a conservative planning estimate for concurrent local agents, but it still marks final capacity confidence as low because no true concurrent multi-agent load test was run.
