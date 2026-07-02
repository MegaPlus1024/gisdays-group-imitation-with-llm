# Action Selector Prototype v1

## Purpose

Define a reusable component that selects one `NextAction` from `AgentState` using an injected model client and optionally validates it against `ScriptRegistry`.

## Why ActionSelector exists

It creates a clean decision boundary between model output and future execution layers, so selection/validation can be tested without running scripts.

## Position in architecture

`AgentState -> PromptContract -> LocalLLMClient -> NextAction -> ActionSelector validation -> AgentRunner (future executor)`

## Relationship to AgentState

`ActionSelector` consumes `AgentState` and passes `state.to_prompt_context()` to the injected client.

## Relationship to LocalLLMClient

`ActionSelector` does not create `LocalLLMClient` internally. It uses dependency injection and calls `generate_next_action(...)`.

## Relationship to PromptContract

Prompt construction remains owned by the model client layer; selector only consumes model output and validates it.

## Relationship to NextAction

Selector expects a `NextAction` (or compatible dict) and normalizes output to the existing `NextAction` model.

## Relationship to ScriptRegistry

When `validate_actions=true`, selector validates the proposed action via `validate_next_action_against_registry(...)`.

## Relationship to AgentRunner

Selector returns structured `ActionSelectionResult` for future runner/executor/history layers.

## V1 behavior

- selects one action only
- no retries
- no execution
- no history mutation
- supports validation required/optional modes

## What this does not implement

- Action execution
- Executor
- Script activity helper calls
- Semantic retry loops
- Multi-step autonomy

## Example usage

```python
from agent.action_selector import ActionSelector
from agent.llm_client import LocalLLMClient
from agent.state import load_agent_state

state = load_agent_state("configs/agent_state.example.json")
client = LocalLLMClient()  # real client requires llama-server
selector = ActionSelector(llm_client=client)
result = selector.select_action(state)
```

## Done criteria

- `ActionSelector` selects `NextAction` via injected client
- optional registry validation is supported
- failures are normalized into `ActionSelectionResult`
- no execution side effects

## Next step

Connect selector output to future Executor and History Logger layers.
