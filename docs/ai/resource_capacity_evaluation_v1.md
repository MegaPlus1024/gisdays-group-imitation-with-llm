# Resource Capacity Evaluation v1

## 1. Purpose

This document summarizes the resource/capacity evidence layer for local LLM agents. It addresses the TZ questions about CPU-only feasibility, RAM/CPU needs, next-action latency, and a formula for estimating concurrent agents.

Primary artifact folder:

`experiments/model_behavior/resources/resource_capacity_v1`

## 2. Inputs

| input | path |
|---|---|
| office-worker repeated trials | `experiments/model_behavior/repeated_trials/office_worker_two_model_repair_n3_v1` |
| developer repeated trials | `experiments/model_behavior/repeated_trials/developer_project_maintenance_two_model_repair_n3_v1` |
| cross-scenario behavioral analysis | `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1` |
| model registry | `configs/evaluation_models.json` |

Models:

- `first_model`
- `qwen2_5_3b_instruct_q4_k_m`

Runtime probe status: `not_run`. The generated report uses existing repeated-trials resource summaries and current system snapshot only.

## 3. Command

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_resource_capacity.py `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,qwen2_5_3b_instruct_q4_k_m `
  --repeated-trials-root office_worker=experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --repeated-trials-root developer_project_maintenance=experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --cross-scenario-analysis experiments\model_behavior\cross_scenario\office_worker_developer_two_model_cross_scenario_v1 `
  --out-dir experiments\model_behavior\resources\resource_capacity_v1 `
  --label resource_capacity_v1 `
  --target-cpu-utilization-percent 70 `
  --reserved-system-ram-mb 4096 `
  --no-probe-runtime `
  --force
```

## 4. System Snapshot

Source: `experiments/model_behavior/resources/resource_capacity_v1/system_resource_snapshot.json`.

| field | value |
|---|---:|
| physical CPU count | 24 |
| logical CPU count | 24 |
| total RAM MB | 130436.711 |
| available RAM MB | 82560.059 |
| reserved RAM assumption MB | 4096 |
| effective available RAM MB | 78464.059 |

Platform: `Windows-10-10.0.19045-SP0`.

## 5. Resource Summary

| model_id | observations | mean selection latency ms | mean total step latency ms | mean wall time ms | mean RSS delta MB | mean CPU end % |
|---|---:|---:|---:|---:|---:|---:|
| `first_model` | 6 | 753.7495 | 755.302667 | 1484.923667 | 6.099833 | 5.95 |
| `qwen2_5_3b_instruct_q4_k_m` | 6 | 489.095667 | 489.742417 | 761.277167 | 5.205167 | 6.15 |

These observations come from scenario-run resource summaries, not a dedicated benchmark monitor.

## 6. CPU-Only Assessment

Short single-agent local runs have been demonstrated on the current CPU-oriented setup for both model ids. This supports a limited statement that CPU-only operation is possible for short experimental trajectories.

This does not prove:

- stable long-running CPU-only operation;
- concurrent multi-agent throughput;
- production capacity;
- browser/office automation performance.

## 7. Capacity Formula

Standalone formula document:

`docs/ai/multi_agent_capacity_formula.md`

The generated artifact also contains:

`experiments/model_behavior/resources/resource_capacity_v1/capacity_formula.md`

Conservative formula:

```text
effective_available_ram_mb = max(0, available_ram_mb - reserved_system_ram_mb)
ram_bound = floor(effective_available_ram_mb / (per_agent_model_ram_mb + per_agent_runtime_overhead_mb))
cpu_bound = floor(target_cpu_utilization_limit_percent / average_cpu_load_percent_per_agent)
estimated_concurrent_agents = min(ram_bound, cpu_bound)
```

## 8. Capacity Estimate

| model_id | model RAM lower-bound MB | overhead MB | CPU %/agent | RAM bound | CPU bound | estimated agents | bottleneck | confidence |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `first_model` | 1065.56 | 128 | 5.95 | 65 | 11 | 11 | cpu | low |
| `qwen2_5_3b_instruct_q4_k_m` | 1840.499 | 128 | 6.15 | 39 | 11 | 11 | cpu | low |

Interpretation:

- Current formula is CPU-bound at the selected 70% target utilization.
- The RAM bound is not the bottleneck on this machine under the current assumptions.
- Confidence remains low because there was no real concurrent load test and no full runtime RSS probe.

## 9. Behavior/Resource Interpretation

- `qwen2_5_3b_instruct_q4_k_m` is faster and contract-valid, but current behavioral artifacts show zero execution success.
- `first_model` has some execution usefulness in one scenario, but weaker validity and higher latency.
- Resource numbers alone are not enough to choose a final model.
- Capacity should be considered together with behavioral quality.

## 10. Limitations

- Runtime probe was not run.
- Model RAM is estimated from GGUF file size, not measured `llama-server` RSS.
- CPU observations are lightweight system snapshots, not isolated process profiling.
- No true concurrent multi-agent load test was run.
- No long-running stability test was run.
- No GPU measurements were taken.
- Browser remains simulated-only and office behavior remains stub/file-based.

## 11. Next Step

Use this as the resource component for the final management report, or run an optional controlled multi-agent capacity smoke test if more evidence is required before final reporting.
