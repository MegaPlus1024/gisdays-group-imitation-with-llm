# Repeated Local Orchestrator/Executor Group Trials v1

## 1. Purpose

This repeated run targets the TZ group-agent gap by checking whether one local orchestrator/executor pair can repeat the same short group scenario more than once.

## 2. Model pair

- orchestrator: `second_model` / Qwen2.5 3B Instruct Q4_K_M
- executor: `second_model` / Qwen2.5 1.5B Instruct Q4_K_M

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
| `trial_001` | `completed_with_failures` | `False` | `True` | 9 | 7 | 7 | 0.875217 | NextActionValidationError: Next-action JSON failed schema validation: 1 validation error for NextAction
expected_result
  Field required [type=missing, input_value={'action': 'read_file', '...for the assigned task.'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing; NextActionJSONError: Invalid JSON output: Unterminated string starting at: line 3 column 3 (char 29); developer_agent_1 NextActionValidationError: Next-action JSON failed schema validation: 1 validation error for NextAction
expected_result
  Field required [type=missing, input_value={'action': 'read_file', '...for the assigned task.'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing; developer_agent_1 NextActionJSONError: Invalid JSON output: Unterminated string starting at: line 3 column 3 (char 29) |

## 6. Aggregate metrics

- mean_pair_quality_score: `0.875217`
- std_pair_quality_score: `0.0`
- mean_final_validation_success_rate: `0.777778`
- mean_execution_success_rate: `1.0`
- total_errors: `2`
- total_safety_violations: `0`

## 7. Failure modes

`{'NextActionValidationError': 2, 'NextActionJSONError': 2}`

## 8. Interpretation

What this proves if trials succeed: the local group pair pipeline is repeatable for this one pair and one scenario.

What it does not prove:

- production readiness;
- GPU throughput;
- concurrent capacity;
- final best pair.

## 9. Next step

If stable, compare more pairs or run a measured GPU/capacity smoke. If unstable, analyze failures and repeat the same protocol.
