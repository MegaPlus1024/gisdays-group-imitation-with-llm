# Single Model Dry Run: qwen2_5_3b_instruct_q4_k_m

Publication note: this is a historical run document. Current repository setup exposes this second model as `second_model`; the earlier id remains here because it was recorded in the original run artifacts.

## 1. Purpose

This document records the second real local-model scenario dry run required for later model comparison under the TZ. The run uses `qwen2_5_3b_instruct_q4_k_m` through local `llama-server`, captures raw model outputs, parse/validation/execution records, history/errors, resource metadata, and behavioral evaluation.

The comparable first-model artifact is:

`experiments/model_behavior/results/office_worker_first_model_run_002_repair_v1`

The second-model artifact is:

`experiments/model_behavior/results/office_worker_qwen2_5_3b_run_001_repair_v1`

## 2. Protocol

The protocol matches the `first_model` repair-policy dry run:

| Protocol item | Value |
|---|---|
| scenario | `configs/evaluation_scenarios/office_worker_basic_session.json` |
| scenario_id | `office_worker_basic_session_v1` |
| agent_id | `office_agent_1` |
| role | `office_worker` from `configs/roles/office_worker.example.json` |
| activity profile | `configs/activity_profiles/office_worker.json` |
| script registry | `configs/script_registry.example.json` |
| max_steps | 5 |
| mode | `local` |
| execute actions | true |
| repair attempts | 1 |
| write safety policy | write actions must target the experiment `workspace/` folder |
| evaluator | `normal_activity_trajectory_evaluator_v1` |

No scenario, role, activity profile, script registry, prompt contract, repair policy, safety policy, evaluator, `max_steps`, execute-actions mode, or artifact schema was intentionally changed between model runs.

## 3. Commands

Python/venv preflight:

```powershell
.\.venv\Scripts\python.exe --version
```

Result:

```text
Python 3.12.10
```

Model preflight:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id qwen2_5_3b_instruct_q4_k_m `
  --json
```

Result: preflight `pass`, `can_attempt_local_run: true`, resolved model path `models\gguf\second_model.gguf`.

llama-server dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId qwen2_5_3b_instruct_q4_k_m `
  -DryRun
```

Result: wrapper resolved `llama-server.exe`, model path, host/port, and command without starting the server.

Runtime endpoint check:

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8080/v1/models' -UseBasicParsing -TimeoutSec 3
```

Result before startup: endpoint was not ready.

Server start:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId qwen2_5_3b_instruct_q4_k_m
```

The server was started by Codex in a managed PowerShell process. The `/v1/models` endpoint returned `second_model.gguf`.

Scenario run:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py `
  --mode local `
  --model-id qwen2_5_3b_instruct_q4_k_m `
  --models-config configs\evaluation_models.json `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\model_behavior\results\office_worker_qwen2_5_3b_run_001_repair_v1 `
  --run-id office_worker_qwen2_5_3b_run_001_repair_v1 `
  --execute-actions `
  --max-steps 5 `
  --repair-attempts 1 `
  --force
```

Result:

```text
status: stopped
success: False
steps: 2
stopped_reason: Reached max_consecutive_failures limit.
```

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_experiment_scenario_runner.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_models.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Results:

```text
16 passed
10 passed
593 passed
```

## 4. Runtime

| Field | Value |
|---|---|
| model_id | `qwen2_5_3b_instruct_q4_k_m` |
| model_name | `qwen2.5-3b-instruct-q4_k_m.gguf` |
| gguf_path | `models/gguf/second_model.gguf` |
| resolved model path | `C:\Users\m\Documents\local-llm-test-gisdays\local-llm-agent-lab\models\gguf\second_model.gguf` |
| base_url | `http://127.0.0.1:8080/v1` |
| ctx_size | 4096 |
| runtime | `llama.cpp / llama-server` |
| server path | `C:\Users\m\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe` |
| wrapper PID | 14060 |
| llama-server PID | 25584 |
| server ownership | started by Codex for this run |
| server stopped | yes, only Codex-started PIDs were stopped |

## 5. Scenario

