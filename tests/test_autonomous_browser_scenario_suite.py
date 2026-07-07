from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_scenario_suite import (
    AutonomousBrowserScenarioSuiteValidationError,
    load_autonomous_browser_scenario_suite,
    run_autonomous_browser_scenario_suite,
)
from src.agent.autonomous_runtime_scenarios import load_autonomous_runtime_scenario, run_autonomous_runtime_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_scenario_suite.example.json"
POLICY_SCENARIO_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_intranet_policy_research.example.json"
PORTAL_SCENARIO_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_portal_approval_check.example.json"
RUNNER_PATH = PROJECT_ROOT / "scripts/run_autonomous_browser_scenario_suite.py"


def _suite_payload() -> dict[str, Any]:
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def test_suite_config_loads() -> None:
    suite = load_autonomous_browser_scenario_suite(SUITE_PATH)

    assert suite.suite_id == "browser_autonomous_runtime_suite_v1"
    assert len(suite.scenario_paths) == 4
    assert suite.expected_min_passed_scenarios == 4


def test_suite_rejects_unsafe_absolute_scenario_path(tmp_path: Path) -> None:
    payload = _suite_payload()
    payload["scenario_paths"] = [str(tmp_path / "scenario.json")]

    with pytest.raises(AutonomousBrowserScenarioSuiteValidationError, match="safe relative path"):
        load_autonomous_browser_scenario_suite(_write_payload(tmp_path, payload))


def test_suite_rejects_missing_scenario_paths(tmp_path: Path) -> None:
    payload = _suite_payload()
    payload["scenario_paths"] = []

    with pytest.raises(AutonomousBrowserScenarioSuiteValidationError, match="scenario_paths"):
        load_autonomous_browser_scenario_suite(_write_payload(tmp_path, payload))


