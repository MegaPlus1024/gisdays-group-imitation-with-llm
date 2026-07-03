# Orchestrator/Executor Pipeline v1

## 1. Purpose

This document describes the first working group-agent MVP for the final TZ target: a controlled prototype where multiple software agents imitate normal user activity in a virtual computer/network-like environment.

The v1 scope is deliberately small. It proves the artifact flow for a group run without downloading models, starting `llama-server`, running local model inference, or claiming production readiness.

## 2. Model roles

Default prototype pair:

- orchestrator candidate: `second_model`
- executor candidate: `first_model`

The mapping is configurable through `configs/evaluation_models.json` and the CLI flags. This is not a final recommendation. It is only the default pair used for the first structural MVP because earlier evidence showed `second_model` had stronger JSON/action-contract validity, while `first_model` remained useful as a guarded executor candidate.

## 3. Scenario

Scenario file:

```text
configs/multi_agent_scenarios/office_developer_group_basic.json
```

Scenario id:

```text
office_developer_group_basic_v1
```

The scenario creates two executor agents:

- `office_agent`, based on the office worker role and profile;
- `developer_agent`, based on the developer role and profile.

The group objective stays local and offline. The office agent reviews local model metadata and writes a safe local note inside the experiment artifact workspace. The developer agent reads local readiness and quality-spec documentation.

## 4. Pipeline

The MVP pipeline is sequential:

```text
scenario/config
  -> orchestrator prompt
  -> orchestrator JSON plan
  -> plan validation
  -> per-agent task assignment
  -> executor NextAction selection
  -> NextAction parse/registry/role validation
  -> optional bounded script execution
  -> per-agent logs
  -> group history
  -> pair quality evaluation
```

Short form:

```text
Plan -> assign -> execute -> validate -> log -> evaluate
```

In fake mode, both orchestrator and executor outputs are deterministic local fixtures. In local mode, the same runner can call OpenAI-compatible local endpoints, but local group inference was not executed for this MVP checkpoint.

## 5. Quality score

The runner writes a prototype `pair_quality_score` in `pair_quality_metrics.json`.

The score combines:

- orchestrator plan validity;
- task assignment coverage;
- executor initial/final validation rates;
- execution success rate;
- role-fit, diversity, repetition, and history-use metrics from the existing activity evaluator;
- group coordination proxy;
- task completion proxy;
- safety violation count;
- mean selection latency.

This score is a prototype engineering signal, not a final scientific metric or deployment recommendation.

## 6. Commands

Fake end-to-end group run:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_group.py `
  --mode fake `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-dir experiments\multi_agent\orchestrator_executor\fake_office_developer_group_v1 `
  --run-id fake_office_developer_group_v1 `
  --orchestrator-model-id second_model `
  --executor-model-id first_model `
  --max-group-steps 2 `
  --max-steps-per-agent 2 `
  --repair-attempts 1 `
  --execute-actions `
  --force
```

Local-compatible command shape, after starting the required local endpoint(s) yourself:

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_group.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-dir experiments\multi_agent\orchestrator_executor\local_office_developer_group_v1 `
  --run-id local_office_developer_group_v1 `
  --orchestrator-model-id second_model `
  --executor-model-id first_model `
  --max-group-steps 2 `
  --max-steps-per-agent 2 `
  --repair-attempts 1 `
  --execute-actions `
  --force
```

## 7. Artifacts

Primary fake-run artifact folder:

```text
experiments/multi_agent/orchestrator_executor/fake_office_developer_group_v1
```

Expected files include:

- `manifest.json`
- `orchestrator_prompt.json`
- `orchestrator_raw_output.json`
- `orchestrator_plan.json`
- `orchestrator_validation.json`
- `agent_assignments.json`
- `group_steps.jsonl`
- `group_history.jsonl`
- `per_agent_actions.jsonl`
- `per_agent_validation_results.jsonl`
- `per_agent_execution_results.jsonl`
- `errors.jsonl`
- `pair_quality_metrics.json`
- `pair_evaluation.json`
- `resource_summary.json`
- `README.md`
- `replay_commands.ps1`

## 8. Limitations

- Local multi-model runtime was not stress-tested.
- No local group inference run was executed in this checkpoint.
- No GPU run was configured or measured.
- No production scheduler was implemented.
- The virtual network is simulated through constrained local state, files, roles, registry actions, and group history; it is not a real network topology or traffic simulator.
- Browser behavior remains simulated-only.
- Office behavior remains stub/file-based.
- The runner is sequential and does not measure concurrent capacity.
- The prototype score is useful for regression tracking, not final model selection.
