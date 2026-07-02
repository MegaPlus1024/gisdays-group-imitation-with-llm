# Script execution bridge v1

## Purpose
Script execution bridge v1 is the boundary that takes one `NextAction`, validates it against `ScriptRegistry`, dispatches only supported safe helpers, and returns a normalized result shape.

## Scope
- One action at a time.
- Validation-first execution by default.
- Safe helper dispatch only:
  - `read_file`
  - `create_file`
  - `append_file`
  - `list_directory`
  - `browser_open_url` (simulated)
  - `office_create_document_stub` (simulated)
  - `run_shell_command` (allowlisted)
- Optional history logging when explicitly enabled and logger context is present.

## Out of scope
- Autonomous loop.
- Multi-agent scheduler.
- Script registry authoring.
- Semantic action planning.
- Real browser automation.
- Real office app automation.
- Llama-server dependency.

## Behavior
1. Accept a validated `NextAction`.
2. If `validate_with_registry=true`, call registry validation first.
3. If validation fails, return a failed result and do not call any script helper.
4. If validation passes, dispatch to the mapped helper.
5. If `normalize_result=true`, include normalized error/result using runner error normalization.
6. If `write_history=true` and `history_logger`, `run_id`, `agent_id` are provided, append history/error records.

## Dispatch map
- `read_file` -> `run_file_activity("read_file", ...)`
- `create_file` -> `run_file_activity("create_file", ...)`
- `append_file` -> `run_file_activity("append_file", ...)`
- `list_directory` -> `run_file_activity("list_directory", ...)`
- `browser_open_url` -> `run_browser_activity("open_url", ...)`
- `office_create_document_stub` -> `run_office_document_activity("create_document_stub", ...)`
- `run_shell_command` -> `run_shell_command_activity(...)`

Unsupported actions return `dispatch_failed`.

## Minimal usage
```python
from agent.schemas import NextAction
from agent.script_execution_bridge import ScriptExecutionBridge

bridge = ScriptExecutionBridge()
action = NextAction(
    action="read_file",
    parameters={"path": "docs/ai/runtime_path_v1.md"},
    reason="Need context",
    expected_result="Read file content"
)
result = bridge.execute_next_action(action)
```
