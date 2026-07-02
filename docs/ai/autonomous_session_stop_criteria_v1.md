# Autonomous session stop criteria v1

## Purpose
Define deterministic stop/continue decisions for future autonomous sessions using normalized step summaries, including normal-activity awareness.

## Why autonomous stop criteria exist
The project has selection, validation, bridge, recovery, and trajectory layers. This module adds a clear policy for when a session should stop, without executing any actions.

## Relationship to original curator specification
The curator specification targets experimental validation of normal user activity simulation by a group of local LLM agents.
This module adds hard stop rules so sessions can halt when behavior drifts away from role-normal activity.

## Relationship to NormalActivityProfile
`NormalActivityProfile` provides behavioral expectations for each role.
This module can use a profile to stop on forbidden-for-normality actions and excessive atypical actions.

## Relationship to RoleTemplate
RoleTemplate is still the permission/constraint layer.
Autonomous stop criteria is a behavior-control layer and does not replace RoleTemplate.

## Position in architecture
`Session step summaries -> AutonomousStopCriteriaEvaluator -> AutonomousStopDecision`

## Relationship to RecoveryLoop
Recovery outcomes (for example `abort_run`, `skip_agent`, `mark_for_review`) are treated as stop signals when enabled in config.

## Relationship to Role-constrained trajectory
Trajectory/runner outputs can be normalized into `AutonomousSessionStepSummary`; this module only evaluates the summary.

## Relationship to Multi-agent orchestrator smoke
This criteria layer is per-session/per-agent and can be called by future orchestrators after each step.

## Relationship to ExecutionHistory
Execution logs are optional upstream artifacts; this module does not read or write logs directly.

## Relationship to trajectory evaluation
This module provides deterministic hard stop criteria only.
A future trajectory evaluator should compute richer role-fit/coherence/diversity/repetition scores.

## Stop decision model
The evaluator returns:
- `should_stop`
- `action` (stop/continue code)
- `reason_category`
- `reason`
- optional `step_index`

## Evaluation order
1. Success
2. Marked-for-review signals
3. Recovery actions
4. Safety signals
5. Validation failure
6. Normal-activity profile checks (forbidden-for-normality, atypical counts, profile repetition)
7. Limits (max steps, consecutive failures, total failures)
8. Repeated action+parameters threshold
9. Progress signal
10. Continue

## Technical stop criteria
- unsafe actions/paths/urls/commands
- validation failures
- recovery abort/skip/mark-for-review decisions
- max steps and failure limits
- repeated action-parameter fingerprints

## Normal-activity stop criteria
- forbidden-for-normality action detection from `NormalActivityProfile`
- excessive atypical action detection from `NormalActivityProfile`
- profile-specific repetition guard (`max_same_action_same_parameters`)

## Repeated action detection
Exact repetitions are detected with deterministic fingerprints:
`action + sorted JSON(parameters)`.

## Atypical action detection
When a profile is configured, atypical actions are counted over session history and compared against `max_atypical_action_count`.

## Forbidden-for-normality action detection
When enabled, a latest action in `profile.forbidden_for_normality` triggers an immediate stop.

## Failure limits
The evaluator supports:
- `max_consecutive_failures`
- `max_total_failures`
- `max_steps`

## Safety stops
Unsafe signals are mapped from `issue_codes` or `error_type`:
- `unsafe_action`
- `unsafe_path`
- `unsafe_url`
- `unsafe_command`

## What this does not implement
- Action execution
- Autonomous runner
- LocalLLMClient calls
- Script helper calls
- Scheduler behavior
- Full trajectory scoring

## Example usage
```python
from agent.autonomous_stop_criteria import (
    AutonomousSessionSummary,
    AutonomousStopCriteriaEvaluator,
)
from agent.activity_profile import load_activity_profile

summary = AutonomousSessionSummary(session_id="s1", agent_id="a1")
profile = load_activity_profile("configs/activity_profiles/office_worker.json")
decision = AutonomousStopCriteriaEvaluator(activity_profile=profile).evaluate(summary)
```

## Required guarantees
- This layer does not execute actions.
- It does not implement an autonomous runner.
- It does not call LocalLLMClient.
- It does not call script helpers.
- It only evaluates a session summary and returns a stop/continue decision.
- NormalActivityProfile is used to stop sessions that drift away from normal role behavior.
- Future trajectory evaluator will compute richer scores, while this module provides hard stop criteria.

## Done criteria
- Deterministic stop/continue decisions from synthetic summaries.
- No runtime/server/model dependency.

## Next step
A future autonomous session runner should evaluate this policy after each step and decide whether to continue or stop.
