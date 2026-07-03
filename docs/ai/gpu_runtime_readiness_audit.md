# GPU Runtime Readiness Audit

## Scope

This audit checks the local GPU/runtime readiness after the measured orchestrator/executor runtime probe. It does not run a GPU-enabled model. It records whether the hardware, installed `llama-server`, and project wrapper are ready for a future measured GPU run.

Runtime probe artifact:

```text
experiments/multi_agent/orchestrator_executor/runtime_probe_candidate_pairs_v1/gpu_runtime_status.json
```

## Findings

| Question | Answer |
|---|---|
| Is an NVIDIA GPU detected? | Yes. `nvidia-smi` reports `NVIDIA RTX PRO 4000 Blackwell`. |
| Driver/CUDA reported by `nvidia-smi` | Driver `582.16`, CUDA `13.0`. |
| Total VRAM reported by `nvidia-smi` | `24467 MiB`. |
| Does installed `llama-server --help` expose GPU flags? | Yes: `--device`, `--list-devices`, `--gpu-layers`, `--n-gpu-layers`, `-ngl`, `--tensor-split`, `--main-gpu`, `--fit`, `--op-offload`. |
| Does `scripts/start_llama_server.ps1` support GPU flags? | No explicit GPU flags are exposed. Dry-run passes model path, host, port, and `--ctx-size 4096`. |
| Does `configs/evaluation_models.json` record GPU settings? | No. It records local model/runtime metadata but not GPU layer/device settings. |
| Was GPU runtime measured? | No. The runtime/capacity probe used the existing CPU-oriented wrapper configuration. |
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

No GPU offload flags are passed by the wrapper today.

## Status

- CPU-only short single-agent runs demonstrated: yes.
- CPU local group runtime measured: yes.
- GPU detected: yes.
- llama-server GPU flags available: yes.
- GPU runtime configured: no.
- GPU runtime measured: no.
- Multi-agent concurrent capacity measured: no; current capacity is estimated from short measured telemetry.

GPU is likely useful for throughput/capacity, but current CPU local group evidence is already functional.

## Recommended Next Step

Add reviewed runtime profile fields and wrapper flags for GPU offload, starting with a dry-run-only change. Then run a small CPU-vs-GPU smoke on the same pair/scenario protocol before any larger stress test.
