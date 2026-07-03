# GPU vs CPU Stress Comparison

| pair | concurrency | CPU profile | GPU profile | CPU wall ms | GPU wall ms | speedup | CPU verdict | GPU verdict | interpretation |
|---|---:|---|---|---:|---:|---:|---|---|---|
| `second_model->first_model` | 1 | `strict_cpu` | `gpu_full_offload` | None | None | None | `failed` | `failed` | GPU profile was not stable for this row. |
| `second_model->first_model` | 2 | `strict_cpu` | `gpu_full_offload` | None | None | None | `failed` | `failed` | GPU profile was not stable for this row. |
| `second_model->second_model` | 1 | `strict_cpu` | `gpu_full_offload` | None | None | None | `failed` | `failed` | GPU profile was not stable for this row. |
| `second_model->second_model` | 2 | `strict_cpu` | `gpu_full_offload` | None | None | None | `failed` | `failed` | GPU profile was not stable for this row. |
