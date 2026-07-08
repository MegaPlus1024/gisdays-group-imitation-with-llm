from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from src.agent.autonomous_browser_scenario_suite import load_autonomous_browser_scenario_suite
from src.agent.autonomous_runtime_browser_suite_integration import run_autonomous_browser_suite_task


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_scenario_suite.example.json"


def test_browser_suite_task_bridge_produces_offline_runtime_summary() -> None:
    summary = run_autonomous_browser_suite_task(SUITE_PATH, repo_root=PROJECT_ROOT)

    assert summary["schema_version"] == "autonomous_runtime_browser_suite_integration_summary_v1"
    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["no_runtime_execution"] is True
    assert summary["runtime_task_count"] == 1
    assert summary["browser_suite_status"] == "passed"
    assert summary["scenarios_attempted"] == 4
    assert summary["scenarios_succeeded"] == 4
    assert summary["scenarios_failed"] == 0
    assert summary["actions_attempted"] == 30
    assert summary["actions_succeeded"] == 30
    assert summary["actions_failed"] == 0
    assert summary["expected_results_total"] == 18
    assert summary["expected_results_passed"] == 18
    assert summary["expected_results_failed"] == 0
    assert summary["required_actions_missing"] == []
    assert summary["stop_reason"] == "all_tasks_terminal"
    assert summary["runtime_trace_event_count"] == 7
    assert [event["event"] for event in summary["runtime_trace"]] == [
        "task_submitted",
        "task_scheduled",
        "task_executed",
        "browser_suite_completed",
        "task_verified",
        "shared_state_updated",
        "runtime_stopped",
    ]
    assert summary["runtime_trace"][0]["status"] == "pending"
    assert summary["runtime_trace"][4]["status"] == "succeeded"
    assert summary["runtime_trace"][3]["browser_suite_status"] == "passed"
    assert summary["task_statuses"] == {"browser_suite_task": "completed"}
    assert summary["shared_state_keys"] == ["browser_suite:last_result"]
    assert summary["required_actions_covered"] == [
        "browser_click",
        "browser_extract_text",
        "browser_fill",
        "browser_open_url",
        "browser_search",
        "browser_snapshot",
        "browser_submit",
        "browser_wait",
    ]
    assert summary["shared_state_updates"][0]["update_type"] == "task_submitted"
    assert summary["shared_state_updates"][-1]["update_type"] == "task_completed"
    assert summary["runtime_summary"]["task_counts"]["completed"] == 1
    assert summary["runtime_summary"]["stop_reason"] == "all_tasks_terminal"
    assert summary["browser_suite_summary"]["schema_version"] == "autonomous_browser_scenario_suite_summary_v1"
    assert summary["browser_suite_summary"]["scenario_count"] == 4
    assert str(PROJECT_ROOT) not in json.dumps(summary)
    assert "C:\\" not in json.dumps(summary)


def test_browser_suite_task_bridge_rejects_invalid_suite_without_traceback(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid_suite.json"
    invalid_path.write_text(
        json.dumps(
            {
                "schema_version": "autonomous_browser_scenario_suite_v1",
                "suite_id": "invalid_suite",
                "scenario_paths": [],
                "expected_min_passed_scenarios": 0,
                "expected_required_actions": ["browser_open_url"],
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = run_autonomous_browser_suite_task(invalid_path, repo_root=PROJECT_ROOT)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "invalid_suite_config"
    assert summary["runtime_task_count"] == 0
    assert summary["browser_suite_status"] == "failed"
    assert summary["shared_state_updates"] == []


def test_browser_suite_task_bridge_propagates_required_action_failures(tmp_path: Path) -> None:
    payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    payload["expected_required_actions"] = ["browser_open_url", "browser_nonexistent_fixture_action"]
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    summary = run_autonomous_browser_suite_task(suite_path, repo_root=PROJECT_ROOT)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "required_actions_missing"
    assert summary["browser_suite_status"] == "failed"
    assert summary["required_actions_missing"] == ["browser_nonexistent_fixture_action"]
    assert summary["browser_suite_summary"]["required_actions_missing"] == ["browser_nonexistent_fixture_action"]
    assert summary["stop_reason"] == "all_tasks_terminal"
    assert summary["runtime_trace_event_count"] == 7
    assert [event["event"] for event in summary["runtime_trace"]] == [
        "task_submitted",
        "task_scheduled",
        "task_executed",
        "browser_suite_failed",
        "task_verified",
        "shared_state_updated",
        "runtime_stopped",
    ]
    assert summary["runtime_trace"][3]["error_code"] == "required_actions_missing"
    assert summary["runtime_trace"][4]["status"] == "failed"
    assert summary["task_statuses"] == {"browser_suite_task": "failed"}
    assert summary["shared_state_keys"] == ["browser_suite:last_result"]


def test_bridge_module_imports_without_playwright_backend() -> None:
    importlib.import_module("src.agent.autonomous_runtime_browser_suite_integration")

    assert "playwright" not in sys.modules


def test_browser_suite_task_bridge_does_not_add_mail_git_calendar_actions() -> None:
    summary = run_autonomous_browser_suite_task(load_autonomous_browser_scenario_suite(SUITE_PATH), repo_root=PROJECT_ROOT)

    assert summary["status"] == "succeeded"
    assert not any(name.startswith(("mail_", "git_", "calendar_", "email_")) for name in summary["required_actions_covered"])
