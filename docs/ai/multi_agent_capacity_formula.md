# Multi-Agent Capacity Formula

## 1. Purpose

This formula estimates how many local LLM agents can run concurrently on the current machine. It is required by the TZ resource block, but it must be treated as a planning estimate, not a measured production capacity result.

## 2. Conservative Formula

```text
effective_available_ram_mb = max(0, available_ram_mb - reserved_system_ram_mb)

ram_bound = floor(
  effective_available_ram_mb /
  (per_agent_model_ram_mb + per_agent_runtime_overhead_mb)
)

cpu_bound = floor(
  target_cpu_utilization_limit_percent /
  average_cpu_load_percent_per_agent
)

estimated_concurrent_agents = min(ram_bound, cpu_bound)
```

## 3. Shared Runtime Formula

If several agents share one already-loaded `llama-server` model process, model RAM is mostly shared:

```text
shared_runtime_ram_bound = floor(
  max(0, effective_available_ram_mb - shared_model_ram_mb) /
  per_agent_runtime_overhead_mb
)
```

The current experiments use one active local model endpoint per run. Until shared serving is explicitly tested, the conservative formula is the safer planning bound.

## 4. Variable Definitions

| variable | meaning |
|---|---|
| `available_ram_mb` | OS-reported available RAM at evaluation time |
| `reserved_system_ram_mb` | RAM reserved for OS and other apps |
| `effective_available_ram_mb` | RAM remaining after reserve |
| `per_agent_model_ram_mb` | model/runtime memory treated as per agent in conservative mode |
| `shared_model_ram_mb` | model memory treated as shared in shared-runtime mode |
| `per_agent_runtime_overhead_mb` | observed/default per-agent orchestration overhead |
| `average_cpu_load_percent_per_agent` | lightweight CPU estimate per active agent |
| `target_cpu_utilization_limit_percent` | planning CPU utilization ceiling |
| `ram_bound` | RAM-limited concurrent-agent estimate |
| `cpu_bound` | CPU-limited concurrent-agent estimate |

## 5. Numeric Example From Current Machine

Source artifact:

`experiments/model_behavior/resources/resource_capacity_v1/resource_capacity_evaluation.json`

System snapshot:

- physical CPU count: `24`
- logical CPU count: `24`
- total RAM MB: `130436.711`
- available RAM MB: `82560.059`
- reserved RAM assumption MB: `4096`
- effective available RAM MB: `78464.059`

`first_model`:

- model RAM lower-bound MB: `1065.56`
- per-agent overhead MB: `128`
- average CPU percent per agent: `5.95`
- RAM bound: `65`
- CPU bound: `11`
- estimated concurrent agents: `11`
- bottleneck: `cpu`
- confidence: `low`

`qwen2_5_3b_instruct_q4_k_m`:

- model RAM lower-bound MB: `1840.499`
- per-agent overhead MB: `128`
- average CPU percent per agent: `6.15`
- RAM bound: `39`
- CPU bound: `11`
- estimated concurrent agents: `11`
- bottleneck: `cpu`
- confidence: `low`

## 6. Warnings

- Model RAM is estimated from GGUF file size, not full `llama-server` RSS under load.
- CPU load uses lightweight system CPU snapshots, not isolated per-model CPU profiling.
- No true concurrent multi-agent load test was run.
- The estimate is a planning bound, not guaranteed throughput.
- The shared-runtime bound must not be used as a recommendation until shared concurrent serving is measured.
