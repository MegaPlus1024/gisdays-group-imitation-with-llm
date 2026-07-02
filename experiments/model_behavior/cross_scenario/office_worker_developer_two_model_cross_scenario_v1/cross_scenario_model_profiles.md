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
