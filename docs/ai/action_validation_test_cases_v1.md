# Action Validation Test Cases v1

## Purpose
Provide a reusable, structured suite of action validation examples for future semantic validation work.

## Why action validation test cases exist
The system already validates generic NextAction shape, but future layers need explicit expected behavior for action names, parameters, role constraints, and safety checks.

## Relationship to NextAction contract
- NextAction contract checks raw JSON object shape.
- This suite includes cases that should fail at that contract layer.

## Relationship to RoleTemplate
Some cases declare `role_template_path` and are expected to fail in future role-constraint validation.

## Relationship to future Script Registry
Some cases are valid NextAction shape but should fail once Script Registry rules are implemented.

## Validation layers
- `next_action_contract`
- `script_registry`
- `role_constraints`
- `safety_policy`
- `executor`
- `not_applicable`

## Case categories
- positive (expected accept)
- negative contract-level
- negative future semantic-level

## Positive cases
Examples:
- valid_read_file_project_doc
- valid_create_file_experiment_note
- valid_run_pytest_command

## Negative contract-level cases
Examples:
- invalid_markdown_fenced_json
- invalid_multiple_actions_array
- invalid_missing_reason
- invalid_empty_action
- invalid_parameters_not_object

## Negative future semantic cases
Examples:
- semantic_unknown_action
- semantic_missing_required_parameter
- semantic_wrong_parameter_type
- semantic_forbidden_path_model_file
- semantic_unsafe_shell_command
- semantic_action_forbidden_by_role

## How to use the suite
1. Load with `load_action_validation_cases(...)`.
2. Use `probe_next_action_contract(...)` for contract-only parsing checks.
3. Later semantic validator should assert expected rejection layer/category for semantic cases.

## What this does not implement
- This task does not implement the Script Registry.
- This task does not execute actions.
- This task does not validate action parameters yet.
- It defines expected behavior for future semantic validation.
- Some cases should pass generic NextAction parsing but still be expected to fail future semantic validation.

## Done criteria
- structured suite exists
- positive + contract-negative + semantic-negative cases are covered
- contract probe helper is reusable and isolated

## Next step
Architecture README and data-flow diagram or Script Registry JSON v1, depending on app sequence.
