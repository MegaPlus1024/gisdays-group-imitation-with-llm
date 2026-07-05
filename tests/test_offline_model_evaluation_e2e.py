from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_catalog import get_model_entry, load_model_catalog
from src.agent.model_comparison_plan import (
    MODEL_COMPARISON_PLAN_FILENAME,
    ModelComparisonPlanConfig,
    build_model_comparison_plan,
    write_model_comparison_plan,
)
from src.agent.model_evaluation_scorecard import (
    MODEL_EVALUATION_SCORECARD_FILENAME,
    build_model_evaluation_scorecard,
    write_model_evaluation_scorecard,
)
from src.agent.model_evaluation_scorecard_cli import main as scorecard_cli_main
from src.agent.model_resource_evaluation import (
    MODEL_RESOURCE_SUMMARY_FILENAME,
    summarize_model_resource_observations,
    write_model_resource_summary,
)
from src.agent.normality_comparison import (
    NORMALITY_COMPARISON_SUMMARY_FILENAME,
    compare_normality_batch_summaries,
    write_normality_comparison_summary,
)
from src.agent.normality_evaluation_runner import NORMALITY_BATCH_SUMMARY_FILENAME


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
SCENARIO_ID = "office_document_file_workflow_basic_v1"
PLANNED_PAIR_IDS = {
    "second_model__to__first_model",
    "second_model__to__second_model",
}
RAW_MARKER = "RAW_FULL_E2E_SYNTHETIC_RESOURCE_OR_EVENT_MARKER"


@dataclass(frozen=True)
class OfflineEvaluationArtifacts:
    plan_path: Path
    normality_batch_path: Path
    normality_comparison_path: Path
    resource_summary_path: Path
    scorecard_path: Path
    scorecard_payload: dict[str, Any]


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_e2e_artifacts(tmp_path: Path) -> OfflineEvaluationArtifacts:
    catalog = load_model_catalog(CATALOG_PATH)

    plan = build_model_comparison_plan(
        catalog,
        [SCENARIO_PATH],
        ModelComparisonPlanConfig(
            plan_id="offline_model_evaluation_e2e_plan",
            repetitions_per_pair=1,
            include_self_pairs=True,
            enabled_only=True,
            include_role_mismatch_pairs=False,
            tags=["offline_e2e"],
        ),
        project_root=PROJECT_ROOT,
    )
    plan_path = write_model_comparison_plan(plan, tmp_path / "plan")

    normality_batch_path = _write_json(
        tmp_path / "normality_batch" / NORMALITY_BATCH_SUMMARY_FILENAME,
        _normality_batch_summary(plan.candidate_pairs),
    )
    normality_comparison = compare_normality_batch_summaries(
        [normality_batch_path],
        project_root=tmp_path,
        model_catalog=catalog,
    )
    normality_comparison_path, _ = write_normality_comparison_summary(
        normality_comparison,
        tmp_path / "normality_comparison",
    )

    resource_summary = summarize_model_resource_observations(
        _resource_observations(plan.candidate_pairs),
        model_catalog=catalog,
        summary_id="offline_model_evaluation_e2e_resource",
        input_count=1,
        tags=["offline_e2e"],
    )
    resource_summary_path = write_model_resource_summary(resource_summary, tmp_path / "resource")

    scorecard = build_model_evaluation_scorecard(
        catalog,
        model_comparison_plan_path=plan_path,
        normality_comparison_summary_path=normality_comparison_path,
        model_resource_summary_path=resource_summary_path,
        scorecard_id="offline_model_evaluation_e2e_scorecard",
        project_root=PROJECT_ROOT,
    )
    scorecard_path, _ = write_model_evaluation_scorecard(scorecard, tmp_path / "scorecard")

    return OfflineEvaluationArtifacts(
        plan_path=plan_path,
        normality_batch_path=normality_batch_path,
        normality_comparison_path=normality_comparison_path,
        resource_summary_path=resource_summary_path,
        scorecard_path=scorecard_path,
        scorecard_payload=_load_json(scorecard_path),
    )


