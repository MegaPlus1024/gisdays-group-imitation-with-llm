# Local Orchestrator/Executor Proof of Concept v1

## 1. Purpose

This proof-of-concept attempt targets the final TZ gap around a group of agents and model-pair evaluation. The goal was to move beyond fake mode and verify whether `second_model` can act as the local orchestrator while `first_model` acts as the local executor model in the group runner.

## 2. Model pair

- orchestrator: `second_model` / Qwen2.5 3B Instruct Q4_K_M / `models/gguf/second_model.gguf`
- executor: `first_model` / Qwen2.5 1.5B Instruct Q4_K_M / `models/gguf/first_model.gguf`

No model files were downloaded or changed.

## 3. Runtime setup

Preferred two-server strategy was used:

| role | model | endpoint | PID |
|---|---|---|---:|
| orchestrator | `second_model.gguf` | `http://127.0.0.1:8081/v1` | 41044 |
| executor | `first_model.gguf` | `http://127.0.0.1:8082/v1` | 16116 |

Both endpoints responded to `/v1/models` before the proof command. Both processes were stopped after the attempt, and the endpoints no longer responded.

## 4. Command

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

## 5. Result

| field | value |
|---|---|
| status | failed before artifact completion |
| success | false |
| plan valid | false |
| executor actions attempted | 0 |
| validation success | 0 |
| execution success | 0 |
| pair quality score | not produced |
| main error | invalid orchestrator JSON output: unterminated string |

Exact CLI error:

```text
ERROR: orchestrator/executor group run failed: Invalid orchestrator JSON output: Unterminated string starting at: line 65 column 5 (char 2374)
```

Blocker details: `docs/ai/local_orchestrator_executor_poc_blocker.md`.

## 6. Interpretation

This attempt proves that the local runtime setup can host both target models at the same time on separate loopback ports and that the group CLI can route orchestrator and executor providers to separate base URLs.

It does not prove a complete local orchestrator/executor group run. The real orchestrator model response failed the JSON plan contract before executor calls were attempted.

## 7. Limitations

- One group step only.
- No executor model call was reached.
- Not a concurrent stress test.
- Not a GPU run.
- No final pair recommendation.
- Browser remains simulated-only.
- Office behavior remains stub/file-based.
- The next work should harden orchestrator-plan output handling before repeating the local proof.
