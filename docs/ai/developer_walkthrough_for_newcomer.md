# Developer Walkthrough for Newcomer

This walkthrough is for a developer who wants to understand the project manually through Python APIs and tests. It intentionally avoids inventing CLI entrypoints that do not exist. All examples reference real files, classes, functions, configs, and tests in this repository.

Assumed working directory:

```powershell
cd <repo>
```

Use the project virtualenv when running snippets:

```powershell
.\.venv\Scripts\python.exe
```

## 1. Mental model

The project pipeline is:

```text
role/config
  -> AgentState
  -> PromptBuilder
  -> LocalLLMClient / ActionSelector
  -> NextAction
  -> ScriptRegistry validation
  -> ScriptExecutionBridge
  -> ScriptExecutionResult / NormalizedScriptResult
  -> ExecutionHistoryLogger
  -> ActivityTrajectoryEvaluator / ModelBehaviorEvaluationResult
```

Concrete files:

| Layer | Main file | Main object |
|---|---|---|
| Role/config | `configs/roles/*.json`, `configs/agent_state.example.json` | role templates and initial state |
| Agent state | `src/agent/state.py` | `AgentState`, `load_agent_state` |
| Prompt rendering | `src/agent/prompt_contract.py` | `PromptBuilder` |
| Local model adapter | `src/agent/llm_client.py` | `LocalLLMClient` |
| Action contract | `src/agent/schemas.py`, `src/agent/action_contract.py` | `NextAction`, `parse_next_action_text` |
| Action selection | `src/agent/action_selector.py` | `ActionSelector` |
| Registry validation | `src/agent/script_registry.py` | `ScriptRegistry`, `validate_next_action_against_registry` |
| Execution bridge | `src/agent/script_execution_bridge.py` | `ScriptExecutionBridge` |
| Script helpers | `src/agent/scripts/*.py` | file/browser/office/shell helpers |
| History/errors | `src/agent/execution_history.py` | `ExecutionHistoryLogger` |
| Behavioral evaluation | `src/agent/activity_profile.py`, `src/agent/activity_evaluator.py` | `NormalActivityProfile`, `ActivityTrajectoryEvaluator` |

## 2. Minimal offline walkthrough without local model

This example does not call `llama-server`. It loads state and registry, creates a `NextAction` manually, validates it, then executes a safe `read_file` through the bridge.

```python
from src.agent.state import load_agent_state
from src.agent.schemas import NextAction
from src.agent.script_registry import (
    load_script_registry,
    validate_next_action_against_registry,
)
from src.agent.script_execution_bridge import (
    ScriptExecutionBridge,
    ScriptExecutionBridgeConfig,
)

state = load_agent_state("configs/agent_state.example.json")
registry = load_script_registry("configs/script_registry.example.json")

next_action = NextAction(
    action="read_file",
    parameters={"path": "docs/ai/model_registry.md"},
    reason="Inspect model registry metadata.",
    expected_result="Model registry text is read.",
)

validation = validate_next_action_against_registry(next_action, registry)
print(validation.accepted)
print([issue.code for issue in validation.issues])

bridge = ScriptExecutionBridge(
    ScriptExecutionBridgeConfig(
        project_root=".",
        validate_with_registry=True,
        normalize_result=True,
        write_history=False,
    )
)

result = bridge.execute_next_action(
    next_action,
    run_id="walkthrough",
    agent_id=state.agent_id,
    step_index=state.current_step,
)

print(result.success)
print(result.dispatched)
print(result.raw_result)
print(result.normalized_result)
```

Observed in this audit:

```text
True
True True read_file True
```

Relevant tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_agent_state.py tests\test_script_registry.py tests\test_script_execution_bridge.py -q
```

## 3. Prompt/NextAction walkthrough

`PromptBuilder` turns `AgentState` into OpenAI-style chat messages. It does not call a model.

```python
from src.agent.state import load_agent_state
from src.agent.prompt_contract import PromptBuilder

state = load_agent_state("configs/agent_state.example.json")
messages = PromptBuilder().build_messages(state)

