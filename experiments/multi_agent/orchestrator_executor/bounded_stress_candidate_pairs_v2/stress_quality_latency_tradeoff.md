# Stress Quality/Latency Tradeoff

| pair | profile | concurrency | quality | wall_time_ms | errors | throughput_runs_per_minute | verdict | score |
|---|---|---:|---:|---:|---:|---:|---|---:|
| `second_model->second_model` | `cpu_requested_device_none` | 1 | 0.895833 | 173322.9835 | 0 | 0.326452 | `stable` | 0.90054 |
| `second_model->second_model` | `gpu_full_offload` | 1 | 0.875198 | 9134.7655 | 4 | 3.053131 | `stable` | 0.893097 |
| `second_model->first_model` | `gpu_full_offload` | 1 | 0.820153 | 7097.973 | 12 | 3.473183 | `unstable` | 0.520106 |
| `second_model->first_model` | `cpu_requested_device_none` | 2 | 0.775 | 82547.034 | 8 | 0.446756 | `unstable` | 0.452496 |
| `second_model->first_model` | `cpu_requested_device_none` | 1 | 0.778125 | 97962.6415 | 12 | 0.554925 | `unstable` | 0.416226 |
| `second_model->first_model` | `gpu_full_offload` | 2 | 0.146138 | 5358.1425 | 16 | 4.770196 | `unstable` | -0.169502 |
| `second_model->second_model` | `gpu_full_offload` | 2 | 0.144059 | 7042.8715 | 16 | 4.366821 | `unstable` | -0.186776 |
| `second_model->second_model` | `cpu_requested_device_none` | 2 | None | 72636.735 | 3 | 0.0 | `failed` | -0.526558 |

Recommendation status: `preliminary only`.
