# Multi-Agent Capacity Formula

## Purpose

This formula gives a conservative planning estimate for how many local LLM agents can run concurrently on the current machine. It is not a measured multi-agent load test.

## Conservative Formula

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

## Shared Runtime Formula

If agents share one `llama-server` process and model instance, model memory is mostly shared:

```text
shared_runtime_ram_bound = floor(
  max(0, effective_available_ram_mb - shared_model_ram_mb) /
  per_agent_runtime_overhead_mb
)
```

## Variables

- `available_ram_mb`: OS-reported available RAM at evaluation time.
- `reserved_system_ram_mb`: RAM held back for the OS and other applications.
- `effective_available_ram_mb`: RAM available after the reserve.
- `per_agent_model_ram_mb`: model/runtime memory treated as per-agent in the conservative estimate.
- `shared_model_ram_mb`: model memory treated as shared in the optimistic shared-runtime estimate.
- `per_agent_runtime_overhead_mb`: observed or default per-agent orchestration overhead.
- `average_cpu_load_percent_per_agent`: lightweight CPU estimate per active agent.
- `target_cpu_utilization_limit_percent`: CPU utilization ceiling used for planning.

## Assumptions

- Conservative mode assumes one runtime/model process per active agent.
- Shared-runtime mode assumes multiple agents can use one loaded model endpoint.
- The current project usually talks to one `llama-server` endpoint per active local model run, so the conservative estimate should be used for planning unless shared serving is explicitly tested.
- The estimate is a planning bound, not guaranteed throughput.

## Numeric Example From Current Snapshot

For `first_model`:

- available RAM MB: `82560.059`
- reserved system RAM MB: `4096.0`
- effective available RAM MB: `78464.059`
- per-agent model RAM MB: `1065.56`
- per-agent runtime overhead MB: `128.0`
- average CPU load percent per agent: `5.95`
- target CPU utilization percent: `70.0`
- RAM bound: `65`
- CPU bound: `11`
- estimated concurrent agents: `11`

## Warning

This number must not be presented as production capacity until a real concurrent multi-agent load test is performed.
