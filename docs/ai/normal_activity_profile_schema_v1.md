# Normal activity profile schema v1

## Purpose
Define a reusable schema for describing what behavior looks normal for a role in this project.

## Why normal activity profiles exist
The pipeline already validates structure, permissions, and safety. We also need a role-level behavioral target for evaluating whether trajectories resemble normal user activity.

## Relationship to original curator specification
The curator objective is experimental validation of normal user activity simulation by a group of local LLM agents. This schema captures the expected behavior envelope used by future evaluators.

## Relationship to RoleTemplate
NormalActivityProfile does not replace RoleTemplate.
RoleTemplate defines permissions and constraints.
NormalActivityProfile defines behavioral expectations for normal activity.

## Relationship to ScriptRegistry
ScriptRegistry answers whether actions are allowed/safe and parameter-valid.
NormalActivityProfile answers whether observed action choices look behaviorally normal for a role.

## Relationship to AgentState.history
Profiles are designed to be applied to trajectory history. Repetition and sequence checks rely on action history over steps.

## Relationship to future trajectory evaluator
This schema does not score trajectories yet.
A future trajectory evaluator will use these profiles to compute role fit, coherence, diversity, and repetition metrics.

## Profile fields
- `typical_actions`: actions expected in normal behavior.
- `atypical_actions`: actions possible but uncommon for the role.
- `forbidden_for_normality`: actions that may be technically possible but behaviorally abnormal.
- `expected_sequences`: action sequence patterns that resemble plausible role workflows.
- `repetition_policy`: limits on repetitive behavior.
- `diversity_policy`: minimum diversity expectations.
- notes/hints fields for evaluator guidance.

## Typical vs atypical vs forbidden-for-normality actions
- Typical: expected and common for role behavior.
- Atypical: not impossible, but unusual and should be limited.
- Forbidden-for-normality: behavior that should strongly lower normality judgement even if technically executable.

## Expected sequence patterns
Sequence patterns define plausible action orderings (for example inspect -> write -> refine). They are behavioral references, not strict hard constraints.

## Repetition policy
Repetition policy limits:
- consecutive same action
- total same action count
- repeated same action with same parameters
- warning threshold for repetitive patterns

## Diversity policy
Diversity policy defines:
- minimum unique actions
- minimum action-family breadth
- preferred families for plausible role coverage

## Example profiles
- `configs/activity_profiles/office_worker.json`
- `configs/activity_profiles/developer.json`
- `configs/activity_profiles/student_researcher.json`

## What this does not implement
- action execution
- trajectory scoring
- model comparison logic
- autonomous runner logic

## Done criteria
- schema supports role-level normality expectations
- profiles load and validate deterministically
- role expectations are separated from permission constraints

## Next step
Implement a trajectory normality evaluator that consumes action histories plus NormalActivityProfile and outputs role fit/coherence/diversity/repetition metrics.
