# GPU Runtime Readiness Audit

## Scope

This audit checks the local GPU/runtime readiness after the measured orchestrator/executor runtime probe and the first GPU smoke. It records whether the hardware, installed `llama-server`, and project wrapper are ready for a future controlled stress run.

Runtime probe artifact:

```text
experiments/multi_agent/orchestrator_executor/runtime_probe_candidate_pairs_v1/gpu_runtime_status.json
```

GPU smoke artifact:

```text
experiments/multi_agent/orchestrator_executor/gpu_smoke_second_to_second_heavy_v1
```

Bounded stress artifact:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v1
```

## Findings

| Question | Answer |
|---|---|
| Is an NVIDIA GPU detected? | Yes. `nvidia-smi` reports `NVIDIA RTX PRO 4000 Blackwell`. |
| Driver/CUDA reported by `nvidia-smi` | Driver `582.16`, CUDA `13.0`. |
| Total VRAM reported by `nvidia-smi` | `24467 MiB`. |
| Does installed `llama-server --help` expose GPU flags? | Yes: `--device`, `--list-devices`, `--gpu-layers`, `--n-gpu-layers`, `-ngl`, `--split-mode`, `--tensor-split`, `--main-gpu`, `--fit`, `--op-offload`. |
| Does `scripts/start_llama_server.ps1` support GPU flags? | Yes. It now exposes `-GpuLayers`, `-MainGpu`, `-SplitMode`, `-TensorSplit`, `-BatchSize`, `-UBatchSize`, `-Threads`, `-FlashAttention`, and `-CpuOnly`. |
| Does `configs/evaluation_models.json` record GPU settings? | No. It records local model/runtime metadata but not GPU layer/device settings. |
| Was GPU runtime measured? | Yes, as a short N=1 smoke for `second_model -> second_model` on the heavy group scenario. |
| Was bounded GPU stress attempted? | Yes, under `gpu_full_offload`, but all attempted heavy action-execution batches failed. |
| Is CPU local group runtime measured? | Yes. The runtime probe measured the two candidate pairs on simple and heavy group scenarios. |

## Hardware Snapshot

`nvidia-smi` result on 2026-07-03:

| field | value |
|---|---|
| GPU | `NVIDIA RTX PRO 4000 Blackwell` |
| driver | `582.16` |
| CUDA | `13.0` |
| VRAM | `24467 MiB` |
| driver model | `WDDM` |

Windows video controller inventory also reported:

- `Intel(R) Graphics`, driver `32.0.101.6629`
- `NVIDIA RTX PRO 4000 Blackwell`, driver `32.0.15.8216`

The Win32 `AdapterRAM` field under-reports modern VRAM here, so `nvidia-smi` is the authoritative VRAM source for this audit.

## Wrapper Dry Run

The dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId second_model -Port 8081 -DryRun
```

resolved `llama-server.exe` and produced this effective command shape:

```text
llama-server -m <second_model.gguf> --host 127.0.0.1 --port 8081 --ctx-size 4096
```

The GPU dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId second_model -Port 8081 -GpuLayers all -MainGpu 0 -SplitMode none -DryRun
```

emits:

```text
--n-gpu-layers all --main-gpu 0 --split-mode none
```

The CPU-only dry run maps `-CpuOnly` to:

```text
--device none
```

## GPU Smoke Result

| metric | CPU baseline | GPU smoke |
|---|---:|---:|
| status | `completed` | `completed` |
| pair quality | `0.875562` | `0.875545` |
| execution success | `1.0` | `1.0` |
| total errors | 2 | 2 |
| wall time ms | `8775.802` | `8716.17` |
| peak RAM MB | `4712.328125` | `4714.621094` |
| peak VRAM MB | `6282.0` | `6282.0` |
| peak GPU utilization percent | `99.0` | `98.0` |

Speedup wall-time ratio: `1.006842`.

The result proves that explicit wrapper GPU flags can start and complete a short local group run. It does not prove meaningful speedup because the baseline was "no explicit wrapper GPU flags", not strict `--device none`, and local GPU telemetry was active in both conditions.

## Status

- CPU-only short single-agent runs demonstrated: yes.
- CPU local group runtime measured: yes.
- GPU detected: yes.
- llama-server GPU flags available: yes.
- GPU runtime configured: yes, optional wrapper flags implemented.
- GPU runtime measured: yes, short N=1 smoke only.
- Bounded multi-agent concurrent stress attempted: yes.
- Stable multi-agent concurrent capacity measured: no; all bounded stress batches failed before successful group-run completion.

GPU is likely useful for throughput/capacity, but the current bounded stress result is not ready to support a capacity recommendation.

## Recommended Next Step

Fix or classify the missing workspace-file failure path from the bounded stress artifact, then rerun the same explicit `strict_cpu` and `gpu_full_offload` profiles.
