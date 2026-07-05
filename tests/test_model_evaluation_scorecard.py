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
from src.agent.model_evaluation_scorecard import (
    MODEL_EVALUATION_SCORECARD_FILENAME,
    MODEL_EVALUATION_SCORECARD_PREVIEW_FILENAME,
    build_model_evaluation_scorecard,
    load_json_summary,
    run_model_evaluation_scorecard,
    write_model_evaluation_scorecard,
)
from src.agent.model_evaluation_scorecard_cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog():
    return load_model_catalog(CATALOG_PATH)


def _normality_summary(
    *,
    orchestrator: str = "second_model",
    executor: str = "first_model",
    mean: float = 0.91,
    findings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    pair_label = f"{orchestrator}->{executor}"
    group = {
        "group_label": pair_label,
        "group_key": {"orchestrator": orchestrator, "executor": executor},
        "entry_count": 2,
        "evaluated_count": 2,
        "failed_count": 0,
        "mean_overall_score": mean,
        "min_overall_score": mean - 0.01,
        "max_overall_score": mean + 0.01,
        "label_counts": {"normal": 2},
        "status_counts": {"ok": 2},
        "top_findings": findings or [{"finding": "role_fit_ok", "count": 2}],
        "trial_ids": ["trial_001", "trial_002"],
        "scenario_ids": ["office_document_file_workflow_basic_v1"],
        "tags": ["offline", "normality"],
        "model_pairs": [pair_label],
    }
    return {
        "schema_version": "normality_comparison_v1",
        "status": "ok",
        "groups": {"by_model_pair": {pair_label: group}},
        "leaderboard": [
            {
                "pair_label": pair_label,
                "orchestrator": orchestrator,
                "executor": executor,
                "mean_overall_score": mean,
                "evaluated_count": 2,
                "failed_count": 0,
            }
        ],
        "warnings": [],
    }


def _resource_summary() -> dict[str, object]:
    pair_group = {
        "group_key": "second_model__to__first_model",
        "group_type": "pair",
        "observation_count": 2,
        "success_count": 2,
        "failure_count": 0,
        "success_rate": 1.0,
        "mean_wall_time_s": 2.5,
        "min_wall_time_s": 2.0,
        "max_wall_time_s": 3.0,
        "mean_peak_ram_gb": 3.5,
        "max_peak_ram_gb": 4.0,
        "mean_peak_vram_gb": 0.0,
        "max_peak_vram_gb": 0.0,
        "runtime_modes": ["offline_fixture"],
        "scenario_ids": ["office_document_file_workflow_basic_v1"],
        "tags": ["offline", "resource"],
        "error_counts": {},
        "warnings": [],
    }
    by_model = {
        "first_model": {
            **pair_group,
            "group_key": "first_model",
            "group_type": "model",
            "mean_peak_ram_gb": 1.5,
            "max_peak_ram_gb": 2.0,
        },
        "second_model": {
            **pair_group,
            "group_key": "second_model",
            "group_type": "model",
            "mean_peak_ram_gb": 2.0,
            "max_peak_ram_gb": 2.5,
        },
    }
    return {
        "schema_version": "model_resource_summary_v1",
        "status": "ok",
        "groups": {
            "by_pair": {"second_model__to__first_model": pair_group},
            "by_model": by_model,
        },
        "warnings": [],
    }


def _plan_path(tmp_path: Path) -> Path:
    plan = build_model_comparison_plan(
        _catalog(),
        [SCENARIO_PATH],
        ModelComparisonPlanConfig(
            plan_id="scorecard_plan",
            repetitions_per_pair=2,
            include_self_pairs=False,
            tags=["scorecard_test"],
        ),
        project_root=PROJECT_ROOT,
    )
    return write_model_comparison_plan(plan, tmp_path / "plan")


def _pair(scorecard, pair_id: str) -> dict[str, Any]:
    return next(pair for pair in scorecard.model_pairs if pair["pair_id"] == pair_id)


def test_load_json_summary_ok(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "summary.json", {"status": "ok"})

    result = load_json_summary(path, project_root=tmp_path)

    assert result.status == "ok"
    assert result.payload == {"status": "ok"}
    assert result.input_path_display == "summary.json"


def test_load_json_summary_missing_is_controlled(tmp_path: Path) -> None:
    result = load_json_summary(tmp_path / "missing.json", project_root=tmp_path)

    assert result.status == "input_missing"
    assert result.payload is None
    assert "summary_file_missing" in result.warnings


def test_load_json_summary_malformed_is_controlled(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")

    result = load_json_summary(path, project_root=tmp_path)

    assert result.status == "invalid_input"
    assert "summary_json_decode_error" in result.warnings


def test_catalog_only_scorecard_builds_candidate_pairs() -> None:
    scorecard = build_model_evaluation_scorecard(_catalog(), project_root=PROJECT_ROOT)

    assert scorecard.status == "ok"
    assert scorecard.no_runtime_execution is True
    assert scorecard.model_count == 2
    assert {pair["pair_id"] for pair in scorecard.model_pairs} == {
        "second_model__to__first_model",
        "second_model__to__second_model",
    }
    pair = _pair(scorecard, "second_model__to__first_model")
    assert pair["sources"] == ["catalog_candidate"]
    assert "missing_normality_metrics" in pair["warnings"]
    assert "missing_resource_metrics" in pair["warnings"]


def test_plan_metadata_is_merged_into_pair_scorecard(tmp_path: Path) -> None:
    plan_path = _plan_path(tmp_path)

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        model_comparison_plan_path=plan_path,
        project_root=PROJECT_ROOT,
    )
    pair = _pair(scorecard, "second_model__to__first_model")

    assert scorecard.plan_used is True
    assert "model_comparison_plan" in pair["sources"]
    assert pair["plan_metadata"]["planned_trial_count"] == 2
    assert pair["plan_metadata"]["scenario_ids"] == ["office_document_file_workflow_basic_v1"]
    assert pair["plan_metadata"]["tags"] == ["gguf", "local", "qwen2.5", "scorecard_test", "small"]


def test_normality_summary_metrics_are_merged(tmp_path: Path) -> None:
    normality_path = _write_json(tmp_path / "normality.json", _normality_summary())

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        normality_comparison_summary_path=normality_path,
        project_root=PROJECT_ROOT,
    )
    pair = _pair(scorecard, "second_model__to__first_model")

    assert scorecard.normality_summary_used is True
    assert pair["normality_rank"] == 1
    assert pair["normality_metrics"]["mean_overall_score"] == pytest.approx(0.91)
    assert pair["normality_metrics"]["label_counts"] == {"normal": 2}


