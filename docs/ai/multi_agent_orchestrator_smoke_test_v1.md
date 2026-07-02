# Multi-agent orchestrator smoke test v1

## Purpose
Provide a deterministic multi-agent smoke layer that runs multiple agent specs sequentially with injected fake runners and produces stable aggregate results.

## Why multi-agent orchestrator smoke exists
We need a lightweight boundary test for multi-agent control flow before any production scheduler or concurrency is introduced.

## Position in architecture
`AgentState/RoleTemplate -> injected runner_factory -> run_trajectory -> per-agent smoke result -> run summary`

## Relationship to AgentState
Each `MultiAgentRunSpec` carries one `AgentState` and agent identity.

## Relationship to RoleTemplate
Role linkage is optional (`role_template_id`) and treated as metadata in v1.

## Relationship to ActionSelector
The orchestrator does not call selector directly; it delegates to injected runners that may use selectors internally.

## Relationship to Role-constrained trajectory runner
Expected runner contract is `run_trajectory(agent_state, run_id=...)`. Any compatible fake or real test runner can be injected.

## Relationship to RecoveryLoop
Recovery behavior remains inside the runner layer. The orchestrator only collects runner outputs and failure states.

## V1 behavior
- Sequential only.
- Input-order execution.
- Per-agent success/failure capture.
- Stable aggregate status and counters.

## Failure isolation
By default, one failed agent does not stop other agents (`isolate_agent_failures=true`, `stop_on_first_agent_failure=false`).

## Sequential-only execution
`execution_mode` is fixed to `sequential` in v1. No parallel scheduling is implemented.

## What this does not implement
- Production scheduler.
- Real parallelism/concurrency.
- LocalLLMClient creation.
- Real script execution helpers.
- Browser/file/office/shell side effects.

## Example usage
```python
from agent.multi_agent_orchestrator import (
    MultiAgentOrchestratorSmoke,
    MultiAgentRunSpec,
)

orchestrator = MultiAgentOrchestratorSmoke(
    runner_factory=my_fake_runner_factory,
)
result = orchestrator.run_smoke(specs, run_id="smoke_demo")
```

## Done criteria
- Multiple fake agents run sequentially.
- Failure isolation and stop-on-first-failure behavior are tested.
- Deterministic summary methods are available.

## Next step
Integrate this smoke layer into a future evaluated multi-agent runner with explicit scheduling policies and richer telemetry.
