from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import src.agent.orchestrator_executor_pipeline as pipeline
from src.agent.prompt_contract import PromptBuilder, PromptContractConfig
from src.agent.state import (
    ActionHistoryEntry,
    ActionSpec,
    AgentConstraints,
    AgentObjective,
    AgentResources,
    AgentRole,
    AgentState,
)
from src.agent.orchestrator_executor_pipeline import (
    ActionParameterRepairConfig,
    ExecutorModelConfig,
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
    PromptBudgetConfig,
)
from src.agent.orchestrator_prompt_contract import (
    OrchestratorPlanJSONError,
    parse_orchestrator_plan_text,
)
from src.agent.scripts.results import ScriptExecutionResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"


def _config(tmp_path: Path, **overrides: object) -> OrchestratorExecutorRunConfig:
    payload: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "mode": "fake",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": SCENARIO,
        "out_dir": str(tmp_path / "group_artifacts"),
        "run_id": "test_orchestrator_executor_fake",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "max_group_steps": 2,
        "max_steps_per_agent": 2,
        "repair_attempts": 1,
        "execute_actions": False,
        "force": True,
    }
    payload.update(overrides)
    return OrchestratorExecutorRunConfig.model_validate(payload)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bloated_agent_state() -> AgentState:
    action_schemas = {
        f"action_{index}": {
            "description": "Long registry action description. " * 60,
            "required_parameters": ["path", "content"],
            "parameters": {
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Relative project path under safe roots. " * 30,
                },
                "content": {
                    "type": "string",
                    "required": False,
                    "description": "Short local note content. " * 30,
                },
            },
            "allowed_file_roots": ["artifacts/single_trial_runs/phase_8_20_compact_retry/workspace/"],
            "forbidden_file_roots": ["models/gguf/", ".venv/", ".git/"],
            "allowed_shell_commands": [],
            "examples": [{"path": f"artifacts/example_{index}.md", "content": "example " * 80}],
        }
        for index in range(12)
    }
    return AgentState(
        agent_id="document_summary_agent",
        role=AgentRole(
            name="document_summary_agent",
            description="Summarize safe local project document workflow state. " * 50,
            constraints=["Use local files only. " * 20],
        ),
        objective=AgentObjective(
            primary="TASK_SENTINEL summarize controlled local document workflow.",
            success_criteria=["Return one valid NextAction JSON object."],
        ),
        resources=AgentResources(
            files=[f"configs/example_{index}.json" for index in range(40)],
            notes=["Large resource note. " * 80 for _ in range(10)],
        ),
        constraints=AgentConstraints(
            allowed_file_roots=["configs/", "docs/", "artifacts/"],
            forbidden_file_roots=["models/gguf/", ".venv/", ".git/"],
        ),
        available_actions=[
            ActionSpec(
                name=f"action_{index}",
                description="Large action description. " * 80,
                parameters_schema=action_schemas[f"action_{index}"]["parameters"],
                safety_notes=["Do not touch forbidden paths. " * 20],
            )
            for index in range(12)
        ],
        history=[
            ActionHistoryEntry(
                step=index,
                action="read_file",
                parameters={"path": f"configs/history_{index}.json", "content": "history " * 100},
                status="success",
                summary="Historical action summary. " * 40,
            )
            for index in range(1, 12)
        ],
        current_step=12,
        metadata={
            "assigned_goal": "TASK_SENTINEL summarize controlled local document workflow.",
            "orchestrator_task_id": "t1",
            "executor_prompt_hints": {
                "agent_id": "document_summary_agent",
                "role_id": "document_summary_agent",
                "task_id": "t1",
                "assigned_goal": "TASK_SENTINEL summarize controlled local document workflow.",
                "success_criteria": "Return one valid NextAction JSON object.",
                "allowed_actions": list(action_schemas),
                "action_schemas": action_schemas,
                "safe_path_roots": ["configs/", "docs/", "artifacts/"],
                "safe_existing_read_paths": [f"configs/example_{index}.json" for index in range(40)],
                "safe_write_path_examples": [f"artifacts/out_{index}.md" for index in range(40)],
                "path_rules": ["Use relative project paths only.", "Do not use absolute paths."],
                "json_only_example": {
                    "action": "action_0",
                    "parameters": {"path": "configs/example_0.json"},
                    "reason": "Read safe local input.",
                    "expected_result": "Local input is available.",
                },
            },
            "raw_prompt": "RAW_PROMPT_MARKER_SHOULD_NOT_LEAK",
        },
    )


def _agent_spec(agent_id: str = "document_summary_agent") -> pipeline.GroupAgentSpec:
    return pipeline.GroupAgentSpec(
        agent_id=agent_id,
        role_template_path="configs/roles/office_document_worker.example.json",
        activity_profile_path="configs/activity_profiles/office_worker.json",
        assigned_goal="Create a local office artifact.",
        executor_model_id="first_model",
    )


