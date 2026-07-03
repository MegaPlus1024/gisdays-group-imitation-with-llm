# Final Multi-Agent Research Report

## 1. Executive summary

The project now has a working research prototype in which local software agents simulate normal user activity in a controlled virtual computer/activity environment.

The local orchestrator/executor multi-agent pipeline works in fake mode and in local two-endpoint runs. It was tested with Qwen2.5 1.5B and 3B Q4_K_M local GGUF models through the project ids `first_model` and `second_model`.

Current preliminary interpretation:

- best observed quality candidate: `second_model -> second_model`;
- resource-balanced and simple-scenario candidate: `second_model -> first_model`;
- `first_model as orchestrator not recommended` because it repeatedly failed at orchestrator plan parsing;
- bounded stress supports only preliminary concurrency evidence;
- production recommendation not made.

## 2. Research objective and TZ mapping

Target: develop and verify a prototype in which a group of software agents imitates normal user activity in a virtual computer network.

| TZ item | Evidence | Status |
|---|---|---|
| local agents | `src/agent/`, single-agent reports, local model artifacts | complete |
| group of agents | `experiments/multi_agent/orchestrator_executor/*`, group history artifacts | complete |
| role/config/script-driven behavior | roles, scenarios, script registry, `NextAction` validation | complete |
| virtual network/activity environment | controlled local filesystem/action environment, simulated browser and office stubs | partially complete |
| model comparison | single-agent comparison, simple/heavy pair matrices | complete |
| orchestrator/executor pair selection | pair matrix artifacts and ranking docs | preliminary |
| quality evaluation | `pair_quality_score`, prototype ranking, behavioral metrics | preliminary |
| runtime/resource measurement | runtime probe candidate pairs v1 | preliminary |
| GPU measurement | GPU smoke and bounded GPU stress rows | preliminary |
| concurrent capacity | bounded stress v2 levels 1 and 2 | partially complete |
| production deployment | no production scheduler or hardening | out of scope |
| final production model choice | evidence remains insufficient | not measured |

## 3. Models

| field | first_model | second_model |
|---|---|---|
| project id | `first_model` | `second_model` |
| upstream/full name | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | `qwen2.5-3b-instruct-q4_k_m.gguf` |
| parameter size | 1.5B | 3B |
| quantization | Q4_K_M | Q4_K_M |
| local file | `models/gguf/first_model.gguf` | `models/gguf/second_model.gguf` |
| observed role | executor candidate; failed as orchestrator | strongest orchestrator; quality candidate executor |

`second_model` also appears in older single-agent artifacts under the historical id `qwen2_5_3b_instruct_q4_k_m`.

## 4. Architecture

The multi-agent prototype extends the single-agent pipeline with explicit orchestration and group artifacts.

Main pieces:

- agent state loads role, resources, constraints, available scripts, and recent history;
- prompt builder renders role-specific model context;
- local LLM client calls OpenAI-compatible local `llama-server` endpoints;
- `NextAction` contract constrains executor output;
- script registry validates known actions and parameters;
- execution bridge runs bounded file/browser-simulated/office-stub actions;
- history logger records per-agent and group events;
- orchestrator plan assigns agents and tasks;
- executor actions are selected, validated, optionally repaired, and executed;
- group history preserves assignments, actions, validation, execution, and errors;
- pair quality metrics summarize plan validity, execution, role fit, history use, diversity, errors, and resource/latency tradeoffs;
- artifacts are written under `experiments/multi_agent/orchestrator_executor/`.

## 5. Evaluation methodology

The evidence base progressed through these stages:

