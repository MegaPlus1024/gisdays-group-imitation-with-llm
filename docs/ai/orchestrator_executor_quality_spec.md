# Orchestrator/Executor Quality Spec

## Purpose

This draft defines how to compare an orchestrator model plus one or more executor models. It is a proposed scoring spec, not an implemented metric.

## Pair Quality Score

```text
pair_quality_score =
  positive_behavior_score
  - latency_penalty
  - resource_penalty
  - safety_violation_penalty
```

Positive component weights sum to 1.0:

| Component | Weight | Already measurable? | Notes |
|---|---:|---|---|
| executor_contract_validity | 0.10 | yes | Initial NextAction parse/schema/contract validity. |
| executor_final_validity_after_repair | 0.08 | yes | Validity after repair attempts. |
| execution_success_rate | 0.13 | yes | Accepted actions that execute successfully. |
| role_fit_score | 0.09 | yes/partial | Role compliance and normality profile fit. |
| sequence_coherence_score | 0.09 | yes/partial | Current evaluator measures limited coherence. |
| history_usage_score | 0.07 | yes/partial | Current metrics exist but are shallow. |
| diversity_score | 0.07 | yes | Action/parameter diversity. |
| anti_template_score | 0.07 | yes/partial | Inverse of repeated/template patterns. |
| failure_recovery_score | 0.07 | partial | Repair and recovery evidence exists; group recovery does not. |
| group_coordination_score | 0.11 | no | Requires orchestrator/executor group artifacts. |
| task_completion_score | 0.12 | no/partial | Requires scenario-level task completion criteria. |

Penalty caps:

| Penalty | Suggested cap | Already measurable? | Notes |
|---|---:|---|---|
| latency_penalty | 0.08 | yes | Use normalized selection latency against scenario budget. |
| resource_penalty | 0.07 | partial | Current CPU/RAM estimates are lightweight. |
| safety_violation_penalty | 0.15 | yes/partial | Apply for unsafe paths, forbidden actions, policy bypass attempts. |

## What Is Already Measurable

- Contract validity.
- Final validity after repair.
- Execution success.
- Role compliance/normal activity scores.
- Diversity/repetition.
- Lightweight history usage.
- Per-step selection latency.
- Lightweight CPU/RAM observations.
- Safety/path validation failures.

## What Is Missing

- Model-backed orchestrator planning.
- Executor assignment metadata.
- Group shared history.
- Group coordination score.
- Scenario task-completion score.
- Concurrent multi-agent resource measurement.
- Pair-level artifacts with `orchestrator_model_id`, `executor_model_ids`, assignments, plans, and per-agent outcomes.

## Pair Comparison Protocol

Compare pairs only under the same:

- scenario set;
- role set;
- executor action registry;
- repair policy;
- local runtime mode;
- max steps and trial count;
- hardware/runtime configuration.

Recommended first comparison:

```text
pair_A = orchestrator_model: stronger_model, executor_models: [first_model]
pair_B = orchestrator_model: stronger_model, executor_models: [second_model]
```

Do not declare a final pair winner from one scenario. Require at least three scenario families and repeated trials per pair.

## Avoiding Overfitting

- Use a holdout scenario not used while tuning prompts.
- Separate office, developer, browser/research, and mixed-role scenarios.
- Report metric breakdowns, not only one score.
- Keep safety failures visible instead of hiding them inside aggregate score.
- Require confidence labels based on trial count and scenario diversity.
