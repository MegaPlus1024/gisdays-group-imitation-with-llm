# GPU Smoke Second-to-Second Heavy v1

- pair: `second_model->second_model`
- scenario: `configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json`
- CPU baseline and GPU smoke are both short N=1 local probes.
- This is not a stress test and not a production recommendation.
- CPU baseline means no explicit wrapper GPU placement flags, not strict `--device none`.

Primary files:

- `gpu_smoke_comparison.json`
- `gpu_smoke_comparison.md`
- `cpu_baseline/`
- `gpu_smoke/`
- `docs/ai/gpu_smoke_second_to_second_heavy_v1.md`
