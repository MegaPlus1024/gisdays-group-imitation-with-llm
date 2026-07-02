# Two-Model Behavior Comparison

## Executive Summary

The artifacts are protocol-compatible and support a cautious first comparison. first_model showed weaker first-attempt action validity but recovered through repair and executed two actions. qwen2_5_3b_instruct_q4_k_m showed stronger first-attempt validity and lower latency, but repeated a missing-file read and achieved zero successful executions. No overall winner should be declared from one short scenario.

- protocol_compatible: `true`
- confidence: `low`

## Protocol

| Check | first | second | compatible |
|---|---|---|---|
| scenario_path | `configs\evaluation_scenarios\office_worker_basic_session.json` | `configs\evaluation_scenarios\office_worker_basic_session.json` | `True` |
| max_steps | `5` | `5` | `True` |
| repair_enabled | `True` | `True` | `True` |
| repair_attempts_per_step | `1` | `1` | `True` |
| execute_actions | `True` | `True` | `True` |
| activity_profile | `office_worker_normal_activity_v1` | `office_worker_normal_activity_v1` | `True` |
| evaluator | `normal_activity_trajectory_evaluator_v1` | `normal_activity_trajectory_evaluator_v1` | `True` |

## Metrics

| Metric | first | second |
|---|---:|---:|
| model_id | `first_model` | `qwen2_5_3b_instruct_q4_k_m` |
| step_count | `3` | `2` |
| initial_validation_accept_rate | `0.0` | `1.0` |
| final_validation_accept_rate | `0.666667` | `1.0` |
| execution_success_rate | `1.0` | `0.0` |
| normal_activity_score | `0.43` | `0.0` |
| diversity_score | `0.75` | `0.5` |
| repetition_score | `0.7250000000000001` | `0.7250000000000001` |
| history_usage_score | `0.0` | `1.0` |
| average_selection_latency_ms | `728.402` | `566.875` |
| average_total_step_latency_ms | `729.737` | `567.583` |
| stop_reason | `validation_failed_after_repair` | `Reached max_consecutive_failures limit.` |

## Action Trajectories

### first: `first_model`

| Step | Action |
|---:|---|
| 1 | `read_file` |
| 2 | `read_file` |

### second: `qwen2_5_3b_instruct_q4_k_m`

| Step | Action |
|---:|---|
| 1 | `read_file` |
| 2 | `read_file` |

## Metric Winners

| Metric | Winner | first | second |
|---|---|---:|---:|
| first_attempt_validation | `second` | 0.0 | 1.0 |
| final_validation_after_repair | `second` | 0.666667 | 1.0 |
| successful_executions | `first` | 2 | 0 |
| fewer_unrecovered_failures | `first` | 1 | 2 |
| normal_activity_score | `first` | 0.43 | 0.0 |
| diversity_score | `first` | 0.75 | 0.5 |
| repetition_score | `tie` | 0.7250000000000001 | 0.7250000000000001 |
| history_usage_score | `second` | 0.0 | 1.0 |
| average_selection_latency_ms | `second` | 728.402 | 566.875 |
| average_total_step_latency_ms | `second` | 729.737 | 567.583 |
| execution_stability | `first` | 1.0 | 0.0 |

## Failure Analysis

| Model side | Failure summary | Error types | Validation issue codes |
|---|---|---|---|
| first `first_model` | Validation/safety failure: write action targeted a path outside the experiment workspace. | `{'validation_failed_after_repair': 1}` | `{'write_path_outside_workspace': 3, 'missing_required_parameter': 2}` |
| second `qwen2_5_3b_instruct_q4_k_m` | Execution failure: model repeatedly targeted a missing file. | `{'file_not_found': 2}` | `{}` |

Shared weaknesses:
- Both runs have low sequence coherence.
- Neither run completed the full five-step trajectory.
- Both runs show repeated same-parameter behavior.

## Limitations

- Only one short scenario was compared.
- Only one run per model is available.
- No repeated trials or statistical confidence interval were computed.
- No benchmark or multi-agent capacity measurement was run.
- Browser behavior remains simulated-only and office behavior remains stub/file-based.
- Resource summaries are lightweight process snapshots, not a benchmark monitor.

## Next Steps

- Repeat the same scenario multiple times per model.
- Add a broader role/coherence/diversity report over these artifacts.
- Add resource/capacity estimates only after repeated real local runs.
