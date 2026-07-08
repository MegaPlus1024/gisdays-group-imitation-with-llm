from __future__ import annotations

import builtins
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_local_planner_diagnostics import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    DiagnosticHttpResponse,
    diagnose_autonomous_browser_local_planner,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_local_planner_diagnostics.example.json"
CLI_PATH = PROJECT_ROOT / "scripts" / "diagnose_autonomous_browser_local_planner.py"


def _config(
    *,
    endpoint_base_url: str = "http://127.0.0.1:8080",
    output_dir: str = "artifacts/autonomous_runtime_summaries/local_planner_diagnostics_tests",
) -> dict[str, Any]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "diagnostic_id": "browser_local_planner_diagnostic_test_v1",
        "endpoint_base_url": endpoint_base_url,
        "model": "second_model",
        "health_timeout_sec": 3,
        "models_timeout_sec": 3,
        "tiny_completion_timeout_sec": 6,
        "micro_planner_timeout_sec": 8,
        "tiny_max_tokens": 16,
        "micro_planner_max_tokens": 96,
        "output_dir": output_dir,
        "limitations": ["test fixture"],
    }


def _write_json_bom(path: Path, payload: Any) -> None:
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


class FakeTransport:
    def __init__(self, responses: dict[tuple[str, str], DiagnosticHttpResponse | BaseException]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, bytes | None, float]] = []

    def __call__(self, method: str, url: str, body: bytes | None, timeout: float) -> DiagnosticHttpResponse:
        self.calls.append((method, url, body, timeout))
        outcome = self.responses[(method, url)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _success_responses(base_url: str, model: str = "second_model") -> dict[tuple[str, str], DiagnosticHttpResponse]:
    health = f"{base_url.rstrip('/')}/health"
    models = f"{base_url.rstrip('/')}/v1/models"
    chat = f"{base_url.rstrip('/')}/v1/chat/completions"
    return {
        ("GET", health): DiagnosticHttpResponse(200, b"ok"),
        ("GET", models): DiagnosticHttpResponse(200, json.dumps({"data": [{"id": model}]}).encode("utf-8")),
        (
            "POST",
            chat,
        ): DiagnosticHttpResponse(
            200,
            json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode("utf-8"),
        ),
    }


def test_no_guard_refuses_without_endpoint_calls(tmp_path: Path) -> None:
    summary = diagnose_autonomous_browser_local_planner(_config(), repo_root=tmp_path)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "allow_local_model_endpoint_required"
    assert summary["model_execution_attempted"] is False
    assert summary["model_execution_completed"] is False
    assert summary["health_status"] == "skipped"


def test_non_local_endpoint_rejected(tmp_path: Path) -> None:
    summary = diagnose_autonomous_browser_local_planner(
        _config(endpoint_base_url="http://example.com:8080"),
        repo_root=tmp_path,
        allow_local_model_endpoint=True,
        transport=FakeTransport({}),
    )

    assert summary["status"] == "failed"
    assert summary["error_code"] == "endpoint_host_not_allowed"


def test_guarded_success_summary_and_steps(tmp_path: Path) -> None:
    transport = FakeTransport(_success_responses("http://127.0.0.1:8080"))
    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=True,
        transport=transport,
    )

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["model_execution_attempted"] is True
    assert summary["model_execution_completed"] is True
    assert summary["health_status"] == "succeeded"
    assert summary["models_status"] == "succeeded"
    assert summary["tiny_completion_status"] == "succeeded"
    assert summary["micro_planner_status"] == "succeeded"
    assert len(summary["steps"]) == 4
    assert summary["steps"][2]["response_preview"] == '{"ok": true}'
    assert summary["steps"][3]["response_preview"]


def test_tiny_completion_timeout_handled(tmp_path: Path) -> None:
    base_url = "http://127.0.0.1:8080"
    transport = FakeTransport(
        {
            ("GET", f"{base_url}/health"): DiagnosticHttpResponse(200, b"ok"),
            ("GET", f"{base_url}/v1/models"): DiagnosticHttpResponse(200, b'{"data": []}'),
            ("POST", f"{base_url}/v1/chat/completions"): TimeoutError("timed out"),
        }
    )
    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=True,
        transport=transport,
    )

    assert summary["status"] == "failed"
    assert summary["error_code"] == "local_planner_timeout"
    assert summary["timeout_step"] == "tiny_completion"
    assert summary["tiny_completion_status"] == "timed_out"


