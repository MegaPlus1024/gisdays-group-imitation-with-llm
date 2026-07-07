from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_mini_matrix_packet import build_controlled_mini_matrix_packet


PAIR_ID = "second_model__to__first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": "model_catalog_v1",
        "models": [
            {
                "model_id": "first_model",
                "display_name": "First Model",
                "upstream_name": "local/first",
                "local_path": "models/first_model.gguf",
                "family": "synthetic",
                "parameter_count_b": 1.0,
                "quantization": "Q4_K_M",
                "enabled": True,
                "roles": {
                    "orchestrator_candidate": False,
                    "executor_candidate": True,
                    "judge_candidate": False,
                },
                "tags": ["fixture"],
            },
            {
                "model_id": "second_model",
                "display_name": "Second Model",
                "upstream_name": "local/second",
                "local_path": "models/second_model.gguf",
                "family": "synthetic",
                "parameter_count_b": 2.0,
                "quantization": "Q5_K_M",
                "enabled": True,
                "roles": {
                    "orchestrator_candidate": True,
                    "executor_candidate": False,
                    "judge_candidate": False,
                },
                "tags": ["fixture"],
            },
        ],
    }


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.chdir(tmp_path)
    _write_json(Path("configs/model_catalog.json"), _catalog_payload())
    _write_json(Path("configs/scenario.json"), {"scenario_id": SCENARIO_ID})
    _write_json(
        Path("configs/local_pipeline_config.json"),
        {
            "schema_version": "single_trial_local_pipeline_config_v1",
            "mode": "controlled_single_trial",
            "models_config_path": "configs/evaluation_models.json",
            "scenario_path": "configs/scenario.json",
            "out_dir": "artifacts/single_trial_runs/base/pipeline",
            "run_id": "base",
            "max_group_steps": 1,
            "max_steps_per_agent": 1,
            "execute_actions": True,
            "action_parameter_repair": {"enabled": True},
            "office_real_document_enabled": True,
            "execution_options": {
                "allow_runtime_execution": True,
                "no_runtime_execution": False,
            },
        },
    )
    return {
        "output_dir": "packets/mini",
        "model_catalog_path": "configs/model_catalog.json",
        "base_local_pipeline_config_path": "configs/local_pipeline_config.json",
    }


def _json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_packet_commands_include_correctness_postprocess_after_artifact_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _workspace(tmp_path, monkeypatch)

    summary = build_controlled_mini_matrix_packet(
        **paths,
        scenario_id=SCENARIO_ID,
        pair_id=PAIR_ID,
        run_id_prefix="phase_8_26_mini_matrix",
        repeat_count=2,
        tags=("controlled_mini_matrix",),
    )
    commands = _json(summary["commands_path"])

    assert summary["status"] == "ready"
    for repeat in commands["repeats"]:
        postprocess = repeat["postprocess_commands"]
        assert [command["name"] for command in postprocess] == [
            "office_execution_artifact_summary",
            "office_execution_correctness_summary",
        ]
        assert "scripts/summarize_office_execution_artifacts.py" in postprocess[0]["argv"]
        assert "scripts/score_office_execution_correctness.py" in postprocess[1]["argv"]
        assert f"{repeat['output_dir']}/office_execution_artifact_summary.json" in postprocess[1]["argv"]
        assert f"{repeat['output_dir']}/office_execution_correctness_summary.json" in postprocess[1]["argv"]
        assert all(command["no_runtime_execution"] is True for command in postprocess)
        assert repeat["runtime_command"]["no_runtime_execution"] is True
    assert commands["aggregate_command"]["name"] == "aggregate_mini_matrix_results"
    assert not Path("artifacts/single_trial_runs/phase_8_26_mini_matrix_r1").exists()
