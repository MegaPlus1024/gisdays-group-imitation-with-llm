from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_planner_output_ingestion import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    extract_autonomous_browser_plan_candidate,
    ingest_autonomous_browser_planner_output,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_output_ingestion.example.json"
VALID_OUTPUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "valid_candidate_output.txt"
INVALID_OUTPUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "invalid_candidate_output.txt"
CLI_PATH = PROJECT_ROOT / "scripts" / "ingest_autonomous_browser_planner_output.py"


def _candidate_plan() -> dict[str, Any]:
    return {
        "schema_version": "autonomous_browser_plan_v1",
        "plan_id": "browser_planner_candidate_generated_v1",
        "goal": "Review local fixture content and capture a bounded browser plan.",
        "scenario_id": "browser_intranet_policy_research",
        "max_actions": 4,
        "actions": [
            {
                "step_id": "open_home",
                "action_name": "browser_open_url",
                "parameters": {"url": "https://local.intranet/"},
                "expected_text": "Office Intranet",
            },
            {
                "step_id": "open_policy",
                "action_name": "browser_open_url",
                "parameters": {"url": "https://docs.local/docs/policy"},
                "expected_text": "Allowed activity",
            },
            {
                "step_id": "search_policy",
                "action_name": "browser_search",
                "parameters": {"query": "fixture-backed result"},
                "expected_text": "fixture-backed result",
            },
        ],
    }


def _config_for(source_output_path: str, *, output_dir: str = "artifacts/browser_planner_output_ingestion_tests") -> dict[str, Any]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "source_output_path": source_output_path,
        "output_dir": output_dir,
        "limitations": ["test fixture"],
    }


def _write_json_bom(path: Path, payload: Any) -> None:
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def test_plain_json_output_accepted(tmp_path: Path) -> None:
    path = tmp_path / "plain.txt"
    path.write_text(json.dumps(_candidate_plan(), ensure_ascii=False), encoding="utf-8")
    extracted = extract_autonomous_browser_plan_candidate(path.read_text(encoding="utf-8"))

    assert extracted["status"] == "accepted"
    assert extracted["extracted_plan_id"] == "browser_planner_candidate_generated_v1"


def test_markdown_fenced_json_accepted() -> None:
    extracted = extract_autonomous_browser_plan_candidate(VALID_OUTPUT_PATH.read_text(encoding="utf-8"))

    assert extracted["status"] == "accepted"
    assert extracted["candidate_plan"]["schema_version"] == "autonomous_browser_plan_v1"


def test_prose_before_and_after_json_accepted() -> None:
    text = "intro prose\n" + VALID_OUTPUT_PATH.read_text(encoding="utf-8") + "\noutro prose"
    extracted = extract_autonomous_browser_plan_candidate(text)

    assert extracted["status"] == "accepted"
    assert extracted["candidate_plan"]["plan_id"] == "browser_planner_candidate_example_v1"


def test_no_json_rejected() -> None:
    extracted = extract_autonomous_browser_plan_candidate(INVALID_OUTPUT_PATH.read_text(encoding="utf-8"))

    assert extracted["status"] == "rejected"
    assert extracted["error_code"] == "no_json_object_found"


def test_multiple_json_objects_rejected() -> None:
    text = json.dumps(_candidate_plan(), ensure_ascii=False) + "\n" + json.dumps(_candidate_plan(), ensure_ascii=False)
    extracted = extract_autonomous_browser_plan_candidate(text)

    assert extracted["status"] == "rejected"
    assert extracted["error_code"] == "multiple_json_objects_found"


def test_invalid_json_rejected() -> None:
    extracted = extract_autonomous_browser_plan_candidate('{"schema_version": "autonomous_browser_plan_v1", "plan_id": "x", }')

    assert extracted["status"] == "rejected"
    assert extracted["error_code"] == "json_parse_failed"


def test_wrong_schema_rejected() -> None:
    extracted = extract_autonomous_browser_plan_candidate('{"schema_version": "wrong", "plan_id": "x", "goal": "y", "scenario_id": "z", "max_actions": 1, "actions": []}')

    assert extracted["status"] == "rejected"
    assert extracted["error_code"] == "wrong_schema_version"


def test_external_url_rejected_through_validator(tmp_path: Path) -> None:
    plan = _candidate_plan()
    plan["actions"][0]["parameters"]["url"] = "https://example.com/"
    path = tmp_path / "external.txt"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    summary = ingest_autonomous_browser_planner_output(
        _config_for("external.txt"),
        repo_root=tmp_path,
    )

    assert summary["status"] == "rejected"
    assert summary["validation_status"] == "rejected"
    assert summary["error_code"] == "external_url_not_allowed"