def _task(task_id: str = "t1", agent_id: str = "document_summary_agent") -> pipeline.OrchestratorPlanTask:
    return pipeline.OrchestratorPlanTask(
        task_id=task_id,
        agent_id=agent_id,
        goal="Create a local office artifact.",
        success_criteria="A valid office action is selected.",
    )


def _repair_config() -> ActionParameterRepairConfig:
    return ActionParameterRepairConfig(
        enabled=True,
        office_default_output_dir=(
            "artifacts/single_trial_runs/phase_8_21_action_repair_retry/"
            "pipeline/workspace/office_outputs"
        ),
    )


def _next_action(action: str, parameters: dict[str, object] | None = None) -> pipeline.NextAction:
    return pipeline.NextAction(
        action=action,
        parameters=parameters or {},
        reason="Select a safe local action.",
        expected_result="The action validates.",
    )


class _FakeBridgeOutput:
    def __init__(self, raw_result: ScriptExecutionResult) -> None:
        self.success = raw_result.success
        self.raw_result = raw_result

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        del mode
        return {
            "action": self.raw_result.action,
            "success": self.raw_result.success,
            "raw_result": self.raw_result.model_dump(mode="json"),
        }


class _RecordingBridge:
    def __init__(self, *, fail_precreate: bool = False, append_success: bool = True) -> None:
        self.fail_precreate = fail_precreate
        self.append_success = append_success
        self.calls: list[dict[str, object]] = []

    def execute_next_action(self, next_action, *, run_id, agent_id, step_index):  # type: ignore[no-untyped-def]
        del run_id, agent_id, step_index
        path = next_action.parameters.get("path")
        self.calls.append({"action": next_action.action, "path": path})
        if next_action.action == "office_create_docx" and self.fail_precreate:
            return _FakeBridgeOutput(
                ScriptExecutionResult(
                    action=next_action.action,
                    success=False,
                    error_type="office_dependency_missing",
                    error_message="Optional python-docx dependency is not installed.",
                    metadata={"office_app_opened": False},
                )
            )
        if next_action.action == "office_append_docx_section" and not self.append_success:
            return _FakeBridgeOutput(
                ScriptExecutionResult(
                    action=next_action.action,
                    success=False,
                    error_type="office_docx_file_missing",
                    error_message="DOCX document does not exist.",
                    metadata={"path_relative": path},
                )
            )
        return _FakeBridgeOutput(
            ScriptExecutionResult(
                action=next_action.action,
                success=True,
                output="ok",
                metadata={"output_path": path, "office_app_opened": False},
            )
        )


def test_parse_valid_orchestrator_plan_json() -> None:
    raw = json.dumps(
        {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_id": "office_agent",
                    "goal": "Read local metadata.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Local metadata was reviewed.",
                }
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "A local-only group run completes.",
        }
    )

    plan = parse_orchestrator_plan_text(
        raw,
        known_agent_ids={"office_agent"},
        allowed_action_names_by_agent={"office_agent": {"read_file", "create_file"}},
    )

    assert plan.tasks[0].task_id == "task_1"
    assert plan.tasks[0].agent_id == "office_agent"


def test_parse_orchestrator_plan_rejects_unknown_agent() -> None:
    raw = json.dumps(
        {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_id": "missing_agent",
                    "goal": "Read local metadata.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Local metadata was reviewed.",
                }
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "A local-only group run completes.",
        }
    )

    with pytest.raises(OrchestratorPlanJSONError, match="Unknown agent_id"):
        parse_orchestrator_plan_text(raw, known_agent_ids={"office_agent"})