def _normality_batch_summary(candidate_pairs: list[dict[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for index, pair in enumerate(candidate_pairs, start=1):
        pair_id = pair["pair_id"]
        orchestrator = pair["orchestrator_model_id"]
        executor = pair["executor_model_id"]
        mean_score = 0.88 if executor == "first_model" else 0.91
        entries.append(
            {
                "scenario_id": SCENARIO_ID,
                "trial_id": f"{SCENARIO_ID}__{pair_id}__normality",
                "model_pair": {
                    "orchestrator": orchestrator,
                    "executor": executor,
                },
                "tags": ["offline_e2e", "normality", *pair.get("tags", [])],
                "status": "ok",
                "label": "normal",
                "overall_score": mean_score,
                "event_count": 2,
                "findings": [f"synthetic_normality_ok_{index}"],
                "warnings": [],
                "event_preview": [
                    {
                        "result_summary": RAW_MARKER,
                        "artifact_paths": ["artifacts/offline_e2e/summary.txt"],
                    }
                ],
            }
        )
    return {
        "status": "ok",
        "batch_id": "offline_model_evaluation_e2e_batch",
        "input_count": len(entries),
        "evaluated_count": len(entries),
        "failed_count": 0,
        "entries": entries,
    }


def _resource_observations(candidate_pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for index, pair in enumerate(candidate_pairs, start=1):
        pair_id = pair["pair_id"]
        observations.append(
            {
                "observation_id": f"offline_e2e_resource_{index:02d}",
                "orchestrator_model_id": pair["orchestrator_model_id"],
                "executor_model_id": pair["executor_model_id"],
                "pair_id": pair_id,
                "scenario_id": SCENARIO_ID,
                "trial_id": f"{SCENARIO_ID}__{pair_id}__resource",
                "runtime_mode": "offline_synthetic",
                "backend": "synthetic_fixture",
                "success": True,
                "wall_time_s": 1.0 + index / 10,
                "peak_ram_gb": 2.0 + index,
                "peak_vram_gb": 0.0,
                "notes": [RAW_MARKER],
                "tags": ["offline_e2e", "resource", *pair.get("tags", [])],
            }
        )
    return observations


def _pair_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {pair["pair_id"]: pair for pair in payload["model_pairs"]}


def _assert_no_tmp_path_leak(payload_text: str, tmp_path: Path) -> None:
    path_variants = {
        str(tmp_path),
        str(tmp_path).replace("\\", "/"),
        str(tmp_path).replace("\\", "\\\\"),
        tmp_path.as_posix(),
    }
    assert all(path_text not in payload_text for path_text in path_variants)


def test_offline_model_evaluation_pipeline_e2e_smoke(
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
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("offline E2E smoke must not import runtime backends")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    catalog = load_model_catalog(CATALOG_PATH)
    assert {entry.model_id for entry in catalog.models} == {"first_model", "second_model"}
    assert get_model_entry(catalog, "first_model").local_path == "models/gguf/first_model.gguf"
    assert get_model_entry(catalog, "second_model").local_path == "models/gguf/second_model.gguf"

    artifacts = _build_e2e_artifacts(tmp_path)
    plan_payload = _load_json(artifacts.plan_path)
    normality_payload = _load_json(artifacts.normality_comparison_path)
    resource_payload = _load_json(artifacts.resource_summary_path)
    scorecard_payload = artifacts.scorecard_payload
    scorecard_text = json.dumps(scorecard_payload, ensure_ascii=False)

    assert artifacts.plan_path == tmp_path / "plan" / MODEL_COMPARISON_PLAN_FILENAME
    assert artifacts.normality_batch_path == tmp_path / "normality_batch" / NORMALITY_BATCH_SUMMARY_FILENAME
    assert artifacts.normality_comparison_path == tmp_path / "normality_comparison" / NORMALITY_COMPARISON_SUMMARY_FILENAME
    assert artifacts.resource_summary_path == tmp_path / "resource" / MODEL_RESOURCE_SUMMARY_FILENAME
    assert artifacts.scorecard_path == tmp_path / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME
    assert all(path.is_file() for path in [
        artifacts.plan_path,
        artifacts.normality_batch_path,
        artifacts.normality_comparison_path,
        artifacts.resource_summary_path,
        artifacts.scorecard_path,
    ])

    plan_pair_ids = {pair["pair_id"] for pair in plan_payload["candidate_pairs"]}
    assert plan_pair_ids == PLANNED_PAIR_IDS
    assert all(pair["orchestrator_model_id"] != "first_model" for pair in plan_payload["candidate_pairs"])
    assert plan_payload["no_runtime_execution"] is True
    assert all(pair["no_runtime_execution"] is True for pair in plan_payload["candidate_pairs"])

    assert set(normality_payload["groups"]["by_model_pair"]) == {
        "second_model->first_model",
        "second_model->second_model",
    }
    assert normality_payload["leaderboard"]
    assert normality_payload["model_catalog_used"] is True
    for group in normality_payload["groups"]["by_model_pair"].values():
        assert group["catalog_metadata"]["known_catalog_pair"] is True

    assert set(resource_payload["groups"]["by_pair"]) == PLANNED_PAIR_IDS
    for group in resource_payload["groups"]["by_pair"].values():
        assert group["observation_count"] == 1
        assert group["mean_wall_time_s"] is not None
        assert group["mean_peak_ram_gb"] is not None
        assert group["max_peak_vram_gb"] == 0.0

    pairs = _pair_rows(scorecard_payload)
    assert scorecard_payload["status"] == "ok"
    assert scorecard_payload["plan_used"] is True
    assert scorecard_payload["normality_summary_used"] is True
    assert scorecard_payload["resource_summary_used"] is True
    assert scorecard_payload["no_runtime_execution"] is True
    assert set(pairs) == PLANNED_PAIR_IDS
    for pair_id in PLANNED_PAIR_IDS:
        pair = pairs[pair_id]
        assert pair["catalog_metadata"]["known_catalog_pair"] is True
        assert pair["plan_metadata"]["planned_trial_count"] == 1
        assert pair["normality_metrics"]["evaluated_count"] == 1
        assert pair["resource_metrics"]["observation_count"] == 1
        assert pair["warnings"] == []

    notes_text = " ".join(scorecard_payload["notes"]).lower()
    assert "no model execution performed" in notes_text
    assert "not a production recommendation" in notes_text
    assert RAW_MARKER not in scorecard_text
    _assert_no_tmp_path_leak(scorecard_text, tmp_path)
    assert not (PROJECT_ROOT / "reports" / MODEL_EVALUATION_SCORECARD_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_EVALUATION_SCORECARD_FILENAME).exists()


def test_offline_model_evaluation_scorecard_cli_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifacts = _build_e2e_artifacts(tmp_path)

    code = scorecard_cli_main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--model-comparison-plan",
            str(artifacts.plan_path),
            "--normality-comparison-summary",
            str(artifacts.normality_comparison_path),
            "--model-resource-summary",
            str(artifacts.resource_summary_path),
            "--output-dir",
            str(tmp_path / "scorecard_cli"),
            "--scorecard-id",
            "offline_model_evaluation_e2e_cli_scorecard",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    scorecard = _load_json(tmp_path / "scorecard_cli" / MODEL_EVALUATION_SCORECARD_FILENAME)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["scorecard_id"] == "offline_model_evaluation_e2e_cli_scorecard"
    assert payload["model_pair_count"] == 2
    assert set(_pair_rows(scorecard)) == PLANNED_PAIR_IDS
