from __future__ import annotations

import builtins
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_planner_output_ingestion import extract_autonomous_browser_plan_candidate
from src.agent.autonomous_browser_planner_output_ingestion_suite import (
    SUITE_CONFIG_SCHEMA_VERSION,
    SUITE_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_planner_output_ingestion_suite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_output_ingestion_suite.example.json"
VALID_OUTPUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "valid_candidate_output.txt"
INVALID_OUTPUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "invalid_candidate_output.txt"
CLI_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_planner_output_ingestion_suite.py"
ARTIFACT_TEST_DIR = PROJECT_ROOT / "artifacts" / "browser_planner_output_ingestion_suite_tests"


def _suite_config(
    captured_outputs: list[str],
    *,
    replay_mode: str = "dry_run",
    output_dir: str = "artifacts/browser_planner_output_ingestion_suite_tests",
    expected_min_ingested: int = 1,
    expected_max_rejected: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": SUITE_CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_planner_output_ingestion_suite_test_v1",
        "captured_outputs": captured_outputs,
        "replay_mode": replay_mode,
        "output_dir": output_dir,
        "expected_min_ingested": expected_min_ingested,
        "expected_max_rejected": expected_max_rejected,
        "limitations": ["test fixture"],
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_json_bom(path: Path, payload: Any) -> None:
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def _cleanup_artifacts() -> None:
    shutil.rmtree(ARTIFACT_TEST_DIR, ignore_errors=True)
    shutil.rmtree(PROJECT_ROOT / "artifacts" / "autonomous_runtime_summaries" / "browser_planner_output_ingestion_suite", ignore_errors=True)


def test_suite_dry_run_with_one_valid_captured_output_succeeds(tmp_path: Path) -> None:
    repo_root = tmp_path
    fixture_path = repo_root / "tests" / "fixtures" / "browser_planner_outputs"
    fixture_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VALID_OUTPUT_PATH, fixture_path / "valid_candidate_output.txt")

    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(["tests/fixtures/browser_planner_outputs/valid_candidate_output.txt"], output_dir="artifacts/browser_planner_output_ingestion_suite_tests"),
        repo_root=repo_root,
    )

    assert summary["schema_version"] == SUITE_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["replay_mode"] == "dry_run"
    assert summary["outputs_total"] == 1
    assert summary["outputs_ingested"] == 1
    assert summary["outputs_rejected"] == 0
    assert summary["dry_runs_succeeded"] == 1
    assert summary["fixture_runs_succeeded"] == 0
    assert summary["actions_attempted_total"] == 0
    assert summary["output_summaries"][0]["status"] == "succeeded"


def test_suite_fixture_execution_with_one_valid_captured_output_succeeds(tmp_path: Path) -> None:
    try:
        summary = run_autonomous_browser_planner_output_ingestion_suite(
            _suite_config(
                ["tests/fixtures/browser_planner_outputs/valid_candidate_output.txt"],
                replay_mode="fixture_execution",
                expected_min_ingested=1,
                expected_max_rejected=0,
                output_dir="artifacts/browser_planner_output_ingestion_suite_tests",
            ),
            repo_root=PROJECT_ROOT,
            execute_fixture=True,
        )

        assert summary["status"] == "succeeded"
        assert summary["replay_mode"] == "fixture_execution"
        assert summary["fixture_runs_succeeded"] == 1
        assert summary["actions_attempted_total"] == 3
        assert summary["expected_results_passed"] == 3
    finally:
        _cleanup_artifacts()


def test_invalid_captured_output_is_counted_as_rejected(tmp_path: Path) -> None:
    repo_root = tmp_path
    fixture_path = repo_root / "tests" / "fixtures" / "browser_planner_outputs"
    fixture_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INVALID_OUTPUT_PATH, fixture_path / "invalid_candidate_output.txt")

    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(
            ["tests/fixtures/browser_planner_outputs/invalid_candidate_output.txt"],
            expected_min_ingested=0,
            expected_max_rejected=1,
            output_dir="artifacts/browser_planner_output_ingestion_suite_tests",
        ),
        repo_root=repo_root,
    )

    assert summary["status"] == "completed_with_failures"
    assert summary["outputs_rejected"] == 1
    assert summary["output_summaries"][0]["status"] in {"rejected", "failed"}


def test_missing_captured_output_gives_structured_failure(tmp_path: Path) -> None:
    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(["tests/fixtures/browser_planner_outputs/missing_candidate_output.txt"], output_dir="artifacts/browser_planner_output_ingestion_suite_tests"),
        repo_root=tmp_path,
    )

    assert summary["status"] == "failed"
    assert summary["error_code"] == "missing_captured_output_file"
    assert summary["output_summaries"][0]["error_code"] == "missing_captured_output_file"


def test_unsafe_output_path_is_rejected() -> None:
    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(["../secret.txt"], output_dir="artifacts/browser_planner_output_ingestion_suite_tests"),
        repo_root=PROJECT_ROOT,
    )

    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"


