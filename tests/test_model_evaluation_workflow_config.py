from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_evaluation_workflow_runner import (
    MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION,
    WORKFLOW_RUN_MANIFEST_FILENAME,
    ModelEvaluationWorkflowConfigError,
    load_model_evaluation_workflow_config,
    run_offline_model_evaluation_workflow,
    workflow_run_config_from_dict,
)
from src.agent.model_evaluation_workflow_runner_cli import main as workflow_runner_cli_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "model_evaluation_workflow.example.json"
CATALOG_RELATIVE = "configs/model_catalog.example.json"
SCENARIO_RELATIVE = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _example_payload(**overrides: object) -> dict[str, Any]:
    payload = _load_json(EXAMPLE_CONFIG_PATH)
    payload.update(overrides)
    return payload


def test_loads_example_config(tmp_path: Path) -> None:
    config = load_model_evaluation_workflow_config(
        EXAMPLE_CONFIG_PATH,
        output_dir_override=tmp_path / "workflow",
    )

    assert config.config_used is True
    assert config.config_schema_version == MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION
    assert config.config_display_path == "configs/model_evaluation_workflow.example.json"
    assert config.model_catalog_path == CATALOG_RELATIVE
    assert config.scenario_paths == [SCENARIO_RELATIVE]
    assert config.output_dir == str(tmp_path / "workflow")
    assert config.output_dir_overridden is True


def test_example_config_has_no_absolute_paths_or_production_overclaim() -> None:
    text = EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8").lower()

    assert "c:\\" not in text
    assert "c:/" not in text
    assert "/users/" not in text
    assert "production-ready" not in text
    assert "no model execution" in text


def test_builds_run_config_from_json_dict(tmp_path: Path) -> None:
    config = workflow_run_config_from_dict(
        _example_payload(),
        output_dir_override=tmp_path / "workflow",
    )

    assert config.workflow_id == "offline_model_eval_example_v1"
    assert config.repetitions_per_pair == 1
    assert config.include_self_pairs is True
    assert config.include_role_mismatch_pairs is False
    assert config.tags == ["offline", "example", "no-runtime"]
    assert config.config_used is True


def test_rejects_missing_required_model_catalog_path(tmp_path: Path) -> None:
    payload = _example_payload(output_dir=str(tmp_path / "workflow"))
    payload.pop("model_catalog_path")

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_rejects_missing_scenario_paths(tmp_path: Path) -> None:
    payload = _example_payload(output_dir=str(tmp_path / "workflow"))
    payload.pop("scenario_paths")

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_rejects_bad_schema_version() -> None:
    payload = _example_payload(schema_version="unexpected_schema")

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_rejects_unknown_top_level_key() -> None:
    payload = _example_payload(unexpected_field=True)

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_rejects_absolute_catalog_path(tmp_path: Path) -> None:
    payload = _example_payload(
        model_catalog_path=str(PROJECT_ROOT / "configs" / "model_catalog.example.json"),
        output_dir=str(tmp_path / "workflow"),
    )

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_rejects_traversal_scenario_path(tmp_path: Path) -> None:
    payload = _example_payload(
        scenario_paths=["../outside/scenario.json"],
        output_dir=str(tmp_path / "workflow"),
    )

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_rejects_repetitions_per_pair_less_than_one(tmp_path: Path) -> None:
    payload = _example_payload(
        repetitions_per_pair=0,
        output_dir=str(tmp_path / "workflow"),
    )

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_rejects_non_list_tags(tmp_path: Path) -> None:
    payload = _example_payload(tags="offline", output_dir=str(tmp_path / "workflow"))

    with pytest.raises(ModelEvaluationWorkflowConfigError):
        workflow_run_config_from_dict(payload)


def test_cli_config_runs_workflow_with_tmp_output_override(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = workflow_runner_cli_main(
        [
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "partial"
    assert payload["workflow_id"] == "offline_model_eval_example_v1"
    assert payload["candidate_pair_count"] == 2
    assert payload["trial_count"] == 2
    assert payload["readiness_status"] == "ready"
    assert (tmp_path / "workflow" / WORKFLOW_RUN_MANIFEST_FILENAME).is_file()


def test_cli_rejects_config_mixed_with_explicit_model_catalog(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = workflow_runner_cli_main(
        [
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--model-catalog",
            CATALOG_RELATIVE,
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "config_conflicts_with_model_catalog"


def test_cli_rejects_config_mixed_with_explicit_scenario(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = workflow_runner_cli_main(
        [
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--scenario",
            SCENARIO_RELATIVE,
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "config_conflicts_with_scenario"


def test_cli_config_output_dir_overrides_config_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "override"

    code = workflow_runner_cli_main(["--config", str(EXAMPLE_CONFIG_PATH), "--output-dir", str(output_dir)])
    payload = json.loads(capsys.readouterr().out)
    manifest = _load_json(output_dir / WORKFLOW_RUN_MANIFEST_FILENAME)

    assert code == 0
    assert payload["status"] == "partial"
    assert manifest["output_dir_overridden"] is True
    assert manifest["output_dir_relative"] == "override"


def test_cli_config_tag_appends_safely(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "workflow"

    code = workflow_runner_cli_main(
        [
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--output-dir",
            str(output_dir),
            "--tag",
            "extra",
        ]
    )
    manifest = _load_json(output_dir / WORKFLOW_RUN_MANIFEST_FILENAME)

    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "partial"
    assert manifest["tags"] == ["offline", "example", "no-runtime", "extra"]


def test_manifest_records_config_used_and_sanitized_config_path(tmp_path: Path) -> None:
    config = load_model_evaluation_workflow_config(
        EXAMPLE_CONFIG_PATH,
        output_dir_override=tmp_path / "workflow",
    )
    run_offline_model_evaluation_workflow(config)
    manifest = _load_json(tmp_path / "workflow" / WORKFLOW_RUN_MANIFEST_FILENAME)
    manifest_text = json.dumps(manifest, ensure_ascii=False)

    assert manifest["config_used"] is True
    assert manifest["config_schema_version"] == MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION
    assert manifest["config_display_path"] == "configs/model_evaluation_workflow.example.json"
    assert str(PROJECT_ROOT) not in manifest_text


def test_missing_config_path_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = workflow_runner_cli_main(
        [
            "--config",
            str(tmp_path / "missing_config.json"),
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert "Traceback" not in captured.err


def test_malformed_config_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "bad_config.json"
    config_path.write_text("{not-json", encoding="utf-8")

    code = workflow_runner_cli_main(
        [
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert "Traceback" not in captured.err


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    config = load_model_evaluation_workflow_config(
        EXAMPLE_CONFIG_PATH,
        output_dir_override=tmp_path / "workflow",
    )

    run_offline_model_evaluation_workflow(config)

    assert not (PROJECT_ROOT / "reports" / WORKFLOW_RUN_MANIFEST_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / WORKFLOW_RUN_MANIFEST_FILENAME).exists()


def test_no_gguf_model_probe_browser_office_calls_are_made(
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
            raise AssertionError("workflow config runner must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    config = load_model_evaluation_workflow_config(
        EXAMPLE_CONFIG_PATH,
        output_dir_override=tmp_path / "workflow",
    )
    result = run_offline_model_evaluation_workflow(config)

    assert result.status == "partial"
