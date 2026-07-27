from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_plan_validation import validate_autonomous_browser_plan
from src.agent.autonomous_browser_planner_output_ingestion import extract_autonomous_browser_plan_candidate
from src.agent.autonomous_browser_plan_playwright_replay_operator import REQUIRED_CONFIRM_VALUE
from src.agent.autonomous_browser_plan_playwright_replay_suite import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_plan_playwright_replay_suite_config,
    run_autonomous_browser_plan_playwright_replay_suite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan.example.json"
CLI_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_plan_playwright_replay_suite.py"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan_playwright_replay_suite.example.json"
PHASE11_EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_phase11_playwright_replay_suite.example.json"
REPLAY_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "autonomous_browser_plan_playwright_replay"
EXAMPLE_CAPTURED_OUTPUTS = (
    "tests/fixtures/autonomous_browser_plan_playwright_replay/suite/captured_output_01.txt",
    "tests/fixtures/autonomous_browser_plan_playwright_replay/suite/captured_output_02.txt",
    "tests/fixtures/autonomous_browser_plan_playwright_replay/suite/captured_output_03.txt",
)


def _base_plan() -> dict[str, Any]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _phase11_plan() -> dict[str, Any]:
    return {
        "schema_version": "autonomous_browser_plan_v1",
        "plan_id": "browser_phase11_playwright_replay_plan_v1",
        "goal": "Review local policy fixture and capture evidence.",
        "scenario_id": "browser_ticket_triage_review",
        "max_actions": 4,
        "actions": [
            {
                "step_id": "open_home",
                "action_name": "browser_open_url",
                "parameters": {"url": "https://local.intranet/"},
                "expected_text": "Office Intranet",
            },
            {
                "step_id": "click_policy",
                "action_name": "browser_click",
                "parameters": {
                    "url": "https://local.intranet/docs/policy",
                    "target_text": "Workspace policy",
                },
                "expected_text": "Allowed activity",
            },
            {
                "step_id": "extract_policy",
                "action_name": "browser_extract_text",
                "parameters": {"url": "https://docs.local/docs/policy"},
                "expected_text": "Allowed activity",
            },
            {
                "step_id": "snapshot_policy",
                "action_name": "browser_snapshot",
                "parameters": {"url": "https://docs.local/docs/policy"},
                "expected_text": "Allowed activity",
            },
        ],
    }


def _resolve_repo_fixture(relative_path: str) -> Path:
    path = Path(relative_path)
    assert not path.is_absolute()
    assert "artifacts" not in path.parts
    resolved = (PROJECT_ROOT / path).resolve()
    assert resolved.is_relative_to(PROJECT_ROOT.resolve())
    assert resolved.is_relative_to(REPLAY_FIXTURE_ROOT.resolve())
    assert resolved.is_file()
    return resolved


def _write_captured_output(repo_root: Path, relative_path: str, text: str) -> Path:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _suite_config(
    *,
    captured_outputs: list[str],
    replay_backend: str = "fixture",
    output_dir: str = "artifacts/replay_suite_tests",
    expected_min_succeeded: int = 3,
    expected_max_failed: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "suite_id": "browser_plan_playwright_replay_suite_test_v1",
        "captured_outputs": captured_outputs,
        "output_dir": output_dir,
        "replay_backend": replay_backend,
        "allowed_hosts": ["local.intranet", "local-intranet.test", "docs.local", "portal.local"],
        "fixture_scope": "local_only",
        "headless": True,
        "timeout_ms": 30_000,
        "expected_min_succeeded": expected_min_succeeded,
        "expected_max_failed": expected_max_failed,
        "limitations": ["test fixture"],
    }


