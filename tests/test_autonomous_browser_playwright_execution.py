from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_playwright_execution import (
    FakePlaywrightBackend,
    FixtureUrlMapper,
    LocalFixtureHttpServer,
    PlaywrightExecutionConfig,
    PlaywrightExecutionError,
    RealPlaywrightBackend,
    _sanitize_diagnostics,
    _resolve_fixture_request_target,
    run_guarded_playwright_smoke,
)
from src.agent.autonomous_browser_playwright_operator import load_playwright_operator_config
from src.agent.autonomous_browser_runtime import BROWSER_RUNTIME_ACTION_NAMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs/autonomous_runtime/playwright_operator.example.json"


class FakeServer:
    def __enter__(self) -> "FakeServer":
        self.started = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb
        self.stopped = True

    def to_summary(self) -> dict[str, Any]:
        return {
            "host": "127.0.0.1",
            "port": 8765,
            "base_url": "http://127.0.0.1:8765",
            "fixture_root": "tests/fixtures/local_intranet/office_site_v1",
        }


def _execution_config() -> PlaywrightExecutionConfig:
    return PlaywrightExecutionConfig.from_operator_config(
        load_playwright_operator_config(CONFIG_PATH),
        repo_root=PROJECT_ROOT,
    )


def test_execution_module_import_does_not_import_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("playwright"):
            raise AssertionError("module-level execution path must not import Playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    config = _execution_config()

    assert config.operator_id == "browser_suite_playwright_operator_v1"


def test_fake_backend_can_simulate_succeeded_smoke() -> None:
    summary = run_guarded_playwright_smoke(
        _execution_config(),
        backend=FakePlaywrightBackend(),
        server=FakeServer(),
    )

    payload = summary.to_dict()
    assert payload["schema_version"] == "autonomous_browser_playwright_smoke_summary_v1"
    assert payload["status"] == "succeeded"
    assert payload["no_runtime_execution"] is False
    assert payload["actions_attempted"] > 0
    assert payload["actions_failed"] == 0
    assert payload["logical_urls_visited"]


def test_fake_backend_can_simulate_playwright_dependency_missing() -> None:
    summary = run_guarded_playwright_smoke(
        _execution_config(),
        backend=FakePlaywrightBackend(fail_with="playwright_dependency_missing"),
        server=FakeServer(),
    )

    assert summary.status == "failed"
    assert summary.error_code == "playwright_dependency_missing"


def test_real_backend_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("playwright"):
            raise AssertionError("constructing backend must not import Playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    backend = RealPlaywrightBackend()

    assert backend.browser_name == "chromium"


def test_fixture_server_config_rejects_non_loopback_host() -> None:
    with pytest.raises(PlaywrightExecutionError, match="fixture_server_host_not_loopback"):
        LocalFixtureHttpServer(
            host="example.com",
            port=8765,
            fixture_root="tests/fixtures/local_intranet/office_site_v1",
            base_url="http://example.com:8765",
            repo_root=PROJECT_ROOT,
        )


def test_fixture_server_config_rejects_unsafe_fixture_root() -> None:
    with pytest.raises(PlaywrightExecutionError, match="fixture_root_unsafe"):
        LocalFixtureHttpServer(
            host="127.0.0.1",
            port=8765,
            fixture_root="../fixtures",
            base_url="http://127.0.0.1:8765",
            repo_root=PROJECT_ROOT,
        )


def test_url_mapper_maps_logical_domain_to_loopback_url() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    assert mapper.map_logical_url("https://local.intranet/docs/policy") == "http://127.0.0.1:8765/docs/policy.html"


def test_url_mapper_maps_root_to_index_fixture() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    assert mapper.map_logical_url("https://local.intranet/") == "http://127.0.0.1:8765/index.html"


def test_url_mapper_maps_ticket_to_fixture_file() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    assert mapper.map_logical_url("https://local.intranet/tickets/1") == "http://127.0.0.1:8765/tickets/1.html"


def test_url_mapper_maps_docs_policy_to_fixture_file() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    assert mapper.map_logical_url("https://docs.local/docs/policy") == "http://127.0.0.1:8765/docs/policy.html"


def test_url_mapper_maps_portal_root_to_domain_fixture() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    assert mapper.map_logical_url("https://portal.local/") == "http://127.0.0.1:8765/portal/index.html"


def test_url_mapper_maps_portal_status_to_domain_fixture() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    assert mapper.map_logical_url("https://portal.local/status") == "http://127.0.0.1:8765/portal/status.html"


def test_fixture_request_target_resolves_manifest_routes() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "tests" / "fixtures" / "local_intranet" / "office_site_v1" / "site_manifest.json").read_text(encoding="utf-8")
    )
    routes = manifest["routes"]
    root = PROJECT_ROOT / "tests" / "fixtures" / "local_intranet" / "office_site_v1"

    assert _resolve_fixture_request_target("/docs/policy", root=root, manifest_routes=routes).relative_to(root).as_posix() == "docs/policy.html"
    assert _resolve_fixture_request_target("/tickets", root=root, manifest_routes=routes).relative_to(root).as_posix() == "tickets/index.html"
    assert _resolve_fixture_request_target("/tickets/1", root=root, manifest_routes=routes).relative_to(root).as_posix() == "tickets/1.html"
    assert _resolve_fixture_request_target("/portal/approvals", root=root, manifest_routes=routes).relative_to(root).as_posix() == "portal/approvals.html"
    assert _resolve_fixture_request_target("/portal/approval-match", root=root, manifest_routes=routes).relative_to(root).as_posix() == "portal/approval-match.html"


