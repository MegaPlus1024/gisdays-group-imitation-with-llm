# Repeated Trials Comparison

- comparison_id: `developer_project_maintenance_two_model_repair_n3_v1`
- protocol_compatible: `True`
- status: `complete`
- confidence: `low`

## Aggregate Metrics

| model_id | trials | failed | mean initial validity | mean final validity | mean execution success | mean normal score | mean selection latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `first_model` | 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 792.611333 |
| `qwen2_5_3b_instruct_q4_k_m` | 3 | 0 | 1.0 | 1.0 | 0.0 | 0.0 | 459.744667 |

## Metric Winners

| metric | winner | first | second |
|---|---|---:|---:|
| mean_first_attempt_validity | `second` | 0.0 | 1.0 |
| mean_final_validity | `second` | 0.0 | 1.0 |
| mean_execution_success | `tie` | 0.0 | 0.0 |
| mean_normal_activity | `tie` | 0.0 | 0.0 |
| mean_diversity | `tie` | 0.416667 | 0.416667 |
| mean_repetition | `tie` | 1.0 | 1.0 |
| mean_history_usage | `tie` | 0.5 | 0.5 |
| mean_selection_latency | `second` | 792.611333 | 459.744667 |
| mean_total_step_latency | `second` | 794.258667 | 460.345333 |
| stability_execution_success_std | `tie` | 0.0 | 0.0 |
| fewer_recurring_execution_failures | `tie` | 3 | 3 |

## Failure Modes

### `first_model`

- common_failure_modes: `{'validation_failed_after_repair': 3}`
- most_common_actions: `[{'action': 'create_file', 'count': 3}]`
- most_common_action_parameters: `[]`

### `qwen2_5_3b_instruct_q4_k_m`

- common_failure_modes: `{'unsafe_path': 3}`
- most_common_actions: `[{'action': 'read_file', 'count': 3}]`
- most_common_action_parameters: `[{'action_parameters': '{"action": "read_file", "parameters": {"path": "src/main.py"}}', 'count': 3}]`

## Limitations

- Only one scenario is repeated.
- Three trials per model is a small sample.
- No multi-agent run is included.
- Browser behavior remains simulated-only and office behavior remains stub/file-based.
- Resource metrics are lightweight scenario-run metadata, not a benchmark monitor.
