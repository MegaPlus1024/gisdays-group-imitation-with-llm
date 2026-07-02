# Registry Fixture Pack v1

## Purpose

Provide deterministic offline fixtures to validate action-contract parsing and registry-based action validation behavior.

## Scope

This pack tests only validation flow:

- `parse_next_action_text`
- `load_script_registry`
- `load_role_template`
- `validate_next_action_against_registry`

It does not execute actions and does not require llama-server.

## Fixture layout

- `tests/fixtures/registry/registries/`
- `tests/fixtures/registry/next_actions/`
- `tests/fixtures/registry/role_templates/`
- `tests/fixtures/registry/expected_results/validation_expectations.json`

## Expectation model

Each case defines:

- next-action input file
- registry file
- optional role template
- expected acceptance boolean
- expected issue codes

## Evaluation

`src/agent/registry_fixtures.py` loads fixtures and evaluates each case using existing APIs only.

`tests/test_registry_fixture_pack.py` ensures:

- all referenced files exist
- expectation file is valid
- actual validation behavior matches expectations

## Out of scope

- executor behavior
- script execution
- semantic post-validation beyond current registry checks
- llama-server runtime calls
