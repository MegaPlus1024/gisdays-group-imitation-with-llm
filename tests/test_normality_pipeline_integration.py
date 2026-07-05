from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.normality_evaluation_runner import (
    NORMALITY_EVALUATION_SUMMARY_FILENAME,
    NormalityEvaluationRunConfig,
    run_normality_evaluation_for_group_history,
    write_normality_evaluation_for_pipeline_result,
)
from src.agent.orchestrator_executor_pipeline import (
    ExecutorProviderResult,
    GroupAgentSpec,
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
    OrchestratorPlanTask,
    OrchestratorProviderResult,
)
from src.agent.state import AgentState


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
OFFICE_WORKSPACE_ROOT = "experiments/multi_agent/orchestrator_executor/workspace"


def _summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_history(
    *,
    summary: str = "Created an offline local document artifact.",
    artifact_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "group_step_index": 1,
            "agent_id": "document_summary_agent",
            "task_id": "task_1",
            "action": "office_create_docx",
            "status": "success",
            "summary": summary,
            "artifact_paths": artifact_paths or ["artifacts/office_documents/offline_basic/summary.docx"],
            "metadata": {
                "execution_attempted": False,
                "execution_success": None,
                "validation_accepted": True,
            },
        }
    ]


def _run_group_history_eval(
    tmp_path: Path,
    *,
    group_history: list[dict[str, Any]] | None = None,
    config: NormalityEvaluationRunConfig | None = None,
) -> tuple[Path, dict[str, Any]]:
    out_dir = tmp_path / "normality"
    result = run_normality_evaluation_for_group_history(
        group_history=group_history or _fake_history(),
        scenario_id="office_document_file_workflow_basic_v1",
        task_summary="Evaluate offline fake pipeline document activity.",
        output_dir=out_dir,
        project_root=tmp_path,
        agent_roles={"document_summary_agent": "office document worker"},
        expected_behavior="Use offline office document actions without execution.",
        environment_summary="Controlled offline fake pipeline artifacts.",
        config=config,
    )
    return out_dir, result.model_dump(mode="json")


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
            prompt_messages=[{"role": "system", "content": "offline fake office document scenario smoke"}],
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
                "action": "office_create_docx",
                "parameters": {
                    "path": f"{OFFICE_WORKSPACE_ROOT}/office_documents/offline_basic/summary.docx",
                    "title": "Offline fake summary",
                    "paragraphs": ["Validation-only fake pipeline smoke."],
                },
                "reason": "Select an allowlisted DOCX action without executing it.",
                "expected_result": "The action validates and is not executed.",
            }
        else:
            action = {
                "action": "office_create_xlsx",
                "parameters": {
                    "path": f"{OFFICE_WORKSPACE_ROOT}/office_documents/offline_basic/tasks.xlsx",
                    "sheet_name": "Tasks",
                    "headers": ["Task", "Status"],
                    "rows": [["Smoke validation", "Planned"]],
                },
                "reason": "Select an allowlisted XLSX action without executing it.",
                "expected_result": "The action validates and is not executed.",
            }
        self.calls.append({"agent_id": agent.agent_id, "action": action["action"]})
        return ExecutorProviderResult(
            raw_model_output=json.dumps(action, ensure_ascii=False),
            metadata={"provider": "office_document_fake_executor", "agent_id": agent.agent_id},
        )


def _pipeline_config(tmp_path: Path) -> OrchestratorExecutorRunConfig:
    return OrchestratorExecutorRunConfig.model_validate(
        {
            "project_root": PROJECT_ROOT,
            "mode": "fake",
            "models_config_path": "configs/evaluation_models.json",
            "scenario_path": SCENARIO_PATH,
            "out_dir": str(tmp_path / "office_document_fake_pipeline"),
            "run_id": "test_normality_fake_pipeline",
            "orchestrator_model_id": "second_model",
            "executor_model_id": "first_model",
            "max_group_steps": 1,
            "max_steps_per_agent": 1,
            "repair_attempts": 0,
            "execute_actions": False,
            "force": True,
        }
    )


def test_group_history_helper_writes_normality_summary(tmp_path: Path) -> None:
    out_dir, result = _run_group_history_eval(tmp_path)
    summary = _summary(out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME)

    assert result["status"] == "ok"
    assert summary["status"] == "ok"
    assert summary["scenario_id"] == "office_document_file_workflow_basic_v1"
    assert summary["event_count"] == 1
    assert summary["label"] in {"normal", "suspicious", "abnormal"}
    assert isinstance(summary["overall_score"], float)
    assert "overall_normality" in summary["dimension_scores"]
    assert summary["judge_mode"] == "deterministic"