def test_example_config_loads_with_relative_paths() -> None:
    config = load_autonomous_browser_plan_playwright_replay_suite_config(EXAMPLE_CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.suite_id == "browser_plan_playwright_replay_suite_v1"
    assert config.replay_backend == "fixture"
    assert config.output_dir == "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_suite"
    assert config.captured_outputs == EXAMPLE_CAPTURED_OUTPUTS
    assert config.fixture_scope == "local_only"
    assert config.headless is True
    assert config.timeout_ms == 30_000
    assert config.expected_min_succeeded == 3
    assert config.expected_max_failed == 0
    for captured_output in config.captured_outputs:
        fixture_path = _resolve_repo_fixture(captured_output)
        extraction = extract_autonomous_browser_plan_candidate(fixture_path.read_text(encoding="utf-8"))
        assert extraction["status"] == "accepted"
        candidate_plan = extraction["candidate_plan"]
        assert isinstance(candidate_plan, dict)
        assert validate_autonomous_browser_plan(candidate_plan)["status"] == "accepted"


def test_phase11_example_config_loads_with_relative_paths() -> None:
    config = load_autonomous_browser_plan_playwright_replay_suite_config(PHASE11_EXAMPLE_CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.suite_id == "browser_phase11_playwright_replay_suite_v1"
    assert config.replay_backend == "playwright"
    assert config.output_dir == "artifacts/autonomous_runtime_summaries/phase11_playwright_replay_suite"
    assert config.captured_outputs == (
        "artifacts/autonomous_runtime_summaries/phase11_local_planner_packet/ticket_triage/raw_planner_output.txt",
        "artifacts/autonomous_runtime_summaries/phase11_local_planner_packet/approval_review/raw_planner_output.txt",
    )
    assert config.fixture_scope == "local_only"
    assert config.headless is True
    assert config.timeout_ms == 30_000
    assert config.expected_min_succeeded == 2
    assert config.expected_max_failed == 0


def test_suite_dry_run_with_three_fixture_outputs_succeeds(tmp_path: Path) -> None:
    captured_outputs = [
        "inputs/trial_01/raw_planner_output.txt",
        "inputs/trial_02/raw_planner_output.txt",
        "inputs/trial_03/raw_planner_output.txt",
    ]
    for relative_path in captured_outputs:
        _write_captured_output(tmp_path, relative_path, json.dumps(_phase11_plan(), ensure_ascii=False, indent=2))

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(captured_outputs=captured_outputs),
        repo_root=tmp_path,
        dry_run=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["suite_id"] == "browser_plan_playwright_replay_suite_test_v1"
    assert summary["replay_backend"] == "fixture"
    assert summary["guard_status"] == "dry_run"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_network_traffic"] is False
    assert summary["outputs_total"] == 3
    assert summary["outputs_succeeded"] == 3
    assert summary["outputs_failed"] == 0
    assert summary["actions_attempted_total"] == 0
    assert summary["actions_succeeded_total"] == 0
    assert summary["actions_failed_total"] == 0
    assert summary["expected_results_passed"] == 0
    assert summary["expected_results_failed"] == 0
    assert summary["expected_results_total"] == 12
    assert summary["thresholds"] == {"expected_min_succeeded": 3, "expected_max_failed": 0}
    assert len(summary["output_summaries"]) == 3
    assert all(item["status"] == "succeeded" for item in summary["output_summaries"])
    assert str(tmp_path) not in encoded
    assert "C:\\" not in encoded
    assert "supersecret" not in encoded


def test_default_refuses_without_guards(tmp_path: Path) -> None:
    captured_outputs = ["inputs/trial_01/raw_planner_output.txt"]
    _write_captured_output(tmp_path, captured_outputs[0], json.dumps(_base_plan(), ensure_ascii=False, indent=2))

    summary = run_autonomous_browser_plan_playwright_replay_suite(_suite_config(captured_outputs=captured_outputs), repo_root=tmp_path)

    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["guard_status"] == "refused"
    assert summary["no_runtime_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["replay_backend"] == "fixture"


@pytest.mark.parametrize(
    ("allow_real_browser", "confirm_real_browser"),
    [
        (True, None),
        (False, REQUIRED_CONFIRM_VALUE),
    ],
)
def test_one_guard_only_refuses(tmp_path: Path, allow_real_browser: bool, confirm_real_browser: str | None) -> None:
    captured_outputs = ["inputs/trial_01/raw_planner_output.txt"]
    _write_captured_output(tmp_path, captured_outputs[0], json.dumps(_base_plan(), ensure_ascii=False, indent=2))

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(captured_outputs=captured_outputs),
        repo_root=tmp_path,
        allow_real_browser=allow_real_browser,
        confirm_real_browser=confirm_real_browser,
    )

    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["guard_status"] == "refused"
    assert summary["no_runtime_execution"] is True
    assert summary["real_browser_execution"] is False


def test_backend_playwright_dry_run_succeeds_without_playwright_import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured_outputs = [
        "inputs/trial_01/raw_planner_output.txt",
        "inputs/trial_02/raw_planner_output.txt",
        "inputs/trial_03/raw_planner_output.txt",
    ]
    for relative_path in captured_outputs:
        _write_captured_output(tmp_path, relative_path, json.dumps(_phase11_plan(), ensure_ascii=False, indent=2))

    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(
            captured_outputs=captured_outputs,
            replay_backend="playwright",
            expected_min_succeeded=1,
            expected_max_failed=0,
        ),
        repo_root=tmp_path,
        dry_run=True,
    )

    assert summary["status"] == "succeeded"
    assert summary["replay_backend"] == "playwright"
    assert summary["guard_status"] == "dry_run"
    assert summary["no_runtime_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["outputs_succeeded"] == 3
    assert summary["expected_results_total"] == 12


def test_backend_playwright_refuses_without_guards(tmp_path: Path) -> None:
    captured_outputs = ["inputs/trial_01/raw_planner_output.txt"]
    _write_captured_output(tmp_path, captured_outputs[0], json.dumps(_phase11_plan(), ensure_ascii=False, indent=2))

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(captured_outputs=captured_outputs, replay_backend="playwright"),
        repo_root=tmp_path,
    )

    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["guard_status"] == "refused"
    assert summary["replay_backend"] == "playwright"
    assert summary["no_runtime_execution"] is True


def test_guarded_fixture_backend_fake_path_can_be_tested_without_real_browser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_outputs = [
        "inputs/trial_01/raw_planner_output.txt",
        "inputs/trial_02/raw_planner_output.txt",
        "inputs/trial_03/raw_planner_output.txt",
    ]
    for relative_path in captured_outputs:
        _write_captured_output(tmp_path, relative_path, json.dumps(_base_plan(), ensure_ascii=False, indent=2))

    calls: list[dict[str, Any]] = []

    def fake_operator(config_artifact: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"config_artifact": config_artifact, "kwargs": kwargs})
        return {
            "schema_version": "autonomous_browser_plan_playwright_replay_operator_summary_v1",
            "status": "succeeded",
            "error_code": None,
            "guard_status": "guarded_replay",
            "no_runtime_execution": False,
            "model_execution": False,
            "real_browser_execution": False,
            "replay_backend": "fixture",
            "fixture_replay_execution": True,
            "playwright_execution": False,
            "browser_opened": False,
            "real_network_traffic": False,
            "replay_plan_path": "fake/replay_plan.json",
            "plan_id": "browser_policy_research_plan_v1",
            "actions_total": 3,
            "actions_attempted": 3,
            "actions_succeeded": 3,
            "actions_failed": 0,
            "expected_results_passed": 3,
            "expected_results_failed": 0,
            "expected_results_total": 3,
            "output_files": ["fake/output.json"],
            "limitations": ["fake"],
            "diagnostics": {"fake": True},
        }

    monkeypatch.setattr(
        "src.agent.autonomous_browser_plan_playwright_replay_suite.run_autonomous_browser_plan_playwright_replay_operator",
        fake_operator,
    )

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(captured_outputs=captured_outputs),
        repo_root=tmp_path,
        allow_real_browser=True,
        confirm_real_browser=REQUIRED_CONFIRM_VALUE,
    )

    assert summary["status"] == "succeeded"
    assert summary["replay_backend"] == "fixture"
    assert summary["guard_status"] == "guarded_replay"
    assert summary["no_runtime_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["outputs_succeeded"] == 3
    assert summary["actions_attempted_total"] == 9
    assert summary["actions_succeeded_total"] == 9
    assert summary["expected_results_passed"] == 9
    assert summary["expected_results_total"] == 9
    assert len(calls) == 3


def test_invalid_captured_output_counted_failed_and_thresholds_respected(tmp_path: Path) -> None:
    captured_outputs = [
        "inputs/trial_01/raw_planner_output.txt",
        "inputs/trial_02/raw_planner_output.txt",
        "inputs/trial_03/raw_planner_output.txt",
    ]
    _write_captured_output(tmp_path, captured_outputs[0], json.dumps(_base_plan(), ensure_ascii=False, indent=2))
    _write_captured_output(tmp_path, captured_outputs[1], "not json at all")
    _write_captured_output(tmp_path, captured_outputs[2], json.dumps(_base_plan(), ensure_ascii=False, indent=2))

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(captured_outputs=captured_outputs, expected_min_succeeded=3, expected_max_failed=0),
        repo_root=tmp_path,
        dry_run=True,
    )

    assert summary["status"] == "failed"
    assert summary["outputs_total"] == 3
    assert summary["outputs_succeeded"] == 2
    assert summary["outputs_failed"] == 1
    assert summary["error_code"] in {"no_json_object_found", "suite_thresholds_not_met", "captured_output_failed"}
    assert any(item["status"] != "succeeded" for item in summary["output_summaries"])


