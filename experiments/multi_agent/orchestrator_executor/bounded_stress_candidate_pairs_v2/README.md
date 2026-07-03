# Bounded Stress Candidate Pairs

- probe_id: `bounded_stress_candidate_pairs_v2`
- mode: `local`
- scenario: `configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json`
- server strategy: two separate local endpoints per pair, including same-model pairs.
- bounded smoke only; not a production recommendation.
- skipped_concurrency_levels: `[4]`
- skip_reason: `bounded v2 keeps level 4 skipped until levels 1 and 2 are interpreted`

Primary files:

- `stress_probe_index.json` / `.csv`
- `stress_batch_metrics.json` / `.csv`
- `stress_summary_by_pair_profile.json` / `.csv`
- `runtime_profile_validation.json`
- `gpu_vs_cpu_stress_comparison.md`
- `capacity_stress_estimates.json` / `.csv`