def test_group_history_summary_redacts_absolute_windows_path(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "outside.docx"])
    out_dir, result = _run_group_history_eval(
        tmp_path,
        group_history=_fake_history(
            summary=f"Attempted to inspect {windows_path}",
            artifact_paths=[windows_path],
        ),
    )
    summary_text = (out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(encoding="utf-8")

    assert windows_path not in summary_text
    assert "absolute_path" in result["redactions_applied"]


def test_group_history_summary_redacts_absolute_posix_path(tmp_path: Path) -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    out_dir, result = _run_group_history_eval(
        tmp_path,
        group_history=_fake_history(
            summary=f"Attempted to inspect {posix_path}",
            artifact_paths=[posix_path],
        ),
    )
    summary_text = (out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(encoding="utf-8")

    assert posix_path not in summary_text
    assert "absolute_path" in result["redactions_applied"]


def test_relative_artifact_path_remains_visible(tmp_path: Path) -> None:
    relative_path = "artifacts/office_documents/offline_basic/summary.docx"
    out_dir, _ = _run_group_history_eval(
        tmp_path,
        group_history=_fake_history(artifact_paths=[relative_path]),
    )
    summary = _summary(out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME)

    assert summary["event_preview"][0]["artifact_paths"] == [relative_path]


def test_long_raw_output_is_not_written_by_default(tmp_path: Path) -> None:
    long_text = "A" * 300
    out_dir, _ = _run_group_history_eval(
        tmp_path,
        group_history=_fake_history(summary=long_text),
        config=NormalityEvaluationRunConfig(max_text_chars=40),
    )
    summary_text = (out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(encoding="utf-8")

    assert long_text not in summary_text
    assert "...[truncated]" in summary_text


def test_disabled_config_does_not_write_summary(tmp_path: Path) -> None:
    out_dir = tmp_path / "normality_disabled"
    result = run_normality_evaluation_for_group_history(
        group_history=_fake_history(),
        scenario_id="office_document_file_workflow_basic_v1",
        task_summary="Disabled offline normality evaluation.",
        output_dir=out_dir,
        project_root=tmp_path,
        config=NormalityEvaluationRunConfig(enabled=False, write_summary=False),
    )

    assert result.status == "judge_disabled"
    assert result.label == "not_evaluated"
    assert not (out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).exists()


def test_fake_office_pipeline_result_feeds_normality_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.orchestrator_executor_pipeline as pipeline

    def fail_http_client(*args: object, **kwargs: object) -> object:
        raise AssertionError("fake normality integration must not create an HTTP client")

    def fail_bridge_execution(*args: object, **kwargs: object) -> object:
        raise AssertionError("execute_actions=false must not dispatch real actions")

    monkeypatch.setattr(pipeline.httpx, "Client", fail_http_client)
    monkeypatch.setattr(pipeline.ScriptExecutionBridge, "execute_next_action", fail_bridge_execution)

    pipeline_result = OrchestratorExecutorRunner(
        _pipeline_config(tmp_path),
        orchestrator_provider=OfficeDocumentOrchestratorProvider(),
        executor_provider=OfficeDocumentExecutorProvider(),
    ).run()
    normality_out = tmp_path / "normality_from_pipeline"

    normality_result = write_normality_evaluation_for_pipeline_result(
        pipeline_result,
        output_dir=normality_out,
        project_root=tmp_path,
    )
    summary = _summary(normality_out / NORMALITY_EVALUATION_SUMMARY_FILENAME)

    assert pipeline_result.status == "completed"
    assert all(not attempt.execution_attempted for item in pipeline_result.per_agent_results for attempt in item.attempts)
    assert normality_result.status == "ok"
    assert summary["status"] == "ok"
    assert summary["scenario_id"] == "office_document_file_workflow_basic_v1"
    assert summary["event_count"] == len(pipeline_result.group_history)
    assert "overall_normality" in summary["dimension_scores"]

    assert not list(tmp_path.rglob("*.docx"))
    assert not list(tmp_path.rglob("*.xlsx"))
    assert not list(tmp_path.rglob("*.pptx"))
    assert not normality_out.is_relative_to(PROJECT_ROOT / "experiments")
