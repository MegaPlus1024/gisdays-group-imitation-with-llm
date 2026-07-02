# Single Model Dry Run: first_model

## 1. Purpose

This is the first real local-model scenario dry run for the project. It verifies that a local LLM can be called through the scenario runner as an agent decision source and that the project records raw model output, parse results, validation results, history/error logs, latency/resource metadata, and behavioral evaluation.

This is not a fake/synthetic run. The action provider was `LocalModelActionProvider` and the runtime endpoint was `http://127.0.0.1:8080/v1`.

## 2. Commands

Preflight Python:

```powershell
.\.venv\Scripts\python.exe --version
```

Result: `Python 3.12.10`

Preflight model registry:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id first_model --json
```

Result: `preflight.status=pass`, `can_attempt_local_run=true`.

Dry-run server wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId first_model -DryRun
```

Result: resolved model path and server path without starting a server.

Runtime readiness check:

```powershell
.\.venv\Scripts\python.exe -c "import httpx,sys; r=httpx.get('http://127.0.0.1:8080/v1/models',timeout=10.0,trust_env=False); print(r.status_code); print(r.text[:1000]); sys.exit(0 if r.status_code == 200 else 1)"
```

Result after managed startup: `200`, model list included `first_model.gguf`.

Managed server startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId first_model
```

The server was started by Codex through a hidden PowerShell process. Server stdout/stderr were redirected into the artifact folder.

Local scenario run:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py `
  --mode local `
  --model-id first_model `
  --models-config configs\evaluation_models.json `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\model_behavior\results\office_worker_first_model_run_001 `
  --run-id office_worker_first_model_run_001 `
  --execute-actions `
  --max-steps 5 `
  --force
```

Result: `status=stopped`, `success=False`, `steps=1`, `stopped_reason=Latest step indicates validation failure.`

Tests after code changes:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_experiment_scenario_runner.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_models.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Results: `10 passed` for `test_experiment_scenario_runner.py`, `10 passed` for `test_evaluation_models.py`, and `587 passed` for full `pytest -q`.

## 3. Runtime

| Field | Value |
|---|---|
| model_id | `first_model` |
| model_name | `first_model.gguf` |
| gguf_path | `models/gguf/first_model.gguf` |
| resolved model path | `C:\Users\m\Documents\local-llm-test-gisdays\local-llm-agent-lab\models\gguf\first_model.gguf` |
| base_url | `http://127.0.0.1:8080/v1` |
| ctx_size | `4096` |
| server path | `C:\Users\m\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe` |
| wrapper PID | `29980` |
| llama-server PID | `26212` |
| server ownership | Started by Codex for this dry run |
| server stopped after run | Yes |

## 4. Scenario

| Field | Value |
|---|---|
| scenario path | `configs\evaluation_scenarios\office_worker_basic_session.json` |
| scenario id | `office_worker_basic_session_v1` |
| agent id | `office_agent_1` |
| role template | `configs/roles/office_worker.example.json` |
| activity profile | `configs/activity_profiles/office_worker.json` |
| max_steps | `5` |
| execute_actions | `true` |
| actual step count | `1` |

Safety workspace policy was enabled in the runner:

```text
experiments/model_behavior/results/office_worker_first_model_run_001/workspace/
```

Write actions are rejected unless their `path` is inside that workspace. Read actions still use the existing registry and role safety checks. Shell action allowlist was not expanded.

## 5. Results

| Metric | Value |
|---|---:|
| status | `stopped` |
| steps attempted | `1` |
| parse_success_count | `1` |
| validation_accept_count | `0` |
| execution_success_count | `0` |
| error_count | `1` |
| stop_reason | `Latest step indicates validation failure.` |
| normal_activity_score | `0.0` |
| diversity_score | `0.5` |
| repetition_score | `1.0` |
| history_usage_score | `0.5` |
| selection_latency_ms | `2731.194` |
| total_step_latency_ms | `2731.467` |
| wall_time_ms | `2742.53` |
| runner process RSS before | `38.305 MB` |
| runner process RSS after | `42.828 MB` |
| system CPU snapshot after | `7.6%` |

## 6. Selected Actions

| step | raw output valid | action | registry accepted | role compliant | executed | success | error type | summary |
|---:|---|---|---|---|---|---|---|---|
| 1 | yes | `read_file` | no | yes | no | no | `validation_failed` | Model omitted required `path` parameter. |

Raw model output:

```json
{
  "action": "read_file",
  "parameters": {},
  "reason": "Read a UTF-8 text file from an allowed project path.",
  "expected_result": "The content of the file is read and returned."
}
```

Validation issue:

```text
missing_required_parameter: Missing required parameter 'path'.
```

## 7. Observed Failures

| Failure type | Observed |
|---|---|
| malformed JSON | no |
| unknown action | no |
| role violation | no |
| unsafe path | no |
| workspace write violation | no |
| execution error | no execution attempted |
| timeout | no |
| server error | no |
| missing required parameter | yes, `read_file.path` |

## 8. Interpretation

This run proves:

- The local `first_model` runtime can be started and queried through the OpenAI-compatible endpoint.
- `ExperimentScenarioRunner` local mode can call the local model and persist real raw model output.
- The pipeline persisted model metadata, raw output, parsed `NextAction`, validation result, history/error records, resource summary, and activity evaluation.
- The validation gate correctly prevented execution of an incomplete action.
- The safety workspace policy was active for write-actions.

This run does not prove:

- Good behavioral quality for `first_model`.
- Successful autonomous task completion.
- Successful action execution, because the first model action was invalid.
- Multi-step behavior, because stop criteria halted after one validation failure.
- Model comparison, because only `first_model` was run.
- Multi-agent capacity or scheduler readiness.

## 9. Next Step

Repeat the same scenario with the second model after this first-model result is reviewed:

```powershell
.\scripts\start_llama_server.ps1 -ModelId second_model
```

Then run the same local scenario with a sibling artifact folder for two-model behavior comparison.

## 10. Follow-up Repair-Policy Dry Run

The first dry run reached the local model and captured real raw output, but stopped because the model returned:

```json
{
  "action": "read_file",
  "parameters": {}
}
```

The validator rejected this with `missing_required_parameter` for `read_file.parameters.path`.

A repair-policy run is needed to test recoverability, not to hide the original error. The repair attempt must be a second model call, must preserve the initial failure in `attempts.jsonl` and `errors.jsonl`, and must not auto-fill the missing parameter in code.

For fair model comparison, every model should be run with the same repair policy, for example `--repair-attempts 1`.

Follow-up result:

| Field | Value |
|---|---|
| artifact | `experiments/model_behavior/results/office_worker_first_model_run_002_repair_v1` |
| status | `stopped` |
| stop reason | `validation_failed_after_repair` |
| steps | 3 |
| initial parse success count | 3 |
| initial validation accept count | 0 |
| repair attempt count | 3 |
| repair validation accept count | 2 |
| final validation accept count | 2 |
| execution success count | 2 |
| unrecovered failure count | 1 |

The original `missing_required_parameter` issue was recovered on steps 1 and 2 by a second model call. The accepted repaired action was `read_file` with `parameters.path = "docs/ai/model_registry.md"`, and both executions succeeded.

The run stopped on step 3 because the model selected `create_file` targeting `docs/ai/model_registry.md`. The experiment workspace safety policy rejected this as `write_path_outside_workspace`; the repair attempt repeated the same unsafe target, so the runner stopped with `validation_failed_after_repair`. This is expected safety behavior and confirms the runner did not write into project documentation during the experiment.
