# Local Orchestrator/Executor POC v3 with Executor Repair

## 1. Purpose

This v3 proof hardens the executor stage after the v2 run reached executor calls but failed validation. It keeps the same controlled local pair:

- orchestrator: `second_model`
- executor: `first_model`

This remains a narrow local proof-of-concept, not a benchmark, stress test, GPU run, production scheduler, or final model-pair recommendation.

## 2. Changes

- Executor prompt now includes task-specific action guidance.
- `AgentState.to_prompt_context()` includes metadata, so assignment and executor hints reach the prompt.
- File path guidance now gives real safe relative examples and rejects absolute/drive-prefixed paths in the prompt.
- Executor repair is implemented for parse/validation failures when `--repair-attempts` is greater than zero.
- `per_agent_attempts.jsonl` records each initial/repair attempt with raw output, parsed action, validation result, execution result, errors, and latency.

The repair path was exercised by offline tests. In this local v3 run, repair was enabled but not needed because both initial executor actions were valid.

## 3. Runtime

| role | model | endpoint | PID |
|---|---|---|---:|
| orchestrator | `second_model.gguf` | `http://127.0.0.1:8081/v1` | 54728 |
| executor | `first_model.gguf` | `http://127.0.0.1:8082/v1` | 3052 |

Both endpoints responded to `/v1/models` before the proof run. Both started processes were stopped afterward, and both endpoints stopped responding.

## 4. Command

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_group.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-dir experiments\multi_agent\orchestrator_executor\local_second_to_first_group_poc_v3_executor_repair `
  --run-id local_second_to_first_group_poc_v3_executor_repair `
  --orchestrator-model-id second_model `
  --executor-model-id first_model `
  --orchestrator-base-url http://127.0.0.1:8081/v1 `
  --executor-base-url http://127.0.0.1:8082/v1 `
  --orchestrator-max-tokens 768 `
  --orchestrator-repair-attempts 1 `
  --max-group-steps 1 `
  --max-steps-per-agent 1 `
  --repair-attempts 1 `
  --execute-actions `
  --force
```

## 5. Result

Artifact folder:

```text
experiments/multi_agent/orchestrator_executor/local_second_to_first_group_poc_v3_executor_repair
```

| field | value |
|---|---|
| status | `completed` |
| success | `true` |
| plan valid | yes |
| executor model calls attempted | 2 |
| initial validation success count | 2 |
| repair attempt count | 0 |
| final validation success count | 2 |
| execution success count | 2 |
| pair quality score | `0.890597` |

Executor actions:

| agent | action | path | validation | execution |
|---|---|---|---|---|
| `office_agent` | `read_file` | `docs/ai/model_research_metadata.md` | accepted | success |
| `developer_agent` | `read_file` | `configs/evaluation_models.json` | accepted | success |

Main errors: none.

## 6. Interpretation

This proves a narrow local two-endpoint orchestrator/executor run can complete with validated and executed executor actions after executor prompt hardening.

It does not prove:

- repeated-trial robustness;
- concurrent multi-agent capacity;
- GPU readiness;
- broad realistic user activity;
- final model-pair suitability.

## 7. Diagnostics

Diagnostic artifacts present:

- `manifest.json`
- `orchestrator_attempts.jsonl`
- `orchestrator_plan.json`
- `per_agent_attempts.jsonl`
- `per_agent_actions.jsonl`
- `per_agent_validation_results.jsonl`
- `per_agent_execution_results.jsonl`
- `errors.jsonl`
- `pair_quality_metrics.json`
- `pair_evaluation.json`
- `runtime_logs/server_run.json`

Next recommended step: run N=3 repeated local group trials with the same hardened executor prompt/repair path before claiming robustness.
