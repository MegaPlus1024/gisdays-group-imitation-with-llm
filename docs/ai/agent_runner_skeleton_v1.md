# Agent Runner Skeleton v1

## Purpose

Define a minimal coordination layer that runs one decision step and returns structured runner outputs without executing actions.

## Why Agent Runner exists

We already have decision and validation components. Runner v1 provides the first controlled integration point between them.

## Position in architecture

AgentState -> Agent decision -> AgentStepResult -> optional ScriptRegistry validation -> RunnerStepResult

## Relationship to Orchestrator

Orchestrator focuses on flow between orchestrator and agent. AgentRunner focuses on one-step decision plus optional registry validation.

## Relationship to Agent

AgentRunner depends on injected `Agent` and calls `decide_next_action(...)`. It does not create `LocalLLMClient`.

## Relationship to ScriptRegistry

If `validate_actions=true`, AgentRunner validates `NextAction` using `validate_next_action_against_registry`.

## Relationship to future Executor

When decision + validation succeed, AgentRunner returns `pending_execution`. Future Executor will consume this and perform real action execution.

## Runner config

`AgentRunnerConfig` controls max steps, validation switch, registry path, and stop behavior flags. `execute_actions` is forbidden in v1.

## Runner step result

`RunnerStepResult` captures:
- decision outcome
- optional validation result
- next action if ready for future execution
- normalized error fields on failures

## Run result

`RunnerRunResult` captures run-level summary and step list with helper counters.

## V1 behavior

- one-step skeleton behavior
- no history mutation
- no retries
- no execution
- no helper dispatch
- stop with:
  - `pending_execution` for valid step
  - `validation_failed` for validation rejection
  - `decision_failed` for agent decision failure

## What this does not implement

- AgentRunner v1 does not execute actions.
- It does not update history.
- It does not implement retries.
- It does not create LocalLLMClient itself.
- It uses dependency injection.
- It can validate NextAction through ScriptRegistry.
- It returns pending_execution when a validated action is ready for a future Executor.
- Future Executor / History Logger will consume RunnerStepResult.

## Example usage

```python
from agent.runner import AgentRunner, AgentRunnerConfig
from agent.state import load_agent_state
from agent.agent import Agent
from agent.llm_client import LocalLLMClient

state = load_agent_state("configs/agent_state.example.json")
client = LocalLLMClient()  # real use requires running llama-server
agent = Agent(client)
runner = AgentRunner(agent=agent, config=AgentRunnerConfig())
result = runner.run_one_step(state, run_id="demo_run")
```

## Done criteria

- can run one fake-agent step
- can validate via script registry
- returns `pending_execution` for valid action
- returns `validation_failed` / `decision_failed` for failures

## Next step

Add future Executor and History Logger layers that consume `RunnerStepResult` without changing this boundary contract.
