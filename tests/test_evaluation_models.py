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
DISPLAY_NAMES_CONFIG = PROJECT_ROOT / "configs" / "model_display_names.json"


def _first_model_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "model_id": "temp_model",
        "display_name": "Temp model",
        "role": "temporary baseline",
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


def _write_models_config(tmp_path: Path, model_payload: dict[str, object]) -> Path:
    config_path = tmp_path / "evaluation_models.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "evaluation_models_v1",
                "models": [model_payload],
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_evaluation_models_config_loads() -> None:
    config = load_evaluation_models_config(MODELS_CONFIG)
    ids = EvaluationModelRegistry(config).model_ids()

    assert "first_model" in ids
    assert "second_model" in ids
    assert "third_model" in ids
    assert "fourth_model" in ids
    assert "fifth_model" in ids
    assert "sixth_model" in ids
    assert "qwen2_5_3b_instruct_q4_k_m" not in ids
    assert "qwen3_6_27b_q5_k_m" not in ids


def test_third_model_registry_entry_uses_relative_gguf_path() -> None:
    config = load_evaluation_models_config(MODELS_CONFIG)
    third_model = next(model for model in config.models if model.model_id == "third_model")

    assert third_model.gguf_path == "models/gguf/third_model.gguf"
    assert not Path(third_model.gguf_path).is_absolute()
    assert third_model.display_name == "Qwen3-14B Q5_K_M"
    assert third_model.role == "strong historical Qwen planner"
    assert third_model.api_model == "third_model"
    assert third_model.enabled is True
    assert any("local GGUF file" in note for note in third_model.notes)


def test_first_model_registry_entry_reflects_granite_alias_metadata() -> None:
    config = load_evaluation_models_config(MODELS_CONFIG)
    first_model = next(model for model in config.models if model.model_id == "first_model")

    assert first_model.gguf_path == "models/gguf/first_model.gguf"
    assert not Path(first_model.gguf_path).is_absolute()
    assert first_model.display_name == "IBM Granite 3.3 8B Instruct Q4_K_M"
    assert first_model.role == "small/medium non-Qwen baseline"
    assert first_model.base_url == "http://127.0.0.1:8081/v1"
    assert first_model.upstream_model_name == "granite-3.3-8b-instruct-q4_k_m.gguf"
    assert first_model.parameter_size == "8B"
    assert any("must not be committed" in note for note in first_model.notes)


def test_fourth_and_fifth_model_registry_entries_use_relative_gguf_paths() -> None:
    config = load_evaluation_models_config(MODELS_CONFIG)
    fourth_model = next(model for model in config.models if model.model_id == "fourth_model")
    fifth_model = next(model for model in config.models if model.model_id == "fifth_model")

    assert fourth_model.gguf_path == "models/gguf/fourth_model.gguf"
    assert fifth_model.gguf_path == "models/gguf/fifth_model.gguf"
    assert not Path(fourth_model.gguf_path).is_absolute()
    assert not Path(fifth_model.gguf_path).is_absolute()
    assert fourth_model.api_model == "fourth_model"
    assert fifth_model.api_model == "fifth_model"
    assert fourth_model.base_url == "http://127.0.0.1:8083/v1"
    assert fifth_model.base_url == "http://127.0.0.1:8084/v1"
    assert fourth_model.display_name == "Mistral Small 3.2 24B Instruct Q4_K_M"
    assert fourth_model.role == "strong non-Qwen challenger"
    assert fifth_model.display_name == "Qwen3-30B-A3B-Instruct-2507 Q4_K_M"
    assert fifth_model.role == "strong efficient MoE challenger"
    assert fifth_model.upstream_model_name == "qwen3-30b-a3b-instruct-2507-q4_k_m.gguf"
    assert any("must not be committed" in note for note in fourth_model.notes)
    assert any("must not be committed" in note for note in fifth_model.notes)


