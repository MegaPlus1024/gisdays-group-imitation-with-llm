# Project Usage Appendix

## 1. Activate environment

```powershell
.\.venv\Scripts\Activate.ps1
```

The Python venv installs project dependencies. It does not add `llama-server.exe` to PATH.

## 2. Check model registry

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id first_model `
  --json
```

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id second_model `
  --json
```

## 3. Start local llama-server by model id

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId first_model
```

For the second model:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId second_model
```

Dry-run only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId first_model -DryRun
```

## 4. Run one local scenario

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py `
  --mode local `
  --model-id first_model `
  --models-config configs\evaluation_models.json `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\model_behavior\results\manual_single_run `
  --run-id manual_single_run `
  --execute-actions `
  --max-steps 5 `
  --repair-attempts 1 `
  --force
```

## 5. Run repeated trials

```powershell
.\.venv\Scripts\python.exe scripts\run_repeated_model_trials.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,second_model `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-root experiments\model_behavior\repeated_trials\manual_office_worker_n3 `
  --label manual_office_worker_n3 `
  --trials 3 `
  --max-steps 5 `
  --repair-attempts 1 `
  --execute-actions `
  --manage-server `
  --force `
  --continue-on-trial-failure
```

## 6. Run behavioral analysis for repeated trials

```powershell
.\.venv\Scripts\python.exe scripts\analyze_behavioral_trials.py `
  --trials-root experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --out-dir experiments\model_behavior\analysis\office_worker_two_model_behavioral_analysis_v1 `
  --label office_worker_two_model_behavioral_analysis_v1 `
  --force
```

## 7. Run cross-scenario comparison

```powershell
.\.venv\Scripts\python.exe scripts\compare_cross_scenario_behavior.py `
  --scenario-analysis office_worker=experiments\model_behavior\analysis\office_worker_two_model_behavioral_analysis_v1=experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --scenario-analysis developer_project_maintenance=experiments\model_behavior\analysis\developer_project_maintenance_two_model_behavioral_analysis_v1=experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --out-dir experiments\model_behavior\cross_scenario\office_worker_developer_two_model_cross_scenario_v1 `
  --label office_worker_developer_two_model_cross_scenario_v1 `
  --force
```

## 8. Run resource/capacity evaluation

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_resource_capacity.py `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,second_model `
  --repeated-trials-root office_worker=experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --repeated-trials-root developer_project_maintenance=experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --cross-scenario-analysis experiments\model_behavior\cross_scenario\office_worker_developer_two_model_cross_scenario_v1 `
  --out-dir experiments\model_behavior\resources\resource_capacity_v1 `
  --label resource_capacity_v1 `
  --target-cpu-utilization-percent 70 `
  --reserved-system-ram-mb 4096 `
  --no-probe-runtime `
  --force
```

## 9. Run current multi-agent research commands

Repeated local group trials:

```powershell
.\.venv\Scripts\python.exe scripts\run_repeated_orchestrator_executor_trials.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-root experiments\multi_agent\orchestrator_executor\repeated_local_second_to_first_group_n3_v1 `
  --label repeated_local_second_to_first_group_n3_v1 `
  --trials 3 `
  --orchestrator-model-id second_model `
  --executor-model-id first_model `
  --orchestrator-port 8081 `
  --executor-port 8082 `
  --manage-servers `
  --execute-actions `
  --continue-on-trial-failure `
  --force
```

Simple pair matrix:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_pair_matrix.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-root experiments\multi_agent\orchestrator_executor\pair_matrix_office_developer_group_n3_v1 `
  --label pair_matrix_office_developer_group_n3_v1 `
  --pairs second_model:first_model,second_model:second_model,first_model:first_model,first_model:second_model `
  --trials 3 `
  --manage-servers `
  --execute-actions `
  --continue-on-pair-failure `
  --force
```

Heavy scenario pair matrix:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_pair_matrix.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\pair_matrix_heavy_group_n3_workspace_policy_v1 `
  --label pair_matrix_heavy_group_n3_workspace_policy_v1 `
  --pairs second_model:first_model,second_model:second_model,first_model:first_model,first_model:second_model `
  --trials 3 `
  --manage-servers `
  --execute-actions `
  --continue-on-pair-failure
```

Runtime probe:

```powershell
.\.venv\Scripts\python.exe scripts\probe_orchestrator_executor_runtime.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --out-root experiments\multi_agent\orchestrator_executor\runtime_probe_candidate_pairs_v1 `
  --label runtime_probe_candidate_pairs_v1 `
  --pairs second_model:first_model,second_model:second_model `
  --scenarios simple=configs\multi_agent_scenarios\office_developer_group_basic.json,heavy=configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --trials 3 `
  --manage-servers `
  --execute-actions `
  --continue-on-pair-failure
```

GPU smoke:

```powershell
.\.venv\Scripts\python.exe scripts\run_gpu_smoke_orchestrator_executor.py `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\gpu_smoke_second_to_second_heavy_v1 `
  --pair second_model:second_model `
  --trials 1 `
  --gpu-layers all `
  --main-gpu 0 `
  --split-mode none `
  --execute-actions
```

Bounded stress v2:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_stress_probe.py `
  --models-config configs\evaluation_models.json `
  --runtime-profiles-config configs\runtime_profiles.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\bounded_stress_candidate_pairs_v2 `
  --label bounded_stress_candidate_pairs_v2 `
  --pairs second_model:second_model,second_model:first_model `
  --profiles cpu_requested_device_none,gpu_full_offload `
  --concurrency-levels 1,2 `
  --runs-per-level 2 `
  --base-port 8081 `
  --execute-actions `
  --timeout-seconds 180 `
  --continue-on-failure `
  --force `
  --skipped-concurrency-levels 4
```

## 10. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Latest reporting-step result: `731 passed` after final multi-agent report consolidation.

## 11. Artifact locations

- single scenario runs: `experiments/model_behavior/results/`
- repeated trials: `experiments/model_behavior/repeated_trials/`
- behavioral analyses: `experiments/model_behavior/analysis/`
- cross-scenario comparison: `experiments/model_behavior/cross_scenario/`
- resource/capacity: `experiments/model_behavior/resources/`
- multi-agent orchestrator/executor: `experiments/multi_agent/orchestrator_executor/`
- final reports: `reports/experiments/`