1. Single-agent local trials: `reports/experiments/final_evaluation_report.md`.
2. Fake group MVP: `experiments/multi_agent/orchestrator_executor/fake_office_developer_group_v1`.
3. Local orchestrator/executor POC: `local_second_to_first_group_poc_v2_repair` and `local_second_to_first_group_poc_v3_executor_repair`.
4. Repeated group trials: `repeated_local_second_to_first_group_n3_v1`.
5. Simple pair matrix: `pair_matrix_office_developer_group_n3_v1`.
6. Heavy scenario matrix: `pair_matrix_heavy_group_n3_workspace_policy_v1`.
7. Runtime/capacity probe: `runtime_probe_candidate_pairs_v1`.
8. GPU smoke: `gpu_smoke_second_to_second_heavy_v1`.
9. Bounded stress v2: `bounded_stress_candidate_pairs_v2`.

No new experimental run was performed for this report. This is a consolidation of existing artifacts.

## 6. Quality metric

`pair_quality_score` and `prototype_pair_rank_score` are prototype metrics, not universally validated scientific metrics.

They combine observed properties such as:

- plan validity;
- action validation;
- execution success;
- role fit;
- history usage;
- diversity;
- error penalties;
- latency and resource tradeoff.

They are useful for ranking these controlled prototype runs, but they should not be treated as a general model benchmark.

## 7. Simple group scenario results

Scenario: `office_developer_group_basic`.

Best observed pair: `second_model -> first_model`.

Repeated local result for `second_model -> first_model`:

| attempted | completed | failed | mean_pair_quality_score | std_pair_quality_score | mean_execution_success_rate | total_errors |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 3 | 0 | `0.890528` | `0.000088` | `1.0` | 0 |

Simple pair-matrix interpretation:

| pair | result |
|---|---|
| `second_model -> first_model` | best observed pair for simple scenario |
| `second_model -> second_model` | completed and worked |
| `first_model -> first_model` | failed due to `orchestrator_plan_parse_failed` |
| `first_model -> second_model` | failed due to `orchestrator_plan_parse_failed` |

## 8. Heavy group scenario results

Scenario: `office_developer_maintenance_group_heavy`.

The heavy scenario uses four agents, two group steps, local fixtures, and `artifact_workspace_only` write policy.

Best observed pair: `second_model -> second_model`.

| pair | completed | failed | mean_pair_quality_score | mean_execution_success_rate | total_errors | prototype_pair_rank_score |
|---|---:|---:|---:|---:|---:|---:|
| `second_model -> second_model` | 3 | 0 | `0.875451` | `1.0` | 6 | `0.759188` |
| `second_model -> first_model` | 3 | 0 | `0.820328` | `1.0` | 18 | `0.571269` |
| `first_model -> first_model` | 0 | 3 | null | null | n/a | failed |
| `first_model -> second_model` | 0 | 3 | null | null | n/a | failed |

Error profile:

| pair | common failure modes |
|---|---|
| `second_model -> second_model` | `NextActionJSONError`, `NextActionValidationError` |
| `second_model -> first_model` | `validation_failed`, `write_path_outside_artifact_workspace`, `HTTPStatusError` |
| `first_model` as orchestrator | `orchestrator_plan_parse_failed` |

## 9. Cross-scenario interpretation

The simple scenario best pair is `second_model -> first_model`.

The heavy scenario best pair is `second_model -> second_model`.

The best pair changed by scenario, which reduces confidence in a universal final recommendation. However, the evidence is consistent that `second_model` is required as orchestrator in the current tests. `first_model` did not provide reliable orchestrator plans.

## 10. Runtime and capacity

Runtime/capacity probe artifact: `experiments/multi_agent/orchestrator_executor/runtime_probe_candidate_pairs_v1`.

| pair | scenario | quality | exec rate | errors | wall ms | RAM MB | CPU % | estimated pairs/agents by RAM |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `second_model -> first_model` | simple | `0.889947` | `1.0` | 0 | `2056.198667` | `3370.539063` | `51.5` | 28 pairs / 112 agents |
| `second_model -> first_model` | heavy | `0.820122` | `1.0` | 18 | `7057.967` | `4390.257813` | `60.6` | 28 pairs / 112 agents |
| `second_model -> second_model` | simple | `0.887296` | `1.0` | 0 | `2552.921333` | `4442.996094` | `57.1` | 22 pairs / 88 agents |
| `second_model -> second_model` | heavy | `0.875509` | `1.0` | 6 | `8699.126667` | `5675.605469` | `51.5` | 22 pairs / 88 agents |

