# Orchestrator/Executor Pair Matrix Comparison v1

## 1. Purpose

This matrix supports the TZ goal by comparing local orchestrator/executor pair behavior for one controlled group-agent scenario. It helps select the current best observed pair for this scenario without making a final production recommendation.

## 2. Evidence base

- scenario: `configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json`
- mode: `local`
- trials per pair: `3`
- models: `first_model` Qwen2.5 1.5B Instruct Q4_K_M, `second_model` Qwen2.5 3B Instruct Q4_K_M
- local endpoints are loopback llama-server endpoints when server management is enabled
- same scenario, action execution mode, repair policy, and pair quality metrics are used across pairs

## 3. Pair summary table

| pair | completed_trials | mean_pair_quality_score | std_pair_quality_score | mean_execution_success_rate | mean_final_validation_success_rate | total_errors | common_failure_modes | prototype_pair_rank_score |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `second_model->second_model` | 3 | 0.875451 | 5.6e-05 | 1.0 | 0.777778 | 6 | `{'NextActionValidationError': 6, 'NextActionJSONError': 6}` | 0.759188 |
| `second_model->first_model` | 3 | 0.820328 | 7.7e-05 | 1.0 | 0.454545 | 18 | `{'validation_failed': 18, 'write_path_outside_artifact_workspace': 18, 'HTTPStatusError': 18}` | 0.571269 |
| `first_model->first_model` | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 6 | `{'orchestrator_plan_parse_failed': 6}` | 0.0 |
| `first_model->second_model` | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 6 | `{'orchestrator_plan_parse_failed': 6}` | 0.0 |

## 4. Pair ranking

The ranking uses `prototype_pair_rank_score`, a local prototype-only score: pair quality, execution success, final validation, plan validity, stability, and a lightweight latency component. It is not a final production score.

1. `second_model->second_model` - `0.759188`
2. `second_model->first_model` - `0.571269`
3. `first_model->first_model` - `0.0`
4. `first_model->second_model` - `0.0`

## 5. Failure analysis

- `second_model__first_model`: `{'validation_failed': 18, 'write_path_outside_artifact_workspace': 18, 'HTTPStatusError': 18}`
- `second_model__second_model`: `{'NextActionValidationError': 6, 'NextActionJSONError': 6}`
- `first_model__first_model`: `{'orchestrator_plan_parse_failed': 6}`
- `first_model__second_model`: `{'orchestrator_plan_parse_failed': 6}`

## 6. Resource/latency notes

- `second_model__first_model`: wall_ms=`6804.056333`, orchestrator_ms=`1644.759333`, executor_ms=`467.207424`, server_strategy=`reused existing repeated group artifact; no servers started`
- `second_model__second_model`: wall_ms=`8776.273`, orchestrator_ms=`1659.897`, executor_ms=`788.232556`, server_strategy=`two separate llama-server endpoints for the same model on different ports`
- `first_model__first_model`: wall_ms=`2557.494333`, orchestrator_ms=`1278.335333`, executor_ms=`None`, server_strategy=`two separate llama-server endpoints for the same model on different ports`
- `first_model__second_model`: wall_ms=`2564.732333`, orchestrator_ms=`1281.9585`, executor_ms=`None`, server_strategy=`two separate llama-server endpoints on different ports`

## 7. Interpretation

The current best observed pair for this one scenario is `second_model->second_model`. This is directional prototype evidence only; final recommendation requires more scenarios and resource measurements.

- second_model -> second_model is strongest here, suggesting the stronger executor improved this scenario while likely increasing local resource cost.
- first_model -> first_model trails the larger-orchestrator baseline, supporting use of a larger orchestrator for this scenario.

## 8. Limitations

- Only one group scenario is included.
- N=3 per pair is directional prototype evidence, not a benchmark.
- No GPU runtime was configured or measured.
- No stress or concurrent capacity test was run.
- prototype_pair_rank_score is not a final production score.

## 9. Next step

Add a heavier multi-agent scenario, measure GPU/runtime separately, and only then update the final report with a broader recommendation.
