# Script Registry JSON v1

## Purpose

Define a strict JSON registry for allowed actions, parameter schemas, and safety constraints.

## Why Script Registry exists

NextAction contract validates output shape, but not whether the action is allowed or properly parameterized. Script Registry adds deterministic non-executing semantic checks.

## Relationship to NextAction contract

- NextAction contract: shape-level validation.
- Script Registry: action/parameter/safety-level validation.

## Relationship to RoleTemplate

RoleTemplate constraints can further restrict allowed actions and file roots during registry validation.

## Relationship to Action Validation Test Cases

Semantic future cases in `configs/action_validation_cases.example.json` are now testable through registry validation.

## Registry schema

- `ScriptRegistry` with unique script names.
- `ScriptDescriptor` for each action.
- `ScriptParameterSpec` for parameter rules.
- `ScriptSafetySpec` for string-based safety constraints.

## ScriptDescriptor fields

- name, description
- parameters
- safety
- examples
- result_shape
- tags

## ParameterSpec fields

- name, type, required, description
- min_length/max_length
- allowed_values
- default

## SafetySpec fields

- allowed/forbidden file roots
- forbidden command substrings
- allowed/forbidden command prefixes
- requires_confirmation/read_only flags

## Validation behavior

`validate_next_action_against_registry(...)` checks:
- action exists
- required parameters exist
- unknown parameters are rejected
- parameter types/length/allowed values
- string-based path and command safety checks
- optional role-based action and path constraints

## Example scripts

- `read_file`
- `create_file`
- `run_shell_command`

## What this does not implement

- Script Registry validates whether a NextAction is allowed and correctly parameterized.
- It does not execute actions.
- It does not inspect real files.
- It is not a security sandbox.
- It is deterministic string-based validation v1.
- Executor / Script Runner comes later.

## Done criteria

- registry JSON loads and validates
- semantic validator rejects invalid actions/params/safety issues
- tests cover unknown actions, missing params, forbidden paths, unsafe commands, role restrictions

## Next step

Wire ScriptRegistry validation into a future runner/executor boundary before any action execution layer is introduced.
