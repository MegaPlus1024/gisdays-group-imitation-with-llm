from __future__ import annotations

import importlib
import json
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
    MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
    ModelPairTrialExecutionRequest,
    build_trial_execution_requests_from_plan,
    run_model_pair_matrix,
    write_model_pair_matrix_run_summary,
)
from src.agent.model_pair_pipeline_executor import InjectedPipelineModelPairTrialExecutor
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


def _plan_payload(**overrides: object) -> dict[str, Any]:
    config = ModelComparisonPlanConfig.model_validate(
        {
            "plan_id": "injected_pipeline_plan",
            "include_self_pairs": False,
            "repetitions_per_pair": 1,
            "tags": ["injected_pipeline_test"],
            **overrides,
        }
    )
    plan = build_model_comparison_plan(
        load_model_catalog(CATALOG_PATH),
        [SCENARIO_PATH],
        config,
        project_root=PROJECT_ROOT,
    ).model_dump(mode="json")
    plan["trials"][0]["task_summary"] = "Create an offline fixture artifact and validate it."
    plan["trials"][0]["expected_outputs"] = {
        "checks": [{"type": "status_equals", "expected": "succeeded"}],
    }
    return plan


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": "office_agent",
        "role": "office document worker",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Created an offline fixture artifact.",
        "artifact_paths": ["artifacts/injected_pipeline/report.docx"],
    }
    payload.update(overrides)
    return payload


