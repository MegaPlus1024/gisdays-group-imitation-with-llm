from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_catalog import load_model_catalog
from src.agent.model_comparison_plan import (
    ModelComparisonPlanConfig,
    build_model_comparison_plan,
    write_model_comparison_plan,
)
from src.agent.model_pair_execution_api import (
    ModelPairExecutionApiConfig,
    run_model_pair_execution_matrix,
    run_model_pair_execution_matrix_from_plan_path,
)
from src.agent.model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME,
    NORMALITY_JUDGE_INPUTS_JSONL_FILENAME,
    build_normality_inputs_from_matrix_run_summary,
    build_resource_observations_from_matrix_run_summary,
)
from src.agent.model_pair_matrix_runner import (
    MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
    MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME,
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


def _plan_payload(**overrides: object) -> dict[str, Any]:
    config = ModelComparisonPlanConfig.model_validate(
        {
            "plan_id": "model_pair_execution_api_plan",
            "include_self_pairs": False,
            "repetitions_per_pair": 1,
            "tags": ["model_pair_execution_api_test"],
            **overrides,
        }
    )
    plan = build_model_comparison_plan(
        load_model_catalog(CATALOG_PATH),
        [SCENARIO_PATH],
        config,
        project_root=PROJECT_ROOT,
    ).model_dump(mode="json")
    plan["trials"][0]["task_summary"] = "Run a fake high-level model pair execution API trial."
    plan["trials"][0]["expected_outputs"] = {
        "checks": [{"type": "status_equals", "expected": "succeeded"}],
    }
    plan["trials"][0]["tags"] = ["execution_api", "offline"]
    return plan


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "group_step_index": 1,
        "agent_id": "office_agent",
        "task_id": "task_1",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Fake API entrypoint selected a safe offline action.",
        "metadata": {"execution_attempted": False, "execution_success": None},
    }
    payload.update(overrides)
    return payload


def _fake_pipeline_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "success": True,
        "correctness_score": 0.94,
        "group_history": [_event()],
        "event_history": [_event(action="office_validate_docx")],
        "activity_trace": [_event(action="office_record_summary")],
        "artifacts": [{"path": "artifacts/execution_api/report.docx"}],
        "resource_observation": {
            "runtime_mode": "fake_model_pair_execution_api",
            "backend": "explicit_api_fake_entrypoint",
            "success": True,
            "wall_time_s": 1.8,
        },
        "warnings": ["fake_entrypoint_does_not_call_llama_server"],
        "notes": ["synthetic_model_pair_execution_api_result"],
        "metadata": {"pipeline": "fake_execution_api"},
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_api_builds_executor_and_runs_matrix_plan_with_fake_entrypoint(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result()

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=entrypoint,
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )

    assert result["status"] == "succeeded"
    assert result["trial_count"] == 1
    assert result["succeeded_count"] == 1
    assert len(calls) == 1
    assert calls[0]["pair_id"] == PAIR_ID


def test_api_writes_matrix_summary_and_trial_results_jsonl_by_default(tmp_path: Path) -> None:
    output_dir = tmp_path / "matrix"

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(output_dir=output_dir, run_id="api_matrix_run"),
    )
    summary = _json(output_dir / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME)
    rows = _jsonl(output_dir / MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME)

    assert result["matrix_summary_path"] == MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    assert result["trial_results_path"] == MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME
    assert summary["run_id"] == "api_matrix_run"
    assert summary["execution_mode"] == "injected_pipeline"
    assert rows[0]["resource_observation"]["backend"] == "explicit_api_fake_entrypoint"


def test_api_does_not_write_trial_results_jsonl_when_disabled(tmp_path: Path) -> None:
    output_dir = tmp_path / "matrix"

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(output_dir=output_dir, write_trial_results_jsonl=False),
    )

    assert result["trial_results_path"] is None
    assert (output_dir / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME).is_file()
    assert not (output_dir / MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME).exists()


def test_api_returns_bounded_status_counts_and_relative_paths(tmp_path: Path) -> None:
    result = run_model_pair_execution_matrix(
        _plan_payload(repetitions_per_pair=2),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix", tags=("phase_8_5",)),
    )

    assert result["status"] == "succeeded"
    assert result["run_id"] == "model_pair_matrix_run"
    assert result["allow_runtime_execution"] is False
    assert result["no_runtime_execution"] is True
    assert result["matrix_summary_path"] == MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    assert result["trial_results_path"] == MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME
    assert result["adapter_summary_path"] is None
    assert result["trial_count"] == 2
    assert result["failed_count"] == 0
    assert result["tags"] == ["phase_8_5"]


