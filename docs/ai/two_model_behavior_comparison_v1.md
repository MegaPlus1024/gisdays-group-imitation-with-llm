# Two-Model Behavior Comparison v1

## 1. Purpose

This report compares two real local-model scenario artifacts under the TZ requirement to evaluate multiple local LLMs of different sizes by action quality, JSON/NextAction validity, registry acceptance, role compliance, coherence, diversity, repetition, history usage, latency/resource metadata, and observed failure modes.

No model was started for this comparison. The report reads existing artifacts only.

## 2. Inputs

| Model | Artifact folder |
|---|---|
| `first_model` | `experiments/model_behavior/results/office_worker_first_model_run_002_repair_v1` |
| `qwen2_5_3b_instruct_q4_k_m` | `experiments/model_behavior/results/office_worker_qwen2_5_3b_run_001_repair_v1` |

Generated comparison artifact:

`experiments/model_behavior/comparisons/office_worker_two_model_repair_v1`

## 3. Protocol

The comparison artifact reports `protocol_compatible=true`.

| Protocol item | Value |
|---|---|
| scenario | `configs\evaluation_scenarios\office_worker_basic_session.json` |
| role/profile | same office-worker scenario/profile from run artifacts |
| mode | `local` |
| max_steps | 5 |
| execute-actions | true |
| repair_attempts | 1 |
| evaluator | `normal_activity_trajectory_evaluator_v1` |
| safety policy | write actions restricted to each run's experiment workspace |

## 4. Summary Table

| Metric | `first_model` | `qwen2_5_3b_instruct_q4_k_m` |
|---|---:|---:|
| steps | 3 | 2 |
| initial_validation_accept_rate | 0.0 | 1.0 |
| final_validation_accept_rate | 0.666667 | 1.0 |
| execution_success_rate | 1.0 | 0.0 |
| normal_activity_score | 0.43 | 0.0 |
| diversity_score | 0.75 | 0.5 |
| repetition_score | 0.725 | 0.725 |
| sequence_coherence_score | 0.0 | 0.0 |
| history_usage_score | 0.0 | 1.0 |
| role_fit_score | 1.0 | 1.0 |
| average_selection_latency_ms | 728.402 | 566.875 |
| average_total_step_latency_ms | 729.737 | 567.584 |
| stop_reason | `validation_failed_after_repair` | `Reached max_consecutive_failures limit.` |

## 5. Main Findings

- `first_model` had worse first-attempt action validity: initial validation accept rate was `0.0`.
- `first_model` recovered two steps through the repair policy and executed two actions successfully.
- `qwen2_5_3b_instruct_q4_k_m` had better first-attempt and final validation rates: both were `1.0`.
- `qwen2_5_3b_instruct_q4_k_m` had lower latency in this run, but both execution attempts failed because the model repeatedly selected a missing file.
- Both models had weak sequence coherence: `sequence_coherence_score` was `0.0` for both.
- Neither model produced a complete five-step trajectory.
- This is enough for a first comparison artifact, but not enough for a final recommended configuration.

## 6. Failure Modes

### first_model

Observed pattern:

- Step 1 initial action omitted required `read_file.parameters.path`; repair produced `read_file docs/ai/model_registry.md`; execution succeeded.
- Step 2 repeated the same missing-parameter pattern; repair again produced `read_file docs/ai/model_registry.md`; execution succeeded.
- Step 3 selected `create_file docs/ai/model_registry.md`; safety policy rejected the write as `write_path_outside_workspace`.
- Repair for step 3 repeated the unsafe target; run stopped with `validation_failed_after_repair`.

Dominant failure mode: poor first-attempt parameter completeness, followed by an unrecovered workspace safety violation.

### qwen2_5_3b_instruct_q4_k_m

Observed pattern:

- Step 1 selected valid `read_file docs/notes.txt`; execution failed with `file_not_found`.
- Step 2 repeated `read_file docs/notes.txt`; execution failed again with `file_not_found`.
- Stop criteria halted the run with `Reached max_consecutive_failures limit.`

Dominant failure mode: valid action shape but poor grounding in available files, plus repeated same failed action/parameters.

## 7. Behavioral Interpretation

The 3B model looked stronger at the contract layer: JSON parse, NextAction shape, registry acceptance, and role compliance were clean on both steps. However, it did not achieve useful execution because it repeatedly targeted a non-existent file.

`first_model` looked weaker at first-attempt validity, but the repair policy recovered two usable actions and produced two successful executions. Its final stop was a safety-policy rejection, not a runtime crash.

No single winner should be declared from one short scenario. Metric-level winners are useful, but the confidence is low until repeated trials and more scenarios are available.

## 8. Resource/Latency Interpretation

| Metric | Better model in this run | Evidence |
|---|---|---|
| average_selection_latency_ms | `qwen2_5_3b_instruct_q4_k_m` | 566.875 ms vs 728.402 ms |
| average_total_step_latency_ms | `qwen2_5_3b_instruct_q4_k_m` | 567.584 ms vs 729.737 ms |
| wall_time_ms | `qwen2_5_3b_instruct_q4_k_m` | 1147.515 ms vs 2201.756 ms |

These numbers are per-run lightweight metadata, not benchmark results. They should not be used for CPU-only capacity claims without repeated runs and a dedicated monitoring method.

## 9. Limitations

- One scenario only.
- One run per model only.
- Short runs: neither model reached all five steps.
- No repeated trials or statistical confidence interval.
- No multi-agent experiment.
- No benchmark/capacity estimate.
- Browser behavior remains simulated-only.
- Office behavior remains stub/file-based.
- Resource summary is lightweight process/run metadata, not a benchmark monitor.

## 10. Next Step

Use the generated comparison artifact as the input for the next reporting step:

`experiments/model_behavior/comparisons/office_worker_two_model_repair_v1`

Recommended next work:

- Run role-compliance, coherence, and diversity reports across both artifacts.
- Repeat the same scenario multiple times per model.
- Add at least one additional scenario before recommending a configuration.
- Only after repeated real local runs, prepare a resource/capacity estimate.

## 11. Follow-up: repeated trials

The single-run comparison is valid as an initial evidence artifact, but it is insufficient for a recommendation because it does not measure repeatability or stability. The next protocol is documented in:

`docs/ai/repeated_trials_protocol_v1.md`

The repeated-trials target is:

`experiments/model_behavior/repeated_trials/office_worker_two_model_repair_n3_v1`

It repeats the same scenario three times per model with the same repair policy, execute-actions mode, safety policy, and evaluator. The resulting aggregate should be used for directional model comparison, while still avoiding final configuration claims until more scenarios and repeated runs are available.