print(len(messages))
print(messages[0]["role"])
print(messages[1]["role"])
print(messages[0]["content"][:300])
print(messages[1]["content"][:500])
```

Expected shape:

```text
2
system
user
```

Valid `NextAction` JSON:

```python
from src.agent.action_contract import parse_next_action_text

text = """
{
  "action": "read_file",
  "parameters": {"path": "docs/ai/model_registry.md"},
  "reason": "Inspect known model metadata.",
  "expected_result": "Model registry document is available for review."
}
"""

action = parse_next_action_text(text)
print(action.action)
print(action.parameters)
```

Invalid JSON and the real error type:

```python
from src.agent.action_contract import parse_next_action_text, NextActionJSONError

try:
    parse_next_action_text("not json")
except NextActionJSONError as exc:
    print(type(exc).__name__)
    print(str(exc))
```

Relevant tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_prompt_contract.py tests\test_next_action_contract.py tests\test_llm_client.py -q
```

## 4. Role constraints walkthrough

Load a role template:

```python
from src.agent.role_template import load_role_template

office_role = load_role_template("configs/roles/office_worker.example.json")
print(office_role.role_id)
print(office_role.constraints.allowed_action_names)
print(office_role.constraints.forbidden_action_names)
```

Validate an action allowed by the role:

```python
from src.agent.action_contract import parse_next_action_text
from src.agent.role_template import load_role_template
from src.agent.script_registry import load_script_registry, validate_next_action_against_registry

registry = load_script_registry("configs/script_registry.example.json")
office_role = load_role_template("configs/roles/office_worker.example.json")

allowed = parse_next_action_text(
    """
    {
      "action": "read_file",
      "parameters": {"path": "docs/ai/model_registry.md"},
      "reason": "Read an allowed document.",
      "expected_result": "Document text is read."
    }
    """
)

result = validate_next_action_against_registry(allowed, registry, office_role)
print(result.accepted)
print([issue.code for issue in result.issues])
```

Validate an action forbidden by the same role:

```python
forbidden = parse_next_action_text(
    """
    {
      "action": "run_shell_command",
      "parameters": {"command": "python -m pytest -q"},
      "reason": "Try to run tests.",
      "expected_result": "Tests run."
    }
    """
)

result = validate_next_action_against_registry(forbidden, registry, office_role)
print(result.accepted)
print([(issue.code, issue.layer) for issue in result.issues])
```