Capacity estimates are RAM-based from short sequential telemetry. They are not stress capacity. Bottleneck is unknown and confidence is medium.

Quality-cost interpretation from the runtime probe: `second_model -> second_model` was the preliminary quality-cost winner with score `0.687916`, mainly because it held up better in the heavy scenario.

## 11. GPU smoke

Hardware:

- NVIDIA RTX PRO 4000 Blackwell;
- driver `582.16`;
- CUDA `13.0`;
- VRAM `24467 MiB`.

GPU smoke artifact: `experiments/multi_agent/orchestrator_executor/gpu_smoke_second_to_second_heavy_v1`.

| metric | CPU baseline | GPU smoke |
|---|---:|---:|
| status | completed | completed |
| pair_quality_score | `0.875562` | `0.875545` |
| execution_success_rate | `1.0` | `1.0` |
| total_errors | 2 | 2 |
| wall_time_ms | `8775.802` | `8716.17` |
| peak_ram_mb | `4712.328125` | `4714.621094` |
| peak_vram_mb | `6282.0` | `6282.0` |
| peak_gpu_utilization_percent | `99.0` | `98.0` |

Wrapper GPU support works and telemetry works. Speedup wall-time ratio was `1.006842`, so there is no meaningful speedup claim. The CPU baseline was not strict CPU-only.

## 12. Bounded stress v2

v1 bounded stress failed due to a harness/workspace artifact path bug, not model, GGUF, or scenario behavior. It should be treated as invalid capacity evidence.

v2 fixed workspace isolation with short artifact paths, workspace provisioning, fixture preflight, and richer diagnostics.

CPU profile caveat: `cpu_requested_device_none` is not strict verified CPU.

Compact stress result:

| pair | profile | concurrency | completed | failed | quality | exec rate | errors | wall ms | RAM MB | VRAM MB | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `second_model -> second_model` | `cpu_requested_device_none` | 1 | 2 | 0 | `0.895833` | `1.0` | 0 | `173322.98` | `8092.61` | `1715` | stable |
| `second_model -> second_model` | `cpu_requested_device_none` | 2 | 0 | 2 | null | null | 3 | `72636.74` | `7579.28` | `1715` | failed |
| `second_model -> second_model` | `gpu_full_offload` | 1 | 2 | 0 | `0.875198` | `1.0` | 4 | `9134.77` | `5261.97` | `6420` | stable |
| `second_model -> second_model` | `gpu_full_offload` | 2 | 2 | 0 | `0.144059` | `0.0` | 16 | `7042.87` | `4023.91` | `6422` | unstable |
| `second_model -> first_model` | `cpu_requested_device_none` | 1 | 2 | 0 | `0.778125` | `1.0` | 12 | `97962.64` | `6225.35` | `1715` | unstable |
| `second_model -> first_model` | `cpu_requested_device_none` | 2 | 1 | 1 | `0.775000` | `1.0` | 8 | `82547.03` | `5824.04` | `1715` | unstable |
| `second_model -> first_model` | `gpu_full_offload` | 1 | 2 | 0 | `0.820153` | `1.0` | 12 | `7097.97` | `4070.46` | `5482` | unstable |
| `second_model -> first_model` | `gpu_full_offload` | 2 | 2 | 0 | `0.146138` | `0.0` | 16 | `5358.14` | `3122.79` | `5479` | unstable |

Stress interpretation:

- v2 artifacts are usable for a preliminary report;
- concurrency 1 is viable for `second_model -> second_model`, especially under `gpu_full_offload`;
- concurrency 2 unstable;
- no concurrency 4 was run;
- no long soak was run.

## 13. Preliminary recommendation

Recommended preliminary default for a quality-focused local group prototype:

- `second_model -> second_model`.

Rationale:

- best heavy scenario score;
- fewer heavy-scenario errors than `second_model -> first_model`;
- works as both orchestrator and executor;
- stable at bounded stress concurrency 1 under `gpu_full_offload`.

