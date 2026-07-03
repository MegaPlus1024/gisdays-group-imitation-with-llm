# GPU Smoke Comparison

- pair: `second_model->second_model`
- scenario: `configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json`
- interpretation: GPU smoke wall time was roughly comparable to the CPU baseline.
- CPU baseline note: CPU baseline means no explicit wrapper GPU placement flags. This is not the same as strict --device none; local llama-server help reports default GPU layers as auto.

| metric | CPU baseline | GPU smoke |
|---|---:|---:|
| status | `completed` | `completed` |
| pair_quality_score | 0.875562 | 0.875545 |
| execution_success_rate | 1.0 | 1.0 |
| total_errors | 2 | 2 |
| wall_time_ms | 8775.802 | 8716.17 |
| peak_ram_mb | 4712.328125 | 4714.621094 |
| peak_cpu_percent | 49.9 | 55.6 |
| peak_vram_mb | 6282.0 | 6282.0 |
| peak_gpu_utilization_percent | 99.0 | 98.0 |

speedup_wall_time_ratio: `1.006842`
