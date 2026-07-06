from __future__ import annotations

import copy
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_catalog import load_model_catalog
from src.agent.model_comparison_plan import ModelComparisonPlanConfig, build_model_comparison_plan
from src.agent.model_pair_matrix_adapters import (
    build_normality_inputs_from_matrix_run_summary,
    build_resource_observations_from_matrix_run_summary,
)
from src.agent.model_pair_matrix_runner import (
    ModelPairTrialExecutionRequest,
    build_trial_execution_requests_from_plan,
    run_model_pair_matrix,
)
from src.agent.model_pair_pipeline_executor import InjectedPipelineModelPairTrialExecutor
from src.agent.model_pair_pipeline_result_adapter import (
    PIPELINE_RESULT_ADAPTER_NAME,
    adapt_orchestrator_executor_pipeline_result,
    make_pipeline_result_adapter_callable,
)
from src.agent.model_resource_evaluation import summarize_model_resource_observations
from src.agent.model_task_correctness_evaluation import (
    build_correctness_inputs_from_matrix_run_summary,
    evaluate_task_correctness_batch,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
PAIR_ID = "second_model__to__first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"


@dataclass
class FakePipelineResult:
    status: str
    success: bool
    group_history: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifact_dir: str | None = None


def _plan_payload(**overrides: object) -> dict[str, Any]:
    config = ModelComparisonPlanConfig.model_validate(
        {
            "plan_id": "pipeline_result_adapter_plan",
            "include_self_pairs": False,
            "repetitions_per_pair": 1,
            "tags": ["pipeline_result_adapter_test"],
            **overrides,
        }
    )
    plan = build_model_comparison_plan(
        load_model_catalog(CATALOG_PATH),
        [SCENARIO_PATH],
        config,
        project_root=PROJECT_ROOT,
    ).model_dump(mode="json")
    plan["trials"][0]["task_summary"] = "Validate adapted fake pipeline result."
    plan["trials"][0]["expected_outputs"] = {
        "checks": [{"type": "status_equals", "expected": "succeeded"}],
    }
    return plan


def _request() -> ModelPairTrialExecutionRequest:
    return build_trial_execution_requests_from_plan(
        _plan_payload(),
        execution_mode="injected_pipeline",
    )[0]


def _history_event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "group_step_index": 1,
        "agent_id": "office_agent",
        "task_id": "task_1",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Executor step completed.",
        "metadata": {"execution_attempted": False, "execution_success": None},
    }
    payload.update(overrides)
    return payload


def _pipeline_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "success": True,
        "group_history": [_history_event()],
        "event_history": [_history_event(action="office_validate_docx")],
        "activity_trace": [_history_event(action="office_record_summary")],
        "artifacts": [{"path": "artifacts/pipeline/report.docx"}],
        "output_files": ["artifacts/pipeline/summary.json"],
        "resource_observation": {
            "runtime_mode": "fake_pipeline",
            "backend": "orchestrator_executor_fake",
            "success": True,
            "wall_time_s": 1.1,
        },
        "warnings": ["fake_mode_does_not_call_llama_server"],
        "notes": ["Synthetic fake pipeline result."],
        "metadata": {"quality_metric": "synthetic"},
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def test_adapts_dict_success_result_to_succeeded_normalized_result() -> None:
    result = adapt_orchestrator_executor_pipeline_result(_pipeline_result(status="completed", success=True))

    assert result["status"] == "succeeded"
    assert result["task_success"] is True
    assert result["group_history"][0]["action"] == "office_create_docx"
    assert result["metadata"]["adapter_name"] == PIPELINE_RESULT_ADAPTER_NAME
    assert result["metadata"]["pipeline_status_raw"] == "completed"
    assert result["no_runtime_execution"] is True


def test_adapts_dict_failure_and_skipped_results() -> None:
    failed = adapt_orchestrator_executor_pipeline_result(
        _pipeline_result(status="failed", success=False, failure_reason="validation_failed")
    )
    skipped = adapt_orchestrator_executor_pipeline_result(_pipeline_result(status="skipped", success=None))

    assert failed["status"] == "failed"
    assert failed["task_success"] is False
    assert failed["error_code"] == "validation_failed"
    assert skipped["status"] == "skipped"
    assert skipped["task_success"] is None