Resource-balanced candidate:

- `second_model -> first_model`.

Rationale:

- strong simple scenario score;
- lower RAM and latency in the runtime probe;
- weaker and noisier under the heavy scenario.

Not recommended:

- `first_model` as orchestrator.

Rationale:

- plan parse failures in pair matrix runs.

This is not a production recommendation and not a final capacity claim. Production recommendation not made.

## 14. Limitations

- Only two group scenarios.
- N=3 for pair matrices.
- Bounded stress is short only.
- Concurrency 2 unstable.
- No concurrency 4.
- No strict CPU baseline.
- No long soak.
- No real browser automation.
- No real office automation.
- Virtual network is simulated as a controlled local action environment.
- No external network behavior.
- No production scheduler.
- Metrics are prototype metrics.

## 15. Reproducibility

Setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Model file placement:

```text
models\gguf\first_model.gguf
models\gguf\second_model.gguf
```

Repeated local group trials:

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
  --execute-actions `
  --force
```

Pair matrix:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_pair_matrix.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-root experiments\multi_agent\orchestrator_executor\pair_matrix_office_developer_group_n3_v1 `
  --label pair_matrix_office_developer_group_n3_v1 `
  --pairs second_model:first_model,second_model:second_model,first_model:first_model,first_model:second_model `
  --trials 3 `
  --manage-servers `
  --execute-actions `
  --continue-on-pair-failure `
  --force
```

Heavy scenario matrix:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_pair_matrix.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\pair_matrix_heavy_group_n3_workspace_policy_v1 `
  --label pair_matrix_heavy_group_n3_workspace_policy_v1 `
  --pairs second_model:first_model,second_model:second_model,first_model:first_model,first_model:second_model `
  --trials 3 `
  --manage-servers `
  --execute-actions `
  --continue-on-pair-failure
```

Runtime probe:

```powershell
.\.venv\Scripts\python.exe scripts\probe_orchestrator_executor_runtime.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --out-root experiments\multi_agent\orchestrator_executor\runtime_probe_candidate_pairs_v1 `
  --label runtime_probe_candidate_pairs_v1 `
  --pairs second_model:first_model,second_model:second_model `
  --scenarios simple=configs\multi_agent_scenarios\office_developer_group_basic.json,heavy=configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --trials 3 `
  --manage-servers `
  --execute-actions `
  --continue-on-pair-failure
```

GPU smoke:

```powershell
.\.venv\Scripts\python.exe scripts\run_gpu_smoke_orchestrator_executor.py `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\gpu_smoke_second_to_second_heavy_v1 `
  --pair second_model:second_model `
  --trials 1 `
  --gpu-layers all `
  --main-gpu 0 `
  --split-mode none `
  --execute-actions
```

Bounded stress v2:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_stress_probe.py `
  --models-config configs\evaluation_models.json `
  --runtime-profiles-config configs\runtime_profiles.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\bounded_stress_candidate_pairs_v2 `
  --label bounded_stress_candidate_pairs_v2 `
  --pairs second_model:second_model,second_model:first_model `
  --profiles cpu_requested_device_none,gpu_full_offload `
  --concurrency-levels 1,2 `
  --runs-per-level 2 `
  --base-port 8081 `
  --execute-actions `
  --timeout-seconds 180 `
  --continue-on-failure `
  --force `
  --skipped-concurrency-levels 4
```

## 16. Final conclusion

The project satisfies the core prototype objective at research-prototype level:

- local multi-agent orchestrator/executor simulation exists and was validated;
- group-agent activity can be planned, assigned, executed through bounded actions, logged, and evaluated;
- preliminary orchestrator/executor pair selection evidence exists.

The project does not yet satisfy:

- production deployment;
- stable concurrent capacity;
- final hardware sizing;
- robust real-world browser/office/network emulation.

The correct current conclusion is a validated research prototype with preliminary pair guidance, not a production-ready agent platform.
