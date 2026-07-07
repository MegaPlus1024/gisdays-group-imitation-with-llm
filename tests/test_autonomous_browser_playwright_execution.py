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

    assert mapper.map_logical_url("https://local.intranet/docs/policy") == "http://127.0.0.1:8765/docs/policy"


def test_url_mapper_rejects_unknown_domain() -> None:
    mapper = FixtureUrlMapper(
        manifest_path="tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        server_base_url="http://127.0.0.1:8765",
        repo_root=PROJECT_ROOT,
    )

    with pytest.raises(PlaywrightExecutionError, match="unknown_logical_domain"):
        mapper.map_logical_url("https://example.com/docs/policy")


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