def test_unknown_status_gets_warning_and_controlled_status() -> None:
    failed = adapt_orchestrator_executor_pipeline_result(_pipeline_result(status="mystery", success=None))
    skipped = adapt_orchestrator_executor_pipeline_result(
        _pipeline_result(status="mystery", success=None),
        default_status="skipped",
    )

    assert failed["status"] == "failed"
    assert "pipeline_status_unknown" in failed["warnings"]
    assert skipped["status"] == "skipped"
    assert "pipeline_status_unknown" in skipped["warnings"]


def test_extracts_histories_and_fallback_activity_trace() -> None:
    result = adapt_orchestrator_executor_pipeline_result(
        {
            "status": "completed",
            "success": True,
            "group_history": [_history_event(action="group_action")],
            "event_history": [_history_event(action="event_action")],
            "events": [_history_event(action="event_fallback")],
        }
    )

    assert result["group_history"][0]["action"] == "group_action"
    assert result["event_history"][0]["action"] == "event_action"
    assert result["activity_trace"][0]["action"] == "event_fallback"


def test_extracts_steps_and_per_agent_attempts_when_activity_trace_missing() -> None:
    steps = adapt_orchestrator_executor_pipeline_result(
        {"status": "completed", "success": True, "steps": [_history_event(action="step_action")]}
    )
    attempts = adapt_orchestrator_executor_pipeline_result(
        {
            "status": "completed",
            "success": True,
            "per_agent_results": [
                {
                    "agent_id": "office_agent",
                    "attempts": [
                        {
                            "group_step_index": 1,
                            "agent_step_index": 1,
                            "task_id": "task_1",
                            "action": "office_create_docx",
                            "parse_success": True,
                            "validation_accepted": True,
                            "execution_attempted": False,
                            "execution_success": None,
                        }
                    ],
                }
            ],
        }
    )

    assert steps["activity_trace"][0]["action"] == "step_action"
    assert attempts["activity_trace"][0]["agent_id"] == "office_agent"
    assert attempts["activity_trace"][0]["action"] == "office_create_docx"


def test_extracts_artifact_refs_and_resource_observation() -> None:
    result = adapt_orchestrator_executor_pipeline_result(
        _pipeline_result(
            artifacts=[{"path": "artifacts/a.docx"}, {"artifact_path": "artifacts/b.xlsx"}],
            output_files=["artifacts/c.json"],
            generated_files=[{"file_path": "artifacts/d.md"}],
        )
    )

    assert result["artifact_refs"] == [
        "artifacts/a.docx",
        "artifacts/b.xlsx",
        "artifacts/c.json",
        "artifacts/d.md",
    ]
    assert result["resource_observation"]["runtime_mode"] == "fake_pipeline"


def test_extracts_task_success_from_success_completed_and_status_fields() -> None:
    assert adapt_orchestrator_executor_pipeline_result({"success": True})["task_success"] is True
    assert adapt_orchestrator_executor_pipeline_result({"completed": True})["task_success"] is True
    assert adapt_orchestrator_executor_pipeline_result({"status": "failed"})["task_success"] is False
    assert adapt_orchestrator_executor_pipeline_result({"status": "skipped"})["task_success"] is None


def test_accepts_dataclass_or_object_like_result_without_exact_type() -> None:
    result = adapt_orchestrator_executor_pipeline_result(
        FakePipelineResult(
            status="completed",
            success=True,
            group_history=[_history_event()],
            artifact_dir="artifacts/fake_pipeline",
        )
    )

    assert result["status"] == "succeeded"
    assert result["group_history"][0]["agent_id"] == "office_agent"
    assert result["artifact_refs"] == ["artifacts/fake_pipeline"]
    assert result["metadata"]["source_result_type"] == "FakePipelineResult"


def test_adapter_does_not_mutate_input() -> None:
    payload = _pipeline_result(group_history=[_history_event(metadata={"path": "artifacts/a.txt"})])
    before = copy.deepcopy(payload)

    adapt_orchestrator_executor_pipeline_result(payload)

    assert payload == before


