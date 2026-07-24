from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.orchestrator_executor_pipeline import (
    ExecutorProviderResult,
    GroupAgentSpec,
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
    OrchestratorPlanTask,
    OrchestratorProviderResult,
    load_orchestrator_executor_scenario,
)
from src.agent.role_template import load_role_template
from src.agent.schemas import NextAction
from src.agent.script_registry import load_script_registry, validate_next_action_against_registry
from src.agent.state import AgentState


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
ROLE_PATH = "configs/roles/office_document_worker.example.json"

OFFICE_WORKSPACE_ROOT = "experiments/multi_agent/orchestrator_executor/workspace"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class OfficeDocumentOrchestratorProvider:
    def create_plan(
        self,
        *,
        scenario: Any,
        agents: list[GroupAgentSpec],
        agent_action_names: dict[str, set[str]],
    ) -> OrchestratorProviderResult:
        assert scenario.scenario_id == "office_document_file_workflow_basic_v1"
        for agent in agents:
            assert {"office_create_docx", "office_create_xlsx"}.issubset(
                agent_action_names[agent.agent_id]
            )

        raw = json.dumps(
            {
                "tasks": [
                    {
                        "task_id": "task_1",
                        "agent_id": "document_summary_agent",
                        "goal": "Plan a local DOCX artifact without executing document actions.",
                        "allowed_action_focus": ["office_create_docx"],
                        "success_criteria": "DOCX action is selected and validated only.",
                    },
                    {
                        "task_id": "task_2",
                        "agent_id": "document_tracker_agent",
                        "goal": "Plan a local XLSX artifact without executing document actions.",
                        "allowed_action_focus": ["office_create_xlsx"],
                        "success_criteria": "XLSX action is selected and validated only.",
                    },
                ],
                "coordination_notes": "Offline fake pipeline validation only.",
                "expected_group_outcome": "Office document actions validate without execution.",
            },
            ensure_ascii=False,
        )
        return OrchestratorProviderResult(
            raw_model_output=raw,
            prompt_messages=[
                {
                    "role": "system",
                    "content": "offline fake office document scenario smoke",
                }
            ],
            metadata={"provider": "office_document_fake_orchestrator"},
        )


class OfficeDocumentExecutorProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def next_action(
        self,
        *,
        agent: GroupAgentSpec,
        task: OrchestratorPlanTask,
        state: AgentState,
        group_step_index: int,
        agent_step_index: int,
        out_dir: Path,
        project_root: Path,
    ) -> ExecutorProviderResult:
        del task, state, group_step_index, agent_step_index, out_dir, project_root
        if agent.agent_id == "document_summary_agent":
            action = {
                "action_name": "office_create_docx",
                "parameters": {
                    "path": f"{OFFICE_WORKSPACE_ROOT}/office_documents/offline_basic/summary.docx",
                    "title": "Offline fake summary",
                    "paragraphs": ["Validation-only fake pipeline smoke."],
                },
            }
        else:
            action = {
                "action_name": "office_create_xlsx",
                "parameters": {
                    "path": f"{OFFICE_WORKSPACE_ROOT}/office_documents/offline_basic/tasks.xlsx",
                    "sheet_name": "Tasks",
                    "headers": ["Task", "Status"],
                    "rows": [["Smoke validation", "Planned"]],
                },
            }
        self.calls.append({"agent_id": agent.agent_id, "action_name": action["action_name"]})
        return ExecutorProviderResult(
            raw_model_output=json.dumps(action, ensure_ascii=False),
            metadata={"provider": "office_document_fake_executor", "agent_id": agent.agent_id},
        )


