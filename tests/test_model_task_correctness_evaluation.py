from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_catalog import load_model_catalog
from src.agent.model_comparison_plan import ModelComparisonPlanConfig, build_model_comparison_plan
from src.agent.model_pair_matrix_runner import (
    MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
    ModelPairTrialExecutionResult,
    StaticModelPairTrialExecutor,
    build_trial_execution_requests_from_plan,
    run_model_pair_matrix,
    write_model_pair_matrix_run_summary,
)
from src.agent.model_task_correctness_evaluation import (
    TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME,
    TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION,
    DisabledTaskCorrectnessEvaluator,
    RuleBasedTaskCorrectnessEvaluator,
    StaticTaskCorrectnessEvaluator,
    TaskCorrectnessEvaluationInput,
    TaskCorrectnessInputLoadError,
    build_correctness_input_from_trial_result,
    build_correctness_inputs_from_matrix_run_summary,
    evaluate_task_correctness_batch,
    load_task_correctness_inputs_from_file,
    write_task_correctness_batch_summary,
)
from src.agent.model_task_correctness_evaluation_cli import main as correctness_cli_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _input(**overrides: object) -> TaskCorrectnessEvaluationInput:
    payload = {
        "trial_id": "trial_1",
        "scenario_id": "scenario_1",
        "pair_id": "model_a__to__model_b",
        "orchestrator_model_id": "model_a",
        "executor_model_id": "model_b",
        "task_summary": "Synthetic task.",
        "expected_outputs": [],
        "artifact_refs": [],
        "trial_status": "succeeded",
        "trial_result": {"status": "succeeded"},
        "tags": ["correctness_test"],
        **overrides,
    }
    return TaskCorrectnessEvaluationInput.model_validate(payload)


def _plan(**overrides: object):
    config = ModelComparisonPlanConfig.model_validate(
        {
            "plan_id": "correctness_matrix_plan",
            "include_self_pairs": False,
            "repetitions_per_pair": 1,
            "tags": ["correctness_test"],
            **overrides,
        }
    )
    return build_model_comparison_plan(
        load_model_catalog(CATALOG_PATH),
        [SCENARIO_PATH],
        config,
        project_root=PROJECT_ROOT,
    )


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _input_payload(**overrides: object) -> dict[str, Any]:
    return _input(**overrides).model_dump(mode="json")


def test_static_evaluator_returns_mapped_trial_result() -> None:
    evaluator = StaticTaskCorrectnessEvaluator(
        {
            "trial_1": {
                "status": "passed",
                "task_success": True,
                "correctness_score": 0.92,
                "check_results": [],
            }
        }
    )

    result = evaluator.evaluate(_input())

    assert result.status == "passed"
    assert result.task_success is True
    assert result.correctness_score == 0.92
    assert result.no_runtime_execution is True


def test_static_evaluator_fallback_returns_skipped_controlled_result() -> None:
    result = StaticTaskCorrectnessEvaluator({}).evaluate(_input())

    assert result.status == "skipped"
    assert "static_correctness_result_missing" in result.warnings
    assert result.task_success is None


def test_rule_based_evaluator_passes_required_key_check() -> None:
    result = RuleBasedTaskCorrectnessEvaluator().evaluate(
        _input(
            expected_outputs={"checks": [{"type": "required_key", "key": "answer"}]},
            trial_result={"status": "succeeded", "answer": "done"},
        )
    )

    assert result.status == "passed"
    assert result.task_success is True
    assert result.correctness_score == 1.0


def test_rule_based_evaluator_fails_missing_required_key_check() -> None:
    result = RuleBasedTaskCorrectnessEvaluator().evaluate(
        _input(
            expected_outputs={"checks": [{"type": "required_key", "key": "answer"}]},
            trial_result={"status": "succeeded"},
        )
    )

    assert result.status == "failed"
    assert result.task_success is False
    assert "required key missing: answer" in result.failure_reasons


def test_rule_based_evaluator_handles_status_equals_expected() -> None:
    result = RuleBasedTaskCorrectnessEvaluator().evaluate(
        _input(expected_outputs={"checks": [{"type": "status_equals", "expected": "succeeded"}]})
    )

    assert result.status == "passed"
    assert result.check_results[0].metadata["actual"] == "succeeded"


