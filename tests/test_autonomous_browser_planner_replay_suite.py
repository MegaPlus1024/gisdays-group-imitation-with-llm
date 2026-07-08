from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_planner_replay_suite import (
    REPLAY_SUITE_CONFIG_SCHEMA_VERSION,
    REPLAY_SUITE_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_planner_replay_suite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_replay_suite.example.json"
SAFE_PLAN_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_candidate.example.json"
CLI_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_planner_replay_suite.py"
ARTIFACT_TEST_DIR = PROJECT_ROOT / "artifacts" / "browser_planner_replay_suite_tests"


def _write_config(
    path: Path,
    *,
    candidate_plans: list[str],
    replay_mode: str = "dry_run",
    output_dir: str = "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite_tests",
    expected_min_accepted: int = 1,
    expected_min_fixture_success: int = 0,
) -> None:
    payload = {
        "schema_version": REPLAY_SUITE_CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_planner_replay_suite_test_v1",
        "candidate_plans": candidate_plans,
        "replay_mode": replay_mode,
        "output_dir": output_dir,
        "expected_min_accepted": expected_min_accepted,
        "expected_min_fixture_success": expected_min_fixture_success,
        "limitations": ["test fixture"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bad_plan() -> dict[str, Any]:
    candidate = _load_plan(SAFE_PLAN_PATH)
    candidate["actions"][0]["action_name"] = "browser_not_real"
    return candidate


def test_suite_dry_run_with_one_safe_candidate_succeeds(tmp_path: Path) -> None:
    config_path = tmp_path / "suite.json"
    _write_config(config_path, candidate_plans=["configs/autonomous_runtime/browser_planner_candidate.example.json"])

    summary = run_autonomous_browser_planner_replay_suite(config_path, repo_root=PROJECT_ROOT)

    assert summary["schema_version"] == REPLAY_SUITE_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["replay_mode"] == "dry_run"
    assert summary["candidates_total"] == 1
    assert summary["candidates_accepted"] == 1
    assert summary["dry_runs_succeeded"] == 1
    assert summary["fixture_runs_succeeded"] == 0
    assert summary["actions_attempted_total"] == 0
    assert summary["candidate_summaries"][0]["validation_status"] == "accepted"


def test_suite_fixture_execution_with_one_safe_candidate_succeeds(tmp_path: Path) -> None:
    config_path = tmp_path / "suite.json"
    _write_config(
        config_path,
        candidate_plans=["configs/autonomous_runtime/browser_planner_candidate.example.json"],
        replay_mode="fixture_execution",
        expected_min_fixture_success=1,
    )

    summary = run_autonomous_browser_planner_replay_suite(config_path, repo_root=PROJECT_ROOT, execute_fixture=True)

    assert summary["status"] == "succeeded"
    assert summary["replay_mode"] == "fixture_execution"
    assert summary["fixture_runs_succeeded"] == 1
    assert summary["actions_attempted_total"] == 3
    assert summary["expected_results_passed"] == 3


def test_rejected_candidate_is_counted_and_does_not_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    ARTIFACT_TEST_DIR.mkdir(parents=True, exist_ok=True)
    bad_plan_path = ARTIFACT_TEST_DIR / "bad_candidate.json"
    bad_plan_path.write_text(json.dumps(_bad_plan(), ensure_ascii=False, indent=2), encoding="utf-8")
    config = {
        "schema_version": REPLAY_SUITE_CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_planner_replay_suite_test_v1",
        "candidate_plans": ["artifacts/browser_planner_replay_suite_tests/bad_candidate.json"],
        "replay_mode": "fixture_execution",
        "output_dir": "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite_tests",
        "expected_min_accepted": 0,
        "expected_min_fixture_success": 0,
        "limitations": ["test fixture"],
    }

    called = False

    def forbidden(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("fixture execution must not run for rejected candidates")

    monkeypatch.setattr(
        "src.agent.autonomous_browser_planner_packet.run_autonomous_browser_plan_fixture_execution",
        forbidden,
    )

    summary = run_autonomous_browser_planner_replay_suite(config, repo_root=PROJECT_ROOT, execute_fixture=True)

    assert summary["status"] in {"completed_with_failures", "failed"}
    assert summary["candidates_rejected"] == 1
    assert summary["fixture_runs_failed"] == 1
    assert called is False


def test_missing_candidate_is_structured_failure(tmp_path: Path) -> None:
    config_path = tmp_path / "suite.json"
    _write_config(config_path, candidate_plans=["configs/autonomous_runtime/missing_candidate.json"])

    summary = run_autonomous_browser_planner_replay_suite(config_path, repo_root=PROJECT_ROOT)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "missing_candidate_file"
    assert summary["candidate_summaries"][0]["error_code"] == "missing_candidate_file"


def test_unsafe_candidate_path_is_rejected() -> None:
    config = {
        "schema_version": REPLAY_SUITE_CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_planner_replay_suite_test_v1",
        "candidate_plans": [r"C:\Users\m\Documents\secret.json"],
        "replay_mode": "dry_run",
        "output_dir": "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite_tests",
        "expected_min_accepted": 1,
        "expected_min_fixture_success": 0,
        "limitations": ["test fixture"],
    }

    summary = run_autonomous_browser_planner_replay_suite(config, repo_root=PROJECT_ROOT)

    assert summary["status"] == "failed"
    assert summary["candidate_summaries"][0]["error_code"] == "unsafe_candidate_path"


def test_aggregate_counts_match_candidate_summaries() -> None:
    config = {
        "schema_version": REPLAY_SUITE_CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_planner_replay_suite_test_v1",
        "candidate_plans": [
            "configs/autonomous_runtime/browser_planner_candidate.example.json",
            "artifacts/browser_planner_replay_suite_tests/bad_candidate.json",
        ],
        "replay_mode": "dry_run",
        "output_dir": "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite_tests",
        "expected_min_accepted": 1,
        "expected_min_fixture_success": 0,
        "limitations": ["test fixture"],
    }

    summary = run_autonomous_browser_planner_replay_suite(config, repo_root=PROJECT_ROOT)

    assert summary["candidates_total"] == len(summary["candidate_summaries"])
    assert summary["candidates_accepted"] + summary["candidates_rejected"] == summary["candidates_total"]
    assert summary["dry_runs_succeeded"] + summary["dry_runs_failed"] == summary["candidates_total"]


def test_cli_dry_run_success_exits_zero_and_prints_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "succeeded"
    assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")
    assert (PROJECT_ROOT / "artifacts" / "autonomous_runtime_summaries" / "browser_planner_replay_suite" / "autonomous_browser_planner_replay_suite_summary.json").exists()


def test_cli_fixture_success_exits_zero_and_prints_json(tmp_path: Path) -> None:
    config_path = tmp_path / "suite.json"
    _write_config(
        config_path,
        candidate_plans=["configs/autonomous_runtime/browser_planner_candidate.example.json"],
        replay_mode="fixture_execution",
        expected_min_fixture_success=1,
    )

    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(config_path), "--execute-fixture"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "succeeded"
    assert payload["replay_mode"] == "fixture_execution"


def test_cli_invalid_suite_exits_nonzero_with_structured_json(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid_suite.json"
    config_path.write_text(json.dumps({"schema_version": "wrong"}, ensure_ascii=False, indent=2), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(config_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode != 0
    assert payload["status"] == "failed"
    assert payload["schema_version"] == REPLAY_SUITE_SUMMARY_SCHEMA_VERSION


def test_no_absolute_local_paths_in_summary() -> None:
    config = {
        "schema_version": REPLAY_SUITE_CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_planner_replay_suite_test_v1",
        "candidate_plans": ["configs/autonomous_runtime/browser_planner_candidate.example.json"],
        "replay_mode": "dry_run",
        "output_dir": "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite_tests",
        "expected_min_accepted": 1,
        "expected_min_fixture_success": 0,
        "limitations": ["test fixture"],
    }

    summary = run_autonomous_browser_planner_replay_suite(config, repo_root=PROJECT_ROOT)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded


def test_no_secret_values_in_output() -> None:
    secret_plan = _load_plan(SAFE_PLAN_PATH)
    secret_plan["actions"][0]["parameters"]["query"] = "api_key=supersecret"
    candidate_path = ARTIFACT_TEST_DIR / "secret_candidate.json"
    candidate_path.write_text(json.dumps(secret_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    config = {
        "schema_version": REPLAY_SUITE_CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_planner_replay_suite_test_v1",
        "candidate_plans": ["artifacts/browser_planner_replay_suite_tests/secret_candidate.json"],
        "replay_mode": "dry_run",
        "output_dir": "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite_tests",
        "expected_min_accepted": 0,
        "expected_min_fixture_success": 0,
        "limitations": ["test fixture"],
    }

    summary = run_autonomous_browser_planner_replay_suite(config, repo_root=PROJECT_ROOT)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "supersecret" not in encoded


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_planner_replay_suite(CONFIG_PATH, repo_root=PROJECT_ROOT)

    assert summary["status"] == "succeeded"
