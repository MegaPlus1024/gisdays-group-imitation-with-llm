from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from src.agent.autonomous_browser_stateful_readonly_planner_final_summary import (
    CSV_FILENAME,
    JSON_FILENAME,
    MARKDOWN_FILENAME,
    SUMMARY_SCHEMA_VERSION,
    write_final_presentation_benchmark_summary,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_CONFIG = PROJECT_ROOT / "configs" / "evaluation_models.json"
SCRIPT_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "summarize_autonomous_browser_stateful_readonly_planner_final_benchmark.py"
)


def _fake_evaluator_summary() -> dict[str, object]:
    return {
        "schema_version": "autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator_summary_v1",
        "status": "completed_with_failures",
        "error_code": "truncated_model_output",
        "scenario_catalog": "final_presentation_v1",
        "model_aliases": ["first_model", "fourth_model"],
        "scenario_ids": [
            "stateful_single_fact_sanity_check",
            "stateful_policy_search_marker_review",
            "stateful_policy_allowed_activity",
            "stateful_policy_source_disambiguation",
            "stateful_approval_policy_crosscheck",
        ],
        "best_model_by_pass_rate": "fourth_model",
        "model_summaries": [
            {
                "alias": "first_model",
                "outputs_present": 4,
                "validation_accepted": 2,
                "validation_rejected": 2,
                "workflows_succeeded": 1,
                "workflows_failed": 3,
                "pass_rate_overall": 0.25,
                "validation_acceptance_rate": 0.5,
                "finish_reason_counts": {"length": 1, "stop": 3},
                "failure_class_counts": {"model_failed_task": 2, "none": 1, "validation_error": 1},
            },
            {
                "alias": "fourth_model",
                "outputs_present": 4,
                "validation_accepted": 4,
                "validation_rejected": 0,
                "workflows_succeeded": 3,
                "workflows_failed": 1,
                "pass_rate_overall": 0.75,
                "validation_acceptance_rate": 1.0,
                "finish_reason_counts": {"stop": 4},
                "failure_class_counts": {"model_failed_task": 1, "none": 3},
            },
        ],
        "output_summaries": [
            {
                "model_alias": "first_model",
                "scenario_id": "stateful_single_fact_sanity_check",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "succeeded",
            },
            {
                "model_alias": "first_model",
                "scenario_id": "stateful_policy_search_marker_review",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "succeeded",
            },
            {
                "model_alias": "first_model",
                "scenario_id": "stateful_policy_allowed_activity",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "failed",
            },
            {
                "model_alias": "first_model",
                "scenario_id": "stateful_policy_source_disambiguation",
                "captured_output_present": True,
                "validation_status": "rejected",
                "workflow_status": "failed",
            },
            {
                "model_alias": "first_model",
                "scenario_id": "stateful_approval_policy_crosscheck",
                "captured_output_present": False,
                "validation_status": "missing",
                "workflow_status": "failed",
            },
            {
                "model_alias": "fourth_model",
                "scenario_id": "stateful_single_fact_sanity_check",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "succeeded",
            },
            {
                "model_alias": "fourth_model",
                "scenario_id": "stateful_policy_search_marker_review",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "succeeded",
            },
            {
                "model_alias": "fourth_model",
                "scenario_id": "stateful_policy_allowed_activity",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "succeeded",
            },
            {
                "model_alias": "fourth_model",
                "scenario_id": "stateful_policy_source_disambiguation",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "failed",
            },
            {
                "model_alias": "fourth_model",
                "scenario_id": "stateful_approval_policy_crosscheck",
                "captured_output_present": True,
                "validation_status": "accepted",
                "workflow_status": "succeeded",
            },
        ],
    }


def _fake_runner_summary() -> dict[str, object]:
    return {
        "schema_version": "autonomous_browser_stateful_readonly_planner_multimodel_sequential_summary_v1",
        "model_results": [
            {"model_alias": "first_model", "requests_total": 4, "elapsed_seconds": 12.0},
            {"model_alias": "fourth_model", "requests_total": 4, "elapsed_seconds": 20.0},
        ],
    }


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_writer_produces_markdown_csv_and_json(tmp_path: Path) -> None:
    output_dir = tmp_path / "summary"
    result = write_final_presentation_benchmark_summary(
        evaluator_summary=_fake_evaluator_summary(),
        runner_summary=_fake_runner_summary(),
        models_config_path=MODELS_CONFIG,
        output_dir=output_dir,
    )

    markdown_path = output_dir / MARKDOWN_FILENAME
    csv_path = output_dir / CSV_FILENAME
    json_path = output_dir / JSON_FILENAME

    assert result["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert result["status"] == "succeeded"
    assert result["winner_by_pass_rate"] == "fourth_model"
    assert markdown_path.exists()
    assert csv_path.exists()
    assert json_path.exists()

    markdown = markdown_path.read_text(encoding="utf-8")
    csv_text = csv_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert "Final Presentation Benchmark Summary" in markdown
    assert "stateful_policy_search_marker_review" in markdown
    assert "stateful_single_fact_sanity_check" in markdown
    assert "PASS" in markdown
    assert "FAIL" in markdown
    assert "REJECTED" in markdown
    assert "MISSING" in markdown
    assert "| stateful_single_fact_sanity_check | ultra_easy | sanity | PASS | PASS |" in markdown
    assert "fourth_model" in csv_text
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["winner_by_pass_rate"] == "fourth_model"
    matrix_rows = {item["scenario_id"]: item for item in payload["scenario_matrix_rows"]}
    assert matrix_rows["stateful_single_fact_sanity_check"]["difficulty"] == "ultra_easy"
    assert matrix_rows["stateful_single_fact_sanity_check"]["benchmark_category"] == "sanity"
    assert matrix_rows["stateful_single_fact_sanity_check"]["results"]["first_model"] == "PASS"
    assert matrix_rows["stateful_policy_search_marker_review"]["results"]["first_model"] == "PASS"
    assert matrix_rows["stateful_policy_allowed_activity"]["results"]["first_model"] == "FAIL"
    assert matrix_rows["stateful_policy_source_disambiguation"]["results"]["first_model"] == "REJECTED"
    assert matrix_rows["stateful_approval_policy_crosscheck"]["results"]["first_model"] == "MISSING"


def test_summary_cli_writes_outputs_from_fake_artifacts(tmp_path: Path, capsys) -> None:
    evaluator_path = tmp_path / "evaluator.json"
    runner_path = tmp_path / "runner.json"
    output_dir = tmp_path / "cli-summary"
    evaluator_path.write_text(json.dumps(_fake_evaluator_summary(), ensure_ascii=False, indent=2), encoding="utf-8")
    runner_path.write_text(json.dumps(_fake_runner_summary(), ensure_ascii=False, indent=2), encoding="utf-8")

    module = _load_cli_module(SCRIPT_PATH)
    exit_code = module.main(
        [
            "--evaluator-summary",
            str(evaluator_path),
            "--runner-summary",
            str(runner_path),
            "--models-config",
            str(MODELS_CONFIG),
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["winner_by_pass_rate"] == "fourth_model"
    assert (output_dir / MARKDOWN_FILENAME).exists()
    assert (output_dir / CSV_FILENAME).exists()
    assert (output_dir / JSON_FILENAME).exists()
