from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_catalog import load_model_catalog
from src.agent.model_resource_evaluation import (
    MODEL_RESOURCE_SUMMARY_FILENAME,
    ModelResourceObservation,
    load_model_resource_observations_from_file,
    run_model_resource_evaluation,
    summarize_model_resource_observations,
    write_model_resource_summary,
)
from src.agent.model_resource_evaluation_cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"


def _observation(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "observation_id": "obs_001",
        "model_id": "first_model",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "runtime_mode": "cpu",
        "backend": "fake",
        "success": True,
        "wall_time_s": 1.5,
        "peak_ram_gb": 2.0,
        "peak_vram_gb": 0.0,
        "tags": ["offline"],
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    return path


def _summary(observations: list[dict[str, object]]):
    return summarize_model_resource_observations(
        [ModelResourceObservation.model_validate(row) for row in observations]
    )


def _summary_json(out_dir: Path) -> dict[str, Any]:
    return json.loads((out_dir / MODEL_RESOURCE_SUMMARY_FILENAME).read_text(encoding="utf-8"))


def test_load_json_list_observations(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "observations.json", [_observation()])

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert result.status == "ok"
    assert len(result.observations) == 1
    assert result.observations[0].model_id == "first_model"


def test_load_json_dict_observations(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "observations.json", {"observations": [_observation()]})

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert result.status == "ok"
    assert result.observations[0].observation_id == "obs_001"


def test_load_jsonl_observations(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "observations.jsonl", [_observation(), _observation(observation_id="obs_002")])

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert result.status == "ok"
    assert [obs.observation_id for obs in result.observations] == ["obs_001", "obs_002"]


def test_missing_file_controlled(tmp_path: Path) -> None:
    result = load_model_resource_observations_from_file(tmp_path / "missing.json", project_root=tmp_path)

    assert result.status == "input_missing"
    assert result.observations == []
    assert "resource_observation_file_missing" in result.warnings


def test_malformed_json_controlled(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert result.status == "invalid_input"
    assert result.invalid_count == 1
    assert "resource_observation_json_decode_error" in result.warnings


def test_alias_fields_normalize_correctly(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "observations.json",
        [
            {
                "observation_id": "obs_alias",
                "model": "second_model",
                "duration_s": 3.0,
                "ram_peak_gb": 4.0,
                "vram_peak_gb": 5.0,
                "status": "completed",
            }
        ],
    )

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)
    obs = result.observations[0]

    assert obs.model_id == "second_model"
    assert obs.wall_time_s == pytest.approx(3.0)
    assert obs.peak_ram_gb == pytest.approx(4.0)
    assert obs.peak_vram_gb == pytest.approx(5.0)
    assert obs.success is True


def test_pair_id_derived_from_orchestrator_executor(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "observations.json",
        [_observation(model_id=None, orchestrator="second_model", executor="first_model")],
    )

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert result.observations[0].pair_id == "second_model__to__first_model"


def test_negative_metrics_produce_invalid_warning(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "observations.json", [_observation(wall_time_s=-1.0)])

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert result.status == "invalid_input"
    assert result.invalid_count == 1
    assert "negative_metric_rejected:wall_time_s" in result.warnings


def test_aggregation_by_model_works() -> None:
    summary = _summary([_observation(), _observation(observation_id="obs_002", success=False, error_code="timeout")])
    group = summary.groups["by_model"]["first_model"]

    assert group.observation_count == 2
    assert group.success_count == 1
    assert group.failure_count == 1
    assert group.success_rate == pytest.approx(0.5)
    assert group.error_counts == {"timeout": 1}


def test_aggregation_by_pair_works() -> None:
    summary = _summary([
        _observation(model_id=None, orchestrator_model_id="second_model", executor_model_id="first_model")
    ])

    assert "second_model__to__first_model" in summary.groups["by_pair"]
    assert summary.groups["by_model"]["second_model"].observation_count == 1
    assert summary.groups["by_model"]["first_model"].observation_count == 1


def test_aggregation_by_runtime_mode_works() -> None:
    summary = _summary([_observation(runtime_mode="gpu_full_offload")])

    assert summary.groups["by_runtime_mode"]["gpu_full_offload"].observation_count == 1


def test_aggregation_by_scenario_works() -> None:
    summary = _summary([_observation(scenario_id="scenario_a")])

    assert summary.groups["by_scenario"]["scenario_a"].observation_count == 1


def test_success_rate_and_error_counts_calculated() -> None:
    summary = _summary(
        [
            _observation(success=True),
            _observation(observation_id="obs_002", success=False, error_code="http_400"),
            _observation(observation_id="obs_003", success=False, error_code="http_400"),
        ]
    )
    group = summary.groups["by_model"]["first_model"]

    assert group.success_rate == pytest.approx(1 / 3)
    assert group.error_counts == {"http_400": 2}


def test_catalog_enrichment_adds_family_params_quantization() -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    summary = summarize_model_resource_observations(
        [ModelResourceObservation.model_validate(_observation(model_id="second_model"))],
        model_catalog=catalog,
    )
    metadata = summary.groups["by_model"]["second_model"].catalog_metadata

    assert metadata is not None
    assert metadata["family"] == "qwen2.5"
    assert metadata["parameter_count_b"] == pytest.approx(3.0)
    assert metadata["quantization"] == "Q4_K_M"


def test_unknown_catalog_model_adds_warning() -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    summary = summarize_model_resource_observations(
        [ModelResourceObservation.model_validate(_observation(model_id="unknown_model"))],
        model_catalog=catalog,
    )

    assert summary.groups["by_model"]["unknown_model"].catalog_metadata is None
    assert any("model_catalog_entry_missing:unknown_model" in warning for warning in summary.warnings)


def test_absolute_windows_path_in_notes_is_redacted(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside", "trace.txt"])
    path = _write_json(tmp_path / "observations.json", [_observation(notes=[f"read {windows_path}"])])

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert windows_path not in result.observations[0].notes[0]
    assert "<absolute_path>" in result.observations[0].notes[0]


def test_absolute_posix_path_in_notes_is_redacted(tmp_path: Path) -> None:
    posix_path = "/home/example/outside/trace.txt"
    path = _write_json(tmp_path / "observations.json", [_observation(notes=[f"read {posix_path}"])])

    result = load_model_resource_observations_from_file(path, project_root=tmp_path)

    assert posix_path not in result.observations[0].notes[0]
    assert "<absolute_path>" in result.observations[0].notes[0]


def test_no_gguf_model_files_are_opened_or_read(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    original_read_text = Path.read_text
    original_exists = Path.exists

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError(f"unexpected GGUF read: {self}")
        return original_read_text(self, *args, **kwargs)

    def forbid_gguf_exists(self: Path) -> bool:
        if self.suffix.lower() == ".gguf":
            raise AssertionError(f"unexpected GGUF exists check: {self}")
        return original_exists(self)

    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)

    summary = summarize_model_resource_observations(
        [ModelResourceObservation.model_validate(_observation(model_id="second_model"))],
        model_catalog=catalog,
    )

    assert summary.status == "ok"


def test_summary_json_written_to_tmp_output_dir(tmp_path: Path) -> None:
    summary = _summary([_observation()])

    path = write_model_resource_summary(summary, tmp_path / "out")
    payload = _summary_json(tmp_path / "out")

    assert path == tmp_path / "out" / MODEL_RESOURCE_SUMMARY_FILENAME
    assert payload["schema_version"] == "model_resource_summary_v1"
    assert payload["summary_path_relative"] == MODEL_RESOURCE_SUMMARY_FILENAME


def test_cli_evaluates_multiple_inputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = _write_json(tmp_path / "first.json", [_observation()])
    second = _write_json(tmp_path / "second.json", [_observation(observation_id="obs_002", model_id="second_model")])

    code = main(["--input", str(first), "--input", str(second), "--output-dir", str(tmp_path / "out")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["input_count"] == 2
    assert payload["observation_count"] == 2
    assert payload["group_counts"]["by_model"] == 2
    assert (tmp_path / "out" / MODEL_RESOURCE_SUMMARY_FILENAME).is_file()


def test_cli_with_catalog_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _write_json(tmp_path / "observations.json", [_observation(model_id="second_model")])

    code = main(
        [
            "--input",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--model-catalog",
            str(CATALOG_PATH),
            "--summary-id",
            "resource_summary_test",
            "--tag",
            "offline",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    summary = _summary_json(tmp_path / "out")

    assert code == 0
    assert payload["status"] == "ok"
    assert summary["summary_id"] == "resource_summary_test"
    assert summary["tags"] == ["offline"]
    assert summary["groups"]["by_model"]["second_model"]["catalog_metadata"]["family"] == "qwen2.5"


def test_cli_missing_input_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--input", str(tmp_path / "missing.json"), "--output-dir", str(tmp_path / "out")])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["observation_count"] == 0
    assert "Traceback" not in captured.err


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "observations.json", [_observation()])

    run_model_resource_evaluation([source], tmp_path / "out")

    assert not (PROJECT_ROOT / "reports" / MODEL_RESOURCE_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_RESOURCE_SUMMARY_FILENAME).exists()