def test_fake_group_run_completes_and_writes_artifacts(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    out_dir = Path(result.artifact_dir or "")

    assert result.status == "completed"
    assert result.success is True
    assert result.orchestrator_model_id == "second_model"
    assert result.executor_model_ids == ["first_model"]
    assert 0.0 <= result.quality_metrics.pair_quality_score <= 1.0

    for name in [
        "manifest.json",
        "orchestrator_prompt.json",
        "orchestrator_raw_output.json",
        "orchestrator_plan.json",
        "orchestrator_validation.json",
        "agent_assignments.json",
        "group_steps.jsonl",
        "group_history.jsonl",
        "per_agent_actions.jsonl",
        "per_agent_attempts.jsonl",
        "per_agent_validation_results.jsonl",
        "per_agent_execution_results.jsonl",
        "errors.jsonl",
        "pair_quality_metrics.json",
        "pair_evaluation.json",
        "resource_summary.json",
        "README.md",
        "replay_commands.ps1",
    ]:
        assert (out_dir / name).exists(), name


def test_fake_group_run_logs_per_agent_actions_and_group_history(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    out_dir = Path(result.artifact_dir or "")

    actions = _jsonl(out_dir / "per_agent_actions.jsonl")
    group_history = _jsonl(out_dir / "group_history.jsonl")

    assert len(actions) == 4
    assert len(group_history) == 4
    assert {row["agent_id"] for row in actions} == {"office_agent", "developer_agent"}
    assert {row["agent_id"] for row in group_history} == {"office_agent", "developer_agent"}
    assert all(row["validation_accepted"] is True for row in actions)


def test_pair_quality_score_is_persisted_in_range(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    metrics = _json(Path(result.artifact_dir or "") / "pair_quality_metrics.json")

    assert metrics["orchestrator_plan_valid"] is True
    assert 0.0 <= metrics["pair_quality_score"] <= 1.0
    assert metrics["metadata"]["prototype_scoring"] is True
    assert result.pair_evaluation.verdict in {"prototype_pass", "prototype_with_failures", "failed"}


def test_fake_mode_does_not_call_http_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.orchestrator_executor_pipeline as pipeline

    def fail_http_client(*args: object, **kwargs: object) -> object:
        raise AssertionError("fake mode must not create an HTTP client")

    monkeypatch.setattr(pipeline.httpx, "Client", fail_http_client)

    result = OrchestratorExecutorRunner(_config(tmp_path)).run()

    assert result.status == "completed"


def test_executor_compact_prompt_budget_reduces_context_and_preserves_contract() -> None:
    state = _bloated_agent_state()
    builder = PromptBuilder(PromptContractConfig(include_history_limit=20))

    messages, metadata = pipeline._executor_messages_with_budget(
        builder,
        state,
        PromptBudgetConfig(
            executor_max_prompt_chars=12000,
            max_history_items=3,
            compact_executor_context=True,
        ),
    )
    text = json.dumps(messages, ensure_ascii=False)

    assert metadata["prompt_budget_applied"] is True
    assert metadata["prompt_chars_before"] > metadata["prompt_chars_after"]
    assert metadata["estimated_prompt_chars"] == metadata["prompt_chars_after"]
    assert metadata["prompt_budget_strategy"] in {"compact_executor_context", "minimal_executor_context"}
    assert "NEXT_ACTION_OUTPUT_CONTRACT" in text
    assert "TASK_SENTINEL" in text
    assert "document_summary_agent" in text
    assert "RAW_PROMPT_MARKER_SHOULD_NOT_LEAK" not in text
    assert metadata["prompt_chars_after"] <= 12000


def test_local_executor_request_diagnostics_include_prompt_budget_metadata() -> None:
    model = ExecutorModelConfig(
        model_id="first_model",
        base_url="http://127.0.0.1:8081/v1",
        model_name="first_model.gguf",
        api_model="first_model",
    )
    payload = {
        "model": "first_model",
        "messages": [{"role": "user", "content": "shape only"}],
        "temperature": 0.0,
        "max_tokens": 1,
    }

    error = pipeline._local_model_http_error(
        pipeline.httpx.ConnectError("offline shape check"),
        model=model,
        payload=payload,
        url="http://127.0.0.1:8081/v1/chat/completions",
        request_metadata={
            "estimated_prompt_chars": 11800,
            "prompt_budget_applied": True,
            "prompt_chars_before": 42000,
            "prompt_chars_after": 11800,
            "prompt_budget_max_chars": 12000,
            "compact_executor_context": True,
            "max_history_items": 6,
            "prompt_budget_strategy": "compact_executor_context",
        },
    )

    shape = error.diagnostics["request_shape"]
    assert shape["estimated_prompt_chars"] == 11800
    assert shape["prompt_budget_applied"] is True
    assert shape["prompt_chars_before"] == 42000
    assert shape["prompt_chars_after"] == 11800
    assert shape["compact_executor_context"] is True
    assert shape["max_tokens_present"] is True


@pytest.mark.parametrize(
    ("action", "extension"),
    [
        ("office_create_docx", ".docx"),
        ("office_append_docx_section", ".docx"),
        ("office_create_xlsx", ".xlsx"),
        ("office_update_xlsx_cell", ".xlsx"),
        ("office_append_xlsx_row", ".xlsx"),
        ("office_create_pptx", ".pptx"),
        ("office_add_pptx_slide", ".pptx"),
    ],
)
def test_office_write_missing_path_gets_controlled_default(action: str, extension: str) -> None:
    result = pipeline._apply_action_parameter_repair(
        next_action=_next_action(action),
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )

    path = result.next_action.parameters["path"]
    assert path == (
        "artifacts/single_trial_runs/phase_8_21_action_repair_retry/"
        f"pipeline/workspace/office_outputs/t1_document_summary_agent{extension}"
    )
    assert result.metadata is not None
    assert result.metadata["parameter_repair_applied"] is True
    assert result.metadata["parameter_repair_type"] == "default_office_output_path"
    assert result.metadata["repaired_parameters"] == ["path"]
    assert result.metadata["path_source"] == "controlled_default"
    assert result.metadata["expected_extension"] == extension


def test_office_append_docx_blank_path_gets_controlled_default() -> None:
    result = pipeline._apply_action_parameter_repair(
        next_action=_next_action("office_append_docx_section", {"path": "   ", "paragraphs": ["note"]}),
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )

    assert result.next_action.parameters["path"].endswith("t1_document_summary_agent.docx")
    assert result.metadata is not None
    assert result.metadata["parameter_repair_type"] == "default_office_output_path"
    assert result.metadata["expected_extension"] == ".docx"


def test_office_append_docx_safe_no_extension_path_gets_extension_repair() -> None:
    result = pipeline._apply_action_parameter_repair(
        next_action=_next_action(
            "office_append_docx_section",
            {
                "path": (
                    "artifacts/single_trial_runs/phase_8_23_office_extension_retry/"
                    "pipeline/workspace/office_outputs/summary"
                ),
                "paragraphs": ["note"],
            },
        ),
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_23_office_extension_retry/pipeline",
        project_root=PROJECT_ROOT,
    )

    assert result.next_action.parameters["path"].endswith("/summary.docx")
    assert result.metadata is not None
    assert result.metadata["parameter_repair_type"] == "office_path_extension_repair"
    assert result.metadata["path_source"] == "model_path_with_extension_repair"
    assert result.metadata["expected_extension"] == ".docx"


def test_office_append_docx_existing_safe_path_is_preserved() -> None:
    original = _next_action(
        "office_append_docx_section",
        {"path": "artifacts/single_trial_runs/x/pipeline/workspace/office_outputs/manual.docx"},
    )

    result = pipeline._apply_action_parameter_repair(
        next_action=original,
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )

    assert result.next_action.parameters["path"] == "artifacts/single_trial_runs/x/pipeline/workspace/office_outputs/manual.docx"
    assert result.metadata is None


def test_office_create_unsafe_paths_are_not_silently_repaired() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    original = _next_action("office_create_docx", {"path": "C:/Users/m/out.docx"})

    result = pipeline._apply_action_parameter_repair(
        next_action=original,
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )
    validation = pipeline.validate_next_action_against_registry(result.next_action, registry, role)

    assert result.next_action.parameters["path"] == "C:/Users/m/out.docx"
    assert result.metadata is None
    assert validation.accepted is False
    assert {issue.code for issue in validation.issues} >= {"unsafe_path"}


def test_office_create_traversal_path_is_not_silently_repaired() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    original = _next_action("office_create_xlsx", {"path": "../tasks.xlsx"})

    result = pipeline._apply_action_parameter_repair(
        next_action=original,
        agent=_agent_spec("document_tracker_agent"),
        task=_task("t2", "document_tracker_agent"),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )
    validation = pipeline.validate_next_action_against_registry(result.next_action, registry, role)

    assert result.next_action.parameters["path"] == "../tasks.xlsx"
    assert result.metadata is None
    assert validation.accepted is False
    assert {issue.code for issue in validation.issues} >= {"unsafe_path"}


def test_office_append_docx_traversal_path_is_not_silently_repaired() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    original = _next_action("office_append_docx_section", {"path": "../tasks.docx", "paragraphs": ["note"]})

    result = pipeline._apply_action_parameter_repair(
        next_action=original,
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )
    validation = pipeline.validate_next_action_against_registry(result.next_action, registry, role)

    assert result.next_action.parameters["path"] == "../tasks.docx"
    assert result.metadata is None
    assert validation.accepted is False
    assert {issue.code for issue in validation.issues} >= {"unsafe_path"}


def test_office_path_repair_validates_after_repair() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")

    result = pipeline._apply_action_parameter_repair(
        next_action=_next_action("office_create_docx"),
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )
    validation = pipeline.validate_next_action_against_registry(result.next_action, registry, role)
    scenario_issue = pipeline._scenario_action_constraint_issue(
        next_action=result.next_action,
        scenario=pipeline.load_orchestrator_executor_scenario(
            PROJECT_ROOT / "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
        ),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )

    assert validation.accepted is True
    assert scenario_issue is None


def test_group_history_includes_parameter_repair_metadata() -> None:
    record = pipeline._history_from_attempt(
        pipeline.ExecutorActionAttempt(
            group_step_index=1,
            agent_step_index=1,
            agent_id="document_summary_agent",
            task_id="t1",
            raw_model_output="{}",
            parse_success=True,
            action="office_create_docx",
            next_action=_next_action(
                "office_create_docx",
                {"path": "artifacts/single_trial_runs/x/pipeline/workspace/office_outputs/t1.docx"},
            ).model_dump(mode="json"),
            validation_accepted=True,
            parameter_repair={
                "parameter_repair_applied": True,
                "parameter_repair_type": "default_office_output_path",
                "repaired_parameters": ["path"],
                "path_source": "controlled_default",
            },
        ),
        action_execution_enabled=False,
    )

    assert record.status == "success"
    assert record.metadata["parameter_repair"]["parameter_repair_applied"] is True
    assert record.metadata["parameter_repair"]["path_source"] == "controlled_default"
    assert record.metadata["validation_only"] is True
    assert record.metadata["action_execution_enabled"] is False


def test_validation_only_run_records_action_execution_diagnostics(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(
        _config(tmp_path, max_group_steps=1, max_steps_per_agent=1, execute_actions=False)
    ).run()
    manifest = _json(Path(result.artifact_dir or "") / "manifest.json")

    assert result.quality_metrics.metadata["validation_only"] is True
    assert result.quality_metrics.metadata["validation_success_count"] == 2
    assert result.quality_metrics.metadata["execution_attempted_count"] == 0
    assert result.quality_metrics.metadata["execution_success_count"] == 0
    assert result.quality_metrics.metadata["action_execution_enabled"] is False
    assert "action_execution_not_attempted_validation_only" in result.warnings
    assert all(row.metadata["validation_only"] is True for row in result.group_history)
    assert all(row.metadata["action_execution_enabled"] is False for row in result.group_history)
    assert manifest["action_execution"]["validation_only"] is True
    assert manifest["action_execution"]["execution_attempted_count"] == 0


def test_executor_attempt_executes_controlled_office_action_with_fake_bridge() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    scenario = pipeline.load_orchestrator_executor_scenario(
        PROJECT_ROOT / "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
    )
    out_dir = PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_22_action_execution_retry/pipeline"
    action_path = (
        "artifacts/single_trial_runs/phase_8_22_action_execution_retry/"
        "pipeline/workspace/office_outputs/t1_document_summary_agent.docx"
    )

    class FakeBridge:
        def __init__(self) -> None:
            self.paths: list[str] = []

        def execute_next_action(self, next_action, *, run_id, agent_id, step_index):  # type: ignore[no-untyped-def]
            del run_id, agent_id, step_index
            self.paths.append(next_action.parameters["path"])
            raw = ScriptExecutionResult(
                action=next_action.action,
                success=True,
                output="created",
                metadata={"output_path": next_action.parameters["path"]},
            )

            class Output:
                def __init__(self, raw_result: ScriptExecutionResult) -> None:
                    self.success = True
                    self.raw_result = raw_result

                def model_dump(self, *, mode: str = "json"):  # type: ignore[no-untyped-def]
                    del mode
                    return {
                        "action": next_action.action,
                        "success": True,
                        "raw_result": self.raw_result.model_dump(mode="json"),
                    }

            return Output(raw)

    bridge = FakeBridge()
    attempt = pipeline._executor_attempt_from_result(
        provider_result=pipeline.ExecutorProviderResult(
            raw_model_output=json.dumps(
                _next_action("office_create_docx", {"path": action_path, "paragraphs": ["Controlled note."]}).model_dump(
                    mode="json"
                )
            )
        ),
        attempt_index=0,
        attempt_type="initial",
        agent=_agent_spec(),
        task=_task(),
        state=_bloated_agent_state(),
        role_template=role,
        registry=registry,
        bridge=bridge,  # type: ignore[arg-type]
        group_step_index=1,
        agent_step_index=1,
        execute_actions=True,
        scenario=scenario,
        out_dir=out_dir,
        project_root=PROJECT_ROOT,
        action_parameter_repair=ActionParameterRepairConfig(enabled=True),
        latency_ms=1.0,
    )

    assert attempt.error_type is None
    assert attempt.execution_attempted is True
    assert attempt.execution_success is True
    assert bridge.paths == [action_path]
    assert Path(action_path).is_absolute() is False
    assert str(attempt.execution_result["raw_result"]["metadata"]["output_path"]).startswith(
        "artifacts/single_trial_runs/phase_8_22_action_execution_retry/pipeline/workspace/"
    )


def test_executor_attempt_repairs_append_docx_no_extension_before_fake_bridge() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    scenario = pipeline.load_orchestrator_executor_scenario(
        PROJECT_ROOT / "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
    )
    out_dir = PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_23_office_extension_retry/pipeline"
    action_path = (
        "artifacts/single_trial_runs/phase_8_23_office_extension_retry/"
        "pipeline/workspace/office_outputs/t1_document_summary_agent"
    )

    class FakeBridge:
        def __init__(self) -> None:
            self.paths: list[str] = []

        def execute_next_action(self, next_action, *, run_id, agent_id, step_index):  # type: ignore[no-untyped-def]
            del run_id, agent_id, step_index
            self.paths.append(next_action.parameters["path"])
            raw = ScriptExecutionResult(
                action=next_action.action,
                success=True,
                output="appended",
                metadata={"output_path": next_action.parameters["path"]},
            )

            class Output:
                def __init__(self, raw_result: ScriptExecutionResult) -> None:
                    self.success = True
                    self.raw_result = raw_result

                def model_dump(self, *, mode: str = "json"):  # type: ignore[no-untyped-def]
                    del mode
                    return {
                        "action": next_action.action,
                        "success": True,
                        "raw_result": self.raw_result.model_dump(mode="json"),
                    }

            return Output(raw)

    bridge = FakeBridge()
    attempt = pipeline._executor_attempt_from_result(
        provider_result=pipeline.ExecutorProviderResult(
            raw_model_output=json.dumps(
                _next_action(
                    "office_append_docx_section",
                    {"path": action_path, "paragraphs": ["Controlled note."]},
                ).model_dump(mode="json")
            )
        ),
        attempt_index=0,
        attempt_type="initial",
        agent=_agent_spec(),
        task=_task(),
        state=_bloated_agent_state(),
        role_template=role,
        registry=registry,
        bridge=bridge,  # type: ignore[arg-type]
        group_step_index=1,
        agent_step_index=1,
        execute_actions=True,
        scenario=scenario,
        out_dir=out_dir,
        project_root=PROJECT_ROOT,
        action_parameter_repair=ActionParameterRepairConfig(enabled=True),
        latency_ms=1.0,
    )

    assert attempt.error_type is None
    assert attempt.execution_attempted is True
    assert attempt.execution_success is True
    assert bridge.paths == [f"{action_path}.docx"]
    assert attempt.parameter_repair is not None
    assert attempt.parameter_repair["parameter_repair_type"] == "office_path_extension_repair"
    assert attempt.parameter_repair["expected_extension"] == ".docx"


def test_append_docx_safe_missing_path_precreates_when_enabled() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    scenario = pipeline.load_orchestrator_executor_scenario(
        PROJECT_ROOT / "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
    )
    out_dir = PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/pipeline"
    action_path = (
        "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/"
        "pipeline/workspace/office_outputs/missing_target.docx"
    )
    bridge = _RecordingBridge()

    attempt = pipeline._executor_attempt_from_result(
        provider_result=pipeline.ExecutorProviderResult(
            raw_model_output=json.dumps(
                _next_action(
                    "office_append_docx_section",
                    {"path": action_path, "paragraphs": ["Controlled note."]},
                ).model_dump(mode="json")
            )
        ),
        attempt_index=0,
        attempt_type="initial",
        agent=_agent_spec(),
        task=_task(),
        state=_bloated_agent_state(),
        role_template=role,
        registry=registry,
        bridge=bridge,  # type: ignore[arg-type]
        group_step_index=1,
        agent_step_index=1,
        execute_actions=True,
        scenario=scenario,
        out_dir=out_dir,
        project_root=PROJECT_ROOT,
        action_parameter_repair=ActionParameterRepairConfig(
            enabled=True,
            create_missing_docx_for_append=True,
        ),
        latency_ms=1.0,
    )

    assert attempt.error_type is None
    assert attempt.execution_attempted is True
    assert attempt.execution_success is True
    assert [call["action"] for call in bridge.calls] == ["office_create_docx", "office_append_docx_section"]
    assert bridge.calls[0]["path"] == action_path
    assert attempt.precreate_metadata is not None
    assert attempt.precreate_metadata["precreated_missing_document"] is True
    assert attempt.precreate_metadata["precreated_document_type"] == "docx"
    assert attempt.precreate_metadata["precreate_reason"] == "append_target_missing"
    assert attempt.precreate_metadata["path_source"] == "safe_model_path"


def test_append_docx_precreate_disabled_preserves_missing_file_failure() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    scenario = pipeline.load_orchestrator_executor_scenario(
        PROJECT_ROOT / "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
    )
    out_dir = PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_24_docx_precreate_disabled/pipeline"
    action_path = (
        "artifacts/single_trial_runs/phase_8_24_docx_precreate_disabled/"
        "pipeline/workspace/office_outputs/missing_target.docx"
    )
    bridge = _RecordingBridge(append_success=False)

    attempt = pipeline._executor_attempt_from_result(
        provider_result=pipeline.ExecutorProviderResult(
            raw_model_output=json.dumps(
                _next_action(
                    "office_append_docx_section",
                    {"path": action_path, "paragraphs": ["Controlled note."]},
                ).model_dump(mode="json")
            )
        ),
        attempt_index=0,
        attempt_type="initial",
        agent=_agent_spec(),
        task=_task(),
        state=_bloated_agent_state(),
        role_template=role,
        registry=registry,
        bridge=bridge,  # type: ignore[arg-type]
        group_step_index=1,
        agent_step_index=1,
        execute_actions=True,
        scenario=scenario,
        out_dir=out_dir,
        project_root=PROJECT_ROOT,
        action_parameter_repair=ActionParameterRepairConfig(enabled=True),
        latency_ms=1.0,
    )

    assert attempt.error_type == "office_docx_file_missing"
    assert attempt.precreate_metadata is None
    assert [call["action"] for call in bridge.calls] == ["office_append_docx_section"]


def test_append_docx_existing_path_is_not_precreated_again(tmp_path: Path) -> None:
    project_root = tmp_path
    out_dir = project_root / "artifacts/single_trial_runs/phase_8_24_existing/pipeline"
    action_path = "artifacts/single_trial_runs/phase_8_24_existing/pipeline/workspace/office_outputs/existing.docx"
    existing_path = project_root / action_path
    existing_path.parent.mkdir(parents=True)
    existing_path.write_bytes(b"placeholder")
    bridge = _RecordingBridge()

    result = pipeline._maybe_precreate_missing_docx_for_append(
        next_action=_next_action(
            "office_append_docx_section",
            {"path": action_path, "paragraphs": ["Controlled note."]},
        ),
        bridge=bridge,  # type: ignore[arg-type]
        agent=_agent_spec(),
        task=_task(),
        agent_step_index=1,
        config=ActionParameterRepairConfig(enabled=True, create_missing_docx_for_append=True),
        out_dir=out_dir,
        project_root=project_root,
        parameter_repair=None,
    )

    assert result.output is None
    assert result.metadata is None
    assert bridge.calls == []


def test_append_docx_workspace_prefix_lookalike_is_not_precreated(tmp_path: Path) -> None:
    project_root = tmp_path
    out_dir = project_root / "artifacts/single_trial_runs/phase_8_24_existing/pipeline"
    action_path = "artifacts/single_trial_runs/phase_8_24_existing/pipeline/workspace_extra/missing.docx"
    bridge = _RecordingBridge()

    result = pipeline._maybe_precreate_missing_docx_for_append(
        next_action=_next_action(
            "office_append_docx_section",
            {"path": action_path, "paragraphs": ["Controlled note."]},
        ),
        bridge=bridge,  # type: ignore[arg-type]
        agent=_agent_spec(),
        task=_task(),
        agent_step_index=1,
        config=ActionParameterRepairConfig(enabled=True, create_missing_docx_for_append=True),
        out_dir=out_dir,
        project_root=project_root,
        parameter_repair=None,
    )

    assert result.output is None
    assert result.metadata is None
    assert bridge.calls == []


def test_append_docx_precreate_dependency_missing_stops_before_append() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    scenario = pipeline.load_orchestrator_executor_scenario(
        PROJECT_ROOT / "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
    )
    out_dir = PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/pipeline"
    action_path = (
        "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/"
        "pipeline/workspace/office_outputs/dependency_missing.docx"
    )
    bridge = _RecordingBridge(fail_precreate=True)

    attempt = pipeline._executor_attempt_from_result(
        provider_result=pipeline.ExecutorProviderResult(
            raw_model_output=json.dumps(
                _next_action(
                    "office_append_docx_section",
                    {"path": action_path, "paragraphs": ["Controlled note."]},
                ).model_dump(mode="json")
            )
        ),
        attempt_index=0,
        attempt_type="initial",
        agent=_agent_spec(),
        task=_task(),
        state=_bloated_agent_state(),
        role_template=role,
        registry=registry,
        bridge=bridge,  # type: ignore[arg-type]
        group_step_index=1,
        agent_step_index=1,
        execute_actions=True,
        scenario=scenario,
        out_dir=out_dir,
        project_root=PROJECT_ROOT,
        action_parameter_repair=ActionParameterRepairConfig(
            enabled=True,
            create_missing_docx_for_append=True,
        ),
        latency_ms=1.0,
    )

    assert attempt.error_type == "office_dependency_missing"
    assert attempt.execution_attempted is True
    assert attempt.execution_success is False
    assert [call["action"] for call in bridge.calls] == ["office_create_docx"]
    assert attempt.precreate_metadata is not None
    assert attempt.precreate_metadata["precreate_success"] is False
    assert attempt.precreate_metadata["precreate_error_type"] == "office_dependency_missing"


def test_group_history_includes_docx_precreate_metadata() -> None:
    record = pipeline._history_from_attempt(
        pipeline.ExecutorActionAttempt(
            group_step_index=1,
            agent_step_index=1,
            agent_id="document_summary_agent",
            task_id="t1",
            raw_model_output="{}",
            parse_success=True,
            action="office_append_docx_section",
            next_action=_next_action(
                "office_append_docx_section",
                {
                    "path": "artifacts/single_trial_runs/x/pipeline/workspace/office_outputs/t1.docx",
                    "paragraphs": ["note"],
                },
            ).model_dump(mode="json"),
            validation_accepted=True,
            execution_attempted=True,
            execution_success=True,
            precreate_metadata={
                "precreated_missing_document": True,
                "precreated_document_type": "docx",
                "precreate_reason": "append_target_missing",
            },
        ),
        action_execution_enabled=True,
    )

    assert record.status == "success"
    assert record.metadata["precreate_metadata"]["precreated_missing_document"] is True
    assert record.metadata["precreate_metadata"]["precreated_document_type"] == "docx"


def test_non_office_actions_are_not_repaired_generically() -> None:
    result = pipeline._apply_action_parameter_repair(
        next_action=_next_action("create_file"),
        agent=_agent_spec(),
        task=_task(),
        config=_repair_config(),
        out_dir=PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
        project_root=PROJECT_ROOT,
    )

    assert result.next_action.parameters == {}
    assert result.metadata is None


def test_office_create_wrong_extension_is_rejected() -> None:
    issue = pipeline._office_create_path_extension_issue(
        _next_action("office_create_pptx", {"path": "artifacts/office_documents/brief.docx"})
    )

    assert issue is not None
    assert issue["code"] == "office_path_extension_mismatch"
    assert issue["metadata"]["expected_extension"] == ".pptx"
    assert issue["metadata"]["actual_extension"] == ".docx"


def test_office_append_docx_wrong_extension_is_rejected_before_execution() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    scenario = pipeline.load_orchestrator_executor_scenario(
        PROJECT_ROOT / "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
    )
    out_dir = PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_23_office_extension_retry/pipeline"

    class RejectingBridge:
        def execute_next_action(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("office backend must not run for extension mismatch")

    attempt = pipeline._executor_attempt_from_result(
        provider_result=pipeline.ExecutorProviderResult(
            raw_model_output=json.dumps(
                _next_action(
                    "office_append_docx_section",
                    {
                        "path": (
                            "artifacts/single_trial_runs/phase_8_23_office_extension_retry/"
                            "pipeline/workspace/document_summary_agent_executor_note.md"
                        ),
                        "paragraphs": ["note"],
                    },
                ).model_dump(mode="json")
            )
        ),
        attempt_index=0,
        attempt_type="initial",
        agent=_agent_spec(),
        task=_task(),
        state=_bloated_agent_state(),
        role_template=role,
        registry=registry,
        bridge=RejectingBridge(),  # type: ignore[arg-type]
        group_step_index=1,
        agent_step_index=1,
        execute_actions=True,
        scenario=scenario,
        out_dir=out_dir,
        project_root=PROJECT_ROOT,
        action_parameter_repair=ActionParameterRepairConfig(enabled=True),
        latency_ms=1.0,
    )

    assert attempt.error_type == "office_path_extension_mismatch"
    assert attempt.validation_accepted is False
    assert attempt.execution_attempted is False
    assert attempt.validation_issues[0]["metadata"]["expected_extension"] == ".docx"
    assert attempt.validation_issues[0]["metadata"]["actual_extension"] == ".md"


def test_compact_executor_prompt_keeps_office_required_path_guidance() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    agent = _agent_spec()
    assignment = pipeline.AgentAssignment(
        agent_id=agent.agent_id,
        task_id="t1",
        assigned_goal="Create a DOCX summary under the controlled workspace.",
        executor_model_id="first_model",
        success_criteria="Use office_create_docx with a path parameter.",
        allowed_action_focus=["office_create_docx"],
    )
    state = pipeline._build_agent_state(
        PROJECT_ROOT,
        agent,
        role,
        registry,
        assignment,
        PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
    )

    messages, metadata = pipeline._executor_messages_with_budget(
        PromptBuilder(PromptContractConfig(include_history_limit=6)),
        state,
        PromptBudgetConfig(
            executor_max_prompt_chars=12000,
            max_history_items=6,
            compact_executor_context=True,
        ),
    )
    text = json.dumps(messages, ensure_ascii=False)

    assert "office_create_docx" in text
    assert "path" in text
    assert ".docx" in text
    assert "office_outputs" in text
    assert "NEXT_ACTION_OUTPUT_CONTRACT" in text
    assert metadata["prompt_chars_after"] <= 12000


def test_compact_executor_prompt_uses_docx_example_for_append_action() -> None:
    registry = pipeline.load_script_registry(PROJECT_ROOT / "configs/script_registry.example.json")
    role = pipeline.load_role_template(PROJECT_ROOT / "configs/roles/office_document_worker.example.json")
    agent = _agent_spec()
    assignment = pipeline.AgentAssignment(
        agent_id=agent.agent_id,
        task_id="t1",
        assigned_goal="Append a DOCX section under the controlled workspace.",
        executor_model_id="first_model",
        success_criteria="Use office_append_docx_section with a .docx path parameter.",
        allowed_action_focus=["office_append_docx_section"],
    )
    state = pipeline._build_agent_state(
        PROJECT_ROOT,
        agent,
        role,
        registry,
        assignment,
        PROJECT_ROOT / "artifacts/single_trial_runs/phase_8_23_office_extension_retry/pipeline",
    )

    messages, metadata = pipeline._executor_messages_with_budget(
        PromptBuilder(PromptContractConfig(include_history_limit=6)),
        state,
        PromptBudgetConfig(
            executor_max_prompt_chars=12000,
            max_history_items=6,
            compact_executor_context=True,
        ),
    )
    text = json.dumps(messages, ensure_ascii=False)

    assert "office_append_docx_section" in text
    assert "prefer office_create_docx" in text
    assert "path" in text
    assert ".docx" in text
    assert "office_outputs" in text
    assert metadata["prompt_chars_after"] <= 12000


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_orchestrator_executor_group.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--scenario" in completed.stdout
    assert "--orchestrator-model-id" in completed.stdout


def test_cli_fake_run_writes_manifest_and_pair_evaluation(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_group_artifacts"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_orchestrator_executor_group.py",
            "--mode",
            "fake",
            "--models-config",
            "configs/evaluation_models.json",
            "--scenario",
            SCENARIO,
            "--out-dir",
            str(out_dir),
            "--run-id",
            "cli_orchestrator_executor_fake",
            "--orchestrator-model-id",
            "second_model",
            "--executor-model-id",
            "first_model",
            "--max-group-steps",
            "2",
            "--max-steps-per-agent",
            "2",
            "--repair-attempts",
            "1",
            "--no-execute-actions",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "pair_quality_score:" in completed.stdout
    assert _json(out_dir / "manifest.json")["run_id"] == "cli_orchestrator_executor_fake"
    assert _json(out_dir / "pair_evaluation.json")["orchestrator_model_id"] == "second_model"
