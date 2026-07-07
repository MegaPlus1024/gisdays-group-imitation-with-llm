from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

import scripts.run_autonomous_browser_playwright_operator as runner_module
from src.agent.autonomous_browser_playwright_execution import (
    FakePlaywrightBackend,
    PlaywrightExecutionConfig,
    PlaywrightExecutionResult,
    RealPlaywrightBackend,
    run_guarded_playwright_smoke,
    run_guarded_playwright_suite,
)
from src.agent.autonomous_browser_playwright_operator import (
    REQUIRED_CONFIRM_VALUE,
    PlaywrightOperatorConfig,
    load_playwright_operator_config,
    validate_playwright_operator_config,
)
from src.agent.autonomous_browser_playwright_evidence import build_playwright_smoke_evidence_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG_PATH = PROJECT_ROOT / "configs/autonomous_runtime/playwright_operator.example.json"
SUITE_CONFIG_PATH = PROJECT_ROOT / "configs/autonomous_runtime/playwright_suite_operator.example.json"


class FakeServer:
    def __enter__(self) -> "FakeServer":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb

    def to_summary(self) -> dict[str, Any]:
        return {
            "host": "127.0.0.1",
            "port": 8765,
            "base_url": "http://127.0.0.1:8765",
            "fixture_root": "tests/fixtures/local_intranet/office_site_v1",
        }


class FakeResponse:
    status = 200


class FakeLocator:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def click(self, *, timeout: int) -> None:
        del timeout
        self.page.clicks += 1


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.clicks = 0
        self.fills: dict[str, str] = {}
        self.waits: list[int] = []

    def goto(self, url: str, *, wait_until: str, timeout: int) -> FakeResponse:
        del wait_until, timeout
        self.url = url
        return FakeResponse()

    def get_by_text(self, text: str) -> FakeLocator:
        del text
        return FakeLocator(self)

    def click(self, selector: str, *, timeout: int) -> None:
        del selector, timeout
        self.clicks += 1

    def fill(self, selector: str, value: str, *, timeout: int) -> None:
        del timeout
        self.fills[selector] = value

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)

    def inner_text(self, selector: str, *, timeout: int) -> str:
        del selector, timeout
        return "Office Intranet Local portal request submitted"


def _suite_config() -> PlaywrightExecutionConfig:
    return PlaywrightExecutionConfig.from_operator_config(
        load_playwright_operator_config(SUITE_CONFIG_PATH),
        repo_root=PROJECT_ROOT,
    )


def _smoke_config_with_scope(scope: dict[str, Any]) -> PlaywrightExecutionConfig:
    payload = load_playwright_operator_config(SMOKE_CONFIG_PATH).to_dict()
    payload["execution_scope"] = scope
    return PlaywrightExecutionConfig.from_operator_config(
        PlaywrightOperatorConfig.from_dict(payload),
        repo_root=PROJECT_ROOT,
    )


def test_suite_config_example_loads_and_validates() -> None:
    readiness = validate_playwright_operator_config(load_playwright_operator_config(SUITE_CONFIG_PATH), repo_root=PROJECT_ROOT)
    checks = {item["name"]: item for item in readiness.to_dict()["checks"]}

    assert readiness.ready is True
    assert checks["execution_scope_mode"]["passed"] is True
    assert checks["execution_scope_max_scenarios"]["passed"] is True
    assert checks["execution_scope_required_actions"]["passed"] is True


def test_suite_scope_rejects_unbounded_max_scenarios(tmp_path: Path) -> None:
    payload = json.loads(SUITE_CONFIG_PATH.read_text(encoding="utf-8"))
    payload["execution_scope"]["max_scenarios"] = 0
    config_path = tmp_path / "suite.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    readiness = validate_playwright_operator_config(load_playwright_operator_config(config_path), repo_root=PROJECT_ROOT)
    checks = {item["name"]: item for item in readiness.to_dict()["checks"]}

    assert readiness.ready is False
    assert checks["execution_scope_max_scenarios"]["passed"] is False


def test_scenario_id_scope_selects_named_scenario() -> None:
    summary = run_guarded_playwright_smoke(
        _smoke_config_with_scope({"mode": "scenario_id", "scenario_id": "browser_portal_approval_check", "max_browser_actions": 8}),
        backend=FakePlaywrightBackend(),
        server=FakeServer(),
    )

    assert summary.status == "succeeded"
    assert summary.scenario_scope["scenario_id"] == "browser_portal_approval_check"


