from __future__ import annotations

import builtins
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_phase11_local_planner_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_phase11_local_planner_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKET_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "autonomous_runtime_summaries" / "phase11_local_planner_packet"
PACKET_CONFIG_SRC = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_phase11_local_planner_packet.example.json"
CLI_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_phase11_local_planner_packet.py"


def _config() -> dict[str, Any]:
    return {
        "schema_version": PACKET_CONFIG_SCHEMA_VERSION,
        "no_runtime_execution": True,
        "packet_id": "browser_phase11_local_planner_packet_v1",
        "model": "second_model",
        "output_dir": "artifacts/autonomous_runtime_summaries/phase11_local_planner_packet",
        "scenario_ids": [
            "browser_ticket_triage_review",
            "browser_approval_form_review",
        ],
        "ingestion_suite_config_path": "artifacts/autonomous_runtime_summaries/phase11_local_planner_packet/ingestion_suite_config.local.json",
        "limitations": ["test fixture"],
    }


def _cleanup_artifacts() -> None:
    shutil.rmtree(PACKET_OUTPUT_DIR, ignore_errors=True)


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    summary = build_autonomous_browser_phase11_local_planner_packet(_config(), repo_root=repo_root)

    try:
        assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
        assert summary["status"] == "succeeded"
        assert summary["no_runtime_execution"] is True
        assert summary["model_execution"] is False
        assert summary["real_browser_execution"] is False
        assert summary["packet_id"] == "browser_phase11_local_planner_packet_v1"
        assert summary["model"] == "second_model"
        assert summary["scenario_count"] == 2
        assert summary["scenario_ids"] == ["browser_ticket_triage_review", "browser_approval_form_review"]
        assert summary["post_run_commands_count"] == 10
        assert len(summary["expected_raw_output_paths"]) == 2
        assert len(summary["packet_files"]) >= 10
        for relative_path in summary["packet_files"]:
            assert not Path(relative_path).is_absolute()

        output_dir = repo_root / "artifacts" / "autonomous_runtime_summaries" / "phase11_local_planner_packet"
        packet_path = output_dir / "autonomous_browser_phase11_local_planner_packet.json"
        readme_path = output_dir / "README.md"
        ticket_prompt_path = output_dir / "planner_prompt.ticket_triage.compact.txt"
        approval_prompt_path = output_dir / "planner_prompt.approval_review.compact.txt"
        request_paths_path = output_dir / "request_paths.json"
        output_paths_path = output_dir / "output_paths.json"
        ingestion_suite_config_path = output_dir / "ingestion_suite_config.local.json"
        commands_path = output_dir / "commands.json"
        commands_md_path = output_dir / "commands.md"
        summary_path = output_dir / "autonomous_browser_phase11_local_planner_packet_summary.json"

        assert packet_path.exists()
        assert readme_path.exists()
        assert ticket_prompt_path.exists()
        assert approval_prompt_path.exists()
        assert request_paths_path.exists()
        assert output_paths_path.exists()
        assert ingestion_suite_config_path.exists()
        assert commands_path.exists()
        assert commands_md_path.exists()
        assert summary_path.exists()
        assert (output_dir / "ticket_triage" / "request.json").exists()
        assert (output_dir / "approval_review" / "request.json").exists()

        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        assert packet["schema_version"] == PACKET_SCHEMA_VERSION
        assert packet["scenario_count"] == 2
        assert packet["scenario_ids"] == ["browser_ticket_triage_review", "browser_approval_form_review"]
        assert packet["scenario_packets"][0]["scenario_id"] == "browser_ticket_triage_review"
        assert packet["scenario_packets"][1]["scenario_id"] == "browser_approval_form_review"

        ticket_prompt = ticket_prompt_path.read_text(encoding="utf-8")
        approval_prompt = approval_prompt_path.read_text(encoding="utf-8")
        assert '"schema_version": "autonomous_browser_plan_v1"' in ticket_prompt
        assert '"schema_version": "autonomous_browser_plan_v1"' in approval_prompt
        assert "No markdown." in ticket_prompt
        assert "No code fences." in ticket_prompt
        assert "Ticket board" in ticket_prompt
        assert "Ticket 1" in ticket_prompt
        assert "Priority" in ticket_prompt
        assert "Local fixture only" in ticket_prompt
        assert "Approvals queue" in approval_prompt
        assert "Approval request" in approval_prompt
        assert "Allowed activity" in approval_prompt
        assert "fixture-backed" in approval_prompt
        assert "```" not in ticket_prompt
        assert "```" not in approval_prompt

        request_paths = json.loads(request_paths_path.read_text(encoding="utf-8"))
        output_paths = json.loads(output_paths_path.read_text(encoding="utf-8"))
        ingestion_suite_config = json.loads(ingestion_suite_config_path.read_text(encoding="utf-8"))
        commands = json.loads(commands_path.read_text(encoding="utf-8"))
        commands_md = commands_md_path.read_text(encoding="utf-8")

        assert len(request_paths) == 2
        assert len(output_paths) == 2
        assert ingestion_suite_config["replay_mode"] == "dry_run"
        assert ingestion_suite_config["expected_min_ingested"] == 2
        assert ingestion_suite_config["expected_max_rejected"] == 0
        assert len(ingestion_suite_config["captured_outputs"]) == 2
        assert "curl.exe --max-time" in commands_md
        assert "Codex must not launch models." in commands_md
        assert "Do not use Invoke-RestMethod for planner generation." in commands_md
        assert "planner_prompt.ticket_triage.compact.txt" in commands_md
        assert "planner_prompt.approval_review.compact.txt" in commands_md
        assert "Get-Content" in commands_md
        assert "raw_planner_output.txt" in commands_md
        assert any(command["id"] == "run_ingestion_suite_dry_run" for command in commands["commands"])
        assert any(command["id"] == "run_ingestion_suite_fixture" for command in commands["commands"])
        assert any(command["id"] == "run_pytest" for command in commands["commands"])

        ticket_request = json.loads((output_dir / "ticket_triage" / "request.json").read_text(encoding="utf-8"))
        approval_request = json.loads((output_dir / "approval_review" / "request.json").read_text(encoding="utf-8"))
        assert ticket_request["model"] == "second_model"
        assert approval_request["model"] == "second_model"
        assert "Ticket board" in ticket_request["messages"][1]["content"]
        assert "Approvals queue" in approval_request["messages"][1]["content"]
    finally:
        _cleanup_artifacts()


