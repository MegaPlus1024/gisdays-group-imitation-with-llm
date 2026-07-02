# Model behavior evaluation v1

## Purpose
Define a stable result schema and helper skeleton for model behavior evaluation across scenarios.

## Why model behaviour evaluation exists
The project needs a consistent way to record and summarize how a model behaved per scenario before full experiments and model comparison execution.

## Relationship to original curator specification
This harness supports the curator goal by structuring evidence for normal user activity simulation quality.

## Relationship to EvaluationScenario
Scenario definitions provide setup context (role/profile/actions/metrics). This module stores and summarizes per-run outcomes against those setups.

## Relationship to NormalActivityProfile
Profiles define normal behavior expectations that feed behavioral scoring outputs included in evaluation results.

## Relationship to ActivityTrajectoryEvaluator
Behavioral scoring comes from `ActivityTrajectoryEvaluator`; this harness stores that score and derived verdict.

## Relationship to behavioral fixtures
Behavioral fixtures provide deterministic trajectories used to build synthetic/offline results in tests.

## Relationship to resource evaluation
Resource metrics fields are included as placeholders for future latency/CPU/RAM/token measurements.

## Result model
`ModelBehaviorEvaluationResult` includes:
- model spec
- scenario/run IDs
- selected actions
- validation metrics
- optional behavioral evaluation block
- resource metric placeholders
- final verdict

## Validation metrics
Includes rates/counters for JSON validity, parsing success, registry acceptance, role compliance, unsafe actions, and failures/recovery.

## Behavioral metrics
Optional `ActivityEvaluationResult` stores normal-activity score, diversity/repetition/coherence/history metrics, and flags.

## Resource metrics
Average/min/max latency, CPU, RAM, and token throughput fields are modeled but optional in v1.

## Verdict derivation
Deterministic helper:
- `insufficient_data` for empty runs or missing required behavioral block
- `fail` for low registry acceptance or low role compliance
- `pass/warning/fail` from normal-activity score thresholds when behavioral evaluation exists

## Synthetic mode
V1 supports synthetic result construction from structured action lists without running models.

## Future local-model mode
Future runners can populate the same models after real local-model scenario runs.

## What this does not implement
- local model execution
- llama-server calls
- action execution
- model comparison pipeline

## Explicit guarantees
- This harness does not run local models in v1.
- It does not call llama-server.
- It does not execute actions.
- It stores and summarizes model behavior evaluation results.
- Future Experiments and Evaluation will use it after generating trajectories from actual local models.

## Example usage
```python
from agent.model_behavior_evaluation import (
    ModelBehaviorModelSpec,
    ModelBehaviorSelectedAction,
    build_synthetic_model_behavior_result,
)
from agent.activity_profile import load_activity_profile

model = ModelBehaviorModelSpec(model_id="m1", model_name="first_model.gguf")
actions = [ModelBehaviorSelectedAction(step_index=1, action="read_file")]
profile = load_activity_profile("configs/activity_profiles/office_worker.json")
result = build_synthetic_model_behavior_result(
    evaluation_id="eval_1",
    run_id="run_1",
    scenario_id="office_worker_basic_session_v1",
    model=model,
    actions=actions,
    activity_profile=profile,
)
```

## Done criteria
- deterministic result schema
- synthetic builder helpers
- load/save helpers
- no runtime dependencies

## Next step
Integrate with future local-model scenario runners and aggregate multiple results for model comparison reports.