def test_suite_mode_runs_bounded_scenarios_and_covers_all_required_actions() -> None:
    summary = run_guarded_playwright_suite(_suite_config(), backend=FakePlaywrightBackend(), server=FakeServer())
    payload = summary.to_dict()

    assert payload["schema_version"] == "autonomous_browser_playwright_suite_summary_v1"
    assert payload["status"] == "succeeded"
    assert payload["scenario_count"] == 4
    assert payload["scenarios_attempted"] == 4
    assert payload["required_actions_missing"] == []
    assert set(payload["required_actions_covered"]) == set(payload["required_actions"])
    assert payload["overall_action_coverage_ratio"] == 1.0


def test_suite_expected_result_failure_precedes_coverage_when_actions_are_covered() -> None:
    summary = run_guarded_playwright_suite(
        _suite_config(),
        backend=FakePlaywrightBackend(text_preview="fixture text without expected markers"),
        server=FakeServer(),
    )

    assert summary.status == "failed"
    assert summary.error_code == "expected_result_failed"
    assert summary.expected_results_failed > 0


def test_suite_required_action_missing_reports_coverage_failure() -> None:
    config = _smoke_config_with_scope(
        {
            "mode": "suite",
            "max_scenarios": 1,
            "max_browser_actions_per_scenario": 12,
            "required_actions": [
                "browser_open_url",
                "browser_click",
                "browser_extract_text",
                "browser_fill",
                "browser_submit",
                "browser_wait",
                "browser_search",
                "browser_snapshot",
            ],
        }
    )

    summary = run_guarded_playwright_suite(config, backend=FakePlaywrightBackend(), server=FakeServer())

    assert summary.status == "failed"
    assert summary.error_code == "required_action_coverage_failed"
    assert "browser_fill" in summary.required_actions_missing


def test_suite_summary_has_no_local_absolute_paths() -> None:
    summary = run_guarded_playwright_suite(_suite_config(), backend=FakePlaywrightBackend(), server=FakeServer())
    encoded = json.dumps(summary.to_dict(), ensure_ascii=False)

    assert str(PROJECT_ROOT) not in encoded
    assert ":\\" not in encoded


def test_suite_evidence_summarizer_accepts_suite_schema() -> None:
    report = build_playwright_smoke_evidence_report(
        run_guarded_playwright_suite(_suite_config(), backend=FakePlaywrightBackend(), server=FakeServer()).to_dict()
    )

    assert report["passed"] is True
    assert report["source_schema_version"] == "autonomous_browser_playwright_suite_summary_v1"
    assert report["required_actions_missing"] == []


def test_real_backend_plans_fill_submit_wait_without_playwright_import(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("playwright"):
            raise AssertionError("real backend action planning test must not import Playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    backend = RealPlaywrightBackend()
    backend._page = FakePage()

    fill = backend.run_action(
        "browser_fill",
        "http://127.0.0.1:8765/portal/request.html",
        logical_url="https://local-intranet.test/portal/request",
        parameters={"fields": {"owner": "office", "status": "ready"}},
    )
    wait = backend.run_action(
        "browser_wait",
        "http://127.0.0.1:8765/portal/request.html",
        logical_url="https://local-intranet.test/portal/request",
        parameters={"milliseconds": 250},
    )
    submit = backend.run_action(
        "browser_submit",
        "http://127.0.0.1:8765/portal/submitted.html",
        logical_url="https://local-intranet.test/portal/submitted",
        parameters={"form_id": "local-request"},
    )

    assert fill.success is True
    assert "Updated 2 fixture form field" in fill.text_preview
    assert wait.success is True
    assert "Fixture browser wait completed" in wait.text_preview
    assert submit.success is True


def test_runner_writes_suite_summary_filename(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured_paths: list[Path] = []

    class FakeSummary:
        status = "succeeded"

        def to_dict(self) -> dict[str, Any]:
            return {
                "schema_version": "autonomous_browser_playwright_suite_summary_v1",
                "status": self.status,
                "no_runtime_execution": False,
            }

    def fake_suite_runner(config: PlaywrightExecutionConfig) -> FakeSummary:
        assert config.execution_scope["mode"] == "suite"
        return FakeSummary()

    monkeypatch.setattr(
        runner_module,
        "write_autonomous_runtime_scenario_summary",
        lambda payload, path: captured_paths.append(Path(path)),
    )
    rc = runner_module.main(
        [
            "--config",
            str(SUITE_CONFIG_PATH),
            "--allow-real-browser",
            "--confirm-real-browser",
            REQUIRED_CONFIRM_VALUE,
        ],
        suite_execution_runner=fake_suite_runner,
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["schema_version"] == "autonomous_browser_playwright_suite_summary_v1"
    assert captured_paths and captured_paths[0].name == "playwright_suite_summary.json"


def test_suite_fake_tests_do_not_import_runtime_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    summary = run_guarded_playwright_suite(_suite_config(), backend=FakePlaywrightBackend(), server=FakeServer())

    assert summary.status == "succeeded"
