# Orchestrator-Agent Boundary v1

## Purpose
Define the first strict control boundary for one decision step between orchestration flow and agent reasoning.

## Why the boundary exists
It separates responsibilities so runtime calls, flow control, and future execution concerns do not get mixed.

## Responsibilities of Orchestrator
- Own run-level flow (`run_id`, step dispatch).
- Build `AgentStepRequest`.
- Call `Agent.decide_next_action`.
- Return `AgentStepResult`.
- Do not directly call llama-server.

## Responsibilities of Agent
- Receive `AgentStepRequest`.
- Convert `AgentState` to prompt context.
- Call `LocalLLMClient.generate_next_action(...)`.
- Return structured `AgentStepResult`.
- Do not execute actions.

## What is explicitly out of scope
- Full agent loop.
- Script registry and semantic validation.
- Action execution.
- Parallel multi-agent scheduling.
- Browser/file/shell execution layers.

## Data flow
Orchestrator
  -> AgentStepRequest
  -> Agent
  -> LocalLLMClient
  -> NextAction
  -> AgentStepResult

## Error handling
- LocalLLMClient errors are captured by `Agent` and returned as failed `AgentStepResult`.
- Success requires `next_action`.
- Failure requires `error_type` and `error_message`.

## Example usage
```python
from agent.state import load_agent_state
from agent.llm_client import LocalLLMClient
from agent.agent import Agent
from agent.orchestrator import Orchestrator

state = load_agent_state("configs/agent_state.example.json")
client = LocalLLMClient()
agent = Agent(client)
orchestrator = Orchestrator(agent=agent, run_id="demo_run")
result = orchestrator.run_agent_step(state)
```

## Relationship to AgentState and NextAction
- `AgentState` is the structured input context.
- `NextAction` is the structured model output contract.
- This boundary only transports and validates decision-step data.

## Next step
Add Script Registry JSON v1 and semantic action validation before building executor behavior.
