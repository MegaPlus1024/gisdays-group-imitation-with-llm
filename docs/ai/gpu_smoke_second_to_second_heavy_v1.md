# GPU Smoke Second-to-Second Heavy v1

## 1. Purpose

Run a short CPU-compatible baseline versus explicit GPU-flag smoke for the current preliminary orchestrator/executor candidate pair. This is a readiness smoke for the next controlled stress test, not a stress test itself.

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/gpu_smoke_second_to_second_heavy_v1
```

## 2. Candidate Pair

```text
second_model -> second_model
```

This pair was selected because it was the preliminary quality/cost winner in `docs/ai/orchestrator_executor_runtime_capacity_v1.md`.

## 3. Scenario

```text
configs/multi_agent_scenarios/office_developer_maintenance_group_heavy.json
```

The heavy scenario was used because it is the scenario where `second_model -> second_model` became the best observed pair and where runtime cost matters most in the current evidence.

## 4. CPU Baseline Protocol

- trials: 1
- max group steps: 2
- max steps per agent: 1
- orchestrator max tokens: 1024
- orchestrator repair attempts: 1
- executor repair attempts: 1
- execute actions: true
- wrapper GPU placement flags: none
- wrapper flags used: `-CtxSize 4096`

Important caveat: this baseline means no explicit wrapper GPU placement flags. It is not the same as strict `--device none`; local `llama-server --help` reports default GPU layers as `auto`, and GPU telemetry was active during the baseline.

## 5. GPU Smoke Protocol

- trials: 1
- max group steps: 2
- max steps per agent: 1
- orchestrator max tokens: 1024
- orchestrator repair attempts: 1
- executor repair attempts: 1
- execute actions: true
- wrapper flags used for both roles: `-CtxSize 4096 -GpuLayers all -MainGpu 0 -SplitMode none`

`-GpuLayers all` was chosen because the observed local help says `--n-gpu-layers` accepts an exact count, `auto`, or `all`, and the GPU has 24467 MiB VRAM.

## 6. Observed Hardware

| field | value |
|---|---|
| GPU | `NVIDIA RTX PRO 4000 Blackwell` |
| driver | `582.16` |
| total VRAM | `24467 MiB` |

An unrelated graphics workload was present during the audit/smoke window, so GPU utilization should not be interpreted as model-only utilization.

## 7. llama-server Flags Used

Observed flag source:

```text
docs/ai/llama_server_gpu_flags_observed.md
```

Effective GPU smoke wrapper flags:

| role | wrapper flags |
|---|---|
| orchestrator | `-CtxSize 4096 -GpuLayers all -MainGpu 0 -SplitMode none` |
| executor | `-CtxSize 4096 -GpuLayers all -MainGpu 0 -SplitMode none` |

## 8. Results Table

| metric | CPU baseline | GPU smoke |
|---|---:|---:|
| status | `completed` | `completed` |
| pair_quality_score | `0.875562` | `0.875545` |
| execution_success_rate | `1.0` | `1.0` |
| total_errors | 2 | 2 |
| wall_time_ms | `8775.802` | `8716.17` |
| peak_ram_mb | `4712.328125` | `4714.621094` |
| peak_cpu_percent | `49.9` | `55.6` |
| peak_vram_mb | `6282.0` | `6282.0` |
| peak_gpu_utilization_percent | `99.0` | `98.0` |

Speedup wall-time ratio:

```text
1.006842
```

## 9. Interpretation

GPU wrapper support works for a short managed orchestrator/executor smoke: the explicit GPU-flag run started, completed, wrote telemetry, and stopped both endpoints.

The speed result is neutral. The explicit GPU run was only about 0.7% faster in wall time, which is too small to claim a meaningful speedup and is not evidence of meaningful acceleration. The baseline also showed active GPU telemetry, so this artifact should be read as "no explicit wrapper GPU flags vs explicit GPU flags", not as a clean CPU-only vs GPU benchmark.

Quality remained comparable and execution success stayed `1.0` in both runs.

## 10. Limitations

- N=1 per condition.
- No true concurrent stress test.
- Baseline was not strict `--device none`.
- GPU utilization may include unrelated local graphics workload.
- The scenario runner is sequential.
- No final production recommendation is made.

## 11. Next Step

Before a larger stress test, run one controlled strict CPU-only diagnostic with `-CpuOnly` or move directly to a controlled GPU stress smoke with idle GPU conditions and explicit monitoring. The next stress test should preserve the same safety policy and keep concurrency bounded.
