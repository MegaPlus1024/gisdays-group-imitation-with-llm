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
| `trial_001` | `failed` | `False` | `False` | 0 | 0 | 0 | None | FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\m\\Documents\\local-llm-test-gisdays\\local-llm-agent-lab\\experiments\\multi_agent\\orchestrator_executor\\bounded_stress_candidate_pairs_v1\\second_model__second_model\\strict_cpu\\concurrency_1\\group_runs\\run_001\\runs\\trial_001\\per_agent_validation_results.jsonl' |

## 6. Aggregate metrics

- mean_pair_quality_score: `None`
- std_pair_quality_score: `None`
- mean_final_validation_success_rate: `0.0`
- mean_execution_success_rate: `0.0`
- total_errors: `1`
- total_safety_violations: `0`

## 7. Failure modes

`{'FileNotFoundError': 1}`

## 8. Interpretation

What this proves if trials succeed: the local group pair pipeline is repeatable for this one pair and one scenario.

What it does not prove:

- production readiness;
- GPU throughput;
- concurrent capacity;
- final best pair.

## 9. Next step

If stable, compare more pairs or run a measured GPU/capacity smoke. If unstable, analyze failures and repeat the same protocol.
