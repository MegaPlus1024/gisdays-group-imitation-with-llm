# Next-action contract v1

## Purpose
Define the strict output shape the local model must return when proposing exactly one next action.

## Why this contract exists
- It gives `LocalLLMClient` a stable parse/validation boundary.
- It prevents prompt-output drift (essay text, arrays, or malformed JSON).
- It isolates generic structure validation before future semantic checks.

## Relationship to AgentState and LocalLLMClient
- `AgentState` is input context.
- `LocalLLMClient` sends that context to local llama-server.
- The model response is parsed by the next-action contract parser.
- Valid output becomes `NextAction` for future semantic validation/execution layers.

## Contract shape
```json
{
  "action_name": "string",
  "parameters": {}
}
```

## Validation rules
- `action_name` must be a non-empty string after whitespace trim.
- `parameters` must be a JSON object; if omitted it defaults to `{}`.
- Extra fields are rejected.
- Input text must be valid JSON and must decode to an object.
- Markdown-fenced JSON is rejected by design.
- The legacy output keys `action`, `reason`, and `expected_result` are rejected by design.

## Example usage
```python
from agent.action_contract import parse_next_action_text

text = '{"action_name":"read_file","parameters":{"path":"docs/ai/model_registry.md"}}'
next_action = parse_next_action_text(text)
```

## What this does not implement
- Script registry validation (allowed action names).
- Action-specific parameter semantic validation.
- Action execution.
- Full agent loop.

## Next step
Keep semantic action validation checking `action_name` and `parameters` against registry rules.
