from __future__ import annotations

import copy
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
    ModelPairTrialExecutionRequest,
    build_trial_execution_requests_from_plan,
    run_model_pair_matrix,
)
from src.agent.model_pair_pipeline_bridge import (
    build_pipeline_trial_context,
    make_model_pair_pipeline_callable,
)
from src.agent.model_pair_pipeline_executor import InjectedPipelineModelPairTrialExecutor
from src.agent.model_resource_evaluation import summarize_model_resource_observations
from src.agent.model_task_correctness_evaluation import build_correctness_inputs_from_matrix_run_summary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
PAIR_ID = "second_model__to__first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"


def _plan_payload(**overrides: object) -> dict[str, Any]:
    config = ModelComparisonPlanConfig.model_validate(
        {
            "plan_id": "pipeline_bridge_plan",
            "include_self_pairs": False,
            "repetitions_per_pair": 1,
            "tags": ["pipeline_bridge_test"],
            **overrides,
        }
    )
    plan = build_model_comparison_plan(
        load_model_catalog(CATALOG_PATH),
        [SCENARIO_PATH],
        config,
        project_root=PROJECT_ROOT,
    ).model_dump(mode="json")
    plan["trials"][0]["task_summary"] = "Run a fake pipeline bridge trial."
    plan["trials"][0]["expected_outputs"] = {
        "checks": [{"type": "status_equals", "expected": "succeeded"}],
    }
    plan["trials"][0]["tags"] = ["bridge_trial", "offline"]
    return plan


def _request() -> ModelPairTrialExecutionRequest:
    return build_trial_execution_requests_from_plan(
        _plan_payload(),
        execution_mode="injected_pipeline",
    )[0]


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "group_step_index": 1,
        "agent_id": "office_agent",
        "task_id": "task_1",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Fake pipeline selected a safe offline action.",
        "metadata": {"execution_attempted": False, "execution_success": None},
    }
    payload.update(overrides)
    return payload


def _fake_pipeline_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "success": True,
        "correctness_score": 0.91,
        "group_history": [_event()],
        "activity_trace": [_event(action="office_validate_docx")],
        "artifacts": [{"path": "artifacts/bridge/report.docx"}],
        "resource_observation": {
            "runtime_mode": "fake_pipeline_bridge",
            "backend": "explicit_bridge_callable",
            "success": True,
            "wall_time_s": 1.4,
        },
        "warnings": ["fake_mode_does_not_call_llama_server"],
        "notes": ["synthetic_bridge_pipeline_result"],
        "metadata": {"pipeline": "fake"},
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def test_build_pipeline_trial_context_includes_trial_pair_scenario_and_model_ids() -> None:
    context = build_pipeline_trial_context(_request())

    assert context["trial_id"].endswith("__r01")
    assert context["scenario_id"] == SCENARIO_ID
    assert context["scenario_path"] == SCENARIO_PATH
    assert context["pair_id"] == PAIR_ID
    assert context["orchestrator_model_id"] == "second_model"
    assert context["executor_model_id"] == "first_model"
    assert context["repeat_index"] == 1
    assert context["execution_mode"] == "injected_pipeline"
    assert context["no_runtime_execution"] is True


def test_context_includes_task_summary_expected_outputs_and_tags() -> None:
    context = build_pipeline_trial_context(_request())

    assert context["task_summary"] == "Run a fake pipeline bridge trial."
    assert context["expected_outputs"]["checks"][0]["type"] == "status_equals"
    assert context["tags"] == ["bridge_trial", "offline"]


def test_context_is_json_serializable_and_does_not_mutate_request() -> None:
    request = _request()
    before = copy.deepcopy(request.model_dump(mode="json"))

    context = build_pipeline_trial_context(request)
    encoded = json.dumps(context, ensure_ascii=False, sort_keys=True)

    assert "pipeline_bridge_plan" in encoded
    assert request.model_dump(mode="json") == before


def test_context_redacts_absolute_paths_and_secret_like_fields() -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "scenario.json"])
    request = ModelPairTrialExecutionRequest(
        trial_id="trial_absolute_path",
        scenario_id=SCENARIO_ID,
        scenario_path=windows_path,
        pair_id=PAIR_ID,
        orchestrator_model_id="second_model",
        executor_model_id="first_model",
        repeat_index=1,
        tags=[f"opened {windows_path}"],
        task_summary="token=SECRET_TOKEN should be hidden",
        expected_outputs={"raw_prompt": "DO_NOT_COPY", "checks": [{"type": "status_equals", "expected": "succeeded"}]},
        metadata={"api_key": "DO_NOT_COPY", "note": "safe"},
        execution_mode="injected_pipeline",
    )

    context_text = json.dumps(build_pipeline_trial_context(request), ensure_ascii=False)

    assert windows_path not in context_text
    assert "SECRET_TOKEN" not in context_text
    assert "DO_NOT_COPY" not in context_text
    assert "<absolute_path>" in context_text
    assert "<redacted_secret>" in context_text


