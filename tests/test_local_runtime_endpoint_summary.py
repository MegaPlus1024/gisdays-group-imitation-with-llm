from __future__ import annotations

import builtins
import json
import socket
from pathlib import Path
from typing import Any

import pytest

import src.agent.local_runtime_endpoint_summary as endpoint_summary
from src.agent.local_runtime_endpoint_summary import (
    LOCAL_RUNTIME_ENDPOINT_SUMMARY_SCHEMA_VERSION,
    main as endpoint_summary_main,
    summarize_local_runtime_endpoints,
)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _models_config(*, include_endpoints: bool = True, secret_endpoint: bool = False) -> dict[str, Any]:
    first_endpoint = "http://127.0.0.1:8080/v1" if include_endpoints else None
    second_endpoint = "http://127.0.0.1:8080/v1" if include_endpoints else None
    if secret_endpoint:
        first_endpoint = "http://127.0.0.1:8080/v1?api_key=SECRET_KEY"
    rows = [
        {
            "model_id": "first_model",
            "model_name": "first_model.gguf",
            "gguf_path": "models/gguf/first_model.gguf",
            "runtime": "llama.cpp / llama-server",
            "api_style": "openai_compatible",
        },
        {
            "model_id": "second_model",
            "model_name": "second_model.gguf",
            "gguf_path": "models/gguf/second_model.gguf",
            "runtime": "llama.cpp / llama-server",
            "api_style": "openai_compatible",
        },
    ]
    if first_endpoint is not None:
        rows[0]["base_url"] = first_endpoint
    if second_endpoint is not None:
        rows[1]["base_url"] = second_endpoint
    return {"schema_version": "evaluation_models_v1", "models": rows}


def _scenario_config() -> dict[str, Any]:
    return {
        "scenario_id": "office_document_file_workflow_basic_v1",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
    }


def _local_pipeline_config(**overrides: Any) -> dict[str, Any]:
    payload = {
        "mode": "local",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": "configs/scenario.json",
        "out_dir": "artifacts/single_trial_runs/test/pipeline",
        "run_id": "endpoint_summary_test",
    }
    payload.update(overrides)
    return payload


def _workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_endpoints: bool = True,
    secret_endpoint: bool = False,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(Path("configs/evaluation_models.json"), _models_config(
        include_endpoints=include_endpoints,
        secret_endpoint=secret_endpoint,
    ))
    _write_json(Path("configs/scenario.json"), _scenario_config())
    _write_json(Path("configs/local_pipeline.json"), _local_pipeline_config())


def test_extracts_endpoints_and_detects_shared_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, monkeypatch)

    summary = summarize_local_runtime_endpoints(_local_pipeline_config())

    assert summary["schema_version"] == LOCAL_RUNTIME_ENDPOINT_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "resolved"
    assert summary["orchestrator_model_id"] == "second_model"
    assert summary["executor_model_id"] == "first_model"
    assert summary["orchestrator_endpoint"] == "http://127.0.0.1:8080/v1"
    assert summary["executor_endpoint"] == "http://127.0.0.1:8080/v1"
    assert summary["shared_endpoint"] is True
    assert summary["no_runtime_execution"] is True


def test_endpoint_summary_uses_dual_endpoint_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, monkeypatch)

    summary = summarize_local_runtime_endpoints(
        _local_pipeline_config(
            mode="controlled_single_trial",
            orchestrator_base_url="http://127.0.0.1:8080/v1",
            executor_base_url="http://127.0.0.1:8081/v1",
        )
    )

    assert summary["status"] == "resolved"
    assert summary["orchestrator_endpoint"] == "http://127.0.0.1:8080/v1"
    assert summary["executor_endpoint"] == "http://127.0.0.1:8081/v1"
    assert summary["shared_endpoint"] is False
    assert summary["warnings"] == []
    assert summary["no_runtime_execution"] is True


def test_endpoint_sanitizer_preserves_runtime_urls_and_secret_queries() -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "models.json"])

    assert endpoint_summary._safe_text("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"
    assert endpoint_summary._safe_text("http://127.0.0.1:8081/v1") == "http://127.0.0.1:8081/v1"
    assert endpoint_summary._safe_text("https://example.test/v1") == "https://example.test/v1"
    assert endpoint_summary._safe_text("ws://127.0.0.1:8080/ws") == "ws://127.0.0.1:8080/ws"
    assert (
        endpoint_summary._safe_text("http://host/v1?token=secret")
        == "http://host/v1?token=<redacted_secret>"
    )
    text = endpoint_summary._safe_text(f"see http://127.0.0.1:8080/v1 while reading {windows_path}")
    assert "http://127.0.0.1:8080/v1" in text
    assert windows_path not in text
    assert "<absolute_path>" in text


def test_detects_missing_endpoint_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, monkeypatch, include_endpoints=False)

    summary = summarize_local_runtime_endpoints(_local_pipeline_config())

    assert summary["status"] == "missing"
    assert "orchestrator_endpoint" in summary["missing_fields"]
    assert "executor_endpoint" in summary["missing_fields"]
    assert summary["orchestrator_endpoint"] is None
    assert summary["executor_endpoint"] is None