def test_default_config_sets_no_runtime_execution_in_entrypoint_input(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result()

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=entrypoint,
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )

    assert calls[0]["execution_options"]["allow_runtime_execution"] is False
    assert calls[0]["execution_options"]["no_runtime_execution"] is True
    assert result["allow_runtime_execution"] is False
    assert result["no_runtime_execution"] is True


def test_allow_runtime_execution_true_is_explicitly_passed_to_entrypoint_input(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result(no_runtime_execution=False)

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=entrypoint,
        config=ModelPairExecutionApiConfig(
            output_dir=tmp_path / "matrix",
            allow_runtime_execution=True,
        ),
    )

    assert calls[0]["execution_options"]["allow_runtime_execution"] is True
    assert calls[0]["execution_options"]["no_runtime_execution"] is False
    assert calls[0]["metadata"]["explicit_runtime_opt_in"] is True
    assert result["allow_runtime_execution"] is True
    assert result["no_runtime_execution"] is False


def test_fake_entrypoint_receives_entrypoint_input_not_raw_request(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        assert isinstance(entrypoint_input, dict)
        assert "execution_options" in entrypoint_input
        assert "scenario_config" in entrypoint_input
        assert "model_bindings" in entrypoint_input
        assert "repeat_index" in entrypoint_input
        calls.append(entrypoint_input)
        return _fake_pipeline_result()

    run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=entrypoint,
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )

    assert len(calls) == 1
    assert calls[0]["scenario_id"] == SCENARIO_ID


def test_per_trial_fake_failure_becomes_failed_run_without_crashing(tmp_path: Path) -> None:
    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(
            status="failed",
            success=False,
            failure_reason="fake_pipeline_failed",
            resource_observation={"success": False, "backend": "explicit_api_fake_entrypoint"},
        ),
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )
    summary = _json(tmp_path / "matrix" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME)

    assert result["status"] == "failed"
    assert result["failed_count"] == 1
    assert summary["trial_results"][0]["status"] == "failed"
    assert summary["trial_results"][0]["error_code"] == "fake_pipeline_failed"


def test_exception_from_fake_entrypoint_becomes_controlled_failed_trial(tmp_path: Path) -> None:
    def entrypoint(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("RAW_SECRET_EXCEPTION_DETAIL")

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=entrypoint,
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )
    text = json.dumps(_json(tmp_path / "matrix" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME), ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["failed_count"] == 1
    assert "pipeline_executor_failed" in result["warnings"]
    assert "RAW_SECRET_EXCEPTION_DETAIL" not in text
    assert "RuntimeError" not in text


def test_auto_adapter_outputs_write_resource_normality_and_summary_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "matrix"

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(
            output_dir=output_dir,
            auto_matrix_adapter_outputs=True,
            adapter_id="api_adapter_test",
        ),
    )
    adapter_dir = output_dir / "matrix_adapters"
    adapter_summary = _json(adapter_dir / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME)

    assert (adapter_dir / MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME).is_file()
    assert (adapter_dir / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME).is_file()
    assert result["adapter_summary_path"] == f"matrix_adapters/{MATRIX_RUN_ADAPTER_SUMMARY_FILENAME}"
    assert result["adapter_resource_observations_path"] == f"matrix_adapters/{MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME}"
    assert result["adapter_normality_inputs_path"] == f"matrix_adapters/{NORMALITY_JUDGE_INPUTS_JSONL_FILENAME}"
    assert result["resource_observation_count"] == 1
    assert result["normality_input_count"] == 1
    assert adapter_summary["adapter_id"] == "api_adapter_test"


def test_auto_adapter_outputs_do_not_run_normality_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_judge(*_: object, **__: object) -> object:
        raise AssertionError("normality judge must not run from execution API")

    monkeypatch.setattr("src.agent.normality_judge.run_normality_judge", forbidden_judge)

    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(
            output_dir=tmp_path / "matrix",
            auto_matrix_adapter_outputs=True,
        ),
    )

    assert result["status"] == "succeeded"
    assert result["normality_input_count"] == 1


