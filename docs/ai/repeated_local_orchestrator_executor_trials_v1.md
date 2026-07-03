# Repeated Local Orchestrator/Executor Trials v1

## 1. Purpose

The v3 local proof showed that one controlled two-endpoint group run could complete. This repeated run checks whether the same orchestrator/executor pair can repeat the same short group scenario three times without hiding failures.

This relates to the TZ target by strengthening the group-agent and orchestrator/executor-pair evidence. It is still not a stress test, GPU benchmark, production capacity test, or final model-pair recommendation.

## 2. Model pair

- orchestrator: `second_model` / Qwen2.5 3B Instruct Q4_K_M / `models/gguf/second_model.gguf`
- executor: `first_model` / Qwen2.5 1.5B Instruct Q4_K_M / `models/gguf/first_model.gguf`

## 3. Scenario

```text
office_developer_group_basic_v1
```

Scenario file:

```text
configs/multi_agent_scenarios/office_developer_group_basic.json
```

## 4. Command

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
  --max-group-steps 1 `
  --max-steps-per-agent 1 `
  --orchestrator-max-tokens 768 `
  --orchestrator-repair-attempts 1 `
  --repair-attempts 1 `
  --execute-actions `
  --continue-on-trial-failure `
  --force
```

## 5. Result

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/repeated_local_second_to_first_group_n3_v1
```

| metric | value |
|---|---:|
| attempted trials | 3 |
| completed trials | 3 |
| failed trials | 0 |
| mean pair quality score | `0.890528` |
| std pair quality score | `0.000088` |
| min pair quality score | `0.890435` |
| max pair quality score | `0.890646` |
| mean execution success rate | `1.0` |
| total errors | 0 |
| total safety violations | 0 |

All three trials produced valid plans, two executor calls, two final validation successes, and two execution successes.

Common actions:

```text
read_file: 6
```

Common action parameters:

- `read_file` on `docs/ai/model_research_metadata.md`: 3
- `read_file` on `configs/evaluation_models.json`: 3

## 6. Runtime management

The CLI started and stopped two local servers:

| role | model | port | wrapper PID | llama PID | stopped |
|---|---|---:|---:|---:|---|
| orchestrator | `second_model` | 8081 | 58868 | 16148 | yes |
| executor | `first_model` | 8082 | 9192 | 2152 | yes |

After the run, both `/v1/models` endpoints stopped responding.

## 7. Limitations

- One pair only.
- One short scenario only.
- Sequential group runner only.
- No stress/concurrency/capacity measurement.
- No GPU runtime.
- No final model recommendation.

## 8. Next step

If the next objective is model-pair selection, compare additional orchestrator/executor pairs with the same repeated protocol. If the next objective is deployment readiness, run a measured capacity smoke separately.
