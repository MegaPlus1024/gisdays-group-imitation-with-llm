# Script Registry Loader and Validator v1

## Purpose
Harden registry loading and semantic validation for non-executing action checks.

## Why loader/validator hardening exists
The project now has multiple action families (file, browser, office, shell). Loader/validator behavior must be deterministic and strict before any executor layer is introduced.

## Relationship to Script Registry JSON v1
`configs/script_registry.example.json` is the canonical schema-driven source for action descriptors and safety policy.

## Relationship to NextAction contract
`NextAction` confirms generic output shape. Registry validation confirms action name, parameters, and safety semantics.

## Relationship to RoleTemplate
RoleTemplate is optional input to validator. If provided, validator enforces action and path constraints from role rules.

## Relationship to Action Validation Test Cases
`configs/action_validation_cases.example.json` cases are reused to validate expected accepts/rejects at semantic layer.

## Relationship to script activity stubs
Validator is aligned with file/browser/office/shell action families, but does not call activity helpers.

## Loader behavior
- Loads JSON from disk.
- Raises clear load errors for missing file or invalid JSON.
- Validates through Pydantic schema.
- Raises validation error for malformed registry structure.

## Validator behavior
- Checks action existence.
- Checks required/unknown/wrong-type parameters.
- Checks string length and allowed values.
- Applies path safety checks (absolute/drive/traversal, allowed/forbidden roots).
- Applies command safety checks (forbidden substrings, forbidden commands, allowlist).
- Applies optional role constraints for actions and paths.

## Supported validation layers
- `script_registry`
- `role_constraints`
- `safety_policy`

## What this does not implement
- Loader validates registry JSON only.
- Validator performs deterministic semantic checks.
- Validator does not execute actions.
- Validator does not inspect real files.
- Validator does not open browser or office apps.
- Validator does not run shell commands.
- Executor will come later.

## Done criteria
- strict loader errors
- strict schema validation
- stable issue codes/layers
- role-aware semantic checks
- broad offline tests passing

## Next step
Integrate validator results into orchestrator/runner recovery flow, then add executor layer separately.
