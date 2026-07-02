# Cross-Scenario Behavioral Analysis v1

## 1. Executive Summary

Across two scenarios, `qwen2_5_3b_instruct_q4_k_m` is consistently stronger on action-contract validity and latency. `first_model` is repair-dependent and only showed useful execution in the office-worker scenario. Both models remain weak on coherence and template-like behavior, so the project is not ready for a final model recommendation.

## 2. Evidence Base

- scenarios: `['office_worker', 'developer_project_maintenance']`
- models: `['first_model', 'qwen2_5_3b_instruct_q4_k_m']`
- total trajectories: `12`
- protocol: local mode, execute-actions, max_steps=5, repair_attempts=1

## 3. Cross-Scenario Metrics Table

| scenario | model | trials | initial valid | final valid | execution success | normal score | diversity | history | latency ms | failures |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `office_worker` | `first_model` | 3 | 0.0 | 0.666667 | 1.0 | 0.43 | 0.75 | 0.0 | 714.887333 | `{'validation_failed_after_repair': 3}` |
| `office_worker` | `qwen2_5_3b_instruct_q4_k_m` | 3 | 1.0 | 1.0 | 0.0 | 0.0 | 0.5 | 1.0 | 518.446667 | `{'file_not_found': 6}` |
| `developer_project_maintenance` | `first_model` | 3 | 0.0 | 0.0 | 0.0 | 0.0 | 0.416667 | 0.5 | 792.611333 | `{'validation_failed_after_repair': 3}` |
| `developer_project_maintenance` | `qwen2_5_3b_instruct_q4_k_m` | 3 | 1.0 | 1.0 | 0.0 | 0.0 | 0.416667 | 0.5 | 459.744667 | `{'unsafe_path': 3}` |

## 4. Model Profiles

### `first_model`

- profile: `['repair_dependent', 'template_like', 'scenario_sensitive']`
- stable failure patterns: `{'validation_failed_after_repair': 6}`
- scenario-specific failures: `{}`
- dominant action patterns: `[{'scenario_id': 'office_worker', 'action_parameters': '{"action": "read_file", "parameters": {"path": "docs/ai/model_registry.md"}}', 'count': 6}]`
- scenario sensitivity: `high`

### `qwen2_5_3b_instruct_q4_k_m`

- profile: `['contract_valid_but_execution_weak', 'template_like', 'scenario_sensitive']`
- stable failure patterns: `{}`
- scenario-specific failures: `{'office_worker': {'file_not_found': 6}, 'developer_project_maintenance': {'unsafe_path': 3}}`
- dominant action patterns: `[{'scenario_id': 'office_worker', 'action_parameters': '{"action": "read_file", "parameters": {"path": "docs/notes.txt"}}', 'count': 6}, {'scenario_id': 'developer_project_maintenance', 'action_parameters': '{"action": "read_file", "parameters": {"path": "src/main.py"}}', 'count': 3}]`
- scenario sensitivity: `medium`


## 5. Scenario Sensitivity

| model | verdict | key deltas | failure modes changed |
|---|---|---|---|
| `first_model` | `high` | `{'initial_validity': 0.0, 'final_validity': -0.666667, 'execution_success': -1.0, 'normal_activity': -0.43, 'diversity': -0.333333, 'repetition': 0.275, 'history_usage': 0.5, 'latency_ms': 77.724}` | `False` |
| `qwen2_5_3b_instruct_q4_k_m` | `medium` | `{'initial_validity': 0.0, 'final_validity': 0.0, 'execution_success': 0.0, 'normal_activity': 0.0, 'diversity': -0.083333, 'repetition': 0.275, 'history_usage': -0.5, 'latency_ms': -58.702}` | `True` |

## 6. Failure Pattern Analysis

- `first_model` stable: `{'validation_failed_after_repair': 6}`; scenario-specific: `{}`
- `qwen2_5_3b_instruct_q4_k_m` stable: `{}`; scenario-specific: `{'office_worker': {'file_not_found': 6}, 'developer_project_maintenance': {'unsafe_path': 3}}`

## 7. Resource/Latency Observations

- Latency winner: `qwen2_5_3b_instruct_q4_k_m` (753.749333 ms vs 489.095667 ms).
- These are per-step/per-run latency observations, not capacity measurements.

## 8. Recommendation Readiness

Recommendation readiness status: `not_ready_for_final_recommendation`

Criteria:
- `at_least_2_scenarios_completed`: `True`
- `repeated_trials_per_model`: `True`
- `behavioral_analysis`: `True`
- `resource_latency_observations`: `True`
- `full_resource_benchmark`: `False`
- `multi_agent_capacity_estimate`: `False`
- `more_than_one_role`: `True`
- `real_browser_office_automation`: `False`
- `enough_for_provisional_model_preference`: `limited`
- `enough_for_final_recommended_configuration`: `False`

Required next steps:
- Run resource/capacity evaluation.
- Resolve or explicitly document action workspace/safety mismatch for developer source-file reads.
- Add multi-agent capacity formula and measurement plan.
- Prepare final report only after resource/capacity data is available.

## 9. What This Proves

- Repeated local-model experiment infrastructure works across two scenarios.
- Artifacts support behavioral comparison across roles.
- Failure modes are measurable and differ by model/scenario.

## 10. What This Does Not Prove

- Production readiness.
- Multi-agent capacity.
- Final best model.
- Real browser/office automation.

## 11. Next Step

Run resource/capacity evaluation and define the multi-agent capacity formula.