The office worker role forbids `run_shell_command`; this is verified in:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_role_template.py tests\test_script_registry.py tests\test_script_registry_loader_validator.py -q
```

Specific tests:

| Test | What it checks |
|---|---|
| `tests/test_role_template.py::test_load_role_template_loads_office_worker` | role config loads |
| `tests/test_role_template.py::test_allowed_action_set_returns_expected_actions` | allowed action set is exposed |
| `tests/test_script_registry.py::test_role_template_can_forbid_action` | office role rejects shell command |
| `tests/test_script_registry.py::test_role_allowed_roots_constrain_path_access` | role roots constrain file access |

## 5. Script actions walkthrough

The exposed registry actions are defined in `configs/script_registry.example.json`. The bridge supports these actions through `src/agent/script_execution_bridge.py`.

| Action name | Execution function/class | Minimal valid parameters | Expected result shape | Relevant tests |
|---|---|---|---|---|
| `read_file` | `ScriptExecutionBridge._dispatch` -> `run_file_activity` -> `read_file` in `src/agent/scripts/file_activity.py` | `{"path": "docs/ai/model_registry.md"}` | `ScriptExecutionResult(action="read_file", success=True, output=str, metadata={...})` | `tests/test_file_activity_script.py`, `tests/test_script_execution_bridge.py`, `tests/test_script_registry.py` |
| `create_file` | `run_file_activity` -> `create_file` | `{"path": "docs/example.txt", "content": "hello"}` | `ScriptExecutionResult(..., success=True, metadata={"bytes_written": ...})` | `tests/test_file_activity_script.py`, `tests/test_script_registry_loader_validator.py` |
| `append_file` | `run_file_activity` -> `append_file` | `{"path": "docs/example.txt", "content": "more"}` | `ScriptExecutionResult(..., success=True, metadata={"bytes_written": ...})` | `tests/test_file_activity_script.py` |
| `list_directory` | `run_file_activity` -> `list_directory` | `{"path": "docs/ai/"}` | `ScriptExecutionResult(..., success=True, output="name1\nname2...", metadata={"entry_count": ...})` | `tests/test_file_activity_script.py` |
| `browser_open_url` | bridge maps to `run_browser_activity("open_url", ...)` -> `open_url` in `src/agent/scripts/browser_activity.py` | For bridge execution use localhost, for example `{"url": "http://127.0.0.1"}` | Simulated `ScriptExecutionResult`; metadata includes `simulated=True`, `browser_opened=False` | `tests/test_browser_activity_script.py` |
| `office_create_document_stub` | bridge maps to `run_office_document_activity("create_document_stub", ...)` -> `create_document_stub` | `{"path": "docs/report.md", "title": "Report", "body": "Body"}` | Writes Markdown-like text; metadata includes `simulated=True`, `office_app_opened=False` | `tests/test_office_document_activity_script.py` |
| `run_shell_command` | `run_shell_command_activity` -> `run_allowed_shell_command` in `src/agent/scripts/shell_command_activity.py` | `{"command": "python -m pytest -q"}` | `ScriptExecutionResult(..., output=stdout/stderr, metadata={"returncode": ..., "wall_time_seconds": ...})` | `tests/test_shell_command_activity_script.py` |

Safety notes:

- `create_file`, `append_file`, and `office_create_document_stub` write files. In tests they are run under `tmp_path`; do the same for experiments or use a deliberate output path.
- `browser_open_url` is simulated-only. `BrowserActivityConfig` rejects `simulated_only=False`.
- `run_shell_command` really executes allowlisted commands when `simulate` is not set, but `simulate` is not an exposed registry parameter. Tests monkeypatch `subprocess.run`.
- Registry validation accepts `browser_open_url` with `https://example.com`, but the default browser helper rejects external hosts during execution. Use `http://localhost` or `http://127.0.0.1` for bridge-level execution.

To inspect script action behavior:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_file_activity_script.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_browser_activity_script.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_office_document_activity_script.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_shell_command_activity_script.py -q
```

## 6. History and error logging walkthrough

Create a logger in a temporary folder, write one success history record and one error record, then read them back.

```python
from tempfile import TemporaryDirectory

from src.agent.execution_history import (
    ExecutionErrorRecord,
    ExecutionHistoryConfig,
    ExecutionHistoryLogger,
    ExecutionHistoryRecord,
    utc_now_iso,
)

with TemporaryDirectory() as tmp:
    logger = ExecutionHistoryLogger(
        config=ExecutionHistoryConfig(log_root=f"{tmp}/logs")
    )

    history = ExecutionHistoryRecord(
        record_id="decision_run_agent_step1_selected",
        record_type="decision",
        status="success",
        created_at=utc_now_iso(),
        run_id="run",
        agent_id="agent",
        step_index=1,
        action="read_file",
        summary="Selected one action",
    )

    error = ExecutionErrorRecord(
        error_id="error_run_agent_step1_failed",
        created_at=utc_now_iso(),
        run_id="run",
        agent_id="agent",
        step_index=1,
        action="read_file",
        error_type="SampleError",
        error_message="Something went wrong",
    )

    logger.append_history(history)
    logger.append_error(error)

    print(logger.history_path)
    print(logger.error_path)
    print(logger.read_history())
    print(logger.read_errors())
```

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_execution_history_error_log.py -q
```

Specific test:

| Test | What it checks |
|---|---|
| `tests/test_execution_history_error_log.py::test_logger_append_and_read_history_and_error` | append/read success and error JSONL records |
| `tests/test_execution_history_error_log.py::test_logger_clear_logs_removes_files` | log cleanup |
| `tests/test_execution_history_error_log.py::test_load_jsonl_raises_on_non_object_line` | malformed JSONL protection |

