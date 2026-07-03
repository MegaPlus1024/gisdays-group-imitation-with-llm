# Orchestrator/Executor Runtime Capacity v1

## 1. Purpose

This document records the measured local runtime/resource probe for the two remaining orchestrator/executor candidate pairs after the basic and heavy scenario matrices.

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/runtime_probe_candidate_pairs_v1
```

The probe is a short local measurement. It is not a concurrent stress test and does not produce production sizing.

## 2. Protocol

- mode: `local`
- models config: `configs/evaluation_models.json`
- pairs: `second_model -> first_model`, `second_model -> second_model`
- scenarios:
  - `simple`: `configs/multi_agent_scenarios/office_developer_group_basic.json`
  - `heavy`: `configs/multi_agent_scenarios/office_developer_maintenance_group_heavy.json`
- trials: 3 per pair/scenario
- managed endpoints: yes, two local `llama-server` endpoints per pair
- ports: 8081 for orchestrator, 8082 for executor
- runtime telemetry: per-process RSS/CPU sampled with `psutil`
- GPU used for measurements: no

Primary generated files:

```text
runtime_capacity_report.md
runtime_metrics_by_pair_scenario.json
capacity_estimates.json
quality_cost_tradeoff.json
gpu_runtime_status.json
replay_commands.ps1
```

## 3. Runtime Results

| pair | scenario | completed_trials | mean_pair_quality_score | mean_execution_success_rate | total_errors | mean_wall_time_ms | peak_ram_mb_pair | peak_cpu_percent_pair |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `second_model -> first_model` | `simple` | 3 | `0.889947` | `1.0` | 0 | `2056.198667` | `3370.539063` | `51.5` |
| `second_model -> second_model` | `simple` | 3 | `0.887296` | `1.0` | 0 | `2552.921333` | `4442.996094` | `57.1` |
| `second_model -> first_model` | `heavy` | 3 | `0.820122` | `1.0` | 18 | `7057.967` | `4390.257813` | `60.6` |
| `second_model -> second_model` | `heavy` | 3 | `0.875509` | `1.0` | 6 | `8699.126667` | `5675.605469` | `51.5` |

## 4. Capacity Estimate

The capacity estimate uses the maximum measured pair RSS across the probed scenarios and the system RAM snapshot from the run. It reserves 4096 MB in the default estimate.

| pair | peak_ram_mb_pair | peak_cpu_percent_pair | estimated_concurrent_pairs_by_ram | estimated_agents_by_ram | bottleneck | confidence |
|---|---:|---:|---:|---:|---|---|
| `second_model -> first_model` | `4390.257813` | `60.6` | 28 | 112 | `unknown` | `medium` |
| `second_model -> second_model` | `5675.605469` | `57.1` | 22 | 88 | `unknown` | `medium` |

This is capacity by RAM only. It does not prove that 22 or 28 concurrent pairs would maintain acceptable latency.

## 5. Quality vs Cost

| pair | mean_quality | total_errors | peak_ram_mb_pair | mean_wall_time_ms | quality_cost_score |
|---|---:|---:|---:|---:|---:|
| `second_model -> second_model` | `0.881402` | 6 | `5675.605469` | `5626.024` | `0.687916` |
| `second_model -> first_model` | `0.855035` | 18 | `4390.257813` | `4557.082833` | `0.570069` |

`second_model -> second_model` is the preliminary quality/cost winner because it held up much better on the heavy scenario. `second_model -> first_model` remains cheaper in RAM and slightly faster in this short probe, and it was marginally better on the simple scenario.

## 6. GPU Readiness

GPU was audited after the runtime measurements, and a later N=1 GPU smoke was run for `second_model -> second_model` on the heavy scenario.

Findings:

- GPU detected: yes, `NVIDIA RTX PRO 4000 Blackwell`.
- `nvidia-smi`: available, driver `582.16`, CUDA `13.0`, total VRAM `24467 MiB`.
- Installed `llama-server --help` exposes GPU flags including `--device`, `--list-devices`, `--gpu-layers`, `--n-gpu-layers`, `-ngl`, `--tensor-split`, and `--main-gpu`.
- `scripts/start_llama_server.ps1` now exposes optional GPU/runtime flags. Existing commands without GPU parameters remain compatible.
- GPU smoke artifact: `experiments/multi_agent/orchestrator_executor/gpu_smoke_second_to_second_heavy_v1`.
- GPU smoke doc: `docs/ai/gpu_smoke_second_to_second_heavy_v1.md`.

GPU is likely useful for throughput/capacity, but current CPU local group evidence is already functional.

CPU/GPU smoke summary:

| metric | CPU baseline | GPU smoke |
|---|---:|---:|
| status | `completed` | `completed` |
| pair quality | `0.875562` | `0.875545` |
| wall time ms | `8775.802` | `8716.17` |
| peak VRAM MB | `6282.0` | `6282.0` |

Speedup wall-time ratio was `1.006842`, so the first smoke is a readiness check, not evidence of meaningful acceleration.

## 7. Bounded Stress Follow-up

A later bounded stress smoke was run with explicit runtime profiles:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v1
```

Profiles:

- `strict_cpu`: wrapper `-CpuOnly`, emitted `--device none`.
- `gpu_full_offload`: emitted `--n-gpu-layers 999 --main-gpu 0 --split-mode none`.

Candidate pairs:

- `second_model -> second_model`
- `second_model -> first_model`

Concurrency levels tested: `1`, `2`. Concurrency `4` was skipped with an explicit bounded-smoke reason.

Stress result:

| pair | profile | levels | max stable concurrency observed | verdict |
|---|---|---|---:|---|
| `second_model -> second_model` | `strict_cpu` | `1,2` | none | failed |
| `second_model -> second_model` | `gpu_full_offload` | `1,2` | none | failed |
| `second_model -> first_model` | `strict_cpu` | `1,2` | none | failed |
| `second_model -> first_model` | `gpu_full_offload` | `1,2` | none | failed |

The common failure mode was `FileNotFoundError` in heavy action-execution trials, including missing workspace files such as `workspace/office_agent_1_executor_note.md`. Telemetry and server lifecycle artifacts were preserved, but the result does not establish stable concurrent capacity.

## 8. Server Management

All four pair/scenario measurements started managed local endpoints and stopped them after the run. The generated `server_run.json` files record `endpoint_stopped: true` for both roles in all four runs.

Post-run checks:

- `http://127.0.0.1:8081/v1/models`: stopped
- `http://127.0.0.1:8082/v1/models`: stopped
- active `llama-server.exe` processes after probe: none

## 9. Recommendation Status

Recommendation status: preliminary only.

The measured runtime probe is enough to keep `second_model -> second_model` as the current preliminary quality/cost candidate for the non-concurrent local orchestrator/executor group workflow. It is not enough for a production recommendation because the bounded concurrent stress follow-up observed no stable concurrency.

## 10. Limitations

- N=3 per pair/scenario.
- The later bounded concurrent stress smoke ran, but every attempted batch failed.
- CPU local runtime only.
- GPU hardware was detected and a short GPU smoke completed, but bounded GPU stress did not produce completed group runs.
- Browser behavior remains simulated-only.
- Office behavior remains stub/file-based.
- The virtual network is still a controlled local action environment, not a full network simulation.
