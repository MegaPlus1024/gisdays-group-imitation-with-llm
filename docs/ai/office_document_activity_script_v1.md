# Office Document Activity Script v1

## Purpose

Provide a safe offline stub for office-like document activity using local text/Markdown/JSON files.

## Relationship to Script Registry

This script can be exposed as constrained actions in script registry entries, but it does not depend on registry execution.

## Relationship to future Executor

Executor may call these functions later. In v1 they are standalone helpers returning `ScriptExecutionResult`.

## Supported actions

- `create_document_stub`
- `append_document_section`
- `read_document_stub`
- `extract_document_outline_stub`
- `create_table_note_stub`
- `run_office_document_activity` dispatcher

## Path safety rules

- relative paths only
- no absolute paths
- no drive-prefixed paths
- no `..` traversal
- allowed roots enforced (`docs/`, `experiments/`, `configs/`, `tests/`)
- forbidden roots blocked (`models/gguf/`, `.venv/`, `.git/`)
- allowed extensions only (`.md`, `.txt`, `.json`)

## Simulation-only behavior

- metadata always includes `simulated: true`
- metadata includes `office_app_opened: false`
- no GUI app is opened

## Result format

Returns validated `ScriptExecutionResult`:

- `action`
- `success`
- optional `output`
- `error_type`/`error_message` on failure
- metadata

## Examples

- create a report stub in `docs/notes.md`
- append a section to an existing Markdown note
- extract heading outline from a Markdown document
- write a Markdown table note

## What this does not implement

- Office document activity v1 does not create real `.docx` or `.xlsx` files.
- It does not open Word, Excel, LibreOffice, or GUI applications.
- It does not use `python-docx` or `openpyxl`.
- It does not access the internet.
- It validates and simulates office-like document activity using safe local text/Markdown/JSON files.
- Future Executor or office automation layer may replace the simulated behavior.
- This is not a security sandbox.

## Done criteria

- all five office stub actions return structured results
- path safety blocks forbidden roots and traversal
- only safe text-like files are handled
- no external office dependency is required

## Next step

Wire these stubs into a future Executor layer with script-registry/semantic-validation gates.
