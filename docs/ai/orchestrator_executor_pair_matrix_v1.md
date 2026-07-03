# Orchestrator/Executor Pair Matrix v1

## 1. Purpose

This comparison extends the repeated local group-agent proof from one pair to a small orchestrator/executor matrix. It supports model-pair selection for the current TZ prototype while staying within one short group scenario and without making a final production recommendation.

## 2. Protocol

- scenario: `configs/multi_agent_scenarios/office_developer_group_basic.json`
- mode: `local`
- trials: 3 per pair
- max group steps: 1
- max steps per agent: 1
- orchestrator repair attempts: 1
- executor repair attempts: 1
- execute actions: true
- GPU: not used
- stress/capacity benchmark: not run
- external network/model downloads: not used

The existing `second_model -> first_model` N=3 artifact was reused after protocol validation:

```text
experiments/multi_agent/orchestrator_executor/repeated_local_second_to_first_group_n3_v1
```

Matrix artifact root:

```text
experiments/multi_agent/orchestrator_executor/pair_matrix_office_developer_group_n3_v1
```

## 3. Command

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_pair_matrix.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-root experiments\multi_agent\orchestrator_executor\pair_matrix_office_developer_group_n3_v1 `
  --label pair_matrix_office_developer_group_n3_v1 `
  --pairs second_model:first_model,second_model:second_model,first_model:first_model,first_model:second_model `
  --existing-pair-run second_model:first_model=experiments\multi_agent\orchestrator_executor\repeated_local_second_to_first_group_n3_v1 `
  --trials 3 `
  --base-orchestrator-port 8081 `
  --base-executor-port 8082 `
  --manage-servers `
  --max-group-steps 1 `
  --max-steps-per-agent 1 `
  --orchestrator-max-tokens 768 `
  --orchestrator-repair-attempts 1 `
  --repair-attempts 1 `
  --execute-actions `
  --continue-on-pair-failure `
  --force
```

## 4. Pair summary

| rank | pair | status | completed | failed | mean pair quality | std pair quality | execution success | total errors | common failure modes | prototype pair rank score |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| 1 | `second_model -> first_model` | reused | 3 | 0 | `0.890528` | `0.000088` | `1.0` | 0 | `{}` | `0.952618` |
| 2 | `second_model -> second_model` | completed | 3 | 0 | `0.887740` | `0.000110` | `1.0` | 0 | `{}` | `0.948958` |
| 3 | `first_model -> first_model` | failed | 0 | 3 | `0.0` | `0.0` | `0.0` | 6 | `orchestrator_plan_parse_failed: 6` | `0.0` |
| 4 | `first_model -> second_model` | failed | 0 | 3 | `0.0` | `0.0` | `0.0` | 6 | `orchestrator_plan_parse_failed: 6` | `0.0` |

The rank score is `prototype_pair_rank_score`, not a final production score.

## 5. Interpretation

For this one scenario, `second_model -> first_model` is the current best observed pair. It narrowly outranked `second_model -> second_model` because quality was slightly higher and the reused run had lower observed wall/executor latency.

`second_model -> second_model` also passed all three trials. This shows that the stronger model can work as both orchestrator and executor in this scenario, but it did not improve the prototype score enough to beat `second_model -> first_model` here.

Both pairs with `first_model` as orchestrator failed all three trials before executor actions, with `orchestrator_plan_parse_failed`. This supports keeping the larger `second_model` as orchestrator for this scenario.

## 6. Server management

The generated local pairs used two separate llama-server endpoints on ports 8081 and 8082. Same-model pairs also used two separate endpoints rather than sharing one endpoint, keeping the protocol consistent across roles. Each generated pair wrote its own `server_run.json`; all started endpoints were stopped after each pair.

The reused `second_model -> first_model` pair did not start servers during the matrix run.

## 7. Limitations

- One group scenario only.
- N=3 per pair.
- No GPU runtime.
- No stress or capacity benchmark.
- No final production recommendation.
- Failed `first_model` orchestrator pairs may improve only after additional prompt/repair work; this matrix records current behavior, not a permanent model property.

## 8. Next step

Add a heavier multi-agent scenario and run the same matrix protocol. After that, measure runtime/GPU/capacity separately before updating any final recommendation.
