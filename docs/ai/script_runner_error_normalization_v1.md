# Script Runner Error Normalization v1

## Purpose

Normalize heterogeneous script activity helper failures into stable structured records for future orchestration layers.

## Why error normalization exists

Different helpers emit different `error_type` strings. Without normalization, recovery and analytics become inconsistent.

## Relationship to ScriptExecutionResult

This layer consumes `ScriptExecutionResult` and produces `NormalizedScriptResult` with canonical category, severity, retryability, and recovery mapping.

## Relationship to FailureRecoveryPolicy

`recovery_category` is derived deterministically so future runner logic can route failures to recovery policy decisions.

## Relationship to ScriptRegistry

This layer does not validate action semantics. It only normalizes execution-level result/exception errors.

## Relationship to future Executor

Executor (later) will call helpers and then pass helper outputs/exceptions into this normalizer.

## Canonical categories

- none
- unknown_action
- missing_parameter
- invalid_parameter
- unsafe_action
- unsafe_path
- unsafe_url
- file_not_found
- document_not_found
- directory_not_found
- not_a_file
- not_a_directory
- file_too_large
- document_too_large
- permission_denied
- command_failed
- command_timeout
- executable_not_found
- script_timeout
- execution_error
- internal_error
- unknown_error

## Severity

Derived from category using deterministic mapping (`warning`/`error` etc.).

## Retryability

Default retryable categories:
- command_timeout
- script_timeout
- execution_error

All other categories default to non-retryable.

## Recovery category mapping

Maps script categories into recovery-policy-compatible categories such as:
- invalid_action_parameters
- unsafe_action
- file_not_found
- permission_denied
- execution_error
- unknown_error

## Examples

- `unknown_shell_action` -> `unknown_action`
- `unsafe_command` -> `unsafe_action`
- `document_not_found` -> `document_not_found` (+ recovery category `file_not_found`)
- `TimeoutError` exception -> `script_timeout`

## What this does not implement

- This layer does not execute actions.
- This layer does not retry actions.
- This layer does not implement Executor.
- It only converts heterogeneous script errors into stable normalized records.

## Done criteria

- deterministic category mapping
- deterministic severity/retryability/recovery mapping
- shape-validated normalized outputs
- zero execution side effects

## Next step

Integrate this normalizer into future Executor and History Logger layers.
