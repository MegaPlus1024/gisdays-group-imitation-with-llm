# Consolidated Behavioral Analysis

## Executive Summary

The repeated-trials artifacts show stable differences: first_model is repair-dependent but executes repaired actions, while qwen2_5_3b_instruct_q4_k_m has strong contract validity but repeats a missing-file action.

## Evidence Base

- `trials_root`: `<repo>\experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1`
- `model_count`: `2`
- `trials_per_model`: `{'first_model': 3, 'qwen2_5_3b_instruct_q4_k_m': 3}`
- `scenario_path`: `configs\evaluation_scenarios\developer_project_maintenance.json`
- `max_steps`: `5`
- `repair_attempts_per_step`: `1`
- `execute_actions`: `True`

## Summary Table

| Model | Role | Coherence | Diversity | Failure focus | Selection latency mean ms |
|---|---|---|---|---|---:|
| `first_model` | acceptable | failed | narrow | {'validation_failed_after_repair': 3} | 792.611333 |
| `qwen2_5_3b_instruct_q4_k_m` | strong | weak | template_like | {'Latest step error_type indicates unsafe behavior.': 3} | 459.744667 |

## Cross-Model Findings

- `summary`: The repeated-trials artifacts show stable differences: first_model is repair-dependent but executes repaired actions, while qwen2_5_3b_instruct_q4_k_m has strong contract validity but repeats a missing-file action.
- `contract_validity_winner`: qwen2_5_3b_instruct_q4_k_m
- `final_validity_winner`: qwen2_5_3b_instruct_q4_k_m
- `latency_winner`: qwen2_5_3b_instruct_q4_k_m
- `failure_patterns`: {'first_model': {'validation_failed_after_repair': 3}, 'qwen2_5_3b_instruct_q4_k_m': {'Latest step error_type indicates unsafe behavior.': 3}}
- `template_behavior`: {'first_model': ['low_action_family_diversity'], 'qwen2_5_3b_instruct_q4_k_m': ['repeated_same_action', 'repeated_same_parameters', 'low_action_family_diversity']}
- `coherence_verdicts`: {'first_model': 'failed', 'qwen2_5_3b_instruct_q4_k_m': 'weak'}

## What This Proves

- Repeated local model trials can be run and analyzed from artifacts.
- Behavioral differences are observable across models under the same protocol.
- Repair policy materially changes final validity for repair-dependent models.

## What This Does Not Prove

- One scenario only.
- Three trials per model is still a small sample.
- No multi-agent run.
- No benchmark or CPU-only capacity estimate.
- Browser behavior remains simulated-only.
- Office behavior remains stub/file-based.

## Recommendations For Next Experiment

- Add at least one more scenario, such as developer project maintenance or student research/reporting.
- Run N=3 or N=5 per model with the same protocol.
- Then compute cross-scenario aggregate behavior and resource summaries.
