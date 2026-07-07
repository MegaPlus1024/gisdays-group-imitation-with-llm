from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.agent.evaluation_models import (
    EvaluationModelRegistry,
    EvaluationModelSpec,
    EvaluationModelsConfig,
    load_evaluation_models_config,
    preflight_evaluation_model,
    resolve_evaluation_model,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_CONFIG = PROJECT_ROOT / "configs" / "evaluation_models.json"


def _first_model_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "model_id": "temp_model",
        "display_name": "Temp model",
        "model_name": "temp_model.gguf",
        "gguf_path": "models/gguf/missing_temp_model.gguf",
        "quantization": "Q4_K_M",
        "parameter_size": "1B",
        "runtime": "llama.cpp / llama-server",
        "base_url": "http://127.0.0.1:8080/v1",
        "api_style": "openai_compatible",
        "expected_cpu_only": True,
        "ctx_size": 4096,
        "timeout_seconds": 120.0,
        "temperature": 0.0,
        "max_tokens": 512,
        "enabled": True,
        "notes": [],
    }
    payload.update(overrides)
    return payload


def test_evaluation_models_config_loads() -> None:
    config = load_evaluation_models_config(MODELS_CONFIG)
    ids = EvaluationModelRegistry(config).model_ids()

    assert "first_model" in ids
    assert "second_model" in ids
    assert "qwen2_5_3b_instruct_q4_k_m" not in ids


def test_duplicate_model_id_rejected() -> None:
    model = _first_model_payload(model_id="dup")
    with pytest.raises(ValueError, match="model_id values must be unique"):
        EvaluationModelsConfig.model_validate({"models": [model, model]})


def test_resolve_known_model_id() -> None:
    model = resolve_evaluation_model("first_model", MODELS_CONFIG)

    assert model.model_id == "first_model"
    assert model.model_name == "first_model.gguf"
    assert model.api_model == "first_model"


def test_resolve_second_model_and_legacy_alias() -> None:
    canonical = resolve_evaluation_model("second_model", MODELS_CONFIG)
    legacy = resolve_evaluation_model("qwen2_5_3b_instruct_q4_k_m", MODELS_CONFIG)

    assert canonical.model_id == "second_model"
    assert canonical.model_name == "second_model.gguf"
    assert canonical.gguf_path == "models/gguf/second_model.gguf"
    assert legacy.model_id == "second_model"


def test_unknown_model_id_fails() -> None:
    with pytest.raises(KeyError, match="Unknown evaluation model_id"):
        resolve_evaluation_model("does_not_exist", MODELS_CONFIG)


def test_duplicate_alias_rejected() -> None:
    first = _first_model_payload(model_id="one", aliases=["legacy"])
    second = _first_model_payload(model_id="two", aliases=["legacy"])
    with pytest.raises(ValueError, match="model aliases must be unique"):
        EvaluationModelsConfig.model_validate({"models": [first, second]})


def test_empty_api_model_rejected() -> None:
    with pytest.raises(ValueError, match="optional model string fields"):
        EvaluationModelSpec.model_validate(_first_model_payload(api_model=" "))


def test_alias_conflicting_with_model_id_rejected() -> None:
    first = _first_model_payload(model_id="one", aliases=["two"])
    second = _first_model_payload(model_id="two")
    with pytest.raises(ValueError, match="model aliases must not conflict"):
        EvaluationModelsConfig.model_validate({"models": [first, second]})


def test_disabled_model_preflight_warns_without_override() -> None:
    model = EvaluationModelSpec.model_validate(
        _first_model_payload(enabled=False, gguf_path="models/gguf/first_model.gguf")
    )
    result = preflight_evaluation_model(model, PROJECT_ROOT)

    assert result.status == "warn"
    assert result.can_attempt_local_run is False
    assert any(warning.code == "model_disabled" for warning in result.warnings)


def test_missing_gguf_path_warning_and_require_file_failure() -> None:
    model = EvaluationModelSpec.model_validate(_first_model_payload())

    warning_result = preflight_evaluation_model(model, PROJECT_ROOT)
    fail_result = preflight_evaluation_model(model, PROJECT_ROOT, require_model_file=True)

    assert warning_result.status == "warn"
    assert any(warning.code == "model_file_missing" for warning in warning_result.warnings)
    assert fail_result.status == "fail"
    assert any(issue.code == "model_file_missing" for issue in fail_result.issues)


def test_fake_run_agent_scenario_uses_model_id_metadata_in_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "fake_model_registry_run"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_agent_scenario.py",
            "--mode",
            "fake",
            "--model-id",
            "first_model",
            "--models-config",
            "configs/evaluation_models.json",
            "--out-dir",
            str(out_dir),
            "--max-steps",
            "1",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model"]["model_id"] == "first_model"
    assert manifest["model"]["model_name"] == "first_model.gguf"
    assert manifest["model"]["gguf_path"] == "models/gguf/first_model.gguf"
    assert manifest["model"]["preflight_status"] == "pass"


def test_fake_run_agent_scenario_records_legacy_alias_resolution(tmp_path: Path) -> None:
    out_dir = tmp_path / "fake_model_alias_run"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_agent_scenario.py",
            "--mode",
            "fake",
            "--model-id",
            "qwen2_5_3b_instruct_q4_k_m",
            "--models-config",
            "configs/evaluation_models.json",
            "--out-dir",
            str(out_dir),
            "--max-steps",
            "1",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["requested_model_id"] == "qwen2_5_3b_instruct_q4_k_m"
    assert manifest["resolved_model_id"] == "second_model"
    assert manifest["model"]["model_id"] == "second_model"
    assert manifest["model"]["model_name"] == "second_model.gguf"


def test_local_mode_missing_model_file_fails_before_http_call(tmp_path: Path) -> None:
    models_config = tmp_path / "evaluation_models.json"
    models_config.write_text(
        json.dumps(
            {
                "models": [
                    _first_model_payload(
                        model_id="missing_local_model",
                        model_name="missing_local_model.gguf",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "should_not_exist"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_agent_scenario.py",
            "--mode",
            "local",
            "--model-id",
            "missing_local_model",
            "--models-config",
            str(models_config),
            "--out-dir",
            str(out_dir),
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "model_file_missing" in completed.stderr
    assert not out_dir.exists()


def test_check_evaluation_model_json_works_offline() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_evaluation_model.py",
            "--models-config",
            "configs/evaluation_models.json",
            "--model-id",
            "first_model",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["model"]["model_id"] == "first_model"
    assert payload["preflight"]["status"] == "pass"


def test_start_llama_server_help_works() -> None:
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ".\\scripts\\start_llama_server.ps1",
            "-Help",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "-ModelId first_model" in completed.stdout
