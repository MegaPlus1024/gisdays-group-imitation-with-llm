# Consolidated Behavioral Analysis

## Executive Summary

The repeated-trials artifacts show stable differences: first_model is repair-dependent but executes repaired actions, while qwen2_5_3b_instruct_q4_k_m has strong contract validity but repeats a missing-file action.

## Evidence Base

- `trials_root`: `C:\Users\m\Documents\local-llm-test-gisdays\local-llm-agent-lab\experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1`
- `model_count`: `2`
- `trials_per_model`: `{'first_model': 3, 'qwen2_5_3b_instruct_q4_k_m': 3}`
- `scenario_path`: `configs\evaluation_scenarios\office_worker_basic_session.json`
- `max_steps`: `5`
- `repair_attempts_per_step`: `1`
- `execute_actions`: `True`

## Summary Table

| Model | Role | Coherence | Diversity | Failure focus | Selection latency mean ms |
|---|---|---|---|---|---:|
| `first_model` | acceptable | failed | template_like | {'validation_failed_after_repair': 3} | 714.887333 |
| `qwen2_5_3b_instruct_q4_k_m` | strong | failed | failure_loop | {'Reached max_consecutive_failures limit.': 3} | 518.446667 |

## Cross-Model Findings

- `summary`: The repeated-trials artifacts show stable differences: first_model is repair-dependent but executes repaired actions, while qwen2_5_3b_instruct_q4_k_m has strong contract validity but repeats a missing-file action.
- `contract_validity_winner`: qwen2_5_3b_instruct_q4_k_m
- `final_validity_winner`: qwen2_5_3b_instruct_q4_k_m
- `latency_winner`: qwen2_5_3b_instruct_q4_k_m
- `failure_patterns`: {'first_model': {'validation_failed_after_repair': 3}, 'qwen2_5_3b_instruct_q4_k_m': {'Reached max_consecutive_failures limit.': 3}}
- `template_behavior`: {'first_model': ['repeated_same_action', 'repeated_same_parameters', 'low_action_family_diversity', 'template_repetition'], 'qwen2_5_3b_instruct_q4_k_m': ['repeated_same_action', 'repeated_same_parameters', 'low_action_family_diversity', 'repeated_failure_pattern']}
- `coherence_verdicts`: {'first_model': 'failed', 'qwen2_5_3b_instruct_q4_k_m': 'failed'}

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
