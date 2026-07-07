from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_first_run_packet import (
    COMMAND_JSON_FILENAME,
    CONTROLLED_SINGLE_TRIAL_TAG,
    FIRST_SINGLE_TRIAL_RUN_PACKET_SCHEMA_VERSION,
    LOCAL_MODEL_PAIR_ENTRYPOINT_REF,
    LOCAL_PIPELINE_CONFIG_FILENAME,
    RUN_SINGLE_TRIAL_SCRIPT_FILENAME,
    SINGLE_TRIAL_RUNTIME_CONFIRMATION,
    build_first_single_trial_run_packet,
    main as packet_main,
)


PAIR_ID = "second_model__to__first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"
RUN_ID = "phase_8_12_first"
TRIAL_ID = f"{SCENARIO_ID}__{PAIR_ID}__r01"
DUAL_ENDPOINT_CONFIG_PATH = Path("configs/local_pipeline/single_trial_local_pipeline.dual_endpoint.example.json")
DUAL_ENDPOINT_COMPACT_CONFIG_PATH = Path(
    "configs/local_pipeline/single_trial_local_pipeline.dual_endpoint.compact.example.json"
)
DUAL_ENDPOINT_COMPACT_REPAIR_CONFIG_PATH = Path(
    "configs/local_pipeline/single_trial_local_pipeline.dual_endpoint.compact_repair.example.json"
)
DUAL_ENDPOINT_COMPACT_REPAIR_EXECUTE_CONFIG_PATH = Path(
    "configs/local_pipeline/single_trial_local_pipeline.dual_endpoint.compact_repair_execute.example.json"
)
DUAL_ENDPOINT_COMPACT_REPAIR_EXECUTE_V2_CONFIG_PATH = Path(
    "configs/local_pipeline/single_trial_local_pipeline.dual_endpoint.compact_repair_execute_v2.example.json"
)
DUAL_ENDPOINT_COMPACT_REPAIR_EXECUTE_V3_CONFIG_PATH = Path(
    "configs/local_pipeline/single_trial_local_pipeline.dual_endpoint.compact_repair_execute_v3.example.json"
)


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


def _local_pipeline_config(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "single_trial_local_pipeline_config_v1",
        "mode": "local",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": "configs/scenario.json",
        "out_dir": "artifacts/single_trial_runs/phase_8_12_first/pipeline",
        "run_id": RUN_ID,
        "max_group_steps": 1,
        "max_steps_per_agent": 1,
        "execute_actions": False,
        "force": True,
        "execution_options": {
            "allow_runtime_execution": True,
            "no_runtime_execution": False,
        },
    }
    payload.update(overrides)
    return payload


def _fixture_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    scenario_exists: bool = True,
    local_config_overrides: dict[str, Any] | None = None,
) -> dict[str, str]:
    monkeypatch.chdir(tmp_path)
    _write_json(Path("configs/model_catalog.json"), _catalog_payload())
    _write_json(Path("configs/local_pipeline_config.json"), _local_pipeline_config(**(local_config_overrides or {})))
    if scenario_exists:
        _write_json(Path("configs/scenario.json"), {"scenario_id": SCENARIO_ID})
    return {
        "output_dir": "packets/first",
        "model_catalog_path": "configs/model_catalog.json",
        "local_pipeline_config_path": "configs/local_pipeline_config.json",
    }


def _build_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    **overrides: Any,
) -> dict[str, Any]:
    paths = _fixture_workspace(
        tmp_path,
        monkeypatch,
        scenario_exists=overrides.pop("scenario_exists", True),
        local_config_overrides=overrides.pop("local_config_overrides", None),
    )
    payload: dict[str, Any] = {
        **paths,
        "scenario_id": SCENARIO_ID,
        "pair_id": PAIR_ID,
        "run_id": RUN_ID,
    }
    payload.update(overrides)
    return build_first_single_trial_run_packet(**payload)


