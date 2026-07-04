# llama-server GPU Flags Observed

## 1. Scope

This file records the local `llama-server --help` facts used to implement wrapper GPU support. It intentionally keeps only the relevant help excerpts instead of copying the full help output.

## 2. Executable

Resolved executable:

```text
<local_appdata>\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe
```

Version command:

```powershell
& "<path>\llama-server.exe" --version
```

Observed version:

```text
version: 9264 (ce02093fd)
built with Clang 19.1.5 for Windows x86_64
```

## 3. GPU-Related Flags Observed

| purpose | observed flag names | notes |
|---|---|---|
| device selection / CPU-only | `--device <dev1,dev2,..>` | Help says `none = don't offload`; wrapper `-CpuOnly` maps to `--device none`. |
| list devices | `--list-devices` | Inspection-only command. |
| GPU layers | `-ngl`, `--gpu-layers`, `--n-gpu-layers N` | Help says exact number, `auto`, or `all`; wrapper uses readable `--n-gpu-layers`. |
| split mode | `-sm`, `--split-mode {none,layer,row,tensor}` | Wrapper exposes `-SplitMode`. |
| tensor split | `-ts`, `--tensor-split N0,N1,N2,...` | Wrapper exposes `-TensorSplit`. |
| main GPU | `-mg`, `--main-gpu INDEX` | Wrapper exposes `-MainGpu`. |
| fit to device memory | `-fit`, `--fit [on|off]` | Observed but not exposed by wrapper v1. |
| fit target | `-fitt`, `--fit-target MiB0,MiB1,...` | Observed but not exposed by wrapper v1. |
| fit context | `-fitc`, `--fit-ctx N` | Observed but not exposed by wrapper v1. |
| op offload | `--op-offload`, `--no-op-offload` | Observed but not exposed by wrapper v1. |

## 4. CPU/Thread Flags Observed

| purpose | observed flag names | wrapper parameter |
|---|---|---|
| generation threads | `-t`, `--threads N` | `-Threads` |
| batch/prompt threads | `-tb`, `--threads-batch N` | not exposed in wrapper v1 |
| HTTP worker threads | `--threads-http N` | not exposed in wrapper v1 |
| CPU affinity | `--cpu-mask`, `--cpu-range`, `--cpu-strict` | not exposed in wrapper v1 |

## 5. Context/Batch Flags Observed

| purpose | observed flag names | wrapper parameter |
|---|---|---|
| context size | `-c`, `--ctx-size N` | `-CtxSize` |
| logical batch size | `-b`, `--batch-size N` | `-BatchSize` |
| physical micro-batch size | `-ub`, `--ubatch-size N` | `-UBatchSize` |
| continuous batching | `-cb`, `--cont-batching`, `-nocb`, `--no-cont-batching` | not exposed in wrapper v1 |
| flash attention | `-fa`, `--flash-attn [on|off|auto]` | `-FlashAttention` |

## 6. Backend Indication

The help output exposes GPU offload/device flags but does not print a separate backend label in the filtered help excerpt. Runtime hardware inspection confirms NVIDIA GPU availability via `nvidia-smi`; the version output identifies the Windows x86_64 build but not a CUDA/Vulkan backend string. Therefore the wrapper only exposes flags that the executable itself accepts and leaves backend validation to dry-run/smoke artifacts.

## 7. Wrapper Mapping

| PowerShell parameter | llama-server flag |
|---|---|
| `-GpuLayers` / `-NGpuLayers` | `--n-gpu-layers` |
| `-MainGpu` | `--main-gpu` |
| `-SplitMode` | `--split-mode` |
| `-TensorSplit` | `--tensor-split` |
| `-BatchSize` | `--batch-size` |
| `-UBatchSize` | `--ubatch-size` |
| `-Threads` | `--threads` |
| `-CtxSize` | `--ctx-size` |
| `-FlashAttention` | `--flash-attn` |
| `-CpuOnly` | `--device none` |
