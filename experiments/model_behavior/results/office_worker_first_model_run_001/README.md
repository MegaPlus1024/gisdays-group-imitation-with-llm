# Experiment scenario run

## Summary

- runner: `experiment_scenario_runner_v1`
- run_id: `office_worker_first_model_run_001`
- scenario_id: `office_worker_basic_session_v1`
- mode: `local`
- execute_actions: `True`
- stopped_reason: `Latest step indicates validation failure.`

## Artifact files

- `manifest.json`
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
