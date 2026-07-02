# Evaluation scenario v1

## Purpose
Define reusable experiment setups for evaluating normal user activity simulation by local LLM agents.

## Why evaluation scenarios exist
The project has profiles, evaluator, and fixtures. Scenarios connect them into concrete experiment-ready definitions without executing models.

## Relationship to original curator specification
Scenarios operationalize the curator objective by specifying role-centric setups for validating normal activity simulation.

## Relationship to NormalActivityProfile
Each agent spec points to an activity profile that defines normal/atypical/forbidden-for-normality behavior expectations.

## Relationship to ActivityTrajectoryEvaluator
Scenarios define which behavioral metrics and expectations should be collected and checked by trajectory evaluation pipelines.

## Relationship to behavioral fixtures
Scenarios can reference offline behavioral fixtures used as baseline trajectory validation inputs.

## Relationship to model comparison
Scenarios are model-agnostic setup definitions. Future model comparison runs the same scenarios across different local models.

## Relationship to resource evaluation
Resource plan fields declare what runtime/resource metrics should be collected later (latency/CPU/RAM/tokens/s).

## Scenario schema
`EvaluationScenario` includes:
- identity and mode (`single_agent` / `multi_agent`)
- per-agent specs
- stop policy reference and limits
- metric list
- expected behavior thresholds
- resource collection plan
- behavioral fixture references

## Agent specs
Each agent spec links:
- role id
- role template path
- normal activity profile path
- initial state path (optional)
- allowed/available action list
- expected action families/notes

## Stop policy
Scenario stop policy defines max steps and high-level stop toggles, plus optional link to autonomous stop criteria config.

## Expected behavior
Expected behavior block contains heuristic thresholds such as:
- min normal activity score
- min diversity score
- max repeated same-parameter patterns
- max forbidden-for-normality actions
- required sequence patterns

## Metrics
Metrics list declares what to collect in future runs, covering:
- technical validity rates
- behavioral scores
- resource and latency metrics
- failure/recovery counters

## Resource plan
Resource plan indicates measurement intent (CPU-only, latency/cpu/ram/tokens, multi-agent capacity estimate).

## Example scenarios
- `office_worker_basic_session.json`
- `developer_project_maintenance.json`
- `student_researcher_experiment_report.json`
- `mixed_roles_multi_agent_session.json`

## What this does not implement
- running models
- executing actions
- script helper calls
- model comparison execution
- scheduler implementation

## Explicit guarantees
- Evaluation scenarios do not execute models or actions.
- They define experiment setups for future Experiments and Evaluation.
- Future model comparison will run local models against these scenarios.
- Scenarios connect role, activity profile, allowed actions, expected behavior, behavioral fixtures, and metrics.

## Done criteria
- scenarios validate via schema
- reference checks can report missing dependencies
- scenario summaries are deterministic and JSON-serializable

## Next step
Integrate scenario loader into experiment orchestration that runs local models and evaluates resulting trajectories against scenario expectations.
