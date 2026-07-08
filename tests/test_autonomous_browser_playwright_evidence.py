from __future__ import annotations

import builtins
import copy
import json
from pathlib import Path
from typing import Any

import pytest

import scripts.summarize_playwright_smoke_evidence as cli
from src.agent.autonomous_browser_playwright_evidence import (
    EVIDENCE_SCHEMA_VERSION,
    PlaywrightSmokeEvidenceError,
    build_playwright_smoke_evidence_report,
    render_playwright_smoke_evidence_markdown,
    validate_playwright_smoke_summary,
)


def _successful_summary() -> dict[str, Any]:
    return {
        "schema_version": "autonomous_browser_playwright_smoke_summary_v1",
        "operator_id": "browser_suite_playwright_operator_v1",
        "status": "succeeded",
        "error_code": None,
        "no_runtime_execution": False,
        "actions_attempted": 6,
        "actions_succeeded": 6,
        "actions_failed": 0,
        "browser_backend": {"type": "playwright", "browser_name": "chromium", "headless": True},
        "scenario_scope": {
            "mode": "first_scenario_only",
            "max_browser_actions": 8,
            "scenario_id": "browser_intranet_research_group_basic",
        },
        "logical_urls_visited": [
            "https://local.intranet/tickets/1",
            "https://docs.local/docs/policy",
        ],
        "diagnostics": {
            "actions": [
                {
                    "action_name": "browser_open_url",
                    "served_url": "http://127.0.0.1:8765/tickets/1.html",
                    "logical_url": "https://local.intranet/tickets/1",
                    "success": True,
                },
                {
                    "action_name": "browser_extract_text",
                    "served_url": "http://127.0.0.1:8765/tickets/1.html",
                    "logical_url": "https://local.intranet/tickets/1",
                    "success": True,
                },
                {
                    "action_name": "browser_snapshot",
                    "served_url": "http://127.0.0.1:8765/tickets/1.html",
                    "logical_url": "https://local.intranet/tickets/1",
                    "success": True,
                },
                {
                    "action_name": "browser_open_url",
                    "served_url": "http://127.0.0.1:8765/docs/policy.html",
                    "logical_url": "https://docs.local/docs/policy",
                    "success": True,
                },
                {
                    "action_name": "browser_search",
                    "served_url": "http://127.0.0.1:8765/docs/policy.html",
                    "logical_url": "https://docs.local/docs/policy",
                    "success": True,
                },
                {
                    "action_name": "browser_snapshot",
                    "served_url": "http://127.0.0.1:8765/docs/policy.html",
                    "logical_url": "https://docs.local/docs/policy",
                    "success": True,
                },
            ]
        },
        "expected_results": [
            {"step_id": "reader_open_ticket", "expected_text": "Quarterly Access Review", "passed": True},
            {"step_id": "reader_extract_ticket", "expected_text": "Expected activity", "passed": True},
            {"step_id": "reader_snapshot_ticket", "expected_text": None, "passed": True},
            {"step_id": "checker_open_policy", "expected_text": "Allowed activity", "passed": True},
            {"step_id": "checker_search_policy", "expected_text": "fixture-backed result", "passed": True},
            {"step_id": "checker_snapshot_policy", "expected_text": None, "passed": True},
        ],
    }


def _successful_suite_summary() -> dict[str, Any]:
    summary = _successful_summary()
    summary.update(
        {
            "schema_version": "autonomous_browser_playwright_suite_summary_v1",
            "status": "succeeded",
            "error_code": None,
            "expected_results_total": 30,
            "expected_results_passed": 30,
            "expected_results_failed": 0,
            "scenario_count": 4,
            "scenarios_attempted": 4,
            "scenarios_succeeded": 4,
            "scenarios_failed": 0,
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
            "required_actions_covered": [
                "browser_open_url",
                "browser_click",
                "browser_extract_text",
                "browser_fill",
                "browser_submit",
                "browser_wait",
                "browser_search",
                "browser_snapshot",
            ],
            "required_actions_missing": [],
            "overall_action_coverage_ratio": 1.0,
        }
    )
    summary["logical_urls_visited"] = [
        "https://local.intranet/tickets/1",
        "https://docs.local/docs/policy",
        "https://local-intranet.test/",
        "https://local-intranet.test/tickets",
        "https://local-intranet.test/docs/policy",
        "https://local-intranet.test/portal/request",
        "https://local-intranet.test/portal/submitted",
        "https://local.intranet/",
        "https://local.intranet/docs/policy",
        "https://portal.local/portal",
        "https://portal.local/portal/approvals",
        "https://portal.local/portal/status",
    ]
    summary["scenario_scope"] = {"mode": "suite"}
    return summary


