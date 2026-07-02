# Experiment Scenario Runner v1

## Purpose

`ExperimentScenarioRunner` provides a reproducible end-to-end scenario run for the local LLM agent prototype. It connects the existing project contracts into one artifact-producing pipeline:

`evaluation scenario -> AgentState -> PromptBuilder -> action provider -> raw model output -> NextAction parse -> registry and role validation -> ScriptExecutionBridge -> normalized result -> AgentState history -> ExecutionHistoryLogger -> stop criteria -> ActivityTrajectoryEvaluator -> model behavior result -> artifact folder`

The implementation lives in `src/agent/experiment_scenario_runner.py`. The CLI wrapper is `scripts/run_agent_scenario.py`.

## Why This Closes The Current Gap

Before this runner, the project had separate pieces for state, prompt rendering, local model calls, action parsing, script validation, script execution, history logging, stop criteria, and behavioral evaluation. This runner wires those pieces into a single reproducible run that can be executed offline in fake mode or pointed at a local OpenAI-compatible runtime in local mode.

The runner does not replace `AgentRunner`. `AgentRunner` remains selection-only. This runner is an experiment harness for producing scenario artifacts.

## Architecture

The runner loads:

- Scenario: `configs/evaluation_scenarios/*.json` through `load_evaluation_scenario`.
- Role template: the scenario agent's `role_template_path` through `load_role_template`.
- Activity profile: the scenario agent's `activity_profile_path` through `load_activity_profile`.
- Initial state: the scenario agent's `initial_state_path`, or `configs/agent_state.example.json`.
- Script registry: `configs/script_registry.example.json` by default.

For each step it records:

- rendered prompt messages and prompt summary;
- raw action-provider output;
- parse success or parse error;
- parsed `NextAction`;
- registry and role validation result;
- execution attempt and execution result, when enabled;
- normalized execution result;
- per-step latency;
- stop reason when a stop criterion triggers.

## Fake Mode

Fake mode is the default and never calls `llama-server`.

It uses `ScriptedActionProvider`, which accepts raw JSON strings, dictionaries, or `NextAction` objects. This mode is intended for repeatable tests, dry runs, and artifact-format validation.

Example:

```powershell
python scripts\run_agent_scenario.py `
  --mode fake `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\scenario_runs\office_fake_v1 `
  --run-id office_fake_v1 `
  --max-steps 1 `
  --force
```

Use `--scripted-actions` to pass either a JSON string or a path to a JSON file containing a list of actions:

```powershell
python scripts\run_agent_scenario.py `
  --mode fake `
  --scripted-actions tests\fixtures\scenario_actions.json `
  --out-dir experiments\scenario_runs\scripted_v1 `
  --force
```

## Local Mode

Local mode is implemented structurally through `LocalModelActionProvider`, which calls an OpenAI-compatible `/chat/completions` endpoint and extracts assistant content with `LocalLLMClient.extract_assistant_content`.

Local mode is not exercised by offline tests and should only be used when `llama-server` is already running:

```powershell
python scripts\run_agent_scenario.py `
  --mode local `
  --model-id first_model `
  --model-name first_model.gguf `
  --base-url http://127.0.0.1:8080/v1 `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\scenario_runs\office_local_dry_run_v1
```

## Using Evaluation Model Registry

Use `configs/evaluation_models.json` when a run should reference a stable experiment model id. This records model metadata and preflight status in `manifest.json`.

Fake run with model metadata:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py --mode fake --model-id first_model --models-config configs\evaluation_models.json --max-steps 1 --force
```

Local run shape, not executed by this task:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py --mode local --model-id first_model --models-config configs\evaluation_models.json --scenario configs\evaluation_scenarios\office_worker_basic_session.json --out-dir experiments\model_behavior\results\office_worker_first_model_run_001 --execute-actions --max-steps 5
```

Check model metadata and preflight without starting `llama-server`:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id first_model --json
```

## Artifact Layout

Each run writes an artifact directory containing:

| File | Contents |
|---|---|
| `manifest.json` | Run metadata, scenario id, mode, model id/name, artifact list, limitations. |
| `steps.jsonl` | Full per-step records. |
| `raw_model_outputs.jsonl` | Raw provider output per step. |
| `selected_actions.jsonl` | Parsed `NextAction` objects for parse-success steps. |
| `validation_results.jsonl` | Registry and role validation results. |
| `execution_results.jsonl` | Raw and normalized execution output for executed steps. |
| `history.jsonl` | Execution history records from `ExecutionHistoryLogger`. |
| `errors.jsonl` | Parse, validation, provider, or execution errors. Empty when no errors occur. |
| `activity_evaluation.json` | `ActivityTrajectoryEvaluator` result. |
| `model_behavior_result.json` | Model behavior summary using existing model behavior schemas. |
| `resource_summary.json` | Python/platform/process metadata and per-step latencies. |
| `replay_commands.ps1` | Re-run command template. |
| `README.md` | Human-readable run summary. |

## Example Commands

Show CLI usage:

```powershell
python scripts\run_agent_scenario.py --help
```

Run fake mode with action execution:

```powershell
python scripts\run_agent_scenario.py --mode fake --max-steps 1 --force
```

Run fake mode without executing actions:

```powershell
python scripts\run_agent_scenario.py --mode fake --no-execute-actions --max-steps 1 --force
```

Run tests for the runner:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_experiment_scenario_runner.py -q
```

## Safety Boundaries

- Fake mode does not call a local model, browser, network, or `llama-server`.
- Script execution is still constrained by `ScriptRegistry` and `ScriptExecutionBridge`.
- `--no-execute-actions` records selection and validation artifacts without bridge execution.
- Browser action execution remains the existing simulated/stub implementation.
- Office document action execution remains the existing stub/file-based implementation.
- The runner does not add git or mail actions.

## Limitations

- Runner v1 supports one agent per run. Multi-agent scenarios should be split or handled by future orchestration.
- Local mode is implemented but not covered by offline tests.
- There are no real local-model trajectory artifacts until `--mode local` is run against a live local runtime.
- No multi-agent capacity measurement is produced.
- `resource_summary.json` records lightweight process/platform/latency data only; it is not a heavy benchmark monitor.
- Explicit completion depends on future action-contract support; current stop integration covers max steps, validation failure, unsafe actions, repetition, and normality-related stops.

## Next Step: Real Local-Model Dry Run

After starting `llama-server`, run one local-mode scenario with a low `--max-steps` value and inspect:

- `raw_model_outputs.jsonl` for actual model responses;
- `validation_results.jsonl` for registry and role compliance;
- `execution_results.jsonl` for bridge output;
- `activity_evaluation.json` for normal-activity quality;
- `resource_summary.json` for first latency measurements.