def test_redacts_absolute_paths_and_secret_like_text() -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "report.docx"])
    posix_path = "/home/example/secret/report.docx"
    result = adapt_orchestrator_executor_pipeline_result(
        _pipeline_result(
            group_history=[
                _history_event(
                    summary=f"opened {windows_path}",
                    metadata={"posix": posix_path, "note": "token=SECRET_TOKEN"},
                )
            ],
            artifact_dir=windows_path,
            notes=[f"read {posix_path}"],
        )
    )
    text = json.dumps(result, ensure_ascii=False)

    assert windows_path not in text
    assert posix_path not in text
    assert "SECRET_TOKEN" not in text
    assert "<absolute_path>" in text
    assert "<redacted_secret>" in text


def test_drops_raw_prompt_response_fields_and_bounds_long_text() -> None:
    marker = "RAW_PROMPT_RESPONSE_MARKER_SHOULD_NOT_COPY"
    result = adapt_orchestrator_executor_pipeline_result(
        _pipeline_result(
            group_history=[
                _history_event(
                    raw_prompt=marker,
                    raw_response=marker,
                    raw_model_output=marker,
                    summary="x" * 700,
                )
            ],
            metadata={"raw_response": marker},
        )
    )
    text = json.dumps(result, ensure_ascii=False)

    assert marker not in text
    assert "raw_prompt" not in text
    assert "raw_response" not in text
    assert result["group_history"][0]["summary"].endswith("...[truncated]")


def test_adapter_callable_calls_pipeline_once_and_works_with_injected_executor() -> None:
    calls: list[ModelPairTrialExecutionRequest] = []

    def pipeline(request: ModelPairTrialExecutionRequest) -> dict[str, Any]:
        calls.append(request)
        return _pipeline_result()

    request = _request()
    adapted_callable = make_pipeline_result_adapter_callable(pipeline)
    normalized = adapted_callable(request)

    assert len(calls) == 1
    assert normalized["status"] == "succeeded"

    executor_calls: list[ModelPairTrialExecutionRequest] = []

    def executor_pipeline(executor_request: ModelPairTrialExecutionRequest) -> dict[str, Any]:
        executor_calls.append(executor_request)
        return _pipeline_result()

    trial_result = InjectedPipelineModelPairTrialExecutor(
        make_pipeline_result_adapter_callable(executor_pipeline)
    ).execute_trial(request)

    assert len(executor_calls) == 1
    assert trial_result.status == "succeeded"
    assert trial_result.task_success is True
    assert trial_result.group_history[0]["action"] == "office_create_docx"


def test_adapted_result_flows_through_matrix_resource_normality_and_correctness() -> None:
    summary = run_model_pair_matrix(
        _plan_payload(),
        InjectedPipelineModelPairTrialExecutor(
            make_pipeline_result_adapter_callable(lambda _: _pipeline_result())
        ),
        execution_mode="injected_pipeline",
    )

    resource_observations = build_resource_observations_from_matrix_run_summary(summary)
    resource_summary = summarize_model_resource_observations(resource_observations)
    normality_inputs = build_normality_inputs_from_matrix_run_summary(summary)
    correctness_inputs = build_correctness_inputs_from_matrix_run_summary(summary)
    correctness_summary = evaluate_task_correctness_batch(correctness_inputs)

    assert resource_observations[0]["backend"] == "orchestrator_executor_fake"
    assert resource_summary.groups["by_pair"][PAIR_ID].success_count == 1
    assert normality_inputs[0]["group_history"][0]["action"] == "office_create_docx"
    assert "normality_trace_missing" not in normality_inputs[0]["warnings"]
    assert correctness_inputs[0].trial_status == "succeeded"
    assert correctness_summary.passed_count == 1


def test_no_model_http_llama_browser_office_imports_or_gguf_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_gguf_exists(self: Path) -> bool:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF exists check")
        return original_exists(self)

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF read")
        return original_read_text(self, *args, **kwargs)

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {
            "httpx",
            "requests",
            "openai",
            "playwright",
            "selenium",
            "torch",
            "llama_cpp",
            "docx",
            "openpyxl",
            "pptx",
        }:
            raise AssertionError("pipeline result adapter must stay data-only")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    import src.agent.model_pair_pipeline_result_adapter as adapter_module

    importlib.reload(adapter_module)
    result = adapter_module.adapt_orchestrator_executor_pipeline_result(_pipeline_result())

    assert result["status"] == "succeeded"
    assert result["no_runtime_execution"] is True
