# Behavioral validation fixtures v1

## Purpose
Provide deterministic offline behavioral fixtures for validating normal user activity simulation trajectories.

## Why behavioral fixtures exist
The evaluator and profiles need stable benchmark trajectories so future model evaluations can be compared on the same behavioral cases.

## Relationship to original curator specification
These fixtures operationalize the curator goal of validating normal user activity simulation by local LLM agents through repeatable trajectory checks.

## Relationship to NormalActivityProfile
Each trajectory references a role profile. Expected outcomes are interpreted relative to that role’s typical/atypical/forbidden-for-normality action rules.

## Relationship to ActivityTrajectoryEvaluator
Fixtures are direct inputs for `ActivityTrajectoryEvaluator` and expectation assertions.

## Fixture directory layout
- `tests/fixtures/behavioral_trajectories/README.md`
- `tests/fixtures/behavioral_trajectories/trajectories/*.json`
- `tests/fixtures/behavioral_trajectories/expected_results/behavioral_expectations.json`

## Single-role trajectories
Includes role-appropriate and role-inappropriate cases for:
- office worker
- developer
- student researcher
- history-aware behavior

## Multi-agent trajectory fixture
`mixed_roles_multi_agent.json` contains independent role trajectories in one fixture so each agent path can be evaluated separately.

## Expected results
Expectation suite defines:
- allowed verdicts
- robust score ranges
- required/forbidden flags
- comparative score expectations between cases

## How future model evaluation should use these fixtures
Future experiments should:
1. generate model trajectories;
2. normalize into step format;
3. evaluate with profiles/evaluator;
4. compare against this fixture expectation baseline.

## What this does not implement
- action execution
- LocalLLMClient calls
- runtime/model invocation
- model comparison logic itself

## Explicit guarantees
- Fixtures do not execute actions.
- Fixtures do not call LocalLLMClient.
- Fixtures are deterministic offline data.
- Future experiments will compare model-generated trajectories against these expectations.

## Done criteria
- fixture pack loads deterministically;
- expectation suite validates against evaluator outputs;
- role-specific differences (for example office vs developer shell usage) are test-covered.

## Next step
Use this fixture pack as a stable baseline in Behavioral Evaluation Readiness and then in full Experiments and Evaluation.
