from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_planner_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
    REPLAY_SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_planner_packet,
    replay_autonomous_browser_planner_output,
    write_autonomous_browser_planner_packet,
)
from src.agent.autonomous_browser_plan_validation import validate_autonomous_browser_plan


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKET_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_packet.example.json"
PLAN_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_candidate.example.json"
PACKET_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_planner_packet.py"
REPLAY_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "replay_autonomous_browser_planner_output.py"


def _load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bad_candidate() -> dict[str, Any]:
    candidate = _load_plan(PLAN_PATH)
    candidate["actions"][0]["action_name"] = "browser_not_real"
    return candidate


def test_packet_builder_creates_prompt_packet_with_allowed_and_prohibited_sections(tmp_path: Path) -> None:
    packet = build_autonomous_browser_planner_packet()
    paths = write_autonomous_browser_planner_packet(packet, tmp_path / "packet")
    prompt = paths["prompt"].read_text(encoding="utf-8")

    assert packet["schema_version"] == PACKET_SCHEMA_VERSION
    assert "ALLOWED ACTIONS" in prompt
    assert "PROHIBITED OUTPUTS" in prompt
    assert "JSON only" in prompt
    assert "browser_open_url" in prompt
    assert "browser execution requests" in prompt


def test_packet_does_not_include_secrets_or_absolute_local_paths() -> None:
    packet = build_autonomous_browser_planner_packet()
    encoded = json.dumps(packet, ensure_ascii=False)

    assert "supersecret" not in encoded
    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded


def test_safe_candidate_plan_validates() -> None:
    result = validate_autonomous_browser_plan(_load_plan(PLAN_PATH))

    assert result["status"] == "accepted"
    assert result["schema_version"] == "autonomous_browser_plan_validation_result_v1"


def test_replay_dry_run_succeeds() -> None:
    summary = replay_autonomous_browser_planner_output(PLAN_PATH, repo_root=PROJECT_ROOT)

    assert summary["schema_version"] == REPLAY_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["validation_status"] == "accepted"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "skipped"
    assert summary["real_browser_execution"] is False
    assert summary["model_execution"] is False
    assert summary["no_runtime_execution"] is True
    assert summary["actions_attempted"] == 0


def test_replay_fixture_execution_succeeds_with_execute_fixture() -> None:
    summary = replay_autonomous_browser_planner_output(PLAN_PATH, repo_root=PROJECT_ROOT, execute_fixture=True)

    assert summary["status"] == "succeeded"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "succeeded"
    assert summary["actions_total"] == 3
    assert summary["actions_attempted"] == 3
    assert summary["actions_succeeded"] == 3
    assert summary["expected_results_passed"] == 3
    assert summary["stop_reason"] == "all_tasks_terminal"


def test_invalid_candidate_exits_nonzero_with_structured_json(tmp_path: Path) -> None:
    candidate_path = tmp_path / "bad_candidate.json"
    candidate_path.write_text(json.dumps(_bad_candidate(), ensure_ascii=False, indent=2), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(REPLAY_SCRIPT_PATH), "--candidate-plan", str(candidate_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode != 0
    assert payload["status"] == "rejected"
    assert payload["error_code"] == "unknown_browser_action"
    assert payload["schema_version"] == REPLAY_SUMMARY_SCHEMA_VERSION


def test_replay_validates_before_fixture_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def forbidden(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("fixture execution must not run for invalid plans")

    monkeypatch.setattr(
        "src.agent.autonomous_browser_planner_packet.run_autonomous_browser_plan_fixture_execution",
        forbidden,
    )

    summary = replay_autonomous_browser_planner_output(_bad_candidate(), repo_root=PROJECT_ROOT, execute_fixture=True)

    assert summary["status"] == "rejected"
    assert called is False


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    packet = build_autonomous_browser_planner_packet()
    summary = replay_autonomous_browser_planner_output(PLAN_PATH, repo_root=PROJECT_ROOT)

    assert packet["packet_id"] == "browser_planner_packet_v1"
    assert summary["status"] == "succeeded"


def test_compact_json_output_is_valid() -> None:
    completed = subprocess.run(
        [sys.executable, str(PACKET_SCRIPT_PATH), "--config", str(PACKET_CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "succeeded"
    assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")


def test_generated_artifacts_are_not_required_for_committed_tests(tmp_path: Path) -> None:
    packet = build_autonomous_browser_planner_packet()
    paths = write_autonomous_browser_planner_packet(packet, tmp_path / "packet")

    assert paths["packet"].exists()
    assert paths["prompt"].exists()