## 7. Behavioral evaluator walkthrough

Load an activity profile and evaluate a synthetic trajectory:

```python
from src.agent.activity_profile import load_activity_profile
from src.agent.activity_evaluator import (
    ActivityTrajectoryEvaluator,
    ActivityTrajectoryStep,
)

profile = load_activity_profile("configs/activity_profiles/office_worker.json")

steps = [
    ActivityTrajectoryStep(
        step_index=1,
        action="read_file",
        parameters={"path": "docs/ai/model_registry.md"},
        reason="Review previous note before drafting.",
    ),
    ActivityTrajectoryStep(
        step_index=2,
        action="office_create_document_stub",
        parameters={"path": "docs/report.md", "title": "Report", "body": "Body"},
    ),
    ActivityTrajectoryStep(
        step_index=3,
        action="append_file",
        parameters={"path": "docs/report.md", "content": "More"},
        used_history=True,
    ),
]

result = ActivityTrajectoryEvaluator().evaluate(steps, profile)

print(result.verdict)
print(result.score)
print(result.metrics.role_fit_score)
print(result.metrics.diversity_score)
print(result.metrics.repetition_score)
print(result.metrics.sequence_coherence_score)
print(result.metrics.history_usage_score)
print(result.metrics.normal_activity_score)
print(result.metrics.flags)
```

Observed in this audit for the example above:

```text
normal 0.9249999999999999 1.0 0.9249999999999999
```

Important field names:

| Requested/expected concept | Real field or method | Location |
|---|---|---|
| `valid_action_rate` | not found in `ActivityEvaluationResult` | Use registry validation or `ModelBehaviorValidationMetrics` for validation rates |
| `role_compliance_rate` | not found in `ActivityEvaluationResult`; exists as `ModelBehaviorValidationMetrics.role_compliance_rate()` | `src/agent/model_behavior_evaluation.py` |
| Role fit | `result.metrics.role_fit_score` | `src/agent/activity_evaluator.py` |
| Diversity | `result.metrics.diversity_score` | `src/agent/activity_evaluator.py` |
| Repetition | `result.metrics.repetition_score` | `src/agent/activity_evaluator.py` |
| Sequence coherence | `result.metrics.sequence_coherence_score` | `src/agent/activity_evaluator.py` |
| History usage | `result.metrics.history_usage_score` | `src/agent/activity_evaluator.py` |
| Normal activity score | `result.metrics.normal_activity_score`, also `result.score` | `src/agent/activity_evaluator.py` |

If you need validation/role compliance rates, use the model behavior harness:

```python
from src.agent.model_behavior_evaluation import (
    ModelBehaviorSelectedAction,
    build_validation_metrics_from_actions,
)

actions = [
    ModelBehaviorSelectedAction(
        step_index=1,
        action="read_file",
        parameters={"path": "docs/ai/model_registry.md"},
        registry_accepted=True,
        role_compliant=True,
    )
]

metrics = build_validation_metrics_from_actions(actions)
print(metrics.registry_acceptance_rate())
print(metrics.role_compliance_rate())
```

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_normal_activity_profile_schema.py tests\test_normal_activity_trajectory_evaluator.py tests\test_model_behavior_evaluation.py -q
```

## 8. Multi-agent smoke walkthrough

The multi-agent smoke layer uses `MultiAgentRunSpec`, `MultiAgentOrchestratorSmoke`, and a `runner_factory`. Tests use a fake runner; there is no full real-model multi-agent CLI.

Minimal example adapted from `tests/test_multi_agent_orchestrator_smoke.py`:

```python
from src.agent.multi_agent_orchestrator import (
    MultiAgentOrchestratorSmoke,
    MultiAgentOrchestratorSmokeConfig,
    MultiAgentRunSpec,
)
from src.agent.state import load_agent_state


class FakeTrajectoryResult:
    def __init__(self, success=True, actions=None, status="completed", stopped_reason=None):
        self.success = success
        self.status = status
        self.stopped_reason = stopped_reason
        self._actions = actions or []
        self.steps = [object()] * len(self._actions)

    def selected_actions(self):
        return list(self._actions)


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run_trajectory(self, state, run_id):
        self.calls.append((state, run_id))
        return self.result


