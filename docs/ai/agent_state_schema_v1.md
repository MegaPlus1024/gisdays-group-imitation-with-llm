# Agent State Schema v1

## Purpose

Define a stable, validated state contract that is sent to the local LLM before it selects the next action.

## Why AgentState exists

Without a schema, state context can drift and prompts become inconsistent. `AgentState` gives a repeatable shape for role/objective/context/action history.

## Relationship to LocalLLMClient

`LocalLLMClient.generate_next_action(agent_state)` expects a structured context payload. `AgentState.to_prompt_context()` produces a compact JSON-serializable object designed for that call path.

## Schema overview

- `AgentRole`
- `AgentObjective`
- `AgentEnvironment`
- `AgentResources`
- `AgentConstraints`
- `ActionSpec`
- `ActionHistoryEntry`
- `AgentState`

## Field descriptions

- `agent_id`: unique state identifier for one orchestrated session.
- `role`: agent identity, description, and optional role constraints.
- `objective`: current primary objective and success criteria.
- `environment`: OS/runtime/network assumptions and notes.
- `resources`: available files/directories/endpoints and notes.
- `constraints`: explicit task constraints and file-root boundaries.
- `available_actions`: lightweight list of possible actions and parameter schema hints.
- `history`: chronological prior actions and outcomes.
- `current_step`: next step index expected by the orchestrator.
- `metadata`: extensible dictionary for schema/version tags.

## Validation rules

- Non-empty required text for key identity fields.
- `ActionHistoryEntry.step >= 1`.
- `AgentState.current_step >= 1`.
- No duplicate action names in `available_actions`.
- No duplicate `history.step` values.
- If history exists: `current_step >= max(history.step) + 1`.
- If history is empty: `current_step == 1`.

## Example usage

```python
from agent.state import load_agent_state
from agent.llm_client import LocalLLMClient

state = load_agent_state("configs/agent_state.example.json")
client = LocalLLMClient()
next_action = client.generate_next_action(state.to_prompt_context())
```

## What this does not implement

- AgentState is the input contract for future model action selection.
- It is not the script registry.
- It does not execute actions.
- It does not validate action parameters semantically against the future full registry yet.
- It reduces prompt chaos by giving the local model a stable context shape.

## Next step

Implement Script registry JSON v1 or semantic action validation.
