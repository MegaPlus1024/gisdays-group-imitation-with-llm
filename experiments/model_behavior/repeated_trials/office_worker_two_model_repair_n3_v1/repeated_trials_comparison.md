# Repeated Trials Comparison

- comparison_id: `office_worker_two_model_repair_n3_v1`
- protocol_compatible: `True`
- status: `complete`
- confidence: `low`

## Aggregate Metrics

| model_id | trials | failed | mean initial validity | mean final validity | mean execution success | mean normal score | mean selection latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `first_model` | 3 | 0 | 0.0 | 0.666667 | 1.0 | 0.43 | 714.887333 |
| `qwen2_5_3b_instruct_q4_k_m` | 3 | 0 | 1.0 | 1.0 | 0.0 | 0.0 | 518.446667 |

## Metric Winners

| metric | winner | first | second |
|---|---|---:|---:|
| mean_first_attempt_validity | `second` | 0.0 | 1.0 |
| mean_final_validity | `second` | 0.666667 | 1.0 |
| mean_execution_success | `first` | 1.0 | 0.0 |
| mean_normal_activity | `first` | 0.43 | 0.0 |
| mean_diversity | `first` | 0.75 | 0.5 |
| mean_repetition | `tie` | 0.725 | 0.725 |
| mean_history_usage | `second` | 0.0 | 1.0 |
| mean_selection_latency | `second` | 714.887333 | 518.446667 |
| mean_total_step_latency | `second` | 716.347 | 519.139667 |
| stability_execution_success_std | `tie` | 0.0 | 0.0 |
| fewer_recurring_execution_failures | `first` | 3 | 6 |

## Failure Modes

### `first_model`

- common_failure_modes: `{'validation_failed_after_repair': 3}`
- most_common_actions: `[{'action': 'read_file', 'count': 6}]`
- most_common_action_parameters: `[{'action_parameters': '{"action": "read_file", "parameters": {"path": "docs/ai/model_registry.md"}}', 'count': 6}]`

### `qwen2_5_3b_instruct_q4_k_m`

- common_failure_modes: `{'file_not_found': 6}`
- most_common_actions: `[{'action': 'read_file', 'count': 6}]`
- most_common_action_parameters: `[{'action_parameters': '{"action": "read_file", "parameters": {"path": "docs/notes.txt"}}', 'count': 6}]`

## Limitations

- Only one scenario is repeated.
- Three trials per model is a small sample.
- No multi-agent run is included.
- Browser behavior remains simulated-only and office behavior remains stub/file-based.
- Resource metrics are lightweight scenario-run metadata, not a benchmark monitor.