def test_packet_builder_rejects_unsafe_config(tmp_path: Path) -> None:
    repo_root = tmp_path
    config = _config()
    config["scenario_ids"] = ["browser_ticket_triage_review"]

    summary = build_autonomous_browser_phase11_local_planner_packet(config, repo_root=repo_root)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"
    assert summary["no_runtime_execution"] is True


def test_packet_builder_output_has_no_absolute_paths_or_secrets(tmp_path: Path) -> None:
    summary = build_autonomous_browser_phase11_local_planner_packet(_config(), repo_root=tmp_path)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "supersecret" not in encoded
    assert "api_key" not in encoded
    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded


def test_cli_success_exits_zero_and_prints_compact_json(tmp_path: Path) -> None:
    config_path = tmp_path / "browser_phase11_local_planner_packet.example.json"
    config_path.write_text(PACKET_CONFIG_SRC.read_text(encoding="utf-8"), encoding="utf-8-sig")

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
        assert payload["execution_status"] == "skipped_by_design"
        assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")
    finally:
        _cleanup_artifacts()


def test_cli_invalid_config_exits_nonzero_with_structured_json(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid_phase11_packet.json"
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
    assert payload["error_code"] == "config_validation_failed"


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = build_autonomous_browser_phase11_local_planner_packet(_config(), repo_root=tmp_path)

    assert summary["status"] == "succeeded"
