# Heavy Scenario Error Analysis v1

## 1. Scope

This document explains the errors observed in the heavy four-agent orchestrator/executor evidence before the runtime/capacity probe.

Primary artifact:

```text
experiments/multi_agent/orchestrator_executor/repeated_local_second_to_first_heavy_group_n3_workspace_policy_v1
```

Related matrix artifact:

```text
experiments/multi_agent/orchestrator_executor/pair_matrix_heavy_group_n3_workspace_policy_v1
```

Note: some earlier prompts and notes refer to `pair_matrix_heavy_group_n3_v1`; the committed local evidence for the bounded heavy matrix is the workspace-policy artifact above.

## 2. Summary

The `second_model -> first_model` heavy run completed all 3 trials, but every trial completed with executor failures:

| metric | value |
|---|---:|
| completed trials | 3 |
| failed trials | 0 |
| mean pair quality score | `0.820328` |
| mean execution success rate | `1.0` |
| mean final validation success rate | `0.454545` |
| mean executor call count | `11.0` |
| total errors | 18 |

Common failure modes:

| failure mode | count |
|---|---:|
| `validation_failed` | 18 |
| `write_path_outside_artifact_workspace` | 18 |
| `HTTPStatusError` | 18 |

The paired raw error stream contains 9 initial validation failures and 9 repair-call HTTP 400 failures. The aggregate failure-mode counter records both the generic validation failure and the specific issue code, so it reports 18 for each label.

## 3. Why `write_path_outside_artifact_workspace` Happened

The heavy scenario sets `write_path_policy: artifact_workspace_only`. That policy intentionally allows write actions only under the trial artifact workspace.

The executor selected write actions outside that workspace, for example:

```text
configs/multi_agent_fixtures/office_developer_maintenance/project_context.md
docs/ai/orchestrator_executor_pair_matrix_v1.md
```

The validator rejected those writes before execution. This is expected safety behavior, not an artifact-path bug. Read actions against local fixtures and docs remained allowed; write actions had the stricter workspace-only rule.

## 4. Repair Behavior

Each rejected initial action triggered one executor repair attempt. The repair attempts failed at the local executor endpoint with:

```text
HTTPStatusError: 400 Bad Request at http://127.0.0.1:8082/v1/chat/completions
```

The endpoint was not generally down: initial executor calls in the same trials succeeded, and managed servers were stopped cleanly after the run. The artifacts did not preserve the HTTP response body, so the exact server-side reason for the 400 is not known. This is a pipeline observability gap around repair calls, not evidence that the safety validator was wrong.

## 5. Why Execution Success Stayed `1.0`

`mean_execution_success_rate` counts actions that reached execution. The unsafe write actions failed validation and were not executed, so they do not enter that denominator.

The errors still affected quality:

- validation success dropped to `0.454545`;
- pair quality dropped to `0.820328`;
- failed steps remained failed after repair;
- the heavy matrix ranked `second_model -> first_model` below `second_model -> second_model`.

So `execution_success_rate = 1.0` does not mean the run was clean. It means the actions that passed validation executed successfully.

## 6. Behavior vs Pipeline Issue

The workspace write violations are legitimate behavior-quality penalties for the executor model. The model selected write paths outside the scenario's allowed artifact workspace.

The repair HTTP 400 failures are a runtime/pipeline robustness issue. The current artifacts prove the repair call was rejected, but they do not capture enough response detail to attribute the 400 to prompt size, request schema, server limits, or another llama-server condition.

## 7. Code-Fix Decision

No validator or path-policy fix was required before runtime measurement. Weakening the workspace-only policy would hide the safety signal.

The useful future fix is diagnostic, not behavioral: capture local endpoint response bodies for failed repair requests when possible.

## 8. Effect On Recommendation

The heavy evidence reduced confidence in `second_model -> first_model` as the default pair. It remained functional, but it produced more errors on the heavy scenario than `second_model -> second_model`.

This justified the follow-up runtime/capacity probe for both candidate pairs instead of recommending a pair from the original basic scenario alone.