def test_sixth_model_registry_entry_and_legacy_alias() -> None:
    config = load_evaluation_models_config(MODELS_CONFIG)
    sixth_model = next(model for model in config.models if model.model_id == "sixth_model")
    legacy = resolve_evaluation_model("qwen3_6_27b_q5_k_m", MODELS_CONFIG)

    assert sixth_model.display_name == "Qwen3.6-27B Q5_K_M"
    assert sixth_model.gguf_path == (
        "models/gguf/sixth_model/Qwen3.6-27B-Q5_K_M.gguf"
    )
    assert not Path(sixth_model.gguf_path).is_absolute()
    assert sixth_model.api_model == "sixth_model"
    assert sixth_model.base_url == "http://127.0.0.1:8085/v1"
    assert sixth_model.quantization == "Q5_K_M"
    assert legacy.model_id == "sixth_model"


def test_model_display_names_match_evaluation_registry() -> None:
    display_payload = json.loads(DISPLAY_NAMES_CONFIG.read_text(encoding="utf-8"))
    registry = load_evaluation_models_config(MODELS_CONFIG)
    registry_names = {model.model_id: model.display_name for model in registry.models}

    assert display_payload["schema_version"] == "model_display_names_v1"
    assert display_payload["models"] == {
        "third_model": {
            "display_name": registry_names["third_model"],
            "quantization": "Q5_K_M",
        },
        "fourth_model": {
            "display_name": registry_names["fourth_model"],
            "quantization": "Q4_K_M",
        },
        "fifth_model": {
            "display_name": registry_names["fifth_model"],
            "quantization": "Q4_K_M",
        },
        "sixth_model": {
            "display_name": registry_names["sixth_model"],
            "quantization": "Q5_K_M",
        },
    }


def test_required_model_downloader_uses_new_path_and_verifies_legacy_before_move() -> None:
    script = (PROJECT_ROOT / "scripts" / "download_required_model.ps1").read_text(
        encoding="utf-8"
    )

    assert r"models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf" in script
    assert (
        r"models\gguf\qwen3_6_27b_q5_k_m\Qwen3.6-27B-Q5_K_M.gguf"
        in script
    )
    assert "Get-FileHash -LiteralPath $LegacyDestinationPath" in script
    assert "Move-Item -LiteralPath $LegacyDestinationPath" in script


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
    missing_model_path = tmp_path / "missing_first_model.gguf"
    models_config = _write_models_config(
        tmp_path,
        _first_model_payload(
            model_id="first_model",
            display_name="IBM Granite 3.3 8B Instruct Q4_K_M",
            role="small/medium non-Qwen baseline",
            model_name="first_model.gguf",
            gguf_path=str(missing_model_path),
        ),
    )
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
            str(models_config),
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
    assert manifest["model"]["gguf_path"] == str(missing_model_path)
    assert manifest["model"]["preflight_status"] == "warn"
    assert [warning["code"] for warning in manifest["model"]["preflight_warnings"]] == ["model_file_missing"]


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


def test_check_evaluation_model_json_passes_with_temporary_model_file(tmp_path: Path) -> None:
    relative_model_path = Path("models") / "gguf" / "test_model.gguf"
    model_path = tmp_path / relative_model_path
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"clean-clone model fixture")
    models_config = _write_models_config(
        tmp_path,
        _first_model_payload(
            model_id="test_model",
            model_name="test_model.gguf",
            gguf_path=relative_model_path.as_posix(),
        ),
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_evaluation_model.py",
            "--models-config",
            str(models_config),
            "--project-root",
            str(tmp_path),
            "--model-id",
            "test_model",
            "--require-model-file",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["model"]["model_id"] == "test_model"
    assert payload["preflight"]["status"] == "pass"
    assert payload["preflight"]["warnings"] == []
    assert payload["preflight"]["metadata"]["model_file_exists"] is True
    assert payload["preflight"]["can_attempt_local_run"] is True


def test_check_evaluation_model_json_works_offline(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_evaluation_model.py",
            "--models-config",
            str(MODELS_CONFIG),
            "--project-root",
            str(tmp_path),
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
    assert payload["preflight"]["status"] == "warn"
    assert [warning["code"] for warning in payload["preflight"]["warnings"]] == ["model_file_missing"]
    assert payload["preflight"]["metadata"]["model_file_exists"] is False
    assert payload["preflight"]["can_attempt_local_run"] is False


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
