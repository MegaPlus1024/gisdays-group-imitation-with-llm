# Role-constrained trajectory run v1

## Purpose
Provide a deterministic multi-step action-selection trajectory under role and registry constraints, without executing actions.

## Why role-constrained trajectory exists
Single-step selection is insufficient for trajectory behavior checks. This layer validates short decision sequences while preserving safety boundaries.

## Position in architecture
Config/RoleTemplate -> ActionSelector -> RoleConstrainedTrajectoryRunner -> updated AgentState history -> TrajectoryRunResult

## Relationship to RoleTemplate
Runner can load a role template and pass selection through the injected selector path that already applies role/registry validation.

## Relationship to ActionSelector
Runner delegates each step to `selector.select_action(current_state)` and never calls llama-server directly.

## Relationship to AgentState.history
Runner appends synthetic history entries to a copied state after successful selections and increments `current_step`.

## Relationship to ExecutionHistory
If `write_history_logs=true` and a logger is injected, selection outcomes are written as synthetic history records only.

## Relationship to future Executor
Executor will be a separate later layer. This runner does not execute any action.

## V1 behavior
- sequential short trajectory (`max_steps`)
- stop conditions on selection/validation/repeat based on config
- repeated action detection by exact `action + parameters`
- deterministic state-copy update behavior

## Stop conditions
- validation failure (if configured)
- selection failure (if configured)
- repeated action detected (if configured)
- max steps reached

## Repeated action detection
Exact repeats are detected using `action` and `parameters` equality. `reason` and `expected_result` are ignored.

## What this does not implement
- This layer does not execute actions.
- It does not call file/browser/office/shell helpers.
- It does not require llama-server in tests.
- It updates a copied AgentState with history, not the original input state.
- It stops on role/registry validation failure when configured.
- Future trajectory runner/executor will generalize this into real action execution.

## Example usage
```python
from agent.role_constrained_trajectory import (
    RoleConstrainedTrajectoryRunner,
    RoleConstrainedTrajectoryConfig,
)
from agent.state import load_agent_state

state = load_agent_state("configs/agent_state.example.json")
runner = RoleConstrainedTrajectoryRunner(selector=my_selector, config=RoleConstrainedTrajectoryConfig())
result = runner.run_trajectory(initial_state=state, run_id="demo_run")
```

## Done criteria
- trajectory can run 2-3 synthetic decision steps with fake selector
- repeated actions are detected
- selection/validation failure stop behavior is enforced
- input state is not mutated

## Next step
Integrate a future executor layer and semantic action validation loop on top of this boundary.