def spec(agent_id: str) -> MultiAgentRunSpec:
    state = load_agent_state("configs/agent_state.example.json")
    state.agent_id = agent_id
    return MultiAgentRunSpec(agent_id=agent_id, agent_state=state)


def runner_factory(run_spec):
    if run_spec.agent_id == "office_agent":
        return FakeRunner(FakeTrajectoryResult(actions=["read_file", "create_file"]))
    return FakeRunner(FakeTrajectoryResult(actions=["read_file", "run_shell_command"]))


orchestrator = MultiAgentOrchestratorSmoke(
    config=MultiAgentOrchestratorSmokeConfig(
        isolate_agent_failures=True,
        stop_on_first_agent_failure=False,
    ),
    runner_factory=runner_factory,
)

result = orchestrator.run_smoke(
    [spec("office_agent"), spec("developer_agent")],
    run_id="walkthrough_multi_agent",
)

print(result.status)
print(result.success)
print(result.total_agents())
print(result.selected_actions_by_agent())
```

This demonstrates separate per-agent results by `agent_id`. It does not run local LLMs and does not execute real scripts.

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_multi_agent_orchestrator_smoke.py -q
```

Specific test ideas:

| Test | What it teaches |
|---|---|
| `test_run_smoke_sequential_order` | agents are processed sequentially |
| `test_run_smoke_completed_when_all_succeed` | successful aggregate result |
| `test_run_smoke_completed_with_failures_when_one_fails` | failure aggregation |
| `test_run_smoke_continues_after_failure_with_isolation` | failure isolation |
| `test_input_agent_state_not_mutated` | input state is preserved |

## 9. Runtime walkthrough with llama-server

Do not run a model unless you intentionally want a local runtime experiment. This section only lists confirmed commands and files.

Documented `llama-server` command template appears in `scripts/run_runtime_baseline.py`, `scripts/archive_smoke_run.py`, and `experiments/*/replay_commands.md`:

```powershell
llama-server `
  -m models\gguf\first_model.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096
```

Confirmed help command for smoke script:

```powershell
python scripts\run_llama_smoke.py --help
```

Usage shape observed:

```text
usage: run_llama_smoke.py [-h] [--base-url BASE_URL] --model-name MODEL_NAME
                          [--prompt-file PROMPT_FILE] [--out-dir OUT_DIR]
                          [--timeout-seconds TIMEOUT_SECONDS]
                          [--server-pid SERVER_PID]
                          [--temperature TEMPERATURE]
                          [--max-tokens MAX_TOKENS]
```

Confirmed help command for runtime baseline:

```powershell
python scripts\run_runtime_baseline.py --help
```

Usage shape observed:

```text
usage: run_runtime_baseline.py [-h] [--base-url BASE_URL]
                               [--model-name MODEL_NAME]
                               [--prompt-file PROMPT_FILE] [--out-dir OUT_DIR]
                               [--runs RUNS]
                               [--timeout-seconds TIMEOUT_SECONDS]
                               [--temperature TEMPERATURE]
                               [--max-tokens MAX_TOKENS]
                               [--server-pid SERVER_PID] [--force]