def test_missing_captured_output_returns_safe_error_code_without_error_d(tmp_path: Path) -> None:
    captured_outputs = [
        "inputs/trial_01/raw_planner_output.txt",
        "inputs/trial_02/raw_planner_output.txt",
    ]
    _write_captured_output(tmp_path, captured_outputs[0], json.dumps(_base_plan(), ensure_ascii=False, indent=2))

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(captured_outputs=captured_outputs, expected_min_succeeded=2, expected_max_failed=0),
        repo_root=tmp_path,
        dry_run=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "failed"
    assert summary["error_code"] in {"source_output_read_failed", "suite_outputs_failed", "captured_output_failed"}
    assert "error_d" not in summary
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["outputs_total"] == 2
    assert summary["outputs_succeeded"] == 1
    assert summary["outputs_failed"] == 1
    assert "error_d" not in encoded


def test_summary_fields_correct_and_no_absolute_paths_or_secret_leakage(tmp_path: Path) -> None:
    captured_outputs = ["inputs/trial_01/raw_planner_output.txt"]
    _write_captured_output(tmp_path, captured_outputs[0], json.dumps(_base_plan(), ensure_ascii=False, indent=2))

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(captured_outputs=captured_outputs, expected_min_succeeded=1, expected_max_failed=0),
        repo_root=tmp_path,
        dry_run=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["suite_id"] == "browser_plan_playwright_replay_suite_test_v1"
    assert summary["thresholds"] == {"expected_min_succeeded": 1, "expected_max_failed": 0}
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded
    assert "supersecret" not in encoded


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured_outputs = ["inputs/trial_01/raw_planner_output.txt"]
    _write_captured_output(tmp_path, captured_outputs[0], json.dumps(_phase11_plan(), ensure_ascii=False, indent=2))
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_plan_playwright_replay_suite(
        _suite_config(
            captured_outputs=captured_outputs,
            replay_backend="playwright",
            expected_min_succeeded=1,
            expected_max_failed=0,
        ),
        repo_root=tmp_path,
        dry_run=True,
    )

    assert summary["status"] == "succeeded"
    assert summary["guard_status"] == "dry_run"
    assert summary["replay_backend"] == "playwright"


def test_cli_dry_run_fixture_smoke_uses_repo_local_paths(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(EXAMPLE_CONFIG_PATH), "--dry-run"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "succeeded"
    assert payload["guard_status"] == "dry_run"
    assert payload["replay_backend"] == "fixture"


def test_cli_dry_run_playwright_smoke_uses_repo_local_paths(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(EXAMPLE_CONFIG_PATH), "--dry-run", "--replay-backend", "playwright"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "succeeded"
    assert payload["guard_status"] == "dry_run"
    assert payload["replay_backend"] == "playwright"


def test_cli_refusal_playwright_smoke_uses_repo_local_paths(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(CLI_PATH), "--config", str(EXAMPLE_CONFIG_PATH), "--replay-backend", "playwright"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert payload["status"] == "refused"
    assert payload["error_code"] == "allow_real_browser_required"
    assert payload["guard_status"] == "refused"
    assert payload["replay_backend"] == "playwright"
