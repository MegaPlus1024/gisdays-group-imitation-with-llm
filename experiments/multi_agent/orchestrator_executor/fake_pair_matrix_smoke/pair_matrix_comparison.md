# Orchestrator/Executor Pair Matrix Comparison v1

## 1. Purpose

This matrix supports the TZ goal by comparing local orchestrator/executor pair behavior for one controlled group-agent scenario. It helps select the current best observed pair for this scenario without making a final production recommendation.

## 2. Evidence base

- scenario: `configs\multi_agent_scenarios\office_developer_group_basic.json`
- mode: `fake`
- trials per pair: `2`
- models: `first_model` Qwen2.5 1.5B Instruct Q4_K_M, `second_model` Qwen2.5 3B Instruct Q4_K_M
- local endpoints are loopback llama-server endpoints when server management is enabled
- same scenario, action execution mode, repair policy, and pair quality metrics are used across pairs

## 3. Pair summary table

| pair | completed_trials | mean_pair_quality_score | std_pair_quality_score | mean_execution_success_rate | mean_final_validation_success_rate | total_errors | common_failure_modes | prototype_pair_rank_score |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `first_model->first_model` | 2 | 0.895833 | 0.0 | 1.0 | 1.0 | 0 | `{}` | 0.96353 |
| `second_model->first_model` | 2 | 0.895833 | 0.0 | 1.0 | 1.0 | 0 | `{}` | 0.963448 |

## 4. Pair ranking

The ranking uses `prototype_pair_rank_score`, a local prototype-only score: pair quality, execution success, final validation, plan validity, stability, and a lightweight latency component. It is not a final production score.

1. `first_model->first_model` - `0.96353`
2. `second_model->first_model` - `0.963448`

## 5. Failure analysis

- `second_model__first_model`: `{}`
- `first_model__first_model`: `{}`

## 6. Resource/latency notes

- `second_model__first_model`: wall_ms=`18.7525`, orchestrator_ms=`0.0605`, executor_ms=`0.01975`, server_strategy=`fake mode; no servers started`
- `first_model__first_model`: wall_ms=`2.3695`, orchestrator_ms=`0.0455`, executor_ms=`0.013`, server_strategy=`fake mode; no servers started`

## 7. Interpretation

The current best observed pair for this one scenario is `first_model->first_model`. This is directional prototype evidence only; final recommendation requires more scenarios and resource measurements.


## 8. Limitations

- Only one group scenario is included.
- N=3 per pair is directional prototype evidence, not a benchmark.
- No GPU runtime was configured or measured.
- No stress or concurrent capacity test was run.
- prototype_pair_rank_score is not a final production score.

## 9. Next step

Add a heavier multi-agent scenario, measure GPU/runtime separately, and only then update the final report with a broader recommendation.
