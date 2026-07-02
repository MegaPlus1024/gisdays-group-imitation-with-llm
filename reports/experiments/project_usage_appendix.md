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

## 9. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Latest reporting-step result: `636 passed`.

## 10. Artifact locations

- single scenario runs: `experiments/model_behavior/results/`
- repeated trials: `experiments/model_behavior/repeated_trials/`
- behavioral analyses: `experiments/model_behavior/analysis/`
- cross-scenario comparison: `experiments/model_behavior/cross_scenario/`
- resource/capacity: `experiments/model_behavior/resources/`
- final reports: `reports/experiments/`
