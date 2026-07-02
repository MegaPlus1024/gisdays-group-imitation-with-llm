# Repeated Trials Comparison

- comparison_id: `fake_repeated_trials_smoke`
- protocol_compatible: `True`
- status: `complete`
- confidence: `low`

## Aggregate Metrics

| model_id | trials | failed | mean initial validity | mean final validity | mean execution success | mean normal score | mean selection latency ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `first_model` | 2 | 0 | 1.0 | 1.0 | 1.0 | 0.595 | 0.107 |
| `qwen2_5_3b_instruct_q4_k_m` | 2 | 0 | 1.0 | 1.0 | 1.0 | 0.595 | 0.076 |

## Metric Winners

| metric | winner | first | second |
|---|---|---:|---:|
| mean_first_attempt_validity | `tie` | 1.0 | 1.0 |
| mean_final_validity | `tie` | 1.0 | 1.0 |
| mean_execution_success | `tie` | 1.0 | 1.0 |
| mean_normal_activity | `tie` | 0.595 | 0.595 |
| mean_diversity | `tie` | 0.5 | 0.5 |
| mean_repetition | `tie` | 0.725 | 0.725 |
| mean_history_usage | `tie` | 0.0 | 0.0 |
| mean_selection_latency | `second` | 0.107 | 0.076 |
| mean_total_step_latency | `second` | 0.7765 | 0.6765 |
| stability_execution_success_std | `tie` | 0.0 | 0.0 |
| fewer_recurring_execution_failures | `tie` | 0 | 0 |

## Failure Modes

### `first_model`

- common_failure_modes: `{}`
- most_common_actions: `[{'action': 'read_file', 'count': 4}]`
- most_common_action_parameters: `[{'action_parameters': '{"action": "read_file", "parameters": {"path": "docs/ai/model_registry.md"}}', 'count': 4}]`

### `qwen2_5_3b_instruct_q4_k_m`

- common_failure_modes: `{}`
- most_common_actions: `[{'action': 'read_file', 'count': 4}]`
- most_common_action_parameters: `[{'action_parameters': '{"action": "read_file", "parameters": {"path": "docs/ai/model_registry.md"}}', 'count': 4}]`

## Limitations

- Only one scenario is repeated.
- Three trials per model is a small sample.
- No multi-agent run is included.
- Browser behavior remains simulated-only and office behavior remains stub/file-based.
- Resource metrics are lightweight scenario-run metadata, not a benchmark monitor.
