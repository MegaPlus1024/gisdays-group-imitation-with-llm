# Stress Quality/Latency Tradeoff

| pair | profile | concurrency | quality | wall_time_ms | errors | throughput_runs_per_minute | verdict | score |
|---|---|---:|---:|---:|---:|---:|---|---:|
| `second_model->second_model` | `strict_cpu` | 1 | None | None | 2 | 0.0 | `failed` | -0.52 |
| `second_model->second_model` | `strict_cpu` | 2 | None | None | 2 | 0.0 | `failed` | -0.52 |
| `second_model->second_model` | `gpu_full_offload` | 1 | None | None | 2 | 0.0 | `failed` | -0.52 |
| `second_model->second_model` | `gpu_full_offload` | 2 | None | None | 2 | 0.0 | `failed` | -0.52 |
| `second_model->first_model` | `strict_cpu` | 1 | None | None | 2 | 0.0 | `failed` | -0.52 |
| `second_model->first_model` | `strict_cpu` | 2 | None | None | 2 | 0.0 | `failed` | -0.52 |
| `second_model->first_model` | `gpu_full_offload` | 1 | None | None | 2 | 0.0 | `failed` | -0.52 |
| `second_model->first_model` | `gpu_full_offload` | 2 | None | None | 2 | 0.0 | `failed` | -0.52 |

Recommendation status: `preliminary only`.
