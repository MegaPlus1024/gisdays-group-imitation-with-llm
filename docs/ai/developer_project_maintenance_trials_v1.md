# Developer Project Maintenance Trials v1

## 1. Purpose

This scenario is the second behavioral evidence point required by the TZ. The previous evidence base covered `office_worker_basic_session`; this run checks whether the same two local models behave differently in a developer maintenance role with file/shell-oriented normal activity.

## 2. Scenario

| Field | Value |
|---|---|
| scenario path | `configs/evaluation_scenarios/developer_project_maintenance.json` |
| scenario_id | `developer_project_maintenance_v1` |
| role | `developer` |
| role template | `configs/roles/developer.example.json` |
| activity profile | `configs/activity_profiles/developer.json` |
| expected behavior | inspect source/docs, make small safe edits, optionally run allowlisted local tests |
| expected action families | `file`, `shell` |
| safety limits | no internet, no model download, writes constrained by experiment workspace policy |

The scenario existed before this run. It was not newly created.

One scenario limitation was observed: the scenario lists `append_file` and `list_directory`, while the developer role template `allowed_action_names` contains `create_file`, `read_file`, and `run_shell_command`. This did not block execution, but it should be reviewed before broader experiments.

## 3. Protocol

| Field | Value |
|---|---|
| models | `first_model`, `qwen2_5_3b_instruct_q4_k_m` |
| trials per model | 3 |
| mode | `local` |
| max_steps | 5 |
| repair_attempts | 1 |
| execute_actions | true |
| server management | CLI-managed `llama-server`, one model at a time |
| repeated-trials root | `experiments/model_behavior/repeated_trials/developer_project_maintenance_two_model_repair_n3_v1` |
| analysis root | `experiments/model_behavior/analysis/developer_project_maintenance_two_model_behavioral_analysis_v1` |

## 4. Commands

Preflight:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id first_model --json
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id qwen2_5_3b_instruct_q4_k_m --json
```

Fake smoke:

```powershell
.\.venv\Scripts\python.exe scripts\run_repeated_model_trials.py `
  --mode fake `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,qwen2_5_3b_instruct_q4_k_m `
  --scenario configs\evaluation_scenarios\developer_project_maintenance.json `
  --out-root experiments\scenario_runs\fake_developer_repeated_trials_smoke `
  --label fake_developer_repeated_trials_smoke `
  --trials 2 `
  --max-steps 2 `
  --repair-attempts 1 `
  --execute-actions `
  --force
```

Real repeated trials:

```powershell
.\.venv\Scripts\python.exe scripts\run_repeated_model_trials.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,qwen2_5_3b_instruct_q4_k_m `
  --scenario configs\evaluation_scenarios\developer_project_maintenance.json `
  --out-root experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --label developer_project_maintenance_two_model_repair_n3_v1 `
  --trials 3 `
  --max-steps 5 `
  --repair-attempts 1 `
  --execute-actions `
  --manage-server `
  --force `
  --continue-on-trial-failure
```

Consolidated analysis:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_behavioral_trials.py `
  --trials-root experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --out-dir experiments\model_behavior\analysis\developer_project_maintenance_two_model_behavioral_analysis_v1 `
  --label developer_project_maintenance_two_model_behavioral_analysis_v1 `
  --force
```

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_repeated_model_trials.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_consolidated_behavioral_analysis.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_scenario_v1.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_experiment_scenario_runner.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

## 5. Results Summary

| model_id | attempted_trials | completed_trials | failed_trials | mean_initial_validation_accept_rate | mean_final_validation_accept_rate | mean_execution_success_rate | mean_normal_activity_score | mean_diversity_score | mean_repetition_score | mean_history_usage_score | mean_avg_selection_latency_ms | common_failure_modes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `first_model` | 3 | 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.416667 | 1.0 | 0.5 | 792.611333 | `validation_failed_after_repair: 3` |
| `qwen2_5_3b_instruct_q4_k_m` | 3 | 3 | 0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.416667 | 1.0 | 0.5 | 459.744667 | `unsafe_path: 3` |

## 6. Behavioral Interpretation

### first_model

- Role compliance verdict: `acceptable`.
- Coherence verdict: `failed`.
- Diversity verdict: `narrow`.
- The model repeatedly selected `create_file` with `path: test_file.txt`.
- Initial and repaired attempts were rejected because the path was outside allowed roots and outside the experiment workspace.
- No actions executed successfully.
- This differs from the office-worker scenario, where repair recovered two `read_file docs/ai/model_registry.md` actions per trial.

### qwen2_5_3b_instruct_q4_k_m

- Role compliance verdict: `strong`.
- Coherence verdict: `weak`.
- Diversity verdict: `template_like`.
- The model consistently selected `read_file src/main.py`, which is developer-relevant at the model/action-selection level.
- Registry validation accepted the action, but `ScriptExecutionBridge` rejected execution as `unsafe_path`.
- No actions executed successfully.
- The model did not repeat the office-worker `docs/notes.txt` missing-file failure; its failure mode changed to a developer-relevant path blocked by execution safety.

## 7. Comparison To Office-Worker Scenario

This is not a full cross-scenario aggregate yet, but the failure patterns changed:

- `first_model` still depends on repair, but in this scenario repair did not recover the action into an executable form.
- `qwen2_5_3b_instruct_q4_k_m` still has strong initial contract validity, but its repeated failure moved from missing `docs/notes.txt` to unsafe execution of `src/main.py`.
- Developer scenario produced more role-relevant choices for the 3B model, especially source-file inspection.
- Neither model showed a successful inspect-edit-test developer loop.
- Both models remained narrow and stopped after one step per trial.

## 8. Limitations

- This is only the second scenario.
- N=3 per model remains a small sample.
- No multi-agent execution.
- No capacity estimate.
- Browser remains simulated-only.
- Office behavior remains stub/file-based.
- The `src/main.py` execution rejection suggests the read-action execution safety boundary should be reviewed before broader developer-role experiments.

## 9. Next Step

Create a cross-scenario aggregate comparison using:

- `experiments/model_behavior/analysis/office_worker_two_model_behavioral_analysis_v1`
- `experiments/model_behavior/analysis/developer_project_maintenance_two_model_behavioral_analysis_v1`

The cross-scenario report should separate contract validity, final validity after repair, execution success, role relevance, repeated failure modes, and latency.

## 10. Included In Cross-Scenario Analysis

This scenario is now included in the cross-scenario behavioral aggregate:

`experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1`

Report-facing summary:

`docs/ai/cross_scenario_behavioral_analysis_v1.md`

The cross-scenario layer compares this developer-maintenance evidence against the office-worker scenario without rerunning models or changing the protocol.
