# Experiment scenario run

## Summary

- runner: `experiment_scenario_runner_v1`
- run_id: `fake_developer_repeated_trials_smoke_qwen2_5_3b_instruct_q4_k_m_trial_002`
- scenario_id: `developer_project_maintenance_v1`
- mode: `fake`
- execute_actions: `True`
- stopped_reason: `Reached max_steps limit.`

## Artifact files

- `manifest.json`
- `attempts.jsonl`
- `steps.jsonl`
- `raw_model_outputs.jsonl`
- `selected_actions.jsonl`
- `validation_results.jsonl`
- `execution_results.jsonl`
- `history.jsonl`
- `errors.jsonl`
- `activity_evaluation.json`
- `model_behavior_result.json`
- `resource_summary.json`
- `replay_commands.ps1`
- `README.md`

## Notes

Fake mode uses scripted actions and does not call `llama-server`.
Local mode is available for future dry runs but was not used to create this artifact unless `mode=local`.
