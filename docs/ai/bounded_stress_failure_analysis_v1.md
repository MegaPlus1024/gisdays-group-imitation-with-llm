# Bounded Stress Failure Analysis v1

## Summary

Artifact:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v1
```

The v1 bounded stress probe failed because the stress harness created artifact paths that were too deep for normal Windows path handling. The failures are a harness/workspace artifact-layout bug, not evidence that the candidate models cannot run the heavy group scenario.

## Failed Stage

The failed stage was artifact workspace file creation during group trial execution.

Representative failed path:

```text
experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v1/second_model__first_model/gpu_full_offload/concurrency_1/group_runs/run_001/runs/trial_001/workspace/office_agent_1_executor_note.md
```

On the local absolute path this was 276 characters. The parent workspace path was 244 characters. A manual write probe to the same directory failed with a Windows path error even though the workspace directory existed.

## Evidence

Failed v1 batch evidence:

- `bounded_stress_candidate_pairs_v1/.../run_index.json`
- `bounded_stress_candidate_pairs_v1/.../batch_summary.json`
- `bounded_stress_candidate_pairs_v1/.../runs/trial_001/trial_error.json`

These artifacts report `FileNotFoundError` for workspace files such as `workspace/office_agent_1_executor_note.md`.

Successful baseline evidence:

- `repeated_local_second_to_first_heavy_group_n3_workspace_policy_v1`
- `pair_matrix_heavy_group_n3_workspace_policy_v1`

The successful repeated heavy path for a comparable workspace note was 232 characters and did not hit the Windows path limit.

Additional offline reproduction:

- Before the fix, fake stress using the v1 deep layout reproduced the same `FileNotFoundError`.
- After the fix, fake stress completed with `completed=1`, `failed=0`, and workspace path length 190.

## Root Cause

Root cause: the stress runner nested artifacts as:

```text
<out_root>/<pair_id>/<profile_id>/concurrency_N/group_runs/run_NNN/runs/trial_001/workspace/<file>
```

For long labels such as `bounded_stress_candidate_pairs_v1`, this pushed common workspace note paths beyond the practical Windows `MAX_PATH` limit. The pipeline's fixture and validator logic were not the cause.

## Classification

- Scenario load: passed.
- Fixture availability: passed.
- Server startup: passed.
- Orchestrator/executor model quality: not measured by v1 because the harness path failure invalidated the run.
- Workspace provisioning: failed through over-deep artifact path layout.
- Concurrency race: not supported by evidence; the same issue reproduced at concurrency 1 and in fake mode.
- Runtime profile handling: not the cause of the `FileNotFoundError`.

## Fix Plan

Implemented in v2:

- use short stress artifact directories under `<out_root>/ba/<batch_slug>/gNNN`;
- keep readable pair/profile/concurrency metadata in JSON/CSV indices;
- record per-run `workspace_path` and path length in `run_index.json`;
- record shared read-only fixture strategy and per-run workspace strategy in batch summaries and pipeline manifests;
- classify failed runs with `failed_stage`, `failure_reason`, `missing_path`, and `missing_path_length`;
- rename active CPU profile from `strict_cpu` to `cpu_requested_device_none` because strict CPU-only execution is not proven by device-level GPU telemetry.
