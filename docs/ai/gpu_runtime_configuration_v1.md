# GPU Runtime Configuration v1

## 1. Purpose

Enable optional GPU acceleration for local `llama-server` runs while keeping existing CPU-compatible commands working by default.

## 2. Observed Hardware

- GPU: `NVIDIA RTX PRO 4000 Blackwell`
- detected by: `nvidia-smi`
- driver: `582.16`
- total VRAM: `24467 MiB`

## 3. Observed llama-server Flags

The exact local flags are recorded in:

```text
docs/ai/llama_server_gpu_flags_observed.md
```

The wrapper implements only observed local help flags.

## 4. Wrapper Parameters

| PowerShell parameter | llama-server flag | notes |
|---|---|---|
| `-GpuLayers` / `-NGpuLayers` | `--n-gpu-layers` | Accepts exact layer count, `auto`, or `all` according to local help. |
| `-MainGpu` | `--main-gpu` | GPU index, usually `0` on this machine. |
| `-SplitMode` | `--split-mode` | Allowed values: `none`, `layer`, `row`, `tensor`. |
| `-TensorSplit` | `--tensor-split` | Comma-separated proportions for multi-GPU use. |
| `-BatchSize` | `--batch-size` | Logical batch size. |
| `-UBatchSize` | `--ubatch-size` | Physical micro-batch size. |
| `-Threads` | `--threads` | CPU generation threads. |
| `-CtxSize` | `--ctx-size` | Existing wrapper parameter; remains default `4096`. |
| `-FlashAttention` | `--flash-attn` | Allowed values: `on`, `off`, `auto`. |
| `-CpuOnly` | `--device none` | Explicitly asks llama-server not to offload. Cannot be combined with GPU placement flags. |

Default behavior remains compatible with the old wrapper: no GPU placement flags are emitted unless the user passes GPU parameters.

## 5. Dry-Run Examples

CPU-compatible dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId second_model `
  -Port 8081 `
  -DryRun
```

GPU dry run with observed flags:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId second_model `
  -Port 8081 `
  -GpuLayers all `
  -MainGpu 0 `
  -SplitMode none `
  -DryRun
```

Explicit CPU-only dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId second_model `
  -Port 8081 `
  -CpuOnly `
  -DryRun
```

## 6. Limitations

- GPU smoke is not a stress test.
- GPU speedup depends on backend/build/model/context and other active GPU workloads.
- Final capacity requires measured concurrent runs.
- This wrapper does not download models and does not change GGUF files.