def test_handles_missing_and_malformed_configs_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(Path("configs/local_pipeline.json"), _local_pipeline_config())

    missing_summary = summarize_local_runtime_endpoints(_local_pipeline_config())
    assert missing_summary["status"] == "missing"
    assert "models_config_path_unreadable" in missing_summary["warnings"]

    Path("bad.json").write_text("{not-json", encoding="utf-8")
    rc = endpoint_summary_main(["--local-pipeline-config", "bad.json"])
    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert rc == 2
    assert result["status"] == "missing"
    assert "local_pipeline_config_malformed" in result["warnings"]


def test_redacts_absolute_paths_and_secret_like_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, monkeypatch, secret_endpoint=True)
    local_config = _local_pipeline_config(models_config_path="\\".join(["C:", "Users", "m", "models.json"]))

    summary = summarize_local_runtime_endpoints(local_config)
    text = json.dumps(summary, ensure_ascii=False)

    assert "<absolute_path>" in text
    assert "C:\\Users" not in text
    assert "SECRET_KEY" not in json.dumps(
        summarize_local_runtime_endpoints(_local_pipeline_config()),
        ensure_ascii=False,
    )
    assert "<redacted_secret>" in json.dumps(
        summarize_local_runtime_endpoints(_local_pipeline_config()),
        ensure_ascii=False,
    )


def test_does_not_read_gguf_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, monkeypatch)
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("GGUF contents must not be read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    summary = summarize_local_runtime_endpoints(_local_pipeline_config())

    assert summary["status"] == "resolved"


def test_does_not_connect_or_instantiate_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, monkeypatch)
    original_import = builtins.__import__

    def forbid_connect(*_: Any, **__: Any) -> object:
        raise AssertionError("network connection must not be attempted")

    def forbid_client_import(name: str, *args: Any, **kwargs: Any) -> object:
        if name.split(".", maxsplit=1)[0] in {"httpx", "requests", "openai", "llama_cpp"}:
            raise AssertionError("HTTP/model clients must not be imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", forbid_connect)
    monkeypatch.setattr(builtins, "__import__", forbid_client_import)

    summary = summarize_local_runtime_endpoints(_local_pipeline_config())

    assert summary["status"] == "resolved"


def test_cli_prints_concise_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, monkeypatch)

    rc = endpoint_summary_main(["--local-pipeline-config", "configs/local_pipeline.json"])
    summary = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert summary["status"] == "resolved"
    assert summary["orchestrator_endpoint"] == "http://127.0.0.1:8080/v1"


def test_cli_writes_optional_output_without_reports_or_experiments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, monkeypatch)

    rc = endpoint_summary_main([
        "--local-pipeline-config",
        "configs/local_pipeline.json",
        "--output",
        "artifacts/endpoint/local_runtime_endpoint_summary.json",
    ])

    assert rc == 0
    assert Path("artifacts/endpoint/local_runtime_endpoint_summary.json").is_file()
    assert not Path("reports").exists()
    assert not Path("experiments").exists()

    rc_forbidden = endpoint_summary_main([
        "--local-pipeline-config",
        "configs/local_pipeline.json",
        "--output",
        "reports/local_runtime_endpoint_summary.json",
    ])
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc_forbidden == 2
    assert summary["status"] == "missing"


def test_existing_first_run_packet_config_can_be_summarized() -> None:
    local_config = json.loads(
        Path("artifacts/first_run_packets/phase_8_13_first/local_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )

    summary = summarize_local_runtime_endpoints(local_config)

    assert summary["status"] == "resolved"
    assert summary["models_config_path"] == "configs/evaluation_models.json"
    assert summary["orchestrator_model_id"] == "second_model"
    assert summary["executor_model_id"] == "first_model"
    assert summary["orchestrator_endpoint"] == "http://127.0.0.1:8080/v1"
    assert summary["executor_endpoint"] == "http://127.0.0.1:8080/v1"
    assert summary["shared_endpoint"] is True
