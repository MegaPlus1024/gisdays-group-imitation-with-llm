# Normal activity trajectory evaluator v1

## Purpose
Provide a deterministic offline evaluator that estimates whether a trajectory looks like normal user activity for a role profile.

## Why trajectory evaluation exists
Technical validity (JSON, schema, registry, safety) is necessary but does not answer the behavioral question from the curator objective.

## Relationship to original curator specification
The original curator specification requires experimental validation of normal user activity simulation by a group of local LLM agents. This evaluator provides heuristic behavioral metrics for that objective.

## Relationship to NormalActivityProfile
`NormalActivityProfile` defines role-specific typical, atypical, forbidden-for-normality actions, sequence patterns, and repetition/diversity expectations. The evaluator scores trajectories against this profile.

## Relationship to RoleTemplate
RoleTemplate defines permissions and constraints.
This evaluator measures behavioral normality and does not replace RoleTemplate.

## Relationship to ScriptRegistry
ScriptRegistry validates technical/safety validity.
This evaluator judges behavioral plausibility.

## Relationship to ExecutionHistory
ExecutionHistory can be a source of step summaries. The evaluator itself consumes normalized steps and does not execute or log actions.

## Relationship to Experiments and Evaluation
This module is designed for offline scoring in future experiment pipelines across local models.

## Input step format
`ActivityTrajectoryStep` contains:
- action and parameters
- success/status/issue hints
- optional reason/expected_result
- optional history usage and progress hints

## Metrics
- role fit (typical/atypical/forbidden balance)
- diversity (unique actions and action families)
- repetition/template behavior
- expected sequence coherence
- history usage
- total normal activity score

## Scoring logic
Weighted score:
- role fit: 0.35
- diversity: 0.20
- repetition: 0.20
- sequence coherence: 0.15
- history usage: 0.10

Optional failed-step penalty applies as `successful_steps / total_steps`.

## Verdicts
- `insufficient_data`: no steps
- `failed`: score below suspicious threshold or severe forbidden-for-normality outcome
- `suspicious`: between suspicious and normal thresholds
- `normal`: at/above normal threshold

## Example: normal office worker trajectory
`read_file -> office_create_document_stub -> append_file`
This typically scores high for office worker profile.

## Example: repetitive/template-like trajectory
Repeated `read_file` with identical parameters many times triggers repetition penalties and flags.

## Example: role-inappropriate trajectory
`run_shell_command` in office worker profile is forbidden-for-normality and should strongly reduce score.

## What this does not implement
- action execution
- LocalLLMClient calls
- model comparison logic
- final scientific proof of behavior quality

## Explicit boundaries
- This evaluator does not execute actions.
- This evaluator does not call LocalLLMClient.
- This evaluator does not replace safety validation.
- It evaluates behavioral normality, not technical validity.
- Scores are heuristic v1 metrics for experiments, not final scientific proof.
- Future Experiments and Evaluation will use this evaluator to compare local models.

## Done criteria
- deterministic offline scoring
- profile-aware metrics and flags
- no runtime/action execution dependency

## Next step
Integrate evaluator outputs into experiment reports and multi-model behavioral comparison workflows.
