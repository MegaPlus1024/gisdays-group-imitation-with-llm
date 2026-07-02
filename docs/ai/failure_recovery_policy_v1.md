# Failure Recovery Policy v1

## Purpose
Define a consistent mapping from failure events to recovery decisions.

## Why recovery policy exists
Current layers can detect failures, but they need one shared policy for what should happen next at control-flow level.

## Relationship to LocalLLMClient
`LocalLLMClient` raises structured runtime and parsing errors. This policy maps those failures to decisions like `retry`, `fail_step`, or `abort_run`.

## Relationship to AgentStepResult
`AgentStepResult` captures step outcomes. Recovery policy decides how future runner/orchestrator logic should react to failure events.

## Failure categories
- invalid_json
- invalid_next_action_schema
- malformed_model_response
- model_request_error
- model_timeout
- llama_server_unreachable
- empty_model_output
- unknown_action
- invalid_action_parameters
- unsafe_action
- execution_error
- file_not_found
- permission_denied
- repeated_action_loop
- max_steps_exceeded
- unknown_error

## Recovery actions
- retry
- retry_with_repair_prompt
- fail_step
- skip_agent
- abort_run
- continue_run
- mark_for_review

## Default decision table
The default table is encoded in `default_recovery_policy()` and mirrored in `configs/failure_recovery_policy.example.json`.

## Retry budget
If `retry_count >= max_retries` for `retry` or `retry_with_repair_prompt`, the decision is converted to `fail_step` with an exhaustion reason.

## What is explicitly not implemented
- This policy does not execute retries yet.
- This policy does not execute actions.
- This policy does not implement fallback models.
- This policy does not implement Script Registry.
- It only maps failure events to decisions.
- Future agent runner/orchestrator will consume `RecoveryDecision`.

## Example usage
```python
from agent.recovery import FailureEvent, RecoveryPolicy

policy = RecoveryPolicy()
event = FailureEvent(
    category="invalid_json",
    source="LocalLLMClient",
    message="Model returned non-JSON text",
    agent_id="student_researcher_001",
    run_id="demo_run",
    step_index=1,
)
decision = policy.decide(event)
```

## Next step
Integrate this policy into a future runner layer that applies `RecoveryDecision` without mixing it with action execution.
