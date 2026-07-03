# Bounded Stress Probe for Candidate Pairs v1

## 1. Purpose

This document records a controlled bounded stress smoke for the local orchestrator/executor pipeline. It is a research smoke, not a destructive stress test and not production sizing.

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v1
```

## 2. Candidate pairs

- `second_model -> second_model`
- `second_model -> first_model`

## 3. Runtime profiles

Profiles are defined in `configs/runtime_profiles.json`.

| profile | server flags | expected GPU use | validation result |
|---|---|---|---|
| `strict_cpu` | `-CpuOnly`, `-CtxSize 4096` -> `--device none` | none | Requested strict CPU, but not proven truly strict because device-level GPU utilization was still observed. |
| `gpu_full_offload` | `-GpuLayers 999`, `-MainGpu 0`, `-SplitMode none`, `-CtxSize 4096` | high | Explicit GPU offload started and produced GPU telemetry. |

`-FlashAttention` was dry-run checked but not enabled in the actual profile because the previous successful GPU smoke did not require it.

## 4. Scenario

Heavy group scenario:

```text
configs/multi_agent_scenarios/office_developer_maintenance_group_heavy.json
```

## 5. Protocol

- mode: `local`
- managed endpoints: two separate `llama-server` endpoints per pair, including same-model pairs
- ports: 8081 for orchestrator, 8082 for executor
- concurrency levels tested: `1`, `2`
- skipped concurrency level: `4`
- skip reason: level 4 would add four concurrent heavy group runs per batch and sixteen additional local group runs across the matrix; levels 1 and 2 were used to keep this a bounded smoke.
- runs per level: `2`
- actual runs per level rule: `max(runs_per_level, concurrency_level)`
- `max_group_steps=2`
- `max_steps_per_agent=1`
- `orchestrator_max_tokens=1024`
- `orchestrator_repair_attempts=1`
- executor `repair_attempts=1`
- `execute_actions=true`
- timeout: `180` seconds per subprocess group run
- external network: not used
- real browser/office automation: not used

Each group run was launched as a subprocess so timeout handling could preserve artifacts without leaving stuck worker threads.

## 6. Results summary

All eight attempted batches failed. The common failure mode was `FileNotFoundError` from failed action/workspace trials, for example missing `workspace/office_agent_1_executor_note.md`. These failures are preserved in per-run `trial_error.json`, `repeated_group_trials_result.json`, stdout/stderr, and batch summaries.

| pair | profile | concurrency | completed | failed | total_errors | peak RAM MB | peak VRAM MB | peak GPU % | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `second_model -> second_model` | `strict_cpu` | 1 | 0 | 2 | 2 | `8099.003907` | `1503.0` | `73.0` | `failed` |
| `second_model -> second_model` | `strict_cpu` | 2 | 0 | 2 | 2 | `7582.277343` | `1525.0` | `77.0` | `failed` |
| `second_model -> second_model` | `gpu_full_offload` | 1 | 0 | 2 | 2 | `5271.523437` | `6189.0` | `99.0` | `failed` |
| `second_model -> second_model` | `gpu_full_offload` | 2 | 0 | 2 | 2 | `4024.4375` | `6192.0` | `99.0` | `failed` |
| `second_model -> first_model` | `strict_cpu` | 1 | 0 | 2 | 2 | `5437.1875` | `1737.0` | `80.0` | `failed` |
| `second_model -> first_model` | `strict_cpu` | 2 | 0 | 2 | 2 | `5275.019532` | `1779.0` | `51.0` | `failed` |
| `second_model -> first_model` | `gpu_full_offload` | 1 | 0 | 2 | 2 | `3200.53125` | `5439.0` | `91.0` | `failed` |
| `second_model -> first_model` | `gpu_full_offload` | 2 | 0 | 2 | 2 | `3120.792969` | `5439.0` | `95.0` | `failed` |

## 7. CPU vs GPU profile comparison

CPU and GPU wall-time speedup could not be computed because no batch completed a group run successfully.

The GPU profile did show expected high GPU activity:

- `second_model -> second_model`: peak GPU utilization `99.0`, peak VRAM `6192.0 MB`
- `second_model -> first_model`: peak GPU utilization `95.0`, peak VRAM `5439.0 MB`

The `strict_cpu` profile emitted `--device none`, but it is not labeled truly strict because device-level GPU telemetry still reported utilization during those batches. This may include unrelated local graphics workload.

## 8. Capacity/stability interpretation

No stable concurrency was observed for either pair/profile:

| pair | profile | max stable concurrency observed | bottleneck |
|---|---|---:|---|
| `second_model -> second_model` | `strict_cpu` | none | `CPU` |
| `second_model -> second_model` | `gpu_full_offload` | none | `GPU` |
| `second_model -> first_model` | `strict_cpu` | none | `CPU` |
| `second_model -> first_model` | `gpu_full_offload` | none | `GPU` |

This does not invalidate the earlier non-concurrent pair-matrix evidence. It means the current heavy scenario with `execute_actions=true` is not stress-ready under these explicit runtime profiles until the action/workspace failure is fixed or classified.

## 9. Limitations

- Short bounded smoke only.
- Not production sizing.
- No uncontrolled load.
- No external network.
- No real browser/office automation.
- Concurrency level 4 was skipped with an explicit bounded-smoke reason.
- GPU telemetry is device-level and can include unrelated local graphics activity.
- All attempted batches failed, so latency/quality degradation and throughput comparisons are not meaningful.

## 10. Next step

Fix or explicitly classify the missing workspace-file failure path in the heavy action-execution scenario, then rerun the same bounded stress probe. Until at least one pair/profile has completed runs at concurrency 1, do not use the GPU/CPU stress result as a preliminary final recommendation.
