# Orchestrator/Executor Runtime and Capacity Probe v1

## 1. Purpose

Compare candidate orchestrator/executor pairs after simple and heavy scenario evidence.

## 2. Candidate pairs

- `second_model->first_model`
- `second_model->second_model`

## 3. Runtime protocol

- probe_id: `runtime_probe_candidate_pairs_v1`
- mode: `local`
- models_config_path: `configs\evaluation_models.json`
- server management: managed two local llama-server endpoints per measured pair when run in local mode.
- telemetry: per-process RSS/CPU sampled with psutil when available.
- capacity estimate: derived from measured peak pair RSS and system RAM snapshot; it is not a concurrent stress test.

Scenarios:

- `simple`: `configs\multi_agent_scenarios\office_developer_group_basic.json`
- `heavy`: `configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json`

## 4. Runtime results table

| pair | scenario | completed_trials | mean_pair_quality_score | mean_execution_success_rate | total_errors | mean_wall_time_ms | peak_ram_mb_pair | peak_cpu_percent_pair |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `second_model->first_model` | `simple` | 3 | 0.889947 | 1.0 | 0 | 2056.198667 | 3370.539063 | 51.5 |
| `second_model->second_model` | `simple` | 3 | 0.887296 | 1.0 | 0 | 2552.921333 | 4442.996094 | 57.1 |
| `second_model->first_model` | `heavy` | 3 | 0.820122 | 1.0 | 18 | 7057.967 | 4390.257813 | 60.6 |
| `second_model->second_model` | `heavy` | 3 | 0.875509 | 1.0 | 6 | 8699.126667 | 5675.605469 | 51.5 |

## 5. Capacity estimate

| pair | estimated pairs by RAM | estimated agents by RAM | bottleneck | confidence |
|---|---:|---:|---|---|
| `second_model->first_model` | 28 | 112 | `unknown` | `medium` |
| `second_model->second_model` | 22 | 88 | `unknown` | `medium` |

## 6. Quality vs cost tradeoff

| pair | mean_quality | total_errors | peak_ram_mb_pair | mean_wall_time_ms | quality_cost_score |
|---|---:|---:|---:|---:|---:|
| `second_model->second_model` | 0.881402 | 6 | 5675.605469 | 5626.024 | 0.687916 |
| `second_model->first_model` | 0.855035 | 18 | 4390.257813 | 4557.082833 | 0.570069 |

Recommendation status: `preliminary only`.

## 7. GPU readiness

- GPU runtime measured in this probe: no.
- GPU audit is recorded separately in `gpu_runtime_status.json` and `docs/ai/gpu_runtime_readiness_audit.md`.
- GPU is likely useful for throughput/capacity, but current CPU local group evidence is already functional.

## 8. Recommendation status

`preliminary only`. Runtime evidence is sufficient for a preliminary local prototype recommendation only, not for production sizing.

## 9. Limitations

- Short local runtime probe, not a production stress test.
- No external network, real browser automation, or real office automation was used.
- Capacity is estimated from measured short-run telemetry, not measured concurrency.
- GPU was audited separately but not used for these local measurements.
