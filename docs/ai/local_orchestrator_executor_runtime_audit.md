# Local Orchestrator/Executor Runtime Audit

## Scope

This audit checks whether the current repository can run a controlled real local orchestrator/executor group proof with:

- orchestrator: `second_model`
- executor: `first_model`
- preferred runtime layout: two local `llama-server` processes on separate ports.

No model download, GGUF change, benchmark, stress test, external network run, or production scheduler work is included.

## Files inspected

- `configs/evaluation_models.json`
- `src/agent/evaluation_models.py`
- `scripts/start_llama_server.ps1`
- `scripts/check_evaluation_model.py`
- `scripts/run_orchestrator_executor_group.py`
- `src/agent/orchestrator_executor_pipeline.py`
- `src/agent/llm_client.py`

## Audit answers

| Question | Answer | Evidence / note |
|---|---|---|
| Does `configs/evaluation_models.json` allow distinct `base_url` per model? | Yes, structurally. | Each model entry has its own `base_url`. Current checked-in values both default to `http://127.0.0.1:8080/v1`, so per-run overrides are safer than editing registry values for a proof. |
| Does `start_llama_server.ps1` support custom port? | Yes. | It exposes `-Port`, defaults to `8080`, prints `Host/port`, and passes `--port $Port` to `llama-server`. |
| Does `start_llama_server.ps1` support custom host? | Yes. | It exposes `-HostAddress` and alias `-Host`, then passes `--host $HostAddress`. |
| Can two `llama-server` processes run simultaneously on different ports? | Supported by script shape; runtime-dependent. | The wrapper can start the same executable with different model paths and ports. Actual success depends on available RAM/CPU and both ports being free. |
| Does `LocalLLMClient` support different `base_url` per provider? | Yes. | `LocalLLMClient` stores `base_url` per instance and builds `endpoint` from it. The group runner's local providers also store per-provider model configs. |
| Does `run_orchestrator_executor_group.py` allow distinct orchestrator/executor base URLs? | Yes after this change. | Added `--orchestrator-base-url` and `--executor-base-url`. Defaults still come from the model registry. |
| Does `run_orchestrator_executor_group.py` allow distinct orchestrator/executor model names? | Yes after this change. | Added `--orchestrator-model-name` and `--executor-model-name`. Defaults still come from the model registry. |
| Does the current local group runner assume one shared endpoint? | No after this change when overrides are provided. | Without overrides, both registry entries currently point to `8080`, so the default effective behavior remains shared endpoint. With overrides, orchestrator and executor providers receive separate URLs. |
| Is sequential model switching needed? | Not for the preferred proof if two servers start successfully. | Sequential switching remains a fallback only if two ports/processes cannot be used safely. |
| What is the safest local proof strategy on this machine? | Two short-lived local servers on separate loopback ports, one group step, one executor step per agent. | Use `second_model` on `127.0.0.1:8081`, `first_model` on `127.0.0.1:8082`, verify `/v1/models`, run max-one-step group proof, then stop only the PIDs started for this proof. |

## Preferred command shape

Start dry-run checks first:

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

If dry-run checks pass and ports are free, start two servers:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId second_model `
  -Port 8081
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId first_model `
  -Port 8082
```

Then run the local group proof with explicit endpoint overrides:

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

## Fallback

If the two-server approach fails because of port, memory, model loading, endpoint mismatch, or CLI/runtime limitation, create `docs/ai/local_orchestrator_executor_poc_blocker.md` and do not claim local proof success.

Sequential runtime switching should only be attempted if the code path can preserve a real orchestrator output and then run real executor calls cleanly. Fake replacement of either side is not an acceptable local proof.
