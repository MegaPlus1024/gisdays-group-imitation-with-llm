# GPU vs CPU Stress Comparison

| pair | concurrency | CPU profile | GPU profile | CPU wall ms | GPU wall ms | speedup | CPU verdict | GPU verdict | interpretation |
|---|---:|---|---|---:|---:|---:|---|---|---|
| `second_model->first_model` | 1 | `cpu_requested_device_none` | `gpu_full_offload` | 97962.6415 | 7097.973 | 13.801495 | `unstable` | `unstable` | GPU profile was not stable for this row. |
| `second_model->first_model` | 2 | `cpu_requested_device_none` | `gpu_full_offload` | 82547.034 | 5358.1425 | 15.405905 | `unstable` | `unstable` | GPU profile was not stable for this row. |
| `second_model->second_model` | 1 | `cpu_requested_device_none` | `gpu_full_offload` | 173322.9835 | 9134.7655 | 18.973994 | `stable` | `stable` | GPU profile was faster in wall time for this bounded row. |
| `second_model->second_model` | 2 | `cpu_requested_device_none` | `gpu_full_offload` | 72636.735 | 7042.8715 | 10.313511 | `failed` | `unstable` | GPU profile was not stable for this row. |