def test_bridge_callable_calls_pipeline_once_and_receives_context_dict() -> None:
    seen: list[dict[str, Any]] = []

    def pipeline(context: dict[str, Any]) -> dict[str, Any]:
        assert isinstance(context, dict)
        assert not isinstance(context, ModelPairTrialExecutionRequest)
        seen.append(context)
        return _fake_pipeline_result()

    result = make_model_pair_pipeline_callable(pipeline)(_request())

    assert len(seen) == 1
    assert seen[0]["pair_id"] == PAIR_ID
    assert result["status"] == "succeeded"
    assert result["task_success"] is True
    assert result["metadata"]["request"]["trial_id"] == seen[0]["trial_id"]


def test_bridge_adapts_failed_fake_pipeline_result() -> None:
    def pipeline(_: dict[str, Any]) -> dict[str, Any]:
        return _fake_pipeline_result(
            status="failed",
            success=False,
            failure_reason="fake_pipeline_failed",
            resource_observation={"success": False},
        )

    result = make_model_pair_pipeline_callable(pipeline)(_request())

    assert result["status"] == "failed"
    assert result["task_success"] is False
    assert result["error_code"] == "fake_pipeline_failed"
    assert result["resource_observation"]["success"] is False


def test_bridge_works_with_injected_executor() -> None:
    executor = InjectedPipelineModelPairTrialExecutor(
        make_model_pair_pipeline_callable(lambda _: _fake_pipeline_result())
    )

    result = executor.execute_trial(_request())

    assert result.status == "succeeded"
    assert result.task_success is True
    assert result.correctness_score == pytest.approx(0.91)
    assert result.group_history[0]["action"] == "office_create_docx"
    assert result.activity_trace[0]["action"] == "office_validate_docx"
    assert result.resource_observation is not None
    assert result.resource_observation["backend"] == "explicit_bridge_callable"


def test_bridge_works_in_run_model_pair_matrix() -> None:
    summary = run_model_pair_matrix(
        _plan_payload(repetitions_per_pair=2),
        InjectedPipelineModelPairTrialExecutor(
            make_model_pair_pipeline_callable(lambda _: _fake_pipeline_result())
        ),
        execution_mode="injected_pipeline",
    )

    assert summary.trial_count == 2
    assert summary.succeeded_count == 2
    assert summary.pair_summaries[0]["resource_observation_count"] == 2
    assert summary.trial_results[0].group_history[0]["action"] == "office_create_docx"


def test_downstream_adapters_see_resource_normality_and_correctness_fields() -> None:
    summary = run_model_pair_matrix(
        _plan_payload(),
        InjectedPipelineModelPairTrialExecutor(
            make_model_pair_pipeline_callable(lambda _: _fake_pipeline_result())
        ),
        execution_mode="injected_pipeline",
    )

    resource_observations = build_resource_observations_from_matrix_run_summary(summary)
    resource_summary = summarize_model_resource_observations(resource_observations)
    normality_inputs = build_normality_inputs_from_matrix_run_summary(summary)
    correctness_inputs = build_correctness_inputs_from_matrix_run_summary(summary)

    assert resource_observations[0]["backend"] == "explicit_bridge_callable"
    assert resource_summary.groups["by_pair"][PAIR_ID].success_count == 1
    assert normality_inputs[0]["group_history"][0]["action"] == "office_create_docx"
    assert normality_inputs[0]["events"][0]["action"] == "office_create_docx"
    assert "normality_trace_missing" not in normality_inputs[0]["warnings"]
    assert correctness_inputs[0].trial_result["task_success"] is True
    assert correctness_inputs[0].trial_result["correctness_score"] == pytest.approx(0.91)


def test_pipeline_callable_exception_is_handled_by_injected_executor_without_raw_leak() -> None:
    def pipeline(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("RAW_SECRET_EXCEPTION_DETAIL")

    result = InjectedPipelineModelPairTrialExecutor(make_model_pair_pipeline_callable(pipeline)).execute_trial(_request())
    text = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

    assert result.status == "failed"
    assert result.error_code == "pipeline_executor_failed"
    assert "RAW_SECRET_EXCEPTION_DETAIL" not in text
    assert "RuntimeError" not in text


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
            raise AssertionError("pipeline bridge must stay data-only")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    import src.agent.model_pair_pipeline_bridge as bridge_module

    importlib.reload(bridge_module)
    request = ModelPairTrialExecutionRequest(
        trial_id="no_runtime_trial",
        scenario_id=SCENARIO_ID,
        scenario_path=SCENARIO_PATH,
        pair_id=PAIR_ID,
        orchestrator_model_id="second_model",
        executor_model_id="first_model",
        repeat_index=1,
        execution_mode="injected_pipeline",
    )
    result = bridge_module.make_model_pair_pipeline_callable(lambda _: _fake_pipeline_result())(request)

    assert result["status"] == "succeeded"
    assert result["no_runtime_execution"] is True
