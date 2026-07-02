# Registry Fixture Pack v1

This fixture pack provides deterministic offline test data for script-registry loading and semantic action validation.

## Purpose

- Reusable fixture inputs for registry validation tests
- Stable expected outcomes for semantic validation checks
- Shared fixtures for future executor-facing tests (without execution)

## Layout

- `registries/`:
  valid and intentionally invalid script registry JSON files
- `next_actions/`:
  model-proposed NextAction JSON cases (valid and semantic-invalid)
- `role_templates/`:
  role template fixtures for role-based action/path constraints
- `expected_results/`:
  expected semantic validation outcomes per test case

## Safety

- Fixtures are for tests only.
- Fixtures do not execute actions.
- Fixtures must remain deterministic and offline-safe.