def test_resource_summary_metrics_are_merged(tmp_path: Path) -> None:
    resource_path = _write_json(tmp_path / "resource.json", _resource_summary())

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        model_resource_summary_path=resource_path,
        project_root=PROJECT_ROOT,
    )
    pair = _pair(scorecard, "second_model__to__first_model")
    first_model = next(model for model in scorecard.models if model["model_id"] == "first_model")

    assert scorecard.resource_summary_used is True
    assert pair["resource_metrics"]["success_rate"] == pytest.approx(1.0)
    assert pair["resource_metrics"]["mean_peak_ram_gb"] == pytest.approx(3.5)
    assert first_model["resource_metrics"]["mean_peak_ram_gb"] == pytest.approx(1.5)


def test_all_inputs_combine_into_one_pair_record(tmp_path: Path) -> None:
    plan_path = _plan_path(tmp_path)
    normality_path = _write_json(tmp_path / "normality.json", _normality_summary())
    resource_path = _write_json(tmp_path / "resource.json", _resource_summary())

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        model_comparison_plan_path=plan_path,
        normality_comparison_summary_path=normality_path,
        model_resource_summary_path=resource_path,
        project_root=PROJECT_ROOT,
    )
    pair = _pair(scorecard, "second_model__to__first_model")

    assert pair["warnings"] == []
    assert pair["normality_metrics"]["evaluated_count"] == 2
    assert pair["resource_metrics"]["observation_count"] == 2
    assert scorecard.overall["pairs_with_plan_metadata"] == 1
    assert scorecard.overall["pairs_with_normality_metrics"] == 1
    assert scorecard.overall["pairs_with_resource_metrics"] == 1


def test_alias_in_normality_summary_resolves_to_canonical_pair(tmp_path: Path) -> None:
    alias = "qwen2_5_3b_instruct_q4_k_m"
    normality_path = _write_json(tmp_path / "normality.json", _normality_summary(orchestrator=alias))

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        normality_comparison_summary_path=normality_path,
        project_root=PROJECT_ROOT,
    )
    pair = _pair(scorecard, "second_model__to__first_model")

    assert pair["orchestrator_model_id"] == "second_model"
    assert pair["catalog_metadata"]["orchestrator"]["resolved_from_alias"] == alias
    assert pair["normality_metrics"]["source_group_label"] == f"{alias}->first_model"


def test_missing_optional_summary_path_adds_warning_without_crash(tmp_path: Path) -> None:
    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        normality_comparison_summary_path=tmp_path / "missing.json",
        project_root=PROJECT_ROOT,
    )

    assert scorecard.status == "ok"
    assert "normality_comparison_summary_missing" in scorecard.warnings