def _pipeline_payload(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "succeeded",
        "task_success": True,
        "correctness_score": 0.88,
        "group_history": [_event()],
        "event_history": [_event(action="office_validate_docx")],
        "activity_trace": [_event(action="office_record_summary")],
        "artifact_refs": ["artifacts/injected_pipeline/report.docx"],
        "resource_observation": {
            "runtime_mode": "offline_injected_fixture",
            "backend": "injected_callable",
            "success": True,
            "wall_time_s": 1.25,
        },
        "warnings": [],
        "notes": ["synthetic_injected_pipeline_result"],
        "metadata": {"source": "test_callable"},
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _request() -> ModelPairTrialExecutionRequest:
    return build_trial_execution_requests_from_plan(
        _plan_payload(),
        execution_mode="injected_pipeline",
    )[0]


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_injected_executor_calls_callable_once_per_trial_and_passes_context() -> None:
    plan = _plan_payload(repetitions_per_pair=2)
    calls: list[ModelPairTrialExecutionRequest] = []

    def pipeline(request: ModelPairTrialExecutionRequest) -> dict[str, Any]:
        calls.append(request)
        return _pipeline_payload()

    summary = run_model_pair_matrix(
        plan,
        InjectedPipelineModelPairTrialExecutor(pipeline),
        execution_mode="injected_pipeline",
    )

    assert len(calls) == 2
    assert [call.repeat_index for call in calls] == [1, 2]
    assert calls[0].trial_id == plan["trials"][0]["trial_id"]
    assert calls[0].scenario_id == SCENARIO_ID
    assert calls[0].scenario_path == SCENARIO_PATH
    assert calls[0].pair_id == PAIR_ID
    assert calls[0].orchestrator_model_id == "second_model"
    assert calls[0].executor_model_id == "first_model"
    assert calls[0].task_summary == "Create an offline fixture artifact and validate it."
    assert calls[0].expected_outputs["checks"][0]["type"] == "status_equals"
    assert calls[0].execution_mode == "injected_pipeline"
    assert summary.succeeded_count == 2


def test_successful_callable_result_maps_to_succeeded_trial_result() -> None:
    result = InjectedPipelineModelPairTrialExecutor(lambda request: _pipeline_payload()).execute_trial(_request())

    assert result.status == "succeeded"
    assert result.task_success is True
    assert result.correctness_score == pytest.approx(0.88)
    assert result.trial_id == _request().trial_id
    assert result.pair_id == PAIR_ID
    assert result.no_runtime_execution is True
    assert result.execution_mode == "injected_pipeline"


def test_failed_and_skipped_callable_results_map_to_trial_statuses() -> None:
    request = _request()

    failed = InjectedPipelineModelPairTrialExecutor(
        lambda _: _pipeline_payload(status="failed", task_success=False, error_code="fixture_failed")
    ).execute_trial(request)
    skipped = InjectedPipelineModelPairTrialExecutor(
        lambda _: _pipeline_payload(status="skipped", task_success=None, correctness_score=None)
    ).execute_trial(request)

    assert failed.status == "failed"
    assert failed.error_code == "fixture_failed"
    assert failed.task_success is False
    assert skipped.status == "skipped"
    assert skipped.task_success is None


def test_unknown_status_becomes_controlled_failed_result() -> None:
    result = InjectedPipelineModelPairTrialExecutor(
        lambda _: _pipeline_payload(status="mystery")
    ).execute_trial(_request())

    assert result.status == "failed"
    assert result.error_code == "pipeline_result_status_invalid"
    assert "pipeline_result_status_invalid" in result.warnings


def test_callable_exception_becomes_failed_result_without_raw_exception_leak() -> None:
    def pipeline(_: ModelPairTrialExecutionRequest) -> dict[str, Any]:
        raise RuntimeError("RAW_SECRET_EXCEPTION_DETAIL")

    result = InjectedPipelineModelPairTrialExecutor(pipeline).execute_trial(_request())
    text = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

    assert result.status == "failed"
    assert result.error_code == "pipeline_executor_failed"
    assert "pipeline_executor_failed" in result.warnings
    assert "RAW_SECRET_EXCEPTION_DETAIL" not in text
    assert "RuntimeError" not in text


def test_raw_prompt_response_and_secret_like_fields_are_not_copied() -> None:
    marker = "RAW_PROMPT_RESPONSE_MARKER_SHOULD_NOT_COPY"
    result = InjectedPipelineModelPairTrialExecutor(
        lambda _: _pipeline_payload(
            group_history=[_event(raw_prompt=marker, summary="token=SECRET_TOKEN")],
            metadata={"raw_response": marker, "api_key": marker},
            resource_observation={"raw_response": marker, "success": True},
        )
    ).execute_trial(_request())
    text = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

    assert marker not in text
    assert "SECRET_TOKEN" not in text
    assert "<redacted_secret>" in text


def test_trace_resource_and_correctness_outputs_feed_downstream_layers() -> None:
    summary = run_model_pair_matrix(
        _plan_payload(),
        InjectedPipelineModelPairTrialExecutor(lambda _: _pipeline_payload()),
        execution_mode="injected_pipeline",
    )

    resource_observations = build_resource_observations_from_matrix_run_summary(summary)
    resource_summary = summarize_model_resource_observations(resource_observations)
    normality_inputs = build_normality_inputs_from_matrix_run_summary(summary)
    correctness_inputs = build_correctness_inputs_from_matrix_run_summary(summary)
    correctness_summary = evaluate_task_correctness_batch(correctness_inputs)

    assert resource_observations[0]["runtime_mode"] == "offline_injected_fixture"
    assert resource_observations[0]["pair_id"] == PAIR_ID
    assert resource_summary.groups["by_pair"][PAIR_ID].success_count == 1
    assert normality_inputs[0]["group_history"][0]["action"] == "office_create_docx"
    assert normality_inputs[0]["events"][0]["action"] == "office_create_docx"
    assert "normality_trace_missing" not in normality_inputs[0]["warnings"]
    assert correctness_inputs[0].trial_result["task_success"] is True
    assert correctness_inputs[0].trial_result["correctness_score"] == pytest.approx(0.88)
    assert correctness_inputs[0].artifact_refs == ["artifacts/injected_pipeline/report.docx"]
    assert correctness_inputs[0].expected_outputs["checks"][0]["type"] == "status_equals"
    assert correctness_summary.passed_count == 1


def test_matrix_run_summary_with_injected_executor_writes_json(tmp_path: Path) -> None:
    summary = run_model_pair_matrix(
        _plan_payload(),
        InjectedPipelineModelPairTrialExecutor(lambda _: _pipeline_payload()),
        output_dir=tmp_path / "matrix",
        execution_mode="injected_pipeline",
        write_trial_results_jsonl=True,
    )
    summary_path = write_model_pair_matrix_run_summary(summary, tmp_path / "matrix_copy")
    payload = _json(summary_path)

    assert (tmp_path / "matrix" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME).is_file()
    assert summary_path == tmp_path / "matrix_copy" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    assert payload["execution_mode"] == "injected_pipeline"
    assert payload["trial_results"][0]["group_history"][0]["action"] == "office_create_docx"
    assert payload["trial_results"][0]["resource_observation"]["backend"] == "injected_callable"


def test_no_model_http_llama_browser_office_imports_or_gguf_reads(
    tmp_path: Path,
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
            raise AssertionError("injected matrix executor must stay dependency-injected")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    import src.agent.model_pair_pipeline_executor as executor_module

    importlib.reload(executor_module)
    summary = run_model_pair_matrix(
        _plan_payload(),
        executor_module.InjectedPipelineModelPairTrialExecutor(lambda _: _pipeline_payload()),
        output_dir=tmp_path / "matrix",
        execution_mode="injected_pipeline",
    )

    assert summary.succeeded_count == 1
    assert summary.no_runtime_execution is True
