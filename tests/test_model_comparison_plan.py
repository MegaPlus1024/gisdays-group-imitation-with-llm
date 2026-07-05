from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.model_catalog import MODEL_CATALOG_SCHEMA_VERSION, ModelCatalog, load_model_catalog
from src.agent.model_comparison_plan import (
    MODEL_COMPARISON_PLAN_FILENAME,
    MODEL_COMPARISON_PLAN_NOTE,
    MODEL_COMPARISON_PLAN_SCHEMA_VERSION,
    ModelComparisonPlanConfig,
    ModelComparisonScenarioRef,
    build_model_comparison_plan,
    load_model_comparison_plan,
    write_model_comparison_plan,
)
from src.agent.model_comparison_plan_cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _catalog() -> ModelCatalog:
    return load_model_catalog(CATALOG_PATH)


def _plan(**overrides: object):
    config = ModelComparisonPlanConfig.model_validate({"plan_id": "test_plan", **overrides})
    return build_model_comparison_plan(
        _catalog(),
        [SCENARIO_PATH],
        config,
        project_root=PROJECT_ROOT,
    )


def _labels(plan) -> list[str]:
    return [pair["pair_label"] for pair in plan.candidate_pairs]


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _disabled_catalog() -> ModelCatalog:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    payload["models"][1]["enabled"] = False
    return ModelCatalog.model_validate(payload)


def test_build_plan_from_example_catalog_and_office_scenario_ref() -> None:
    plan = _plan()

    assert plan.schema_version == MODEL_COMPARISON_PLAN_SCHEMA_VERSION
    assert plan.plan_id == "test_plan"
    assert plan.model_catalog_summary["schema_version"] == MODEL_CATALOG_SCHEMA_VERSION
    assert plan.scenarios[0]["scenario_id"] == "office_document_file_workflow_basic_v1"
    assert plan.no_runtime_execution is True


def test_plan_includes_second_to_first_pair() -> None:
    plan = _plan()

    assert "second_model->first_model" in _labels(plan)


def test_plan_includes_second_to_second_when_self_pairs_enabled() -> None:
    plan = _plan(include_self_pairs=True)

    assert "second_model->second_model" in _labels(plan)


def test_plan_excludes_first_model_as_orchestrator_by_default() -> None:
    plan = _plan()

    assert all(pair["orchestrator_model_id"] != "first_model" for pair in plan.candidate_pairs)


def test_plan_excludes_disabled_models_when_enabled_only() -> None:
    plan = build_model_comparison_plan(
        _disabled_catalog(),
        [SCENARIO_PATH],
        ModelComparisonPlanConfig(plan_id="disabled_model_plan"),
        project_root=PROJECT_ROOT,
    )

    assert plan.candidate_pairs == []
    assert "no_orchestrator_candidates" in plan.warnings


def test_exclude_self_pairs_works() -> None:
    plan = _plan(include_self_pairs=False)

    assert _labels(plan) == ["second_model->first_model"]


def test_repetitions_per_pair_create_deterministic_trial_ids() -> None:
    plan = _plan(repetitions_per_pair=2, include_self_pairs=False)

    assert [trial.trial_id for trial in plan.trials] == [
        "office_document_file_workflow_basic_v1__second_model__to__first_model__r01",
        "office_document_file_workflow_basic_v1__second_model__to__first_model__r02",
    ]
    assert [trial.repeat_index for trial in plan.trials] == [1, 2]


def test_scenario_path_must_be_relative() -> None:
    ref = {
        "scenario_id": "s",
        "scenario_path": "\\".join(["C:", "Temp", "scenario.json"]),
    }

    with pytest.raises(ValueError, match="relative path"):
        build_model_comparison_plan(_catalog(), [ref], ModelComparisonPlanConfig(), project_root=PROJECT_ROOT)


def test_absolute_windows_scenario_path_rejected() -> None:
    path = "\\".join(["C:", "Temp", "scenario.json"])

    with pytest.raises(ValueError, match="relative path"):
        ModelComparisonScenarioRef(scenario_id="s", scenario_path=path)


def test_absolute_posix_scenario_path_rejected() -> None:
    with pytest.raises(ValueError, match="relative path"):
        ModelComparisonScenarioRef(scenario_id="s", scenario_path="/tmp/scenario.json")


def test_traversal_scenario_path_rejected() -> None:
    with pytest.raises(ValueError, match="parent directory traversal"):
        ModelComparisonScenarioRef(scenario_id="s", scenario_path="../scenario.json")


def test_output_plan_json_written_to_tmp_output_dir(tmp_path: Path) -> None:
    plan = _plan(include_self_pairs=False)

    path = write_model_comparison_plan(plan, tmp_path / "plan_out")
    loaded = load_model_comparison_plan(path)

    assert path == tmp_path / "plan_out" / MODEL_COMPARISON_PLAN_FILENAME
    assert loaded.plan_id == "test_plan"
    assert _load_json(path)["trials"][0]["no_runtime_execution"] is True


def test_plan_says_no_runtime_execution_true() -> None:
    plan = _plan()

    assert plan.no_runtime_execution is True
    assert all(pair["no_runtime_execution"] is True for pair in plan.candidate_pairs)
    assert all(trial.no_runtime_execution is True for trial in plan.trials)


def test_plan_has_no_production_recommendation_wording() -> None:
    plan = _plan()
    text = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False).lower()

    assert "production recommendation" not in text
    assert "production-ready" not in text
    assert MODEL_COMPARISON_PLAN_NOTE.lower() in text


def test_plan_does_not_check_or_read_gguf_files(monkeypatch: pytest.MonkeyPatch) -> None:
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

    plan = build_model_comparison_plan(
        catalog,
        [SCENARIO_PATH],
        ModelComparisonPlanConfig(plan_id="no_probe_plan"),
        project_root=PROJECT_ROOT,
    )

    assert plan.trials


def test_cli_writes_plan_and_concise_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "--model-catalog",
            "configs/model_catalog.example.json",
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "plan_out"),
            "--repetitions",
            "2",
            "--exclude-self-pairs",
            "--tag",
            "offline",
            "--plan-id",
            "cli_plan",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    plan = _load_json(tmp_path / "plan_out" / MODEL_COMPARISON_PLAN_FILENAME)

    assert code == 0
    assert payload == {
        "candidate_pair_count": 1,
        "model_count": 2,
        "plan_id": "cli_plan",
        "plan_path": MODEL_COMPARISON_PLAN_FILENAME,
        "status": "ok",
        "trial_count": 2,
    }
    assert plan["plan_id"] == "cli_plan"
    assert plan["trials"][0]["tags"] == ["gguf", "local", "offline", "qwen2.5", "small"]


def test_cli_rejects_missing_catalog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--scenario", SCENARIO_PATH, "--output-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "model_catalog_required"


def test_cli_rejects_no_scenario(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--model-catalog", "configs/model_catalog.example.json", "--output-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "scenario_required"


def test_role_mismatch_flag_includes_first_model_orchestrator_with_warning() -> None:
    default_plan = _plan(include_role_mismatch_pairs=False)
    mismatch_plan = _plan(include_role_mismatch_pairs=True)

    assert "first_model->first_model" not in _labels(default_plan)
    pair = next(pair for pair in mismatch_plan.candidate_pairs if pair["pair_label"] == "first_model->first_model")
    assert "orchestrator_role_not_catalog_candidate" in pair["warnings"]

