# Experiment Readiness Audit v1

## Purpose
This audit checks whether the project has the required foundations to start real Experiments and Evaluation for normal user activity simulation by a group of local LLM agents.

## Why an experiment readiness audit exists
Before running model comparisons, we need a deterministic readiness gate that verifies infrastructure, schemas, fixtures, scenarios, and harness modules are present and consistent.

## Relationship to original curator specification
The curator objective is experimental validation of normal user activity simulation by local LLM agent groups. This audit verifies the project is ready to begin that evaluation stage.

## Relationship to Behavioral Evaluation Readiness
Behavioral Evaluation Readiness delivers profiles, behavioral fixtures, scenarios, and evaluator foundations. The audit confirms those pieces exist and are loadable.

## Relationship to Experiments and Evaluation
This is a prerequisite check for Experiments and Evaluation. It does not replace experiments.

## Required foundations
- Project framing artifacts (`README.md`, objective doc).
- Runtime scripts and requirements.
- Agent architecture modules.
- Parameterized script modules.
- Behavioral evaluation modules and profile configs.
- Evaluation scenario configs.
- Model behavior harness files.
- Core behavioral and scenario tests.

## Recommended artifacts
- Model registry docs/config examples.
- Baseline and comparison artifacts.
- Additional integration-level test files.

## Optional artifacts
- Future experiment output directories and reports.
- These are tracked but should not block readiness.

## Readiness result
- `ready=true` when required checks have zero failures.
- Warnings from recommended/optional checks do not block readiness.

## What this audit checks
- Required/recommended/optional path presence.
- Lightweight semantic loading for activity profiles, scenarios + references, behavioral expectations, and model behavior config.

## What this audit does not check
- The audit does not run local models.
- The audit does not execute actions.
- The audit does not prove model quality.
- The audit does not run pytest automatically.

## Example usage
```python
from agent.experiment_readiness_audit import ExperimentReadinessAuditor

result = ExperimentReadinessAuditor().run_audit()
print(result.ready)
print(result.as_markdown())
```

## Done criteria
- Audit module, config, docs, and tests exist.
- Required foundations are validated deterministically.
- Readiness is blocked only by missing required prerequisites.

## Next step
Select model sets, run scenarios, collect behavioral and resource metrics, compare models, and write final Experiments and Evaluation results.