def test_malformed_optional_summary_adds_warning_without_crash(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        model_resource_summary_path=bad,
        project_root=PROJECT_ROOT,
    )

    assert scorecard.status == "ok"
    assert "model_resource_summary_invalid_input" in scorecard.warnings
    assert any("summary_json_decode_error" in warning for warning in scorecard.warnings)


def test_top_findings_are_bounded_and_redacted(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "trace.txt"])
    findings = [
        {"finding": f"finding_{index} {windows_path}", "count": index}
        for index in range(10)
    ]
    normality_path = _write_json(tmp_path / "normality.json", _normality_summary(findings=findings))

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        normality_comparison_summary_path=normality_path,
        project_root=PROJECT_ROOT,
    )
    pair = _pair(scorecard, "second_model__to__first_model")
    text = json.dumps(scorecard.model_dump(mode="json"), ensure_ascii=False)

    assert len(pair["normality_metrics"]["top_findings"]) == 5
    assert windows_path not in text
    assert "<absolute_path>" in text


def test_scorecard_json_and_markdown_are_written_to_tmp_output_dir(tmp_path: Path) -> None:
    scorecard = build_model_evaluation_scorecard(_catalog(), project_root=PROJECT_ROOT)

    json_path, markdown_path = write_model_evaluation_scorecard(
        scorecard,
        tmp_path / "out",
        write_markdown_preview=True,
    )
    payload = _load_json(json_path)

    assert json_path == tmp_path / "out" / MODEL_EVALUATION_SCORECARD_FILENAME
    assert markdown_path == tmp_path / "out" / MODEL_EVALUATION_SCORECARD_PREVIEW_FILENAME
    assert payload["schema_version"] == "model_evaluation_scorecard_v1"
    assert payload["scorecard_path_relative"] == MODEL_EVALUATION_SCORECARD_FILENAME
    assert markdown_path is not None and markdown_path.is_file()


def test_run_scorecard_writes_output_and_returns_result(tmp_path: Path) -> None:
    scorecard = run_model_evaluation_scorecard(
        CATALOG_PATH,
        tmp_path / "out",
        scorecard_id="run_scorecard_test",
        project_root=PROJECT_ROOT,
    )

    assert scorecard.scorecard_id == "run_scorecard_test"
    assert (tmp_path / "out" / MODEL_EVALUATION_SCORECARD_FILENAME).is_file()


def test_cli_writes_scorecard_with_optional_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    normality_path = _write_json(tmp_path / "normality.json", _normality_summary())

    code = main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--normality-comparison-summary",
            str(normality_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--scorecard-id",
            "cli_scorecard",
            "--write-markdown-preview",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["scorecard_id"] == "cli_scorecard"
    assert payload["markdown_preview_path"] == MODEL_EVALUATION_SCORECARD_PREVIEW_FILENAME
    assert (tmp_path / "out" / MODEL_EVALUATION_SCORECARD_FILENAME).is_file()


def test_cli_missing_catalog_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--output-dir", str(tmp_path / "out")])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "model_catalog_required"
    assert "Traceback" not in captured.err


def test_scorecard_does_not_probe_gguf_files(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = _catalog()
    original_exists = Path.exists
    original_read_text = Path.read_text

    def forbid_gguf_exists(self: Path) -> bool:
        if self.suffix.lower() == ".gguf":
            raise AssertionError(f"unexpected GGUF exists check: {self}")
        return original_exists(self)

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError(f"unexpected GGUF read: {self}")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)

    scorecard = build_model_evaluation_scorecard(catalog, project_root=PROJECT_ROOT)

    assert scorecard.status == "ok"


def test_scorecard_stays_offline_under_forbidden_runtime_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("scorecard must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    normality_path = _write_json(tmp_path / "normality.json", _normality_summary())

    scorecard = build_model_evaluation_scorecard(
        _catalog(),
        normality_comparison_summary_path=normality_path,
        project_root=PROJECT_ROOT,
    )

    assert scorecard.status == "ok"


def test_scorecard_has_no_production_overclaim_wording() -> None:
    scorecard = build_model_evaluation_scorecard(_catalog(), project_root=PROJECT_ROOT)
    text = json.dumps(scorecard.model_dump(mode="json"), ensure_ascii=False).lower()

    assert "production-ready" not in text
    assert scorecard.overall["production_recommendation"] is False
    assert "no model execution performed" in text


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    run_model_evaluation_scorecard(CATALOG_PATH, tmp_path / "out", project_root=PROJECT_ROOT)

    assert not (PROJECT_ROOT / "reports" / MODEL_EVALUATION_SCORECARD_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_EVALUATION_SCORECARD_FILENAME).exists()
