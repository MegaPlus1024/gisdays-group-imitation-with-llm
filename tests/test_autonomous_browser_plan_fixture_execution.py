from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_plan_fixture_execution import (
    EXECUTION_SUMMARY_KEY,
    NORMALIZED_PLAN_KEY,
    PLAN_VALIDATION_KEY,
    SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_plan_fixture_execution,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan.example.json"
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan_fixture_execution.example.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_plan_fixture_execution.py"


def _load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _example_plan(**overrides: Any) -> dict[str, Any]:
    plan = _load_plan(PLAN_PATH)
    plan.update(overrides)
    return plan


def _runtime_trace_events(summary: dict[str, Any]) -> list[str]:
    return [event["event"] for event in summary["runtime_trace"]]


def test_valid_example_plan_executes_successfully_in_fixture_mode() -> None:
    summary = run_autonomous_browser_plan_fixture_execution(PLAN_PATH, repo_root=PROJECT_ROOT)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["no_runtime_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["plan_id"] == "browser_policy_research_plan_v1"
    assert summary["validation_status"] == "accepted"
    assert summary["execution_status"] == "fixture_executed"
    assert summary["actions_planned"] == 3
    assert summary["actions_attempted"] == 3
    assert summary["actions_succeeded"] == 3
    assert summary["actions_failed"] == 0
    assert summary["expected_results_total"] == 3
    assert summary["expected_results_passed"] == 3
    assert summary["expected_results_failed"] == 0
    assert summary["shared_state_keys"] == [
        EXECUTION_SUMMARY_KEY,
        NORMALIZED_PLAN_KEY,
        PLAN_VALIDATION_KEY,
    ]
    assert summary["stop_reason"] == "all_tasks_terminal"
    assert _runtime_trace_events(summary) == [
        "plan_loaded",
        "plan_validated",
        "task_submitted",
        "task_scheduled",
        "fixture_execution_started",
        "action_executed",
        "expected_result_checked",
        "action_executed",
        "expected_result_checked",
        "action_executed",
        "expected_result_checked",
        "shared_state_updated",
        "runtime_stopped",
    ]
    assert summary["runtime_trace"][0]["plan_id"] == "browser_policy_research_plan_v1"
    assert "C:\\" not in json.dumps(summary)


def test_invalid_plan_returns_rejected_summary_and_does_not_execute_actions() -> None:
    plan = _example_plan()
    plan["actions"][0]["action_name"] = "browser_not_real"
    summary = run_autonomous_browser_plan_fixture_execution(plan, repo_root=PROJECT_ROOT)

    assert summary["status"] == "rejected"
    assert summary["validation_status"] == "rejected"
    assert summary["error_code"] == "unknown_browser_action"
    assert summary["execution_status"] == "validation_rejected"
    assert _runtime_trace_events(summary) == [
        "plan_loaded",
        "plan_validated",
        "task_submitted",
        "task_scheduled",
        "execution_skipped_by_design",
        "shared_state_updated",
        "runtime_stopped",
    ]
    assert "fixture_execution_started" not in _runtime_trace_events(summary)


def test_missing_expected_text_produces_structured_failure() -> None:
    plan = _example_plan()
    del plan["actions"][0]["expected_text"]
    summary = run_autonomous_browser_plan_fixture_execution(plan, repo_root=PROJECT_ROOT)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "missing_expected_text"
    assert summary["execution_status"] == "execution_failed"
    assert summary["actions_attempted"] == 0
    assert summary["actions_failed"] == 0
    assert _runtime_trace_events(summary) == [
        "plan_loaded",
        "plan_validated",
        "task_submitted",
        "task_scheduled",
        "fixture_execution_started",
        "shared_state_updated",
        "runtime_stopped",
    ]


def test_missing_fixture_target_produces_structured_failure() -> None:
    plan = _example_plan()
    plan["actions"][0]["parameters"]["url"] = "https://local.intranet/missing"
    summary = run_autonomous_browser_plan_fixture_execution(plan, repo_root=PROJECT_ROOT)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "fixture_resolution_failed"
    assert summary["execution_status"] == "execution_failed"
    assert summary["actions_attempted"] == 1
    assert summary["actions_failed"] == 1
    assert summary["expected_results_passed"] == 0
    assert summary["expected_results_failed"] == 1
    assert "fixture_execution_started" in _runtime_trace_events(summary)


def test_trace_event_order_is_deterministic() -> None:
    first = _runtime_trace_events(run_autonomous_browser_plan_fixture_execution(PLAN_PATH, repo_root=PROJECT_ROOT))
    second = _runtime_trace_events(run_autonomous_browser_plan_fixture_execution(PLAN_PATH, repo_root=PROJECT_ROOT))

    assert first == second


def test_shared_state_keys_present_and_no_absolute_paths_in_output() -> None:
    summary = run_autonomous_browser_plan_fixture_execution(PLAN_PATH, repo_root=PROJECT_ROOT)
    payload = json.dumps(summary)

    assert summary["shared_state_keys"] == [
        EXECUTION_SUMMARY_KEY,
        NORMALIZED_PLAN_KEY,
        PLAN_VALIDATION_KEY,
    ]
    assert str(PROJECT_ROOT) not in payload
    assert PROJECT_ROOT.as_posix() not in payload


def test_secret_like_value_is_redacted_in_failure_diagnostics() -> None:
    plan = _example_plan()
    plan["actions"][0]["parameters"]["url"] = "https://user:supersecret@local.intranet/"
    summary = run_autonomous_browser_plan_fixture_execution(plan, repo_root=PROJECT_ROOT)
    payload = json.dumps(summary)

    assert summary["status"] == "rejected"
    assert "supersecret" not in payload
    assert "user" not in payload


def test_cli_success_exits_zero_and_prints_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")


def test_cli_failure_exits_nonzero_and_prints_structured_json() -> None:
    artifacts_root = PROJECT_ROOT / "artifacts" / "browser_plan_fixture_execution_tests"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    plan_path = artifacts_root / "invalid_fixture_plan.json"
    config_path = artifacts_root / "invalid_fixture_config.json"
    try:
        plan = _example_plan()
        del plan["actions"][0]["expected_text"]
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "autonomous_browser_plan_fixture_execution_config_v1",
                    "no_runtime_execution": True,
                    "plan_path": "artifacts/browser_plan_fixture_execution_tests/invalid_fixture_plan.json",
                    "runtime_id": "browser_plan_fixture_runtime_v1",
                    "agent_id": "browser_plan_executor",
                    "task_id": "browser_plan_fixture_task_v1",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--config", str(config_path)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(completed.stdout)

        assert completed.returncode != 0
        assert payload["status"] == "failed"
        assert payload["error_code"] in {"missing_expected_text", "config_validation_failed"}
    finally:
        if config_path.exists():
            config_path.unlink()
        if plan_path.exists():
            plan_path.unlink()
        if artifacts_root.exists():
            try:
                artifacts_root.rmdir()
            except OSError:
                pass


def test_fixture_execution_imports_without_playwright_or_browser_runtime() -> None:
    assert "playwright" not in sys.modules
    assert "selenium" not in sys.modules
    assert "llama_cpp" not in sys.modules


def test_fixture_execution_does_not_execute_runtime_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "http.server", "socketserver", "llama_cpp", "selenium")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_plan_fixture_execution(PLAN_PATH, repo_root=PROJECT_ROOT)

    assert summary["status"] == "succeeded"