def test_rule_based_evaluator_handles_artifact_ref_listed_without_opening_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid_exists(self: Path) -> bool:
        raise AssertionError("artifact ref checks must not touch filesystem")

    monkeypatch.setattr(Path, "exists", forbid_exists)
    result = RuleBasedTaskCorrectnessEvaluator().evaluate(
        _input(
            expected_outputs={"checks": [{"type": "artifact_ref_listed", "artifact_ref": "artifacts/out.json"}]},
            artifact_refs=["artifacts/out.json"],
        )
    )

    assert result.status == "passed"
    assert result.check_results[0].evidence_refs == ["artifacts/out.json"]


def test_rule_based_evaluator_handles_numeric_threshold_from_trial_result() -> None:
    result = RuleBasedTaskCorrectnessEvaluator().evaluate(
        _input(
            expected_outputs={
                "checks": [
                    {
                        "type": "numeric_score_threshold",
                        "key": "metrics.correctness",
                        "min_score": 0.8,
                    }
                ]
            },
            trial_result={"status": "succeeded", "metrics": {"correctness": 0.91}},
        )
    )

    assert result.status == "passed"
    assert result.correctness_score == 1.0


def test_disabled_evaluator_returns_skipped() -> None:
    result = DisabledTaskCorrectnessEvaluator().evaluate(_input())

    assert result.status == "skipped"
    assert "task_correctness_evaluator_disabled" in result.warnings


def test_batch_summary_counts_passed_failed_partial_skipped() -> None:
    inputs = [
        _input(trial_id="passed_trial"),
        _input(trial_id="failed_trial"),
        _input(trial_id="partial_trial"),
        _input(trial_id="skipped_trial"),
    ]
    evaluator = StaticTaskCorrectnessEvaluator(
        {
            "passed_trial": {"status": "passed", "task_success": True, "correctness_score": 1.0},
            "failed_trial": {"status": "failed", "task_success": False, "correctness_score": 0.0},
            "partial_trial": {"status": "partial", "correctness_score": 0.5},
            "skipped_trial": {"status": "skipped"},
        }
    )

    summary = evaluate_task_correctness_batch(inputs, evaluator, summary_id="counts")

    assert summary.input_count == 4
    assert summary.evaluated_count == 4
    assert summary.passed_count == 1
    assert summary.failed_count == 1
    assert summary.partial_count == 1
    assert summary.skipped_count == 1


def test_mean_correctness_score_calculated_correctly() -> None:
    inputs = [_input(trial_id="trial_a"), _input(trial_id="trial_b"), _input(trial_id="trial_c")]
    evaluator = StaticTaskCorrectnessEvaluator(
        {
            "trial_a": {"status": "passed", "correctness_score": 1.0},
            "trial_b": {"status": "partial", "correctness_score": 0.5},
            "trial_c": {"status": "skipped"},
        }
    )

    summary = evaluate_task_correctness_batch(inputs, evaluator)

    assert summary.mean_correctness_score == 0.75
    assert summary.by_pair["model_a__to__model_b"]["mean_correctness_score"] == 0.75


def test_build_correctness_input_from_matrix_trial_result() -> None:
    trial = ModelPairTrialExecutionResult(
        trial_id="trial_matrix",
        scenario_id="scenario_matrix",
        pair_id="model_a__to__model_b",
        orchestrator_model_id="model_a",
        executor_model_id="model_b",
        status="succeeded",
        task_success=True,
        correctness_score=0.88,
        normality_input_ref="artifacts/normality/events.json",
        execution_mode="static",
    )

    correctness_input = build_correctness_input_from_trial_result(
        trial,
        scenario_metadata={
            "task_summary": "Scenario task",
            "expected_outputs": {"checks": [{"type": "status_equals", "expected": "succeeded"}]},
            "tags": ["scenario_tag"],
        },
    )

    assert correctness_input.trial_id == "trial_matrix"
    assert correctness_input.trial_status == "succeeded"
    assert correctness_input.artifact_refs == ["artifacts/normality/events.json"]
    assert correctness_input.expected_outputs["checks"][0]["type"] == "status_equals"
    assert "scenario_tag" in correctness_input.tags


def test_build_correctness_inputs_from_matrix_run_summary() -> None:
    plan = _plan()
    request = build_trial_execution_requests_from_plan(plan)[0]
    summary = run_model_pair_matrix(
        plan,
        StaticModelPairTrialExecutor(
            {
                request.trial_id: {
                    "status": "succeeded",
                    "task_success": True,
                    "correctness_score": 0.93,
                }
            }
        ),
    )

    inputs = build_correctness_inputs_from_matrix_run_summary(
        summary,
        scenario_metadata_by_id={
            request.scenario_id: {"expected_outputs": {"checks": [{"type": "required_key", "key": "status"}]}}
        },
    )

    assert len(inputs) == 1
    assert inputs[0].trial_id == request.trial_id
    assert inputs[0].trial_result["correctness_score"] == 0.93


