# Execution history and error log v1

## Purpose

Define a minimal, structured logging contract for decision, validation, execution, and runner-step outcomes without executing actions.

## Why this layer exists

The project already validates input/output contracts, but it also needs reproducible records of what happened at each step and why failures occurred.

## Scope

- Structured history records (`ExecutionHistoryRecord`)
- Structured error records (`ExecutionErrorRecord`)
- JSONL append/read helpers via `ExecutionHistoryLogger`
- Conversion helpers from selector/runner/script-result objects into history+error records

## Data model overview

- `ExecutionHistoryConfig`: log paths and limits
- `ExecutionHistoryRecord`: one timeline event
- `ExecutionErrorRecord`: one normalized error event
- `ExecutionHistoryLogger`: append/read/clear utilities

## Record types

- `decision`
- `validation`
- `execution`
- `runner_step`
- `runner_run`
- `error`
- `note`

## Status values

- `success`
- `failure`
- `skipped`
- `pending_execution`
- `validation_failed`
- `decision_failed`
- `execution_failed`
- `unknown`

## Error-log behavior

- Failed decision/validation/execution flows can produce both a history record and an error record.
- Error records include severity, retryable flag, optional recovery category, and metadata.
- History records can reference related errors via `error_id`.

## JSONL behavior

- History and error logs are newline-delimited JSON (`.jsonl`).
- Each line must be a JSON object.
- Empty lines are ignored.

## What this does not implement

- No action execution.
- No automatic mutation of `AgentState.history`.
- No retry loop execution.
- No semantic script-registry validation.
- No direct llama-server dependency.

## Example usage

```python
from agent.execution_history import (
    ExecutionHistoryLogger,
    ExecutionHistoryConfig,
    ExecutionHistoryRecord,
    utc_now_iso,
)

logger = ExecutionHistoryLogger(
    ExecutionHistoryConfig(log_root="logs/execution_demo")
)

record = ExecutionHistoryRecord(
    record_id="decision_demo_run_agent_001_step1_selected",
    record_type="decision",
    status="success",
    created_at=utc_now_iso(),
    run_id="demo_run",
    agent_id="agent_001",
    step_index=1,
    summary="Action selected: read_file",
)

logger.append_history(record)
```

## Next step

Integrate this layer into a future runner pipeline so every decision/validation/execution transition is persisted consistently.
