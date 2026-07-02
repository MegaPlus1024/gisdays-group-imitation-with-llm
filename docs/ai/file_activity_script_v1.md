# File Activity Script v1

## Purpose
Provide controlled local file helper functions for future executor use.

## Relationship to Script Registry
These helpers are execution primitives. Script Registry validation remains a separate layer that decides whether an action/parameters are allowed.

## Relationship to future Executor
Future Executor should call these functions only after registry and policy checks.

## Supported actions
- `read_file`
- `create_file`
- `append_file`
- `list_directory`

## Path safety rules
- relative paths only
- no traversal (`..`)
- no absolute/drive-prefixed paths
- allowed roots enforced
- forbidden roots blocked (`models/gguf/`, `.venv/`, `.git/`)
- resolved paths must stay inside `project_root`

## Result format
All functions return `ScriptExecutionResult` with:
- `action`
- `success`
- `output`
- `error_type` / `error_message`
- `metadata`

## Examples
- `read_file("docs/ai/model_registry.md", config)`
- `create_file("docs/ai/note.md", "text", config)`
- `append_file("experiments/log.txt", "\nnext", config)`
- `list_directory("docs/ai/", config)`

## What this does not implement
- File activity script is a controlled local file helper.
- It does not delete files.
- It does not access models/gguf, .venv, or .git.
- It does not execute shell commands.
- It is not the full Executor.
- Future Executor will call these functions after Script Registry validation.

## Done criteria
- safe path normalization/resolution
- structured success/failure result model
- deterministic action dispatch for file helpers
- offline tests for safety and behavior

## Next step
Integrate these helpers into a future executor boundary after script registry + semantic validation checks.