def test_resource_normality_and_correctness_downstream_compatibility(tmp_path: Path) -> None:
    output_dir = tmp_path / "matrix"

    run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(
            output_dir=output_dir,
            auto_matrix_adapter_outputs=True,
        ),
    )
    summary = _json(output_dir / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME)
    resource_observations = build_resource_observations_from_matrix_run_summary(summary)
    resource_summary = summarize_model_resource_observations(resource_observations)
    normality_inputs = build_normality_inputs_from_matrix_run_summary(summary)
    correctness_inputs = build_correctness_inputs_from_matrix_run_summary(summary)
    correctness_summary = evaluate_task_correctness_batch(correctness_inputs)

    assert resource_observations[0]["backend"] == "explicit_api_fake_entrypoint"
    assert resource_summary.groups["by_pair"][PAIR_ID].success_count == 1
    assert normality_inputs[0]["group_history"][0]["action"] == "office_create_docx"
    assert "normality_trace_missing" not in normality_inputs[0]["warnings"]
    assert correctness_inputs[0].trial_result["task_success"] is True
    assert correctness_summary.passed_count == 1


def test_api_result_does_not_leak_absolute_paths(tmp_path: Path) -> None:
    plan = _plan_payload()
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "scenario.json"])
    plan["scenarios"][0]["scenario_path"] = windows_path
    plan["trials"][0]["scenario_path"] = windows_path

    result = run_model_pair_execution_matrix(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )
    text = json.dumps(result, ensure_ascii=False)

    assert windows_path not in text
    assert "<absolute_path>" not in result["matrix_summary_path"]
    assert result["matrix_summary_path"] == MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME


def test_api_result_does_not_leak_secret_like_text(tmp_path: Path) -> None:
    plan = _plan_payload()
    plan["warnings"] = ["token=SECRET_TOKEN"]
    plan["notes"] = ["api_key=SECRET_KEY"]

    result = run_model_pair_execution_matrix(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(warnings=["password=SECRET_PASSWORD"]),
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix", tags=("secret=TAG_SECRET",)),
    )
    text = json.dumps(result, ensure_ascii=False)

    assert "SECRET_TOKEN" not in text
    assert "SECRET_KEY" not in text
    assert "SECRET_PASSWORD" not in text
    assert "TAG_SECRET" not in text
    assert "<redacted_secret>" in text


def test_plan_path_helper_uses_existing_plan_loader(tmp_path: Path) -> None:
    plan_path = write_model_comparison_plan(
        build_model_comparison_plan(
            load_model_catalog(CATALOG_PATH),
            [SCENARIO_PATH],
            ModelComparisonPlanConfig.model_validate(
                {
                    "plan_id": "model_pair_execution_api_plan_path",
                    "include_self_pairs": False,
                    "repetitions_per_pair": 1,
                }
            ),
            project_root=PROJECT_ROOT,
        ),
        tmp_path / "plan",
    )

    result = run_model_pair_execution_matrix_from_plan_path(
        plan_path,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )

    assert result["status"] == "succeeded"
    assert result["trial_count"] == 1


def test_invalid_output_dir_returns_controlled_error_without_traceback() -> None:
    result = run_model_pair_execution_matrix(
        _plan_payload(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(output_dir=Path("reports") / "forbidden"),
    )

    assert result["status"] == "invalid_input"
    assert result["error"] == "output_dir_forbidden"
    assert result["matrix_summary_path"] is None


def test_no_public_cli_live_mode_added() -> None:
    from src.agent.model_pair_matrix_runner_cli import build_parser

    help_text = build_parser().format_help()

    assert "--plan" in help_text
    assert "--pipeline-entrypoint" not in help_text
    assert "--allow-runtime-execution" not in help_text
    assert "--orchestrator-base-url" not in help_text
    assert "--executor-base-url" not in help_text


def test_no_reports_or_experiments_files_are_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan_payload()
    original_write_text = Path.write_text

    def forbid_reports_or_experiments_write(self: Path, *args: object, **kwargs: object) -> int:
        if "reports" in self.parts or "experiments" in self.parts:
            raise AssertionError("unexpected reports/experiments write")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", forbid_reports_or_experiments_write)

    result = run_model_pair_execution_matrix(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )

    assert result["status"] == "succeeded"


def test_no_model_http_llama_browser_office_imports_or_gguf_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan_payload()
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
        if name.split(".", maxsplit=1)[0] in {
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
            raise AssertionError("model pair execution API must stay dependency-injected")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    import src.agent.model_pair_execution_api as api_module

    importlib.reload(api_module)
    result = api_module.run_model_pair_execution_matrix(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=api_module.ModelPairExecutionApiConfig(output_dir=tmp_path / "matrix"),
    )

    assert result["status"] == "succeeded"
    assert result["no_runtime_execution"] is True