```

Related files:

| File | Purpose |
|---|---|
| `configs/runtime.local.example.json` | runtime/base URL/model path assumptions |
| `configs/models.local.example.json` | model metadata examples |
| `docs/ai/model_registry.md` | model registry rules and model records |
| `experiments/smoke/local_llama_server_smoke_v1/` | archived smoke artifact |
| `experiments/baselines/local_runtime_baseline_v1/summary.json` | first model fixed-prompt baseline |
| `experiments/baselines/second_model_runtime_baseline_v1/summary.json` | second model fixed-prompt baseline |
| `experiments/comparisons/two_model_runtime_comparison_v1/comparison.json` | numeric comparison only |

## 10. What cannot be demonstrated yet

Current publication status:

- End-to-end scenario execution exists in `src/agent/experiment_scenario_runner.py` and `scripts/run_agent_scenario.py`.
- Real local model trajectories exist under `experiments/model_behavior/`.
- Repeated trials, cross-scenario behavioral analysis, and resource/capacity formula artifacts exist.

These are still not completed/full production capabilities:

- `src/agent/runner.py::AgentRunner` remains selection-only for backward compatibility; use `ExperimentScenarioRunner` for end-to-end scenario runs.
- No production multi-agent scheduler is implemented.
- No measured multi-agent stress/capacity test has been run.
- Resource capacity is formula-estimated in `experiments/model_behavior/resources/resource_capacity_v1`, not stress-tested.
- No git/mail action implementation is included.
- Browser activity is simulated-only.
- Office document activity is stub/file-based, not real office application automation.
- No final production model recommendation is made.

Evidence:

| Item | Evidence |
|---|---|
| End-to-end runner | `src/agent/experiment_scenario_runner.py`, `scripts/run_agent_scenario.py` |
| Selection-only legacy runner | `src/agent/runner.py::AgentRunnerConfig.validate_execute_actions_disabled` |
| Multi-agent smoke only | `src/agent/multi_agent_orchestrator.py::MultiAgentOrchestratorSmoke` and tests with fake runner |
| Real behavioral artifacts | `experiments/model_behavior/repeated_trials/office_worker_two_model_repair_n3_v1` and `experiments/model_behavior/repeated_trials/developer_project_maintenance_two_model_repair_n3_v1` |
| Cross-scenario analysis | `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1` |
| Resource/capacity estimate | `experiments/model_behavior/resources/resource_capacity_v1` |

## 11. Reading order

| Order | File | Why read it |
|---:|---|---|
| 1 | `README.md` | Understand project purpose, current status, and explicit limitations |
| 2 | `docs/ai/project_structure_audit_for_report.md` | See architecture audit and green-light assessment |
| 3 | `configs/agent_state.example.json` | See the state shape the agent consumes |
| 4 | `src/agent/state.py` | Understand `AgentState`, resources, constraints, history |
| 5 | `configs/roles/*.json` and `src/agent/role_template.py` | Understand role constraints and role-to-state defaults |
| 6 | `src/agent/prompt_contract.py` | See exactly what prompt messages are built |
| 7 | `src/agent/schemas.py` and `src/agent/action_contract.py` | Understand `NextAction` JSON shape and parsing errors |
| 8 | `configs/script_registry.example.json` and `src/agent/script_registry.py` | Understand allowed actions and validation |
| 9 | `src/agent/script_execution_bridge.py` | See how registry actions dispatch to helpers |
| 10 | `src/agent/scripts/*.py` | Inspect each action family |
| 11 | `src/agent/execution_history.py` | Understand JSONL history/error records |
| 12 | `src/agent/activity_profile.py` and `src/agent/activity_evaluator.py` | Understand behavior scoring |
| 13 | `src/agent/model_behavior_evaluation.py` | Understand model behavior result schema and validation rates |
| 14 | `src/agent/multi_agent_orchestrator.py` | Understand smoke-level multi-agent orchestration |
| 15 | `tests/test_*.py` | Learn the intended behavior through executable examples |

## 12. Test map

| Test file | What concept it teaches | Command to run it |
|---|---|---|
| `tests/test_agent_state.py` | AgentState schema, prompt context, history validation | `.\.venv\Scripts\python.exe -m pytest tests\test_agent_state.py -q` |
| `tests/test_prompt_contract.py` | PromptBuilder messages and local client payload shape | `.\.venv\Scripts\python.exe -m pytest tests\test_prompt_contract.py -q` |
| `tests/test_next_action_contract.py` | NextAction JSON parsing and schema errors | `.\.venv\Scripts\python.exe -m pytest tests\test_next_action_contract.py -q` |
| `tests/test_llm_client.py` | LocalLLMClient with mocked HTTP | `.\.venv\Scripts\python.exe -m pytest tests\test_llm_client.py -q` |
| `tests/test_role_template.py` | Role templates and role constraints | `.\.venv\Scripts\python.exe -m pytest tests\test_role_template.py -q` |
| `tests/test_script_registry.py` | Registry validation, role constraints, safety checks | `.\.venv\Scripts\python.exe -m pytest tests\test_script_registry.py -q` |
| `tests/test_script_registry_loader_validator.py` | Registry loader and validation edge cases | `.\.venv\Scripts\python.exe -m pytest tests\test_script_registry_loader_validator.py -q` |
| `tests/test_action_selector_prototype.py` | ActionSelector behavior with fake model outputs | `.\.venv\Scripts\python.exe -m pytest tests\test_action_selector_prototype.py -q` |
| `tests/test_agent_runner_skeleton.py` | Selection-only AgentRunner | `.\.venv\Scripts\python.exe -m pytest tests\test_agent_runner_skeleton.py -q` |
| `tests/test_script_execution_bridge.py` | Bridge dispatch and normalization | `.\.venv\Scripts\python.exe -m pytest tests\test_script_execution_bridge.py -q` |
| `tests/test_file_activity_script.py` | File action safety and behavior | `.\.venv\Scripts\python.exe -m pytest tests\test_file_activity_script.py -q` |
| `tests/test_browser_activity_script.py` | Simulated browser action safety | `.\.venv\Scripts\python.exe -m pytest tests\test_browser_activity_script.py -q` |
| `tests/test_office_document_activity_script.py` | Office document stub actions | `.\.venv\Scripts\python.exe -m pytest tests\test_office_document_activity_script.py -q` |
| `tests/test_shell_command_activity_script.py` | Shell allowlist and subprocess safety | `.\.venv\Scripts\python.exe -m pytest tests\test_shell_command_activity_script.py -q` |
| `tests/test_execution_history_error_log.py` | JSONL history and error logging | `.\.venv\Scripts\python.exe -m pytest tests\test_execution_history_error_log.py -q` |
| `tests/test_failure_recovery_policy.py` | Recovery decisions by failure category | `.\.venv\Scripts\python.exe -m pytest tests\test_failure_recovery_policy.py -q` |
| `tests/test_recovery_loop.py` | Recovery loop harness with fake selector/bridge | `.\.venv\Scripts\python.exe -m pytest tests\test_recovery_loop.py -q` |
| `tests/test_autonomous_session_stop_criteria.py` | Stop criteria for autonomous sessions | `.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_session_stop_criteria.py -q` |
| `tests/test_normal_activity_profile_schema.py` | Activity profile schema | `.\.venv\Scripts\python.exe -m pytest tests\test_normal_activity_profile_schema.py -q` |
| `tests/test_normal_activity_trajectory_evaluator.py` | Behavioral evaluator metrics | `.\.venv\Scripts\python.exe -m pytest tests\test_normal_activity_trajectory_evaluator.py -q` |
| `tests/test_model_behavior_evaluation.py` | Model behavior result schema and validation rates | `.\.venv\Scripts\python.exe -m pytest tests\test_model_behavior_evaluation.py -q` |
| `tests/test_multi_agent_orchestrator_smoke.py` | Multi-agent smoke orchestration with fake runners | `.\.venv\Scripts\python.exe -m pytest tests\test_multi_agent_orchestrator_smoke.py -q` |
| `tests/test_runtime_baseline.py` | Runtime baseline helper functions, no server call | `.\.venv\Scripts\python.exe -m pytest tests\test_runtime_baseline.py -q` |
| `tests/test_run_llama_smoke.py` | Smoke helper functions, no server call | `.\.venv\Scripts\python.exe -m pytest tests\test_run_llama_smoke.py -q` |
| `tests/test_compare_runtime_baselines.py` | Numeric comparison helper functions | `.\.venv\Scripts\python.exe -m pytest tests\test_compare_runtime_baselines.py -q` |
| `tests/test_archive_smoke_run.py` | Smoke archive helper functions | `.\.venv\Scripts\python.exe -m pytest tests\test_archive_smoke_run.py -q` |

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Observed in the prior audit example:

```text
567 passed in 0.58s
```

Current publication check:

```text
636 passed
```