def test_micro_planner_timeout_handled(tmp_path: Path) -> None:
    base_url = "http://127.0.0.1:8080"
    transport = FakeTransport(
        {
            ("GET", f"{base_url}/health"): DiagnosticHttpResponse(200, b"ok"),
            ("GET", f"{base_url}/v1/models"): DiagnosticHttpResponse(200, b'{"data": []}'),
            ("POST", f"{base_url}/v1/chat/completions"): DiagnosticHttpResponse(
                200,
                json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode("utf-8"),
            ),
        }
    )

    def timeout_on_second_post(method: str, url: str, body: bytes | None, timeout: float) -> DiagnosticHttpResponse:
        if method == "POST" and url.endswith("/chat/completions"):
            if timeout > 0:
                timeout_on_second_post.calls += 1
                if timeout_on_second_post.calls == 2:
                    raise TimeoutError("timed out")
        return transport(method, url, body, timeout)

    timeout_on_second_post.calls = 0  # type: ignore[attr-defined]
    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=True,
        transport=timeout_on_second_post,
    )

    assert summary["status"] == "failed"
    assert summary["error_code"] == "local_planner_timeout"
    assert summary["timeout_step"] == "micro_planner_completion"
    assert summary["micro_planner_status"] == "timed_out"


def test_malformed_json_response_handled(tmp_path: Path) -> None:
    base_url = "http://127.0.0.1:8080"
    transport = FakeTransport(
        {
            ("GET", f"{base_url}/health"): DiagnosticHttpResponse(200, b"ok"),
            ("GET", f"{base_url}/v1/models"): DiagnosticHttpResponse(200, b"not json"),
            ("POST", f"{base_url}/v1/chat/completions"): DiagnosticHttpResponse(200, b"{}"),
        }
    )
    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=True,
        transport=transport,
    )

    assert summary["status"] == "failed"
    assert summary["error_code"] == "response_parse_failed"
    assert summary["models_status"] == "failed"


def test_response_preview_bounded_and_sanitized(tmp_path: Path) -> None:
    base_url = "http://127.0.0.1:8080"
    long_text = "C:\\Users\\m\\Documents\\secret " + ("x" * 1000) + " supersecret api_key"
    transport = FakeTransport(
        {
            ("GET", f"{base_url}/health"): DiagnosticHttpResponse(200, long_text.encode("utf-8")),
            ("GET", f"{base_url}/v1/models"): DiagnosticHttpResponse(200, b'{"data": []}'),
            ("POST", f"{base_url}/v1/chat/completions"): DiagnosticHttpResponse(200, json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode("utf-8")),
        }
    )
    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=True,
        transport=transport,
    )

    preview = summary["steps"][0]["response_preview"]
    assert len(preview) <= 240
    assert "C:\\" not in json.dumps(summary, ensure_ascii=False)
    assert "supersecret" not in json.dumps(summary, ensure_ascii=False)
    assert "api_key" not in json.dumps(summary, ensure_ascii=False)


def test_no_absolute_local_paths_in_summary(tmp_path: Path) -> None:
    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=False,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded


def test_no_secrets_in_output(tmp_path: Path) -> None:
    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=False,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "supersecret" not in encoded
    assert "api_key" not in encoded


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = diagnose_autonomous_browser_local_planner(
        _config(),
        repo_root=tmp_path,
        allow_local_model_endpoint=False,
    )

    assert summary["status"] == "failed"


def test_bom_config_is_accepted(tmp_path: Path) -> None:
    config_path = tmp_path / "diagnostic_config.json"
    _write_json_bom(config_path, _config())
    transport = FakeTransport(_success_responses("http://127.0.0.1:8080"))

    summary = diagnose_autonomous_browser_local_planner(
        config_path,
        repo_root=tmp_path,
        allow_local_model_endpoint=True,
        transport=transport,
    )

    assert summary["status"] == "succeeded"


def test_cli_no_guard_refusal_exits_nonzero_and_prints_compact_json() -> None:
    output_dir = "artifacts/autonomous_runtime_summaries/local_planner_diagnostics_cli_test"
    completed = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--config",
            str(CONFIG_PATH),
            "--output-dir",
            output_dir,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    try:
        assert completed.returncode != 0
        assert payload["status"] == "failed"
        assert payload["error_code"] == "allow_local_model_endpoint_required"
    finally:
        shutil.rmtree(PROJECT_ROOT / output_dir, ignore_errors=True)