def _json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_builds_ready_packet_and_expected_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(tmp_path, monkeypatch, tags=("smoke",))

    assert summary["schema_version"] == FIRST_SINGLE_TRIAL_RUN_PACKET_SCHEMA_VERSION
    assert summary["status"] == "ready"
    assert summary["readiness_status"] == "ready"
    assert summary["run_id"] == RUN_ID
    assert summary["pair_id"] == PAIR_ID
    assert summary["scenario_id"] == SCENARIO_ID
    assert summary["no_runtime_execution"] is True
    assert summary["auto_matrix_adapter_outputs"] is True

    plan_path = Path(summary["plan_path"])
    readiness_path = Path(summary["readiness_summary_path"])
    copied_config_path = Path(summary["local_pipeline_config_path"])
    script_path = Path(summary["run_script_path"])
    command_path = Path(summary["command_path"])
    assert plan_path.name == "model_pair_plan.json"
    assert readiness_path.name == "model_pair_execution_readiness_summary.json"
    assert copied_config_path.name == LOCAL_PIPELINE_CONFIG_FILENAME
    assert script_path.name == RUN_SINGLE_TRIAL_SCRIPT_FILENAME
    assert command_path.name == COMMAND_JSON_FILENAME
    assert all(path.is_file() for path in (plan_path, readiness_path, copied_config_path, script_path, command_path))

    plan = _json(plan_path)
    assert plan["candidate_pairs"][0]["pair_id"] == PAIR_ID
    assert len(plan["candidate_pairs"]) == 1
    assert len(plan["trials"]) == 1
    assert plan["trials"][0]["trial_id"] == TRIAL_ID
    assert CONTROLLED_SINGLE_TRIAL_TAG in plan["trials"][0]["tags"]

    readiness = _json(readiness_path)
    assert readiness["status"] == "ready"
    assert readiness["trial_count"] == 1
    assert readiness["no_runtime_execution"] is True

    script = script_path.read_text(encoding="utf-8")
    assert r".\.venv\Scripts\python.exe scripts/run_single_trial_controlled.py" in script
    assert "--plan packets/first/model_pair_plan.json" in script
    assert "--readiness-summary packets/first/model_pair_execution_readiness_summary.json" in script
    assert f"--entrypoint {LOCAL_MODEL_PAIR_ENTRYPOINT_REF}" in script
    assert "--local-pipeline-config packets/first/local_pipeline_config.json" in script
    assert f"--output-dir artifacts/single_trial_runs/{RUN_ID}" in script
    assert f"--trial-id {TRIAL_ID}" in script
    assert "--allow-runtime-execution" in script
    assert f"--confirm-runtime-execution {SINGLE_TRIAL_RUNTIME_CONFIRMATION}" in script
    assert "--auto-matrix-adapter-outputs" in script
    assert f"--run-id {RUN_ID}" in script
    assert f"--tag {CONTROLLED_SINGLE_TRIAL_TAG}" in script
    assert "--tag smoke" in script