def test_policy_research_scenario_loads_and_completes() -> None:
    scenario = load_autonomous_runtime_scenario(POLICY_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert summary["expected_results_passed"] is True
    assert summary["task_counts"]["completed"] == 8
    assert set(summary["browser_coverage"]["actions_executed"]) == {
        "browser_click",
        "browser_extract_text",
        "browser_open_url",
        "browser_search",
        "browser_snapshot",
    }


def test_portal_approval_scenario_loads_and_completes() -> None:
    scenario = load_autonomous_runtime_scenario(PORTAL_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert summary["expected_results_passed"] is True
    assert summary["task_counts"]["completed"] == 8
    assert summary["browser_session_summaries"]["portal_checker_session"]["current_url"] == "https://portal.local/portal/status"


def test_suite_runs_all_scenarios() -> None:
    suite = load_autonomous_browser_scenario_suite(SUITE_PATH)
    result = run_autonomous_browser_scenario_suite(suite, repo_root=PROJECT_ROOT)

    assert len(result.scenario_results) == 4
    assert {item["status"] for item in result.scenario_results} == {"passed"}


def test_suite_summary_reports_scenario_count_four() -> None:
    summary = run_autonomous_browser_scenario_suite(
        load_autonomous_browser_scenario_suite(SUITE_PATH),
        repo_root=PROJECT_ROOT,
    ).to_summary()

    assert summary["scenario_count"] == 4


def test_suite_summary_reports_all_scenarios_passed() -> None:
    summary = run_autonomous_browser_scenario_suite(
        load_autonomous_browser_scenario_suite(SUITE_PATH),
        repo_root=PROJECT_ROOT,
    ).to_summary()

    assert summary["scenarios_passed"] == 4
    assert summary["scenarios_failed"] == 0
    assert summary["expected_min_passed_scenarios_met"] is True


def test_suite_required_action_coverage_includes_all_browser_actions() -> None:
    summary = run_autonomous_browser_scenario_suite(
        load_autonomous_browser_scenario_suite(SUITE_PATH),
        repo_root=PROJECT_ROOT,
    ).to_summary()

    assert set(summary["required_actions_covered"]) == {
        "browser_open_url",
        "browser_click",
        "browser_extract_text",
        "browser_fill",
        "browser_submit",
        "browser_wait",
        "browser_search",
        "browser_snapshot",
    }
    assert summary["required_actions_missing"] == []
    assert summary["overall_action_coverage_ratio"] == 1.0


def test_suite_reports_missing_required_action(tmp_path: Path) -> None:
    payload = _suite_payload()
    payload["expected_required_actions"].append("browser_nonexistent_fixture_action")
    suite = load_autonomous_browser_scenario_suite(_write_payload(tmp_path, payload))
    summary = run_autonomous_browser_scenario_suite(suite, repo_root=PROJECT_ROOT).to_summary()

    assert summary["required_actions_missing"] == ["browser_nonexistent_fixture_action"]
    assert summary["overall_action_coverage_ratio"] < 1.0


def test_suite_captures_scenario_validation_failure(tmp_path: Path) -> None:
    payload = _suite_payload()
    payload["scenario_paths"] = ["configs/autonomous_runtime/missing_scenario.example.json"]
    payload["expected_min_passed_scenarios"] = 0
    suite = load_autonomous_browser_scenario_suite(_write_payload(tmp_path, payload))
    summary = run_autonomous_browser_scenario_suite(suite, repo_root=PROJECT_ROOT).to_summary()

    assert summary["scenarios_failed"] == 1
    assert summary["failure_reasons"][0]["failure_reason"] == "scenario_validation_failed"
    assert "could not be read" in summary["failure_reasons"][0]["error"]


def test_suite_cli_dry_run_writes_json_summary_to_temp_output(tmp_path: Path) -> None:
    output_name = "browser_suite.summary.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--suite",
            str(SUITE_PATH),
            "--output",
            output_name,
            "--dry-run",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    summary = json.loads((tmp_path / output_name).read_text(encoding="utf-8"))
    assert summary["schema_version"] == "autonomous_browser_scenario_suite_summary_v1"
    assert summary["dry_run"] is True
    assert summary["no_runtime_execution"] is True


def test_suite_cli_output_has_no_absolute_local_paths(tmp_path: Path) -> None:
    output_name = "browser_suite.summary.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--suite",
            str(SUITE_PATH),
            "--output",
            output_name,
            "--dry-run",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output_text = (tmp_path / output_name).read_text(encoding="utf-8")
    assert str(PROJECT_ROOT) not in output_text
    assert "C:\\" not in output_text


def test_suite_summary_is_json_serializable() -> None:
    summary = run_autonomous_browser_scenario_suite(
        load_autonomous_browser_scenario_suite(SUITE_PATH),
        repo_root=PROJECT_ROOT,
    ).to_summary()

    assert json.loads(json.dumps(summary))["schema_version"] == "autonomous_browser_scenario_suite_summary_v1"


def test_suite_does_not_accept_mail_git_calendar_required_actions(tmp_path: Path) -> None:
    payload = _suite_payload()
    payload["expected_required_actions"] = ["browser_open_url", "git_commit"]

    with pytest.raises(AutonomousBrowserScenarioSuiteValidationError, match="browser actions only"):
        load_autonomous_browser_scenario_suite(_write_payload(tmp_path, payload))


def test_suite_makes_no_real_browser_playwright_http_api_or_model_calls() -> None:
    summary = run_autonomous_browser_scenario_suite(
        load_autonomous_browser_scenario_suite(SUITE_PATH),
        repo_root=PROJECT_ROOT,
    ).to_summary()

    assert summary["no_runtime_execution"] is True
    for scenario in summary["scenario_summaries"]:
        assert scenario["no_runtime_execution"] is True
        for session in scenario["browser_sessions"].values():
            assert session["policy_flags"]["fixture_mode"] is True
            assert session["policy_flags"]["playwright_enabled"] is False
            assert session["policy_denials"] == 0
