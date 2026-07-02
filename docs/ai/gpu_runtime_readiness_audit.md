# GPU Runtime Readiness Audit

## Scope

This audit inspects current runtime configuration and documentation only. It does not start `llama-server`, run models, or query local hardware.

## Findings

| Question | Answer |
|---|---|
| Does `scripts/start_llama_server.ps1` support GPU flags? | No explicit GPU flags are exposed. It currently passes model path, host, port, and `--ctx-size`. |
| Does `configs/evaluation_models.json` record GPU settings? | No. It records `ctx_size`, timeout, temperature, max tokens, runtime, and CPU-only expectation, but not GPU layer/device settings. |
| Is there any measured GPU run? | No measured GPU run was found in current docs/artifacts. |
| Is there CPU-only evidence? | Yes, short single-agent local runs are documented as CPU-oriented and resource summaries exist. |
| Is GPU required for current single-agent demos? | No evidence says GPU is required for the existing short single-agent demos. |
| Is GPU likely needed for multi-agent capacity/stress testing? | Uncertain but likely useful for practical throughput; it must be tested on actual hardware. |

## Current Runtime Evidence

- `configs/runtime.local.example.json` says `gpu_required: false` and `gpu_optional_later: true`.
- `configs/evaluation_models.json` has `expected_cpu_only: true` for both current models.
- `docs/ai/resource_capacity_evaluation_v1.md` states CPU-only short single-agent runs were demonstrated.
- `docs/ai/multi_agent_capacity_formula.md` warns that capacity is a planning estimate, not a measured concurrent load result.

## Missing Config Fields

Minimal future fields:

- `n_gpu_layers`
- `main_gpu`
- `tensor_split`
- `threads`
- `batch_size`
- `ctx_size`

Optional runtime fields:

- `runtime_backend` such as `cpu`, `cuda`, `vulkan`, `metal`, or `auto`
- `server_extra_args` for explicitly reviewed llama.cpp arguments
- `runtime_profile_id` for comparing CPU and GPU runs

## llama.cpp Flags To Support After Local Help Verification

The wrapper should support only flags confirmed by the installed `llama-server --help`. Candidate llama.cpp-style flags to verify:

- `--n-gpu-layers` or `-ngl`
- `--main-gpu`
- `--tensor-split`
- `--threads`
- `--batch-size`
- `--ctx-size`

The exact spelling can vary by build/version, so it should be checked before implementation.

## Status

- CPU-only short single-agent runs demonstrated: yes.
- GPU runtime configured: no.
- GPU runtime measured: no.
- Multi-agent concurrent capacity measured: no.
- GPU may be needed for practical multi-agent throughput: uncertain, likely enough to justify a measured GPU smoke once hardware is available.

## Recommended Next Step

Add runtime profile metadata and a dry-run-only extension to `start_llama_server.ps1`, then run CPU/GPU smoke tests only when the user confirms available GPU hardware and the installed `llama-server --help` output.