| Field | Value |
|---|---|
| scenario path | `configs/evaluation_scenarios/office_worker_basic_session.json` |
| role template | `configs/roles/office_worker.example.json` |
| activity profile | `configs/activity_profiles/office_worker.json` |
| expected families | `file`, `office` |
| max_steps | 5 |
| execute_actions | true |
| repair_attempts | 1 |
| write workspace | `experiments/model_behavior/results/office_worker_qwen2_5_3b_run_001_repair_v1/workspace/` |

Write actions are rejected unless their path is inside the experiment workspace. Read actions were allowed to read safe project files according to the registry and role constraints.

## 6. Results

| Metric | Value |
|---|---:|
| status | `stopped` |
| success | false |
| steps attempted | 2 |
| initial_parse_success_count | 2 |
| initial_validation_accept_count | 2 |
| repair_attempt_count | 0 |
| repair_validation_accept_count | 0 |
| final_validation_accept_count | 2 |
| execution_attempted_count | 2 |
| execution_success_count | 0 |
| unrecovered_failure_count | 2 |
| stop_reason | `Reached max_consecutive_failures limit.` |
| normal_activity_score | 0.0 |
| diversity_score | 0.5 |
| repetition_score | 0.725 |
| sequence_coherence_score | 0.0 |
| history_usage_score | 1.0 |
| role_fit_score | 1.0 |
| average_selection_latency_ms | 566.875 |
| average_total_step_latency_ms | 567.584 |
| wall_time_ms | 1147.515 |

The model returned valid JSON and registry-valid actions on the first attempt in both steps. Repair was enabled but not used because there was no parse or validation failure. Both actions failed during execution because `docs/notes.txt` was not found.

## 7. Selected Actions

| step | initial action | initial accepted | repair attempted | final action | final parameters | executed | success | error type | summary |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | `read_file` | yes | no | `read_file` | `{"path": "docs/notes.txt"}` | yes | no | `file_not_found` | The model tried to read `docs/notes.txt`, which does not exist. |
| 2 | `read_file` | yes | no | `read_file` | `{"path": "docs/notes.txt"}` | yes | no | `file_not_found` | The model repeated the same missing file after the first failure. |

## 8. Observed Failures

| Failure type | Observed |
|---|---|
| malformed JSON | no |
| missing parameters | no |
| unknown action | no |
| role violation | no |
| unsafe path | no |
| validation failure | no |
| execution error | yes, `file_not_found` |
| timeout | no |
| repeated action behavior | yes, repeated `read_file docs/notes.txt` |

The run stopped because the stop criteria reached `max_consecutive_failures` after two execution failures.

## 9. Interpretation

This run proves:

- `qwen2_5_3b_instruct_q4_k_m` can be launched through the same local runtime path and queried by `ExperimentScenarioRunner` local mode.
- The model produced parseable `NextAction` JSON on both steps.
- Registry validation and role compliance passed on both steps.
- Execution artifacts, errors, activity evaluation, resource summary, raw outputs, and replay command were saved.
- The replay command now explicitly includes `--execute-actions`.

This run does not prove:

- Successful autonomous task completion.
- Good normal activity quality, because both selected actions failed at execution.
- Multi-agent readiness.
- Capacity or benchmark results.
- Browser, mail, git, or external network behavior.

Comparison readiness against `first_model`:

- Both artifacts use the same scenario, max step limit, repair policy, execute-actions mode, safety policy, registry, and evaluator.
- Both artifacts contain `attempts.jsonl`, `validation_results.jsonl`, `execution_results.jsonl`, `activity_evaluation.json`, `model_behavior_result.json`, and `resource_summary.json`.
- The observed failure mode differs: `first_model` needed repair for missing parameters and later hit write-workspace safety; the 3B model produced valid read actions but repeatedly targeted a missing file.

## 10. Next Step

Run a two-model behavior comparison using:

- `experiments/model_behavior/results/office_worker_first_model_run_002_repair_v1`
- `experiments/model_behavior/results/office_worker_qwen2_5_3b_run_001_repair_v1`

The comparison should report first-attempt validity, final validity after repair, execution success, repeated action behavior, normal activity score, role compliance, diversity, repetition, sequence coherence, history usage, and latency/resource metadata.