def test_secret_like_value_rejected_and_redacted(tmp_path: Path) -> None:
    plan = _candidate_plan()
    plan["actions"][0]["parameters"]["query"] = "api_key=supersecret"
    path = tmp_path / "secret.txt"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    summary = ingest_autonomous_browser_planner_output(
        _config_for("secret.txt"),
        repo_root=tmp_path,
    )

    assert summary["status"] == "rejected"
    assert summary["validation_status"] == "rejected"
    diagnostics_text = json.dumps(summary, ensure_ascii=False)
    assert "supersecret" not in diagnostics_text
    assert "api_key" in diagnostics_text


def test_default_mode_does_dry_run_only() -> None:
    summary = ingest_autonomous_browser_planner_output(
        {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "source_output_path": "tests/fixtures/browser_planner_outputs/valid_candidate_output.txt",
            "output_dir": "artifacts/browser_planner_output_ingestion_tests",
            "limitations": ["test fixture"],
        },
        repo_root=PROJECT_ROOT,
    )

    assert summary["status"] == "succeeded"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "skipped"
    assert summary["actions_attempted"] == 0
    assert summary["no_runtime_execution"] is True


def test_execute_fixture_runs_fixture_backed_offline_execution() -> None:
    summary = ingest_autonomous_browser_planner_output(
        {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "source_output_path": "tests/fixtures/browser_planner_outputs/valid_candidate_output.txt",
            "output_dir": "artifacts/browser_planner_output_ingestion_tests",
            "limitations": ["test fixture"],
        },
        repo_root=PROJECT_ROOT,
        execute_fixture=True,
    )

    assert summary["status"] == "succeeded"
    assert summary["fixture_execution_status"] == "succeeded"
    assert summary["actions_attempted"] == 3
    assert summary["expected_results_passed"] == 3


def test_cli_success_exits_zero_and_prints_compact_json() -> None:
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


def test_ingestion_accepts_bom_raw_output(tmp_path: Path) -> None:
    repo_root = tmp_path
    fixture_dir = repo_root / "tests" / "fixtures" / "browser_planner_outputs"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    bom_output_path = fixture_dir / "bom_candidate_output.txt"
    bom_output_path.write_bytes(b"\xef\xbb\xbf" + VALID_OUTPUT_PATH.read_bytes())

    summary = ingest_autonomous_browser_planner_output(
        _config_for("tests/fixtures/browser_planner_outputs/bom_candidate_output.txt"),
        repo_root=repo_root,
    )

    assert summary["status"] == "succeeded"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "skipped"


def test_cli_accepts_bom_config_and_bom_raw_output() -> None:
    ARTIFACT_TEST_DIR.mkdir(parents=True, exist_ok=True)
    config_path = ARTIFACT_TEST_DIR / "bom_config.json"
    bom_output_path = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "bom_candidate_output.txt"
    try:
        bom_output_path.write_bytes(b"\xef\xbb\xbf" + VALID_OUTPUT_PATH.read_bytes())
        _write_json_bom(
            config_path,
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "source_output_path": "tests/fixtures/browser_planner_outputs/bom_candidate_output.txt",
                "output_dir": "artifacts/browser_planner_output_ingestion_tests",
                "limitations": ["test fixture"],
            },
        )

        completed = subprocess.run(
            [sys.executable, str(CLI_PATH), "--config", str(config_path)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(completed.stdout)
        assert completed.returncode == 0
        assert payload["status"] == "succeeded"
        assert payload["dry_run_status"] == "accepted"
    finally:
        bom_output_path.unlink(missing_ok=True)
        _cleanup_artifacts()


def test_cli_failure_exits_nonzero_with_structured_json(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid_config.json"
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
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION


def test_no_local_absolute_paths_in_output() -> None:
    summary = ingest_autonomous_browser_planner_output(
        {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "source_output_path": "tests/fixtures/browser_planner_outputs/valid_candidate_output.txt",
            "output_dir": "artifacts/browser_planner_output_ingestion_tests",
            "limitations": ["test fixture"],
        },
        repo_root=PROJECT_ROOT,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = ingest_autonomous_browser_planner_output(
        {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "source_output_path": "tests/fixtures/browser_planner_outputs/valid_candidate_output.txt",
            "output_dir": "artifacts/browser_planner_output_ingestion_tests",
            "limitations": ["test fixture"],
        },
        repo_root=PROJECT_ROOT,
    )

    assert summary["status"] == "succeeded"