def test_load_json_list_inputs(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "inputs.json", [_input_payload()])

    inputs = load_task_correctness_inputs_from_file(path)

    assert len(inputs) == 1
    assert inputs[0].trial_id == "trial_1"


def test_load_json_dict_inputs(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "inputs.json", {"inputs": [_input_payload(trial_id="trial_dict")]})

    inputs = load_task_correctness_inputs_from_file(path)

    assert [item.trial_id for item in inputs] == ["trial_dict"]


def test_load_jsonl_inputs(tmp_path: Path) -> None:
    path = tmp_path / "inputs.jsonl"
    path.write_text(json.dumps(_input_payload(), ensure_ascii=False) + "\n", encoding="utf-8")

    inputs = load_task_correctness_inputs_from_file(path)

    assert len(inputs) == 1
    assert inputs[0].pair_id == "model_a__to__model_b"


def test_malformed_input_handled_controlled(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")

    with pytest.raises(TaskCorrectnessInputLoadError, match="input_json_malformed"):
        load_task_correctness_inputs_from_file(path)


def test_cli_evaluates_matrix_run_summary_from_static_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan()
    request = build_trial_execution_requests_from_plan(plan)[0]
    matrix = run_model_pair_matrix(
        plan,
        StaticModelPairTrialExecutor(
            {
                request.trial_id: {
                    "status": "succeeded",
                    "task_success": True,
                    "correctness_score": 0.94,
                }
            }
        ),
        run_id="correctness_matrix",
    )
    matrix_path = write_model_pair_matrix_run_summary(matrix, tmp_path / "matrix")

    code = correctness_cli_main(
        [
            "--matrix-run-summary",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "correctness"),
            "--summary-id",
            "cli_matrix_correctness",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    summary = _load_json(tmp_path / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["summary_id"] == "cli_matrix_correctness"
    assert payload["input_count"] == 1
    assert payload["passed_count"] == 1
    assert payload["summary_path"] == TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME
    assert summary["results"][0]["correctness_score"] == 0.94


def test_cli_evaluates_explicit_json_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = _write_json(
        tmp_path / "inputs.json",
        [
            _input_payload(
                expected_outputs={"checks": [{"type": "required_key", "key": "answer"}]},
                trial_result={"status": "succeeded", "answer": "ok"},
            )
        ],
    )

    code = correctness_cli_main(["--input", str(input_path), "--output-dir", str(tmp_path / "correctness")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["passed_count"] == 1
    assert payload["mean_correctness_score"] == 1.0


def test_cli_missing_input_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = correctness_cli_main(["--output-dir", str(tmp_path / "correctness")])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "input_required"
    assert "Traceback" not in captured.err


def test_cli_static_result_mapping_works(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = _write_json(tmp_path / "inputs.json", [_input_payload(trial_id="static_trial")])
    static_path = _write_json(
        tmp_path / "static_results.json",
        {
            "static_trial": {
                "status": "passed",
                "task_success": True,
                "correctness_score": 0.97,
            }
        },
    )

    code = correctness_cli_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "correctness"),
            "--evaluator",
            "static",
            "--static-result",
            str(static_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["passed_count"] == 1
    assert payload["mean_correctness_score"] == 0.97


def test_summary_json_written_to_tmp_output_dir(tmp_path: Path) -> None:
    summary = evaluate_task_correctness_batch(
        [_input()],
        StaticTaskCorrectnessEvaluator({"trial_1": {"status": "passed", "correctness_score": 1.0}}),
        summary_id="write_summary",
    )

    path = write_task_correctness_batch_summary(summary, tmp_path / "correctness")
    payload = _load_json(path)

    assert path == tmp_path / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME
    assert payload["schema_version"] == TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION
    assert payload["summary_id"] == "write_summary"


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    summary = evaluate_task_correctness_batch([_input()], DisabledTaskCorrectnessEvaluator())

    write_task_correctness_batch_summary(summary, tmp_path / "correctness")

    assert not (PROJECT_ROOT / "reports" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME).exists()


def test_no_gguf_model_probe_browser_or_office_calls_are_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    correctness_input = _input(
        expected_outputs={"checks": [{"type": "required_key", "key": "status"}]},
        trial_result={"status": "succeeded"},
    )
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
            raise AssertionError("correctness evaluator must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    summary = evaluate_task_correctness_batch([correctness_input], RuleBasedTaskCorrectnessEvaluator())

    assert summary.passed_count == 1
    assert summary.no_runtime_execution is True
