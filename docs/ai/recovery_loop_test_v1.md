# Recovery loop test v1

## Purpose
`recovery_loop.py` adds a deterministic harness to prove that failures can be mapped to `FailureEvent`, evaluated by `RecoveryPolicy`, and converted into retry-or-stop outcomes.

## Why recovery loop tests exist
The project already had error types and policy rules, but no tight test harness that verifies the full decision path from selection/bridge failure to final recovery status.

## Position in architecture
`AgentState -> ActionSelector -> NextAction -> ScriptExecutionBridge -> FailureEvent -> RecoveryPolicy -> RecoveryLoopResult`

## Relationship to RecoveryPolicy
The harness does not replace policy logic. It consumes policy decisions and applies simple control flow: retry once (if allowed) or stop with a deterministic terminal status.

## Relationship to ActionSelector
The harness calls injected `selector.select_action(agent_state)` and does not create `LocalLLMClient`.

## Relationship to ScriptExecutionBridge
The harness calls injected `bridge.execute_next_action(...)`. In tests this is a fake bridge, not real file/browser/office/shell execution.

## Relationship to ExecutionHistory
History logging is optional and off by default. Core behavior does not depend on logging.

## FailureEvent mapping
- Selection failures map to `invalid_json` / `malformed_model_response` / `unsafe_action` / `unknown_action` / `invalid_action_parameters` using deterministic rules.
- Bridge failures map from validation/dispatch/execution outcomes, using normalized `recovery_category` when available.

## Retry budget behavior
- `max_attempts` includes the first attempt.
- Retry actions (`retry`, `retry_with_repair_prompt`) only continue when:
  - `enable_retry=true`
  - current attempt is below `max_attempts`
- Otherwise run ends with `retry_budget_exhausted` or policy stop status.

## V1 behavior
- Supports one-step recovery loop.
- Supports retry/stop decisions.
- Returns structured `RecoveryLoopResult` with attempt history.

## What this does not implement
- Production retry orchestration.
- Real script helper execution.
- LocalLLMClient construction.
- Fallback model logic.
- Prompt repair logic.
- Full autonomous runner.

## Example usage
```python
from agent.recovery import RecoveryPolicy
from agent.recovery_loop import RecoveryLoopHarness

harness = RecoveryLoopHarness(
    selector=fake_selector,
    bridge=fake_bridge,
    recovery_policy=RecoveryPolicy(),
)
result = harness.run_once_with_recovery(agent_state)
```

## Done criteria
- Deterministic tests cover retry and stop behavior.
- No llama-server or model files required.
- No real file/browser/office/shell actions are executed.

## Next step
Integrate this harness into a future runner layer that can apply recovery decisions across multi-step trajectories.
