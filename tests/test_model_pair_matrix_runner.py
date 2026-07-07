from __future__ import annotations

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
from src.agent.model_pair_matrix_runner import (
    MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
    MODEL_PAIR_MATRIX_RUN_SUMMARY_SCHEMA_VERSION,
    MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME,
    DryRunModelPairTrialExecutor,
    ModelPairMatrixPlanError,
    ModelPairTrialExecutionRequest,
    ModelPairTrialExecutionResult,
    StaticModelPairTrialExecutor,
    build_trial_execution_requests_from_plan,
    run_model_pair_matrix,
    write_model_pair_matrix_run_summary,
)
from src.agent.model_pair_matrix_runner_cli import main as matrix_cli_main
from src.agent.model_pair_mini_matrix_aggregation import aggregate_mini_matrix_results
from src.agent.model_resource_evaluation import summarize_model_resource_observations


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _plan(**overrides: object):
    config_payload = {
        "plan_id": "matrix_runner_test_plan",
        "include_self_pairs": False,
        "repetitions_per_pair": 1,
        "tags": ["matrix_runner_test"],
        **overrides,
    }
    return build_model_comparison_plan(
        load_model_catalog(CATALOG_PATH),
        [SCENARIO_PATH],
        ModelComparisonPlanConfig.model_validate(config_payload),
        project_root=PROJECT_ROOT,
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_builds_trial_requests_from_model_comparison_plan() -> None:
    plan = _plan(repetitions_per_pair=2)

    requests = build_trial_execution_requests_from_plan(plan)

    assert [request.repeat_index for request in requests] == [1, 2]
    assert requests[0].trial_id.endswith("__r01")
    assert requests[0].pair_id == "second_model__to__first_model"
    assert requests[0].scenario_path == SCENARIO_PATH
    assert requests[0].orchestrator_model_id == "second_model"
    assert requests[0].executor_model_id == "first_model"
    assert requests[0].no_runtime_execution is True
    assert "matrix_runner_test" in requests[0].tags


def test_dry_run_executor_returns_dry_run_for_each_trial() -> None:
    plan = _plan(repetitions_per_pair=2)
    executor = DryRunModelPairTrialExecutor()

    results = [
        executor.execute_trial(request)
        for request in build_trial_execution_requests_from_plan(plan)
    ]

    assert [result.status for result in results] == ["dry_run", "dry_run"]
    assert all(result.no_runtime_execution is True for result in results)
    assert all(result.task_success is None for result in results)


def test_runner_calls_executor_once_per_trial() -> None:
    plan = _plan(repetitions_per_pair=2)

    class CountingExecutor:
        def __init__(self) -> None:
            self.requests: list[ModelPairTrialExecutionRequest] = []

        def execute_trial(self, request: ModelPairTrialExecutionRequest) -> ModelPairTrialExecutionResult:
            self.requests.append(request)
            return ModelPairTrialExecutionResult(
                trial_id=request.trial_id,
                scenario_id=request.scenario_id,
                pair_id=request.pair_id,
                orchestrator_model_id=request.orchestrator_model_id,
                executor_model_id=request.executor_model_id,
                status="succeeded",
                task_success=True,
                correctness_score=0.9,
                no_runtime_execution=True,
                execution_mode=request.execution_mode,
            )

    executor = CountingExecutor()

    summary = run_model_pair_matrix(plan, executor)

    assert len(executor.requests) == len(plan.trials) == 2
    assert summary.succeeded_count == 2


def test_runner_summary_counts_dry_run_trials() -> None:
    summary = run_model_pair_matrix(_plan(repetitions_per_pair=2), DryRunModelPairTrialExecutor())

    assert summary.schema_version == MODEL_PAIR_MATRIX_RUN_SUMMARY_SCHEMA_VERSION
    assert summary.trial_count == 2
    assert summary.dry_run_count == 2
    assert summary.failed_count == 0
    assert summary.pair_summaries[0]["dry_run_count"] == 2
    assert summary.scenario_summaries[0]["dry_run_count"] == 2


def test_static_executor_can_return_succeeded_and_failed_results() -> None:
    plan = _plan(repetitions_per_pair=2)
    requests = build_trial_execution_requests_from_plan(plan)
    executor = StaticModelPairTrialExecutor(
        {
            requests[0].trial_id: {
                "status": "succeeded",
                "task_success": True,
                "correctness_score": 0.95,
            },
            requests[1].trial_id: {
                "status": "failed",
                "task_success": False,
                "error_code": "synthetic_failure",
                "warnings": ["synthetic_warning"],
            },
        }
    )

    summary = run_model_pair_matrix(plan, executor)

    assert summary.succeeded_count == 1
    assert summary.failed_count == 1
    assert summary.trial_results[0].correctness_score == 0.95
    assert summary.trial_results[1].error_code == "synthetic_failure"
    assert "synthetic_warning" in summary.warnings


def test_executor_exception_becomes_failed_trial_without_raw_exception_leak() -> None:
    class RaisingExecutor:
        def execute_trial(self, request: ModelPairTrialExecutionRequest) -> ModelPairTrialExecutionResult:
            raise RuntimeError("RAW_SECRET_EXCEPTION_DETAIL")

    summary = run_model_pair_matrix(_plan(), RaisingExecutor())
    payload_text = json.dumps(summary.model_dump(mode="json"), ensure_ascii=False)

    assert summary.failed_count == 1
    assert summary.trial_results[0].error_code == "trial_executor_failed"
    assert "RAW_SECRET_EXCEPTION_DETAIL" not in payload_text
    assert "RuntimeError" not in payload_text


def test_invalid_plan_missing_trials_returns_controlled_error() -> None:
    payload = _plan().model_dump(mode="json")
    payload.pop("trials")

    with pytest.raises(ModelPairMatrixPlanError, match="plan_trials_missing"):
        build_trial_execution_requests_from_plan(payload)


def test_trial_referencing_missing_pair_is_rejected() -> None:
    payload = _plan().model_dump(mode="json")
    payload["trials"][0]["pair_id"] = "missing_pair"

    with pytest.raises(ModelPairMatrixPlanError, match="trial_pair_ref_missing"):
        build_trial_execution_requests_from_plan(payload)


def test_summary_json_written_to_tmp_output_dir(tmp_path: Path) -> None:
    summary = run_model_pair_matrix(_plan(), DryRunModelPairTrialExecutor())

    summary_path = write_model_pair_matrix_run_summary(summary, tmp_path / "matrix")
    payload = _load_json(summary_path)

    assert summary_path == tmp_path / "matrix" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    assert payload["schema_version"] == MODEL_PAIR_MATRIX_RUN_SUMMARY_SCHEMA_VERSION
    assert payload["dry_run_count"] == 1


def test_optional_trial_results_jsonl_written(tmp_path: Path) -> None:
    summary = run_model_pair_matrix(_plan(repetitions_per_pair=2), DryRunModelPairTrialExecutor())

    write_model_pair_matrix_run_summary(
        summary,
        tmp_path / "matrix",
        write_trial_results_jsonl=True,
    )
    jsonl_path = tmp_path / "matrix" / MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME
    lines = [line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(lines) == 2
    assert json.loads(lines[0])["status"] == "dry_run"


def test_cli_dry_run_works_on_synthetic_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = write_model_comparison_plan(_plan(repetitions_per_pair=2), tmp_path / "plan")

    code = matrix_cli_main(
        [
            "--plan",
            str(plan_path),
            "--output-dir",
            str(tmp_path / "matrix"),
            "--run-id",
            "cli_matrix_run",
            "--write-trial-results-jsonl",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    summary = _load_json(tmp_path / "matrix" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME)

    assert code == 0
    assert payload == {
        "dry_run_count": 2,
        "execution_mode": "dry_run",
        "failed_count": 0,
        "run_id": "cli_matrix_run",
        "status": "ok",
        "summary_path": MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
        "trial_count": 2,
    }
    assert summary["run_id"] == "cli_matrix_run"
    assert (tmp_path / "matrix" / MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME).is_file()


def test_cli_rejects_missing_plan_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = matrix_cli_main(
        [
            "--plan",
            str(tmp_path / "missing_plan.json"),
            "--output-dir",
            str(tmp_path / "matrix"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "plan_file_missing"
    assert "Traceback" not in captured.err


def test_cli_rejects_unsupported_execution_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = write_model_comparison_plan(_plan(), tmp_path / "plan")

    code = matrix_cli_main(
        [
            "--plan",
            str(plan_path),
            "--output-dir",
            str(tmp_path / "matrix"),
            "--execution-mode",
            "local",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "unsupported_execution_mode"


def test_resource_observation_shape_is_compatible_with_resource_evaluator() -> None:
    plan = _plan()
    request = build_trial_execution_requests_from_plan(plan)[0]
    executor = StaticModelPairTrialExecutor(
        {
            request.trial_id: {
                "status": "succeeded",
                "task_success": True,
                "resource_observation": {
                    "pair_id": request.pair_id,
                    "orchestrator_model_id": request.orchestrator_model_id,
                    "executor_model_id": request.executor_model_id,
                    "scenario_id": request.scenario_id,
                    "trial_id": request.trial_id,
                    "success": True,
                    "wall_time_s": 1.25,
                    "peak_ram_gb": 2.5,
                    "peak_vram_gb": 0.0,
                    "runtime_mode": "offline_static",
                    "backend": "static_fixture",
                },
            }
        }
    )

    summary = run_model_pair_matrix(plan, executor)
    resource_summary = summarize_model_resource_observations(
        [summary.trial_results[0].resource_observation or {}],
        summary_id="matrix_resource_compat",
    )

    assert resource_summary.status == "ok"
    assert resource_summary.groups["by_pair"][request.pair_id].observation_count == 1
    assert resource_summary.groups["by_pair"][request.pair_id].success_count == 1


def _write_fake_mini_matrix_repeat(
    root: Path,
    run_id: str,
    *,
    status: str = "succeeded",
    task_success: bool = True,
    correctness_score: float | None = 1.0,
    execution_success_count: int = 2,
    office_artifact_count: int = 2,
) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    group_history = [
        {
            "task_id": f"t{index}",
            "action": "office_append_docx_section",
            "metadata": {
                "validation_accepted": True,
                "execution_attempted": True,
                "execution_success": index <= execution_success_count,
                "action_execution_enabled": True,
            },
        }
        for index in range(1, 3)
    ]
    _write_json(
        run_dir / "model_pair_single_trial_result.json",
        {
            "run_id": run_id,
            "trial_id": f"{SCENARIO_PATH}__second_model__to__first_model__{run_id}",
            "scenario_id": "office_document_file_workflow_basic_v1",
            "pair_id": "second_model__to__first_model",
            "status": status,
            "task_success": task_success,
            "correctness_score": correctness_score,
            "group_history": group_history,
            "warnings": [] if status == "succeeded" else ["fake_failed_repeat"],
        },
    )
    _write_json(
        run_dir / "model_pair_single_trial_matrix_summary.json",
        {
            "run_id": run_id,
            "trial_count": 1,
            "succeeded_count": 1 if status == "succeeded" else 0,
            "failed_count": 1 if status == "failed" else 0,
            "warnings": [],
        },
    )
    _write_json(
        run_dir / "office_execution_artifact_summary.json",
        {
            "run_id": run_id,
            "artifact_count": office_artifact_count,
            "readable_count": office_artifact_count,
            "warnings": [],
        },
    )
    _write_json(
        run_dir / "matrix_adapters" / "matrix_run_adapter_summary.json",
        {
            "source_run_id": run_id,
            "normality_input_count": 1,
            "resource_observation_count": 1,
            "warnings": [],
        },
    )
    return run_dir


def test_mini_matrix_aggregator_combines_three_successful_repeats(tmp_path: Path) -> None:
    run_dirs = [
        _write_fake_mini_matrix_repeat(tmp_path, "phase_8_26_mini_matrix_r1"),
        _write_fake_mini_matrix_repeat(tmp_path, "phase_8_26_mini_matrix_r2"),
        _write_fake_mini_matrix_repeat(tmp_path, "phase_8_26_mini_matrix_r3"),
    ]

    summary = aggregate_mini_matrix_results(run_dirs, summary_id="phase_8_26_mini_matrix_r3")
    payload_text = json.dumps(summary, ensure_ascii=False)

    assert summary["repeat_count"] == 3
    assert summary["succeeded_count"] == 3
    assert summary["task_success_count"] == 3
    assert summary["execution_attempted_count"] == 6
    assert summary["execution_success_count"] == 6
    assert summary["office_artifact_count"] == 6
    assert summary["office_artifact_readable_count"] == 6
    assert summary["normality_input_count"] == 3
    assert summary["mean_correctness_score"] == 1.0
    assert str(tmp_path) not in payload_text


def test_mini_matrix_aggregator_handles_failed_repeat_without_crashing(tmp_path: Path) -> None:
    run_dirs = [
        _write_fake_mini_matrix_repeat(tmp_path, "phase_8_26_mini_matrix_r1"),
        _write_fake_mini_matrix_repeat(
            tmp_path,
            "phase_8_26_mini_matrix_r2",
            status="failed",
            task_success=False,
            correctness_score=None,
            execution_success_count=1,
            office_artifact_count=0,
        ),
        _write_fake_mini_matrix_repeat(tmp_path, "phase_8_26_mini_matrix_r3"),
    ]

    summary = aggregate_mini_matrix_results(run_dirs)

    assert summary["repeat_count"] == 3
    assert summary["succeeded_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["task_failure_count"] == 1
    assert summary["execution_attempted_count"] == 6
    assert summary["execution_success_count"] == 5
    assert summary["office_artifact_count"] == 4
    assert "fake_failed_repeat" in summary["warnings"]


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    run_model_pair_matrix(_plan(), DryRunModelPairTrialExecutor(), output_dir=tmp_path / "matrix")

    assert not (PROJECT_ROOT / "reports" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME).exists()


def test_no_gguf_model_probe_browser_or_office_calls_are_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
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
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("matrix runner must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    summary = run_model_pair_matrix(plan, DryRunModelPairTrialExecutor())

    assert summary.no_runtime_execution is True
    assert summary.dry_run_count == 1
