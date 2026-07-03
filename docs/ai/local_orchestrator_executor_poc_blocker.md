# Local Orchestrator/Executor POC Blocker

## Summary

The controlled real local orchestrator/executor proof was attempted with two live local `llama-server` endpoints, but it did not complete. The orchestrator model call returned invalid/truncated JSON for the group plan, so the runner stopped before executor model calls.

This is a real blocker, not a fake success. The fake-mode MVP remains valid, but this run does not prove a complete local orchestrator/executor group pipeline yet.

## Commands attempted

Preflight checks:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id second_model `
  --json
```

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id first_model `
  --json
```

Dry-run server checks:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId second_model `
  -Port 8081 `
  -DryRun
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId first_model `
  -Port 8082 `
  -DryRun
```

Local proof command:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_group.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-dir experiments\multi_agent\orchestrator_executor\local_second_to_first_group_poc_v1 `
  --run-id local_second_to_first_group_poc_v1 `
  --orchestrator-model-id second_model `
  --executor-model-id first_model `
  --orchestrator-base-url http://127.0.0.1:8081/v1 `
  --executor-base-url http://127.0.0.1:8082/v1 `
  --max-group-steps 1 `
  --max-steps-per-agent 1 `
  --repair-attempts 1 `
  --execute-actions `
  --force
```

## Runtime evidence

Two local endpoints started and responded before the proof command:

| model role | model id | port | PID | `/v1/models` result |
|---|---|---:|---:|---|
| orchestrator | `second_model` | 8081 | 41044 | responded with `second_model.gguf` |
| executor | `first_model` | 8082 | 16116 | responded with `first_model.gguf` |

Both started processes were stopped after the failed attempt. Follow-up endpoint checks for `http://127.0.0.1:8081/v1/models` and `http://127.0.0.1:8082/v1/models` no longer responded.

## Exact failure

The local proof command exited with code `1` and printed:

```text
ERROR: orchestrator/executor group run failed: Invalid orchestrator JSON output: Unterminated string starting at: line 65 column 5 (char 2374)
```

The failure happened while parsing the orchestrator plan from the real `second_model` response. Because no valid plan existed, the runner did not attempt executor calls against `first_model`.

## Cause classification

| Category | Status |
|---|---|
| Port availability | Not the blocker. Ports 8081 and 8082 were free before startup. |
| Model file availability | Not the blocker. Both preflight checks passed and both GGUF files existed. |
| `llama-server` discovery | Not the blocker. Dry-run resolved `llama-server.exe`. |
| Endpoint readiness | Not the blocker. Both `/v1/models` endpoints responded. |
| CLI limitation | Not the blocker after this change. The runner accepted separate base URLs and model names. |
| Model loading | Not the blocker. Both endpoints served model metadata. |
| Orchestrator output contract | Blocker. The real orchestrator response was not complete valid JSON. |
| Executor model call | Not reached. No executor call was attempted because plan validation failed first. |

## Why sequential fallback was not attempted

Sequential switching would require a valid persisted orchestrator plan from the first runtime before stopping it and starting the executor runtime. This attempt did not produce a valid plan. The current runner also does not provide a clean persisted handoff artifact for failed orchestrator-plan parsing, so sequential fallback would not be a clean real proof.

## Needed next

1. Shorten the orchestrator prompt and/or increase orchestrator response budget for local mode.
2. Add explicit orchestrator-plan repair support, separate from executor `NextAction` repair.
3. Persist failed orchestrator raw output and prompt artifacts even when plan parsing fails.
4. Re-run the same two-endpoint proof after the orchestrator plan contract is hardened.

No final model-pair recommendation should be made from this blocked proof attempt.
