# Next Implementation Plan: Orchestrator/Executor

## 1. Goal

Build the smallest research MVP where one orchestrator model assigns work and one or more executor agents choose validated `NextAction` steps with local models.

Status update: the sequential fake-mode MVP now exists. The remaining plan focuses on local runtime proof, repeated pair trials, and measured capacity rather than the first structural implementation.

## 2. Missing Pieces

- Local model-backed orchestrator/executor run.
- Repeated pair-level comparison.
- Measured multi-agent runtime/resource evidence.
- Production-grade group scheduler.
- Stronger group coordination and task-completion metrics.
- Measured multi-agent resource/capacity run.

## 3. Minimal MVP

1. Fake-mode orchestrator creates a deterministic plan for two agents. Implemented.
2. Fake/local-compatible executor path runs validated steps per agent. Implemented for fake mode.
3. Artifacts record plan, assignment, executor outputs, validation, execution, and group summary. Implemented.
4. Pair evaluator computes existing executor metrics plus prototype group coordination metrics. Implemented as an engineering proxy.
5. No concurrency in v1; agents run sequentially with explicit logs. Implemented.

## 4. Proposed Files To Add/Change

- `src/agent/orchestrator_executor.py`
- `src/agent/orchestrator_executor_evaluation.py`
- `configs/orchestrator_executor.example.json`
- `configs/evaluation_scenarios/orchestrator_executor_two_agent_smoke.json`
- `scripts/run_orchestrator_executor_scenario.py`
- `tests/test_orchestrator_executor_config.py`
- `tests/test_orchestrator_executor_fake_run.py`
- `docs/ai/orchestrator_executor_mvp_v1.md`

Data models:

- `OrchestratorModelSpec`
- `ExecutorModelSpec`
- `MultiAgentScenarioSpec`
- `AgentAssignment`
- `OrchestratorPlan`
- `ExecutorStepResult`
- `GroupRunResult`
- `PairEvaluationResult`

## 5. Test Plan

- Config schema validation.
- Fake orchestrator plan generation.
- Executor assignment validation.
- Sequential two-agent fake run.
- Failure isolation and stop-on-failure behavior.
- Artifact shape tests.
- Pair evaluation math tests.
- No local model/network tests in unit suite.

## 6. Experiment Plan

1. Fake two-agent smoke.
2. Local one-agent executor under orchestrator-provided assignment.
3. Local two-agent sequential run with same executor model.
4. Local two-agent sequential run with different executor models.
5. Repeat N=3 after artifacts and metrics are stable.
6. Add measured resource probe only after functional behavior is stable.

## 7. Hardware/GPU Plan

- Keep CPU path as baseline.
- Add runtime profile fields before GPU run.
- Ask user to provide GPU availability and `llama-server --help`.
- Compare CPU vs GPU only with identical scenario, model, ctx size, and trial count.
- Do not claim capacity from formula alone.

## 8. Risks

- Orchestrator may overfit to prompt wording.
- Executor safety policy may reject role-relevant paths.
- Group coordination metrics can become subjective unless artifacts are explicit.
- Concurrent serving may require separate ports or shared endpoint policy.
- GPU flags may differ by llama.cpp build.

## 9. Suggested Next Codex Prompts

1. "Implement fake-mode orchestrator/executor MVP with explicit plan and assignment artifacts. Do not run local models."
2. "Add pair-level evaluator using orchestrator_executor_quality_spec.md and tests with fixture artifacts."
3. "Extend start_llama_server.ps1 with dry-run runtime profiles for CPU/GPU flags after inspecting local llama-server --help."
4. "Run a controlled fake two-agent scenario and update docs with artifact examples."
5. "Prepare a local two-agent sequential experiment protocol, but do not execute it until I confirm runtime readiness."