def test_url_mapper_rejects_unknown_domain() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    with pytest.raises(PlaywrightExecutionError, match="unknown_logical_domain"):
        mapper.map_logical_url("https://example.com/docs/policy")


def test_url_mapper_rejects_missing_fixture() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    with pytest.raises(PlaywrightExecutionError, match="fixture_mapping_not_found"):
        mapper.map_logical_url("https://local.intranet/missing/not-there")


def test_url_mapper_rejects_path_traversal() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    with pytest.raises(PlaywrightExecutionError):
        mapper.map_logical_url("https://local.intranet/../secret")


def test_sanitizer_preserves_logical_and_loopback_urls() -> None:
    sanitized = _sanitize_diagnostics(
        {
            "logical_url": "https://local.intranet/tickets/1",
            "served_url": "http://127.0.0.1:8765/tickets/1.html",
        }
    )

    assert sanitized["logical_url"] == "https://local.intranet/tickets/1"
    assert sanitized["served_url"] == "http://127.0.0.1:8765/tickets/1.html"


def test_sanitizer_redacts_windows_absolute_path() -> None:
    sanitized = _sanitize_diagnostics({"path": "C:\\Users\\m\\secret.txt"})

    assert sanitized["path"] == "<absolute_path>"


def test_summary_has_no_local_absolute_paths() -> None:
    summary = run_guarded_playwright_smoke(
        _execution_config(),
        backend=FakePlaywrightBackend(),
        server=FakeServer(),
    )
    encoded = json.dumps(summary.to_dict(), ensure_ascii=False)

    assert str(PROJECT_ROOT) not in encoded
    assert ":\\" not in encoded


def test_output_summary_is_json_serializable() -> None:
    summary = run_guarded_playwright_smoke(
        _execution_config(),
        backend=FakePlaywrightBackend(),
        server=FakeServer(),
    )

    assert json.loads(json.dumps(summary.to_dict()))["schema_version"] == "autonomous_browser_playwright_smoke_summary_v1"


def test_fake_playwright_http_404_marks_action_failed() -> None:
    backend = FakePlaywrightBackend(http_status=404)

    result = backend.run_action(
        "browser_open_url",
        "http://127.0.0.1:8765/missing.html",
        logical_url="https://local.intranet/missing",
        expected_text="Missing",
    )

    assert result.success is False
    assert result.error_code == "browser_http_error"
    assert result.diagnostics["http_status"] == 404


def test_http_404_summary_prefers_browser_action_failed() -> None:
    summary = run_guarded_playwright_smoke(
        _execution_config(),
        backend=FakePlaywrightBackend(http_status=404),
        server=FakeServer(),
    )

    assert summary.status == "failed"
    assert summary.error_code == "browser_action_failed"
    assert summary.actions_attempted == 1
    assert summary.actions_succeeded == 0
    assert summary.actions_failed == 1
    assert summary.diagnostics["actions"][0]["error_code"] == "browser_http_error"


def test_fake_successful_action_with_expected_text_passes() -> None:
    summary = run_guarded_playwright_smoke(
        _execution_config(),
        backend=FakePlaywrightBackend(),
        server=FakeServer(),
    )

    assert summary.status == "succeeded"
    assert all(item["passed"] for item in summary.expected_results)


def test_no_mail_git_calendar_actions_added() -> None:
    assert not any(name.startswith(("mail_", "git_", "calendar_", "email_")) for name in BROWSER_RUNTIME_ACTION_NAMES)


def test_no_llm_api_model_or_real_browser_calls_in_fake_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    summary = run_guarded_playwright_smoke(
        _execution_config(),
        backend=FakePlaywrightBackend(),
        server=FakeServer(),
    )

    assert summary.status == "succeeded"
