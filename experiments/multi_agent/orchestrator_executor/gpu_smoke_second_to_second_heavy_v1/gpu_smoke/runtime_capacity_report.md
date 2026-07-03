# Orchestrator/Executor Runtime and Capacity Probe v1

## 1. Purpose

Compare candidate orchestrator/executor pairs after simple and heavy scenario evidence.

## 2. Candidate pairs

- `second_model->second_model`

## 3. Runtime protocol

- probe_id: `gpu_smoke`
- mode: `local`
- models_config_path: `configs\evaluation_models.json`
- server management: managed two local llama-server endpoints per measured pair when run in local mode.
- telemetry: per-process RSS/CPU sampled with psutil when available.
- capacity estimate: derived from measured peak pair RSS and system RAM snapshot; it is not a concurrent stress test.

Scenarios:

- `heavy`: `configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json`

## 4. Runtime results table

| pair | scenario | completed_trials | mean_pair_quality_score | mean_execution_success_rate | total_errors | mean_wall_time_ms | peak_ram_mb_pair | peak_cpu_percent_pair |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `second_model->second_model` | `heavy` | 1 | 0.875545 | 1.0 | 2 | 8716.17 | 4714.621094 | 55.6 |

## 5. Capacity estimate

| pair | estimated pairs by RAM | estimated agents by RAM | bottleneck | confidence |
|---|---:|---:|---|---|
| `second_model->second_model` | 26 | 104 | `unknown` | `medium` |

## 6. Quality vs cost tradeoff

| pair | mean_quality | total_errors | peak_ram_mb_pair | mean_wall_time_ms | quality_cost_score |
|---|---:|---:|---:|---:|---:|
| `second_model->second_model` | 0.875545 | 2 | 4714.621094 | 8716.17 | 0.710971 |

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