def test_dual_endpoint_example_config_is_safe_and_packet_ready() -> None:
    payload = _json(DUAL_ENDPOINT_CONFIG_PATH)

    assert payload["schema_version"] == "single_trial_local_pipeline_config_v1"
    assert payload["mode"] == "controlled_single_trial"
    assert payload["models_config_path"] == "configs/evaluation_models.json"
    assert payload["scenario_path"] == "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
    assert payload["out_dir"] == "artifacts/single_trial_runs/phase_8_17_dual_endpoint/pipeline"
    assert payload["run_id"] == "phase_8_17_dual_endpoint"
    assert payload["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert payload["executor_base_url"] == "http://127.0.0.1:8081/v1"
    assert payload["execute_actions"] is False
    assert payload["execution_options"]["allow_runtime_execution"] is True
    assert payload["execution_options"]["no_runtime_execution"] is False
    for key in ("models_config_path", "scenario_path", "out_dir"):
        assert not Path(payload[key]).is_absolute()
        assert ".." not in Path(payload[key]).parts


def test_dual_endpoint_compact_example_config_is_safe_and_ready_for_retry() -> None:
    payload = _json(DUAL_ENDPOINT_COMPACT_CONFIG_PATH)

    assert payload["schema_version"] == "single_trial_local_pipeline_config_v1"
    assert payload["mode"] == "controlled_single_trial"
    assert payload["out_dir"] == "artifacts/single_trial_runs/phase_8_20_compact_retry/pipeline"
    assert payload["run_id"] == "phase_8_20_compact_retry"
    assert payload["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert payload["executor_base_url"] == "http://127.0.0.1:8081/v1"
    assert payload["prompt_budget"]["executor_max_prompt_chars"] == 12000
    assert payload["prompt_budget"]["orchestrator_max_prompt_chars"] == 16000
    assert payload["prompt_budget"]["max_history_items"] == 6
    assert payload["prompt_budget"]["compact_executor_context"] is True
    for key in ("models_config_path", "scenario_path", "out_dir"):
        assert not Path(payload[key]).is_absolute()
        assert ".." not in Path(payload[key]).parts


def test_dual_endpoint_compact_repair_example_config_is_safe_and_ready_for_retry() -> None:
    payload = _json(DUAL_ENDPOINT_COMPACT_REPAIR_CONFIG_PATH)

    assert payload["schema_version"] == "single_trial_local_pipeline_config_v1"
    assert payload["mode"] == "controlled_single_trial"
    assert payload["out_dir"] == "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline"
    assert payload["run_id"] == "phase_8_21_action_repair_retry"
    assert payload["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert payload["executor_base_url"] == "http://127.0.0.1:8081/v1"
    assert payload["prompt_budget"]["executor_max_prompt_chars"] == 12000
    assert payload["prompt_budget"]["compact_executor_context"] is True
    assert payload["action_parameter_repair"]["enabled"] is True
    assert payload["action_parameter_repair"]["office_default_output_dir"] == (
        "artifacts/single_trial_runs/phase_8_21_action_repair_retry/"
        "pipeline/workspace/office_outputs"
    )
    for key in ("models_config_path", "scenario_path", "out_dir"):
        assert not Path(payload[key]).is_absolute()
        assert ".." not in Path(payload[key]).parts
    repair_dir = Path(payload["action_parameter_repair"]["office_default_output_dir"])
    assert not repair_dir.is_absolute()
    assert ".." not in repair_dir.parts


def test_packet_builder_accepts_and_preserves_dual_endpoint_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(
        tmp_path,
        monkeypatch,
        run_id="phase_8_17_dual_endpoint",
        local_config_overrides={
            "mode": "controlled_single_trial",
            "out_dir": "artifacts/single_trial_runs/phase_8_17_dual_endpoint/pipeline",
            "run_id": "phase_8_17_dual_endpoint",
            "orchestrator_base_url": "http://127.0.0.1:8080/v1",
            "executor_base_url": "http://127.0.0.1:8081/v1",
        },
    )

    assert summary["status"] == "ready"
    copied_config = _json(summary["local_pipeline_config_path"])
    command = _json(summary["command_path"])

    assert copied_config["mode"] == "controlled_single_trial"
    assert copied_config["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert copied_config["executor_base_url"] == "http://127.0.0.1:8081/v1"
    assert "http:<absolute_path>" not in json.dumps(copied_config, ensure_ascii=False)
    assert str(summary["local_pipeline_config_path"]) in command["argv"]
    assert "artifacts/single_trial_runs/phase_8_17_dual_endpoint" in command["argv"]
    assert command["no_runtime_execution"] is True


def test_packet_builder_accepts_and_preserves_compact_prompt_budget_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(
        tmp_path,
        monkeypatch,
        run_id="phase_8_20_compact_retry",
        local_config_overrides={
            "mode": "controlled_single_trial",
            "out_dir": "artifacts/single_trial_runs/phase_8_20_compact_retry/pipeline",
            "run_id": "phase_8_20_compact_retry",
            "orchestrator_base_url": "http://127.0.0.1:8080/v1",
            "executor_base_url": "http://127.0.0.1:8081/v1",
            "prompt_budget": {
                "executor_max_prompt_chars": 12000,
                "orchestrator_max_prompt_chars": 16000,
                "max_history_items": 6,
                "compact_executor_context": True,
            },
        },
    )

    assert summary["status"] == "ready"
    assert summary["readiness_status"] == "ready"
    copied_config = _json(summary["local_pipeline_config_path"])
    assert copied_config["prompt_budget"]["executor_max_prompt_chars"] == 12000
    assert copied_config["prompt_budget"]["compact_executor_context"] is True
    assert not Path(f"artifacts/single_trial_runs/phase_8_20_compact_retry").exists()


def test_packet_builder_accepts_and_preserves_compact_repair_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(
        tmp_path,
        monkeypatch,
        run_id="phase_8_21_action_repair_retry",
        local_config_overrides={
            "mode": "controlled_single_trial",
            "out_dir": "artifacts/single_trial_runs/phase_8_21_action_repair_retry/pipeline",
            "run_id": "phase_8_21_action_repair_retry",
            "orchestrator_base_url": "http://127.0.0.1:8080/v1",
            "executor_base_url": "http://127.0.0.1:8081/v1",
            "prompt_budget": {
                "executor_max_prompt_chars": 12000,
                "orchestrator_max_prompt_chars": 16000,
                "max_history_items": 6,
                "compact_executor_context": True,
            },
            "action_parameter_repair": {
                "enabled": True,
                "office_default_output_dir": (
                    "artifacts/single_trial_runs/phase_8_21_action_repair_retry/"
                    "pipeline/workspace/office_outputs"
                ),
            },
        },
    )

    assert summary["status"] == "ready"
    assert summary["readiness_status"] == "ready"
    copied_config = _json(summary["local_pipeline_config_path"])
    assert copied_config["action_parameter_repair"]["enabled"] is True
    assert copied_config["action_parameter_repair"]["office_default_output_dir"].endswith(
        "pipeline/workspace/office_outputs"
    )
    assert not Path("artifacts/single_trial_runs/phase_8_21_action_repair_retry").exists()


def test_summary_paths_are_relative_and_do_not_expose_tmp_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(tmp_path, monkeypatch)
    encoded = json.dumps(summary, ensure_ascii=False)

    for key in ("packet_dir", "plan_path", "readiness_summary_path", "local_pipeline_config_path", "command_path"):
        assert not Path(summary[key]).is_absolute()
    assert str(tmp_path) not in encoded
    assert ":\\" not in encoded


def test_no_auto_matrix_adapter_flag_omits_generated_command_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(tmp_path, monkeypatch, auto_matrix_adapter_outputs=False)

    assert summary["status"] == "ready"
    script = Path(summary["run_script_path"]).read_text(encoding="utf-8")
    command = _json(summary["command_path"])
    assert "--auto-matrix-adapter-outputs" not in script
    assert "--auto-matrix-adapter-outputs" not in command["argv"]


def test_missing_scenario_reference_returns_not_ready_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(tmp_path, monkeypatch, scenario_exists=False)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "not_ready"
    assert summary["readiness_status"] == "not_ready"
    assert "readiness_not_ready" in summary["warnings"]
    assert Path(summary["readiness_summary_path"]).is_file()
    assert "Traceback" not in encoded


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("output_dir", "../packet"),
        ("output_dir", "reports/packet"),
        ("output_dir", "docs/ai/final-packet"),
        ("model_catalog_path", "../model_catalog.json"),
        ("local_pipeline_config_path", "../local_pipeline_config.json"),
    ],
)
def test_rejects_traversal_and_forbidden_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    summary = _build_packet(tmp_path, monkeypatch, **{field: value})

    assert summary["status"] == "invalid"
    assert "Traceback" not in json.dumps(summary, ensure_ascii=False)


def test_rejects_absolute_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture_workspace(tmp_path, monkeypatch)

    summary = build_first_single_trial_run_packet(
        output_dir=tmp_path / "packet",
        model_catalog_path="configs/model_catalog.json",
        scenario_id=SCENARIO_ID,
        pair_id=PAIR_ID,
        local_pipeline_config_path="configs/local_pipeline_config.json",
        run_id=RUN_ID,
    )

    assert summary["status"] == "invalid"
    assert summary["error"] == "output_dir_must_be_relative"


def test_rejects_secret_like_local_pipeline_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(
        tmp_path,
        monkeypatch,
        local_config_overrides={"api_key": "should_not_be_serialized"},
    )

    assert summary["status"] == "invalid"
    assert summary["error"] == "local_pipeline_config_secret_like"
    assert "should_not_be_serialized" not in json.dumps(summary, ensure_ascii=False)


def test_does_not_read_gguf_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("GGUF contents must not be read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    summary = _build_packet(tmp_path, monkeypatch)

    assert summary["status"] == "ready"


def test_does_not_import_runtime_or_browser_office_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__
    forbidden_prefixes = (
        "src.agent.orchestrator_executor_pipeline",
        "src.agent.model_pair_local_pipeline_entrypoint",
        "llama_cpp",
        "playwright",
        "selenium",
        "win32com",
        "office",
    )

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden_prefixes):
            raise AssertionError(f"Forbidden runtime import attempted: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = _build_packet(tmp_path, monkeypatch)

    assert summary["status"] == "ready"


def test_does_not_write_reports_experiments_docs_or_runtime_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = _build_packet(tmp_path, monkeypatch)

    assert summary["status"] == "ready"
    assert not Path("reports").exists()
    assert not Path("experiments").exists()
    assert not Path("docs/ai/final").exists()
    assert not Path(f"artifacts/single_trial_runs/{RUN_ID}").exists()


def test_cli_prints_json_and_does_not_execute_generated_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _fixture_workspace(tmp_path, monkeypatch)

    rc = packet_main(
        [
            "--output-dir",
            paths["output_dir"],
            "--model-catalog",
            paths["model_catalog_path"],
            "--scenario-id",
            SCENARIO_ID,
            "--pair-id",
            PAIR_ID,
            "--local-pipeline-config",
            paths["local_pipeline_config_path"],
            "--run-id",
            RUN_ID,
            "--tag",
            "cli",
        ]
    )
    stdout = capsys.readouterr().out
    summary = json.loads(stdout)

    assert rc == 0
    assert summary["status"] == "ready"
    assert Path(summary["command_path"]).is_file()
    assert not Path(f"artifacts/single_trial_runs/{RUN_ID}").exists()


def test_cli_invalid_returns_nonzero_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _fixture_workspace(tmp_path, monkeypatch)

    rc = packet_main(
        [
            "--output-dir",
            "../packet",
            "--model-catalog",
            paths["model_catalog_path"],
            "--scenario-id",
            SCENARIO_ID,
            "--pair-id",
            PAIR_ID,
            "--local-pipeline-config",
            paths["local_pipeline_config_path"],
            "--run-id",
            RUN_ID,
        ]
    )
    summary = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert summary["status"] == "invalid"


def test_packet_builder_accepts_compact_repair_execute_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture_workspace(
        tmp_path,
        monkeypatch,
        local_config_overrides={
            "run_id": "phase_8_22_action_execution_retry",
            "out_dir": "artifacts/single_trial_runs/phase_8_22_action_execution_retry/pipeline",
            "execute_actions": True,
            "action_parameter_repair": {
                "enabled": True,
                "office_default_output_dir": (
                    "artifacts/single_trial_runs/phase_8_22_action_execution_retry/"
                    "pipeline/workspace/office_outputs"
                ),
            },
            "office_real_document_enabled": True,
            "office_real_document_artifact_root": (
                "artifacts/single_trial_runs/phase_8_22_action_execution_retry/pipeline/workspace"
            ),
            "office_real_document_max_file_bytes": 5000000,
            "office_real_document_max_text_preview_chars": 500,
            "office_real_document_allow_formulas": False,
        },
    )

    summary = build_first_single_trial_run_packet(
        output_dir=paths["output_dir"],
        model_catalog_path=paths["model_catalog_path"],
        scenario_id=SCENARIO_ID,
        pair_id=PAIR_ID,
        local_pipeline_config_path=paths["local_pipeline_config_path"],
        run_id="phase_8_22_action_execution_retry",
        tags=("controlled_single_trial",),
    )
    copied_config = _json(Path(summary["local_pipeline_config_path"]))
    command = _json(Path(summary["command_path"]))

    assert summary["status"] == "ready"
    assert copied_config["execute_actions"] is True
    assert copied_config["office_real_document_enabled"] is True
    assert copied_config["office_real_document_artifact_root"].endswith("pipeline/workspace")
    assert "--allow-runtime-execution" in command["argv"]
    assert command["notes"] == [
        "Prepared command only; this packet builder does not execute runtime.",
        "The generated script requires explicit runtime confirmation before use.",
    ]


def test_packet_builder_accepts_compact_repair_execute_v2_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture_workspace(
        tmp_path,
        monkeypatch,
        local_config_overrides={
            "run_id": "phase_8_23_office_extension_retry",
            "out_dir": "artifacts/single_trial_runs/phase_8_23_office_extension_retry/pipeline",
            "execute_actions": True,
            "action_parameter_repair": {
                "enabled": True,
                "office_default_output_dir": (
                    "artifacts/single_trial_runs/phase_8_23_office_extension_retry/"
                    "pipeline/workspace/office_outputs"
                ),
            },
            "office_real_document_enabled": True,
            "office_real_document_artifact_root": (
                "artifacts/single_trial_runs/phase_8_23_office_extension_retry/pipeline/workspace"
            ),
        },
    )

    summary = build_first_single_trial_run_packet(
        output_dir=paths["output_dir"],
        model_catalog_path=paths["model_catalog_path"],
        scenario_id=SCENARIO_ID,
        pair_id=PAIR_ID,
        local_pipeline_config_path=paths["local_pipeline_config_path"],
        run_id="phase_8_23_office_extension_retry",
        tags=("controlled_single_trial",),
    )
    copied_config = _json(Path(summary["local_pipeline_config_path"]))
    command = _json(Path(summary["command_path"]))

    assert summary["status"] == "ready"
    assert summary["readiness_status"] == "ready"
    assert copied_config["run_id"] == "phase_8_23_office_extension_retry"
    assert copied_config["execute_actions"] is True
    assert copied_config["action_parameter_repair"]["office_default_output_dir"].endswith(
        "phase_8_23_office_extension_retry/pipeline/workspace/office_outputs"
    )
    assert copied_config["office_real_document_enabled"] is True
    assert "--allow-runtime-execution" in command["argv"]


def test_packet_builder_accepts_compact_repair_execute_v3_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture_workspace(
        tmp_path,
        monkeypatch,
        local_config_overrides={
            "run_id": "phase_8_24_docx_precreate_retry",
            "out_dir": "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/pipeline",
            "execute_actions": True,
            "action_parameter_repair": {
                "enabled": True,
                "office_default_output_dir": (
                    "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/"
                    "pipeline/workspace/office_outputs"
                ),
                "create_missing_docx_for_append": True,
            },
            "office_real_document_enabled": True,
            "office_real_document_artifact_root": (
                "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/pipeline/workspace"
            ),
        },
    )

    summary = build_first_single_trial_run_packet(
        output_dir="artifacts/first_run_packets/phase_8_24_docx_precreate_retry",
        model_catalog_path=paths["model_catalog_path"],
        scenario_id=SCENARIO_ID,
        pair_id=PAIR_ID,
        local_pipeline_config_path=paths["local_pipeline_config_path"],
        run_id="phase_8_24_docx_precreate_retry",
        tags=("controlled_single_trial",),
    )
    copied_config = _json(Path(summary["local_pipeline_config_path"]))
    command = _json(Path(summary["command_path"]))

    assert summary["status"] == "ready"
    assert summary["readiness_status"] == "ready"
    assert copied_config["run_id"] == "phase_8_24_docx_precreate_retry"
    assert copied_config["action_parameter_repair"]["create_missing_docx_for_append"] is True
    assert copied_config["out_dir"] == "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry/pipeline"
    assert "artifacts/first_run_packets/phase_8_24_docx_precreate_retry/local_pipeline_config.json" in command["argv"]
    assert "artifacts/single_trial_runs/phase_8_24_docx_precreate_retry" in command["argv"]