def test_aggregate_counts_match_child_ingestion_summaries(tmp_path: Path) -> None:
    repo_root = tmp_path
    fixture_path = repo_root / "tests" / "fixtures" / "browser_planner_outputs"
    fixture_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VALID_OUTPUT_PATH, fixture_path / "valid_candidate_output.txt")
    shutil.copy2(INVALID_OUTPUT_PATH, fixture_path / "invalid_candidate_output.txt")

    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(
            [
                "tests/fixtures/browser_planner_outputs/valid_candidate_output.txt",
                "tests/fixtures/browser_planner_outputs/invalid_candidate_output.txt",
            ],
            expected_min_ingested=1,
            expected_max_rejected=1,
            output_dir="artifacts/browser_planner_output_ingestion_suite_tests",
        ),
        repo_root=repo_root,
    )

    child_summaries = [item["ingestion_summary"] for item in summary["output_summaries"]]
    assert summary["outputs_total"] == len(child_summaries)
    assert summary["outputs_ingested"] + summary["outputs_rejected"] == summary["outputs_total"]
    assert summary["actions_attempted_total"] == sum(int(item.get("actions_attempted", 0)) for item in child_summaries)
    assert summary["expected_results_total"] == sum(int(item.get("expected_results_total", 0)) for item in child_summaries)


def test_cli_dry_run_success_exits_zero_and_prints_compact_json() -> None:
    ARTIFACT_TEST_DIR.mkdir(parents=True, exist_ok=True)
    config_path = ARTIFACT_TEST_DIR / "suite.json"
    _write_json(
        config_path,
        _suite_config(
            ["tests/fixtures/browser_planner_outputs/valid_candidate_output.txt"],
            output_dir="artifacts/browser_planner_output_ingestion_suite_tests",
        ),
    )

    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(config_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    try:
        assert completed.returncode == 0
        assert payload["status"] == "succeeded"
        assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")
        assert (PROJECT_ROOT / "artifacts" / "browser_planner_output_ingestion_suite_tests" / "autonomous_browser_planner_output_ingestion_suite_summary.json").exists()
    finally:
        _cleanup_artifacts()


def test_cli_dry_run_accepts_bom_config() -> None:
    ARTIFACT_TEST_DIR.mkdir(parents=True, exist_ok=True)
    config_path = ARTIFACT_TEST_DIR / "suite_bom.json"
    _write_json_bom(
        config_path,
        _suite_config(
            ["tests/fixtures/browser_planner_outputs/valid_candidate_output.txt"],
            output_dir="artifacts/browser_planner_output_ingestion_suite_tests",
        ),
    )

    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(config_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    try:
        assert completed.returncode == 0
        assert payload["status"] == "succeeded"
    finally:
        _cleanup_artifacts()


def test_cli_fixture_success_exits_zero_and_prints_compact_json() -> None:
    ARTIFACT_TEST_DIR.mkdir(parents=True, exist_ok=True)
    config_path = ARTIFACT_TEST_DIR / "suite_fixture.json"
    _write_json(
        config_path,
        _suite_config(
            ["tests/fixtures/browser_planner_outputs/valid_candidate_output.txt"],
            replay_mode="fixture_execution",
            expected_min_ingested=1,
            expected_max_rejected=0,
            output_dir="artifacts/browser_planner_output_ingestion_suite_tests",
        ),
    )

    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(config_path), "--execute-fixture"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    try:
        assert completed.returncode == 0
        assert payload["status"] == "succeeded"
        assert payload["replay_mode"] == "fixture_execution"
        assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")
    finally:
        _cleanup_artifacts()


def test_cli_invalid_suite_exits_nonzero_with_structured_json(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid_suite.json"
    _write_json(config_path, {"schema_version": "wrong"})

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
    assert payload["schema_version"] == SUITE_SUMMARY_SCHEMA_VERSION


def test_secret_like_values_are_not_printed(tmp_path: Path) -> None:
    repo_root = tmp_path
    output_dir = repo_root / "artifacts" / "browser_planner_output_ingestion_suite_tests"
    source_path = repo_root / "secret_candidate_output.txt"
    plan = extract_autonomous_browser_plan_candidate(VALID_OUTPUT_PATH.read_text(encoding="utf-8"))["candidate_plan"]
    plan["actions"][0]["parameters"]["query"] = "api_key=supersecret"
    source_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(["secret_candidate_output.txt"], output_dir="artifacts/browser_planner_output_ingestion_suite_tests"),
        repo_root=repo_root,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "supersecret" not in encoded
    assert "api_key" in encoded


def test_no_absolute_local_paths_in_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    fixture_path = repo_root / "tests" / "fixtures" / "browser_planner_outputs"
    fixture_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VALID_OUTPUT_PATH, fixture_path / "valid_candidate_output.txt")

    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(["tests/fixtures/browser_planner_outputs/valid_candidate_output.txt"], output_dir="artifacts/browser_planner_output_ingestion_suite_tests"),
        repo_root=repo_root,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    fixture_path = repo_root / "tests" / "fixtures" / "browser_planner_outputs"
    fixture_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VALID_OUTPUT_PATH, fixture_path / "valid_candidate_output.txt")

    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_planner_output_ingestion_suite(
        _suite_config(["tests/fixtures/browser_planner_outputs/valid_candidate_output.txt"], output_dir="artifacts/browser_planner_output_ingestion_suite_tests"),
        repo_root=repo_root,
    )

    assert summary["status"] == "succeeded"
