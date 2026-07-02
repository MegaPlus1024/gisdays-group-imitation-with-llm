# History-aware second action v1

## Purpose

Prove a deterministic two-step selection skeleton where second-step selection can see first-step action history.

## Why history-aware second action exists

Before a full trajectory runner, we need a small contract that demonstrates:
1) first action selection
2) history entry creation
3) updated state for step 2
4) second action selection

## Position in architecture

AgentState -> ActionSelector (first)
-> history helper conversion
-> updated AgentState
-> ActionSelector (second)
-> HistoryAwareSecondActionResult

## Relationship to AgentState.history

The runner appends a derived `ActionHistoryEntry` into a **new** AgentState instance. The original state is preserved unchanged.

## Relationship to ActionSelector

This layer delegates both decisions to `ActionSelector.select_action(...)` and does not bypass selector validation/status handling.

## Relationship to ExecutionHistory

This layer does not persist logs. It returns structured result data that a future runner/logging layer can record.

## Relationship to future Executor

Executor remains a separate layer. This module only selects actions and builds state context for next selection.

## V1 behavior

- Optional first-step success requirement
- Deterministic step-2 state construction
- Optional exact repeat detection (`action` + `parameters`)
- Failure status mapping:
  - `first_action_failed`
  - `second_action_failed`
  - `validation_failed`
  - `repeated_action_detected`

## Repeated action detection

`actions_exactly_equal` compares only action name and parameters. Reason and expected_result are ignored.

## What this does not implement

- This layer does not execute actions.
- It does not persist logs.
- It does not mutate the original AgentState.
- It does not implement a full loop.
- It does not dispatch file/browser/office/shell helpers.

## Example usage

```python
from agent.state import load_agent_state
from agent.action_selector import ActionSelector
from agent.history_aware_selection import HistoryAwareSecondActionRunner

state = load_agent_state("configs/agent_state.example.json")
selector = ActionSelector(llm_client=...)
runner = HistoryAwareSecondActionRunner(selector=selector)
result = runner.select_second_action(state)
```

## Done criteria

- First action can be converted into history entry.
- Second selector call receives updated state with first history entry.
- Original state remains unchanged.
- Repeated exact action can be flagged.

## Next step

Generalize to trajectory runner with controlled multi-step flow and integrated persistence/recovery handling.
