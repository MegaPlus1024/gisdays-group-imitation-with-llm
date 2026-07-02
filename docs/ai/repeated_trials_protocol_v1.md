# Repeated Trials Protocol v1

## 1. Purpose

Repeated trials are required for TZ-level model comparison because a single short scenario run cannot show repeatability, stability, or recurring failure modes. This protocol repeats the same scenario under the same runner, repair policy, registry, evaluator, and safety policy for each model.

## 2. Protocol

| Field | Value |
|---|---|
| scenario | `configs\evaluation_scenarios\office_worker_basic_session.json` |
| models | `first_model`, `qwen2_5_3b_instruct_q4_k_m` |
| mode | `local` for real trials, `fake` for offline smoke |
| execute actions | true |
| max_steps | 5 |
| repair attempts | 1 |
| model registry | `configs\evaluation_models.json` |
| safety policy | write actions restricted to each trial workspace |
| evaluator | same activity evaluator used by `run_agent_scenario.py` |

The protocol does not change the scenario, role/profile, prompt contract, script registry, evaluator, repair policy, or safety policy between models.

## 3. Commands

Offline tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_repeated_model_trials.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_model_behavior_comparison.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_experiment_scenario_runner.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_models.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Fake smoke:

```powershell
.\.venv\Scripts\python.exe scripts\run_repeated_model_trials.py `
  --mode fake `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,qwen2_5_3b_instruct_q4_k_m `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-root experiments\scenario_runs\fake_repeated_trials_smoke `
  --label fake_repeated_trials_smoke `
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
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-root experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --label office_worker_two_model_repair_n3_v1 `
  --trials 3 `
  --max-steps 5 `
  --repair-attempts 1 `
  --execute-actions `
  --manage-server `
  --force `
  --continue-on-trial-failure
```

## 4. Artifact Layout

Each trial is a normal `run_agent_scenario.py` artifact folder:

```text
experiments/model_behavior/repeated_trials/<label>/runs/<model_id>/trial_001/
experiments/model_behavior/repeated_trials/<label>/runs/<model_id>/trial_002/
experiments/model_behavior/repeated_trials/<label>/runs/<model_id>/trial_003/
```

Root aggregate artifacts:

```text
trial_index.json
trial_index.csv
aggregate_metrics.json
aggregate_metrics.csv
failure_modes.json
repeated_trials_comparison.json
repeated_trials_comparison.md
README.md
replay_commands.ps1
```

## 5. Metrics

Per-trial and aggregate metrics include:

- first-attempt JSON/NextAction validity;
- final validity after repair;
- repair attempt count and repair success;
- execution success rate;
- normal activity score;
- diversity score;
- repetition score;
- sequence coherence score;
- history usage score;
- average selection and total step latency;
- lightweight RSS/CPU snapshots when present.

## 6. Failure Modes

Failure aggregation groups recurring error types and repeated action/parameter patterns. Examples include:

- `file_not_found`;
- `write_path_outside_workspace`;
- validation failures;
- repeated same action parameters;
- max consecutive failures.

## 7. Interpretation Rules

Repeated trials are stronger than one run, but three trials on one scenario are still not enough for a final model recommendation. Interpret results as directional evidence:

- report metric winners;
- report stability through mean/std;
- report recurring failure modes;
- avoid declaring a final configuration until additional scenarios and repeated runs are available.

## 8. Limitations

- No multi-agent run.
- One scenario only.
- Browser remains simulated-only.
- Office behavior remains stub/file-based.
- Resource sampling is lightweight and not a benchmark monitor.
- No external network behavior is exercised.

## 9. Follow-up Behavioral Analysis

After repeated trials are complete, build the consolidated behavioral analysis without starting models:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_behavioral_trials.py `
  --trials-root experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --out-dir experiments\model_behavior\analysis\office_worker_two_model_behavioral_analysis_v1 `
  --label office_worker_two_model_behavioral_analysis_v1 `
  --force
```

This analysis reads existing artifacts only and reports role compliance, coherence/history usage, diversity/template behavior, failure modes, and latency/resource observations.
