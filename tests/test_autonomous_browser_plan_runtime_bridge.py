from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_plan_runtime_bridge import (
    DRY_RUN_SCHEMA_VERSION,
    DRY_RUN_SUMMARY_KEY,
    NORMALIZED_PLAN_KEY,
    VALIDATION_RESULT_KEY,
    run_autonomous_browser_plan_dry_run,
)
from src.agent.autonomous_browser_plan_validation import (
    VALIDATION_RESULT_SCHEMA_VERSION,
    validate_autonomous_browser_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan.example.json"
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan_dry_run.example.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_plan_dry_run.py"


def _load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_invalid_plan() -> dict[str, Any]:
    plan = _load_plan(PLAN_PATH)
    plan["actions"][0]["action_name"] = "browser_not_real"
    return plan


def test_valid_plan_produces_dry_run_summary() -> None:
    summary = run_autonomous_browser_plan_dry_run(PLAN_PATH, repo_root=PROJECT_ROOT)

    assert summary["schema_version"] == DRY_RUN_SCHEMA_VERSION
    assert summary["status"] == "accepted"
    assert summary["error_code"] is None
    assert summary["no_runtime_execution"] is True
    assert summary["plan_id"] == "browser_policy_research_plan_v1"
    assert summary["validation_status"] == "accepted"
    assert summary["actions_total"] == 3
    assert summary["normalized_actions_total"] == 3
    assert summary["runtime_task_count"] == 1
    assert summary["execution_status"] == "skipped_by_design"
    assert summary["stop_reason"] == "all_tasks_terminal"
    assert summary["shared_state_keys"] == [
        DRY_RUN_SUMMARY_KEY,
        NORMALIZED_PLAN_KEY,
        VALIDATION_RESULT_KEY,
    ]
    assert [event["event"] for event in summary["runtime_trace"]] == [
        "plan_loaded",
        "plan_validated",
        "task_submitted",
        "task_scheduled",
        "execution_skipped_by_design",
        "shared_state_updated",
        "runtime_stopped",
    ]
    assert summary["runtime_trace"][0]["plan_id"] == "browser_policy_research_plan_v1"
    assert summary["validation_result"]["schema_version"] == VALIDATION_RESULT_SCHEMA_VERSION
    assert summary["validation_result"]["normalized_plan"]["actions"][0]["step_id"] == "open_home"
    assert summary["limitations"]
    assert "C:\\" not in json.dumps(summary)


def test_invalid_plan_is_rejected_with_structured_summary() -> None:
    summary = run_autonomous_browser_plan_dry_run(_make_invalid_plan(), repo_root=PROJECT_ROOT)

    assert summary["schema_version"] == DRY_RUN_SCHEMA_VERSION
    assert summary["status"] == "rejected"
    assert summary["validation_status"] == "rejected"
    assert summary["error_code"] == "unknown_browser_action"
    assert summary["execution_status"] == "skipped_by_design"
    assert summary["stop_reason"] == "validation_rejected"
    assert summary["runtime_trace"][0]["event"] == "plan_loaded"
    assert summary["runtime_trace"][1]["event"] == "plan_validated"
    assert summary["runtime_trace"][2]["event"] == "task_submitted"
    assert summary["runtime_trace"][3]["event"] == "task_scheduled"
    assert summary["runtime_trace"][4]["event"] == "plan_rejected"
    assert summary["runtime_trace"][5]["event"] == "execution_skipped_by_design"
    assert "normalized_plan" not in summary["validation_result"]


def test_secret_like_values_are_redacted_from_output() -> None:
    plan = _make_invalid_plan()
    plan["actions"][0]["parameters"]["url"] = "https://user:supersecret@local.intranet/"
    summary = run_autonomous_browser_plan_dry_run(plan, repo_root=PROJECT_ROOT)
    payload = json.dumps(summary)

    assert summary["status"] == "rejected"
    assert "supersecret" not in payload
    assert "user" not in payload


def test_local_absolute_paths_do_not_appear_in_output() -> None:
    summary = run_autonomous_browser_plan_dry_run(PLAN_PATH, repo_root=PROJECT_ROOT)
    payload = json.dumps(summary)

    assert str(PROJECT_ROOT) not in payload
    assert PROJECT_ROOT.as_posix() not in payload


def test_runtime_trace_order_is_deterministic() -> None:
    summary_one = run_autonomous_browser_plan_dry_run(PLAN_PATH, repo_root=PROJECT_ROOT)
    summary_two = run_autonomous_browser_plan_dry_run(PLAN_PATH, repo_root=PROJECT_ROOT)

    trace_one = [event["event"] for event in summary_one["runtime_trace"]]
    trace_two = [event["event"] for event in summary_two["runtime_trace"]]

    assert trace_one == trace_two


def test_cli_success_exits_zero_and_prints_compact_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["schema_version"] == DRY_RUN_SCHEMA_VERSION
    assert payload["status"] == "accepted"
    assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")


def test_cli_rejects_invalid_plan_with_nonzero_exit() -> None:
    artifacts_root = PROJECT_ROOT / "artifacts" / "browser_plan_dry_run_tests"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    plan_path = artifacts_root / "invalid_plan.json"
    config_path = artifacts_root / "invalid_plan_config.json"
    try:
        plan_path.write_text(json.dumps(_make_invalid_plan(), ensure_ascii=False, indent=2), encoding="utf-8")
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": "autonomous_browser_plan_dry_run_config_v1",
                    "no_runtime_execution": True,
                    "plan_path": "artifacts/browser_plan_dry_run_tests/invalid_plan.json",
                    "runtime_id": "browser_plan_dry_run_runtime_v1",
                    "agent_id": "browser_plan_planner",
                    "task_id": "browser_plan_task_v1",
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
        assert payload["status"] == "rejected"
        assert payload["error_code"] in {"unknown_browser_action", "config_validation_failed"}
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


def test_runtime_bridge_imports_without_playwright_or_browser_runtime() -> None:
    assert "playwright" not in sys.modules
    assert "selenium" not in sys.modules
    assert "llama_cpp" not in sys.modules


def test_runtime_bridge_does_not_execute_runtime_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "http.server", "socketserver", "llama_cpp", "selenium")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_plan_dry_run(PLAN_PATH, repo_root=PROJECT_ROOT)

    assert summary["status"] == "accepted"