def _config(tmp_path: Path) -> OrchestratorExecutorRunConfig:
    return OrchestratorExecutorRunConfig.model_validate(
        {
            "project_root": PROJECT_ROOT,
            "mode": "fake",
            "models_config_path": "configs/evaluation_models.json",
            "scenario_path": SCENARIO_PATH,
            "out_dir": str(tmp_path / "office_document_fake_pipeline"),
            "run_id": "test_office_document_fake_pipeline",
            "orchestrator_model_id": "second_model",
            "executor_model_id": "first_model",
            "max_group_steps": 1,
            "max_steps_per_agent": 1,
            "repair_attempts": 0,
            "execute_actions": False,
            "force": True,
        }
    )


def test_office_document_scenario_fake_pipeline_validates_without_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.orchestrator_executor_pipeline as pipeline

    def fail_http_client(*args: object, **kwargs: object) -> object:
        raise AssertionError("fake office document smoke must not create an HTTP client")

    def fail_bridge_execution(*args: object, **kwargs: object) -> object:
        raise AssertionError("execute_actions=false must not dispatch real office actions")

    monkeypatch.setattr(pipeline.httpx, "Client", fail_http_client)
    monkeypatch.setattr(pipeline.ScriptExecutionBridge, "execute_next_action", fail_bridge_execution)

    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / SCENARIO_PATH)
    role = load_role_template(PROJECT_ROOT / ROLE_PATH)
    executor_provider = OfficeDocumentExecutorProvider()

    assert scenario.execute_actions is False
    assert scenario.metadata["offline_fake_compatible"] is True
    assert scenario.metadata["write_path_policy"] == "artifact_workspace_only"
    assert scenario.metadata["office_real_document_backend_required"] is False
    assert scenario.metadata["optional_office_dependencies_required"] is False
    assert role.metadata["office_real_document_backend_required"] is False

    result = OrchestratorExecutorRunner(
        _config(tmp_path),
        orchestrator_provider=OfficeDocumentOrchestratorProvider(),
        executor_provider=executor_provider,
    ).run()
    out_dir = Path(result.artifact_dir or "")
    actions = _jsonl(out_dir / "per_agent_actions.jsonl")
    history = _jsonl(out_dir / "group_history.jsonl")

    assert result.status == "completed"
    assert result.success is True
    assert result.scenario_id == "office_document_file_workflow_basic_v1"
    assert result.artifact_dir is not None
    assert out_dir.is_relative_to(tmp_path)
    assert executor_provider.calls == [
        {"agent_id": "document_summary_agent", "action_name": "office_create_docx"},
        {"agent_id": "document_tracker_agent", "action_name": "office_create_xlsx"},
    ]

    assert {row["action"] for row in actions} == {"office_create_docx", "office_create_xlsx"}
    assert all(row["parse_success"] is True for row in actions)
    assert all(row["validation_accepted"] is True for row in actions)
    assert all(row["execution_attempted"] is False for row in actions)
    assert all(row["execution_success"] is None for row in actions)
    assert all(row["execution_result"] is None for row in actions)
    assert all(row["status"] == "success" for row in history)
    assert all(row["metadata"]["execution_attempted"] is False for row in history)

    assert (out_dir / "manifest.json").is_file()
    assert (out_dir / "orchestrator_plan.json").is_file()
    assert not list(out_dir.rglob("*.docx"))
    assert not list(out_dir.rglob("*.xlsx"))
    assert not list(out_dir.rglob("*.pptx"))
    assert not (PROJECT_ROOT / "experiments" / "multi_agent" / "orchestrator_executor" / "workspace").exists()


def test_office_document_role_rejects_disallowed_runtime_action() -> None:
    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / SCENARIO_PATH)
    registry = load_script_registry(PROJECT_ROOT / scenario.registry_path)
    role = load_role_template(PROJECT_ROOT / ROLE_PATH)
    action = NextAction(
        action_name="browser_open_url",
        parameters={"url": "http://localhost/offline-smoke"},
    )

    result = validate_next_action_against_registry(action, registry, role)

    assert result.accepted is False
    assert {issue.code for issue in result.issues} >= {
        "forbidden_by_role",
        "action_forbidden_by_role",
    }
