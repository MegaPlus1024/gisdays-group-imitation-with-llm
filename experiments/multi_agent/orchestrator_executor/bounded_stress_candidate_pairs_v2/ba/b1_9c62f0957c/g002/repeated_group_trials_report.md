# Repeated Local Orchestrator/Executor Group Trials v1

## 1. Purpose

This repeated run targets the TZ group-agent gap by checking whether one local orchestrator/executor pair can repeat the same short group scenario more than once.

## 2. Model pair

- orchestrator: `second_model` / Qwen2.5 3B Instruct Q4_K_M
- executor: `first_model` / Qwen2.5 1.5B Instruct Q4_K_M

## 3. Scenario

`office_developer_group_basic_v1`

## 4. Protocol

- N=3 unless the run was interrupted or blocked.
- `max_group_steps=1`.
- `max_steps_per_agent=1`.
- Orchestrator and executor repair attempts are enabled according to the replay command.
- `execute-actions=true`.
- Local mode uses two loopback endpoints when server management is enabled.

## 5. Trial summary table

| trial_id | status | success | plan_valid | executor_calls | final_validation_success_count | execution_success_count | pair_quality_score | main_errors |
|---|---|---|---|---:|---:|---:|---:|---|
| `trial_001` | `completed_with_failures` | `False` | `True` | 11 | 5 | 5 | 0.82018 | validation_failed: write_path_outside_artifact_workspace; HTTPStatusError: Client error '400 Bad Request' for url 'http://127.0.0.1:8082/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400; developer_agent_1 validation_failed: write_path_outside_artifact_workspace; developer_agent_1 HTTPStatusError: Client error '400 Bad Request' for url 'http://127.0.0.1:8082/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400; developer_agent_2 validation_failed: write_path_outside_artifact_workspace; developer_agent_2 HTTPStatusError: Client error '400 Bad Request' for url 'http://127.0.0.1:8082/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400 |

## 6. Aggregate metrics

- mean_pair_quality_score: `0.82018`
- std_pair_quality_score: `0.0`
- mean_final_validation_success_rate: `0.454545`
- mean_execution_success_rate: `1.0`
- total_errors: `6`
- total_safety_violations: `0`

## 7. Failure modes

`{'validation_failed': 6, 'write_path_outside_artifact_workspace': 6, 'HTTPStatusError': 6}`

## 8. Interpretation

What this proves if trials succeed: the local group pair pipeline is repeatable for this one pair and one scenario.

What it does not prove:

- production readiness;
- GPU throughput;
- concurrent capacity;
- final best pair.

## 9. Next step

If stable, compare more pairs or run a measured GPU/capacity smoke. If unstable, analyze failures and repeat the same protocol.
