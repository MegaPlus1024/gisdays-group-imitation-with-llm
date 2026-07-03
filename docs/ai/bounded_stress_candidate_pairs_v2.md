# Bounded Stress Candidate Pairs v2

## 1. Purpose

This document records the corrected bounded stress probe after the v1 artifact-layout failure analysis.

Artifacts:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v2_fix_smoke
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v2
```

The probe is a bounded research smoke. It is not production sizing and not a final recommendation.

## 2. Why v1 Failed

v1 used deep stress artifact paths and hit practical Windows path-length limits when action execution wrote files under per-run workspaces. A representative failed absolute path was 276 characters. The same scenario succeeded in earlier repeated heavy runs with shorter paths.

See:

```text
docs/ai/bounded_stress_failure_analysis_v1.md
```

## 3. Fixes Made

- Stress batch artifacts now use short paths: `<out_root>/ba/<batch_slug>/gNNN`.
- Pair/profile/concurrency names remain in JSON/CSV metadata.
- `run_index.json` records `trial_artifact_path`, `workspace_path`, and `workspace_path_length`.
- Batch summaries record `workspace_strategy` and `fixture_status`.
- Pipeline manifests record `workspace_path`, `workspace_relative_path`, `workspace_policy`, `fixture_strategy`, and `fixture_paths`.
- Failed runs are classified with `failed_stage`, `failure_reason`, `missing_path`, and `missing_path_length`.
- Active CPU profile was renamed to `cpu_requested_device_none`.

## 4. Runtime Profiles and CPU/GPU Caveat

| profile | status |
|---|---|
| `cpu_requested_device_none` | Emits `--device none` through wrapper `-CpuOnly`, but strict CPU-only execution is not proven. Device-level GPU telemetry still showed activity. |
| `gpu_full_offload` | Emits `--n-gpu-layers 999 --main-gpu 0 --split-mode none` and showed high GPU telemetry. |

The old `strict_cpu` profile name is historical only and is no longer active in `configs/runtime_profiles.json`.

## 5. Minimal Fix Smoke Result

Artifact:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v2_fix_smoke
```

| pair | profile | concurrency | completed | failed | mean_pair_quality_score | mean_execution_success_rate | total_errors | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `second_model -> first_model` | `gpu_full_offload` | 1 | 1 | 0 | `0.820233` | `1.0` | 6 | `unstable` |

This smoke proves the v1 harness path failure is fixed: the local run completed and no workspace `FileNotFoundError` occurred. The remaining errors are scenario/model validation and repair-output behavior, not missing workspace files.

## 6. Bounded Stress v2 Result

Artifact:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v2
```

| pair | profile | concurrency | completed | failed | mean_pair_quality_score | mean_execution_success_rate | total_errors | mean_wall_time_ms | peak_ram_mb | peak_vram_mb | stability_verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `second_model -> second_model` | `cpu_requested_device_none` | 1 | 2 | 0 | `0.895833` | `1.0` | 0 | `173322.9835` | `8092.609374` | `1715.0` | `stable` |
| `second_model -> second_model` | `cpu_requested_device_none` | 2 | 0 | 2 | null | null | 3 | `72636.735` | `7579.277344` | `1715.0` | `failed` |
| `second_model -> second_model` | `gpu_full_offload` | 1 | 2 | 0 | `0.875198` | `1.0` | 4 | `9134.7655` | `5261.96875` | `6420.0` | `stable` |
| `second_model -> second_model` | `gpu_full_offload` | 2 | 2 | 0 | `0.144059` | `0.0` | 16 | `7042.8715` | `4023.90625` | `6422.0` | `unstable` |
| `second_model -> first_model` | `cpu_requested_device_none` | 1 | 2 | 0 | `0.778125` | `1.0` | 12 | `97962.6415` | `6225.347656` | `1715.0` | `unstable` |
| `second_model -> first_model` | `cpu_requested_device_none` | 2 | 1 | 1 | `0.775` | `1.0` | 8 | `82547.034` | `5824.042969` | `1715.0` | `unstable` |
| `second_model -> first_model` | `gpu_full_offload` | 1 | 2 | 0 | `0.820153` | `1.0` | 12 | `7097.973` | `4070.460938` | `5482.0` | `unstable` |
| `second_model -> first_model` | `gpu_full_offload` | 2 | 2 | 0 | `0.146138` | `0.0` | 16 | `5358.1425` | `3122.789062` | `5479.0` | `unstable` |

## 7. Stability and Capacity Interpretation

Stable rows:

- `second_model -> second_model` with `cpu_requested_device_none` at concurrency 1.
- `second_model -> second_model` with `gpu_full_offload` at concurrency 1.

No stable concurrency 2 row was observed. GPU concurrency 2 completed but quality collapsed and execution success rate was 0.0, so it is not usable as stable capacity evidence.

For `second_model -> first_model`, no stable row was observed in v2. The runs completed at several levels, but validation/repair and endpoint-style errors made the rows unstable.

## 8. Remaining Limitations

- Concurrency level 4 remained skipped.
- `cpu_requested_device_none` is not strict CPU proof.
- GPU telemetry is device-level and can include unrelated desktop/driver activity.
- Endpoint/HTTP 400 repair failures are still present in local model behavior.
- The heavy scenario remains a short bounded workflow, not a long-duration workload.
- No final model/runtime recommendation is made from this stress run.

## 9. Next Step

Investigate the remaining model-output failure modes under concurrency 2, especially repair `HTTPStatusError` and quality collapse in GPU full-offload concurrency 2. Keep v2 as preliminary stress evidence only.