def test_successful_summary_validates() -> None:
    evidence = validate_playwright_smoke_summary(_successful_summary())

    assert evidence.schema_version == EVIDENCE_SCHEMA_VERSION
    assert evidence.passed is True
    assert evidence.evidence_level == "guarded_real_browser_smoke_succeeded"
    assert evidence.actions_attempted == 6
    assert evidence.expected_results_passed == 6


def test_successful_suite_summary_validates() -> None:
    evidence = validate_playwright_smoke_summary(_successful_suite_summary())

    assert evidence.schema_version == EVIDENCE_SCHEMA_VERSION
    assert evidence.passed is True
    assert evidence.evidence_level == "guarded_real_browser_suite_succeeded"
    assert evidence.scenario_count == 4
    assert evidence.scenarios_succeeded == 4
    assert evidence.required_actions_missing == ()


def test_failed_status_produces_passed_false() -> None:
    summary = _successful_summary()
    summary["status"] = "failed"
    summary["error_code"] = "expected_result_failed"

    evidence = validate_playwright_smoke_summary(summary)

    assert evidence.passed is False
    assert evidence.evidence_level == "guarded_real_browser_smoke_not_succeeded"


def test_expected_result_failure_produces_passed_false() -> None:
    summary = _successful_summary()
    summary["expected_results"][0]["passed"] = False

    evidence = validate_playwright_smoke_summary(summary)

    assert evidence.passed is False
    assert evidence.expected_results_passed == 5


def test_non_loopback_served_url_rejected() -> None:
    summary = _successful_summary()
    summary["diagnostics"]["actions"][0]["served_url"] = "https://example.com/tickets/1.html"

    with pytest.raises(PlaywrightSmokeEvidenceError, match="loopback"):
        validate_playwright_smoke_summary(summary)


def test_local_absolute_path_in_summary_rejected() -> None:
    summary = _successful_summary()
    summary["diagnostics"]["actions"][0]["text_preview"] = "C:\\Users\\m\\secret.txt"

    with pytest.raises(PlaywrightSmokeEvidenceError, match="absolute path"):
        validate_playwright_smoke_summary(summary)


def test_evidence_report_json_serializable() -> None:
    report = build_playwright_smoke_evidence_report(_successful_summary())

    assert json.loads(json.dumps(report))["schema_version"] == EVIDENCE_SCHEMA_VERSION


def test_markdown_renderer_includes_status_actions_and_limitations() -> None:
    report = build_playwright_smoke_evidence_report(_successful_summary())
    markdown = render_playwright_smoke_evidence_markdown(report)

    assert "Status: succeeded" in markdown
    assert "Actions attempted/succeeded/failed: 6/6/0" in markdown
    assert "single guarded smoke scenario" in markdown


def test_markdown_renderer_includes_suite_coverage() -> None:
    report = build_playwright_smoke_evidence_report(_successful_suite_summary())
    markdown = render_playwright_smoke_evidence_markdown(report)

    assert "guarded Playwright browser suite run" in markdown
    assert "Scenarios attempted/succeeded/failed: 4/4/0" in markdown
    assert "Required browser actions covered: 8/8" in markdown
    assert "local loopback fixture suite only" in markdown


def test_cli_writes_markdown_evidence_to_temp_docs_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_successful_summary()), encoding="utf-8")
    output_doc = tmp_path / "docs" / "status" / "playwright_smoke_evidence.md"

    rc = cli.main(["--summary", str(summary_path), "--output-doc", str(output_doc)])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["status"] == "succeeded"
    assert output_doc.is_file()
    assert "guarded Playwright browser smoke run" in output_doc.read_text(encoding="utf-8")


def test_cli_writes_suite_evidence_to_temp_docs_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_successful_suite_summary()), encoding="utf-8")
    output_doc = tmp_path / "docs" / "status" / "playwright_smoke_evidence.md"

    rc = cli.main(["--summary", str(summary_path), "--output-doc", str(output_doc)])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["status"] == "succeeded"
    assert output_doc.is_file()
    rendered = output_doc.read_text(encoding="utf-8")
    assert "guarded Playwright browser suite run" in rendered
    assert "Scenarios attempted/succeeded/failed: 4/4/0" in rendered


def test_cli_refuses_unsafe_output_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(_successful_summary()), encoding="utf-8")

    rc = cli.main(["--summary", str(summary_path), "--output-doc", str(tmp_path / "evidence.md")])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert payload["status"] == "invalid_input"


def test_no_browser_server_model_or_api_call(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    report = build_playwright_smoke_evidence_report(copy.deepcopy(_successful_summary()))

    assert report["passed"] is True
