from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_local_planner_repeated_trials_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_local_planner_repeated_trials_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict[str, Any]:
    return {
        "schema_version": PACKET_CONFIG_SCHEMA_VERSION,
        "packet_id": "browser_local_planner_repeated_trials_packet_v1",
        "model": "second_model",
        "trial_count": 3,
        "prompt_profile": "compact_schema_following",
        "output_dir": "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet",
        "expected_raw_output_paths": [
            "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/trial_01/raw_planner_output.txt",
            "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/trial_02/raw_planner_output.txt",
            "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/trial_03/raw_planner_output.txt",
        ],
        "ingestion_suite_config_path": "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/ingestion_suite_config.local.json",
        "limitations": ["test fixture"],
    }


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    summary = build_autonomous_browser_local_planner_repeated_trials_packet(_config(), repo_root=repo_root)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["packet_id"] == "browser_local_planner_repeated_trials_packet_v1"
    assert summary["trial_count"] == 3
    assert summary["post_run_commands_count"] == 11
    assert len(summary["expected_raw_output_paths"]) == 3
    assert len(summary["packet_files"]) >= 11
    for relative_path in summary["packet_files"]:
        assert not Path(relative_path).is_absolute()

    output_dir = repo_root / "artifacts" / "autonomous_runtime_summaries" / "local_planner_repeated_trials_packet"
    readme_path = output_dir / "README.md"
    prompt_path = output_dir / "planner_prompt.compact.txt"
    trial_request_paths_path = output_dir / "trial_request_paths.json"
    trial_output_paths_path = output_dir / "trial_output_paths.json"
    ingestion_suite_config_path = output_dir / "ingestion_suite_config.local.json"
    commands_path = output_dir / "commands.json"
    commands_md_path = output_dir / "commands.md"
    summary_path = output_dir / "autonomous_browser_local_planner_repeated_trials_packet_summary.json"

    assert readme_path.exists()
    assert prompt_path.exists()
    assert trial_request_paths_path.exists()
    assert trial_output_paths_path.exists()
    assert ingestion_suite_config_path.exists()
    assert commands_path.exists()
    assert commands_md_path.exists()
    assert summary_path.exists()
    assert (output_dir / "trial_01" / "trial_request.json").exists()
    assert (output_dir / "trial_02" / "trial_request.json").exists()
    assert (output_dir / "trial_03" / "trial_request.json").exists()

    compact_prompt = prompt_path.read_text(encoding="utf-8")
    assert '"schema_version": "autonomous_browser_plan_v1"' in compact_prompt
    assert "No markdown." in compact_prompt
    assert "No code fences." in compact_prompt
    assert "```" not in compact_prompt
    assert "browser_open_url" in compact_prompt
    assert "local.intranet" in compact_prompt
    assert "docs.local" in compact_prompt

    trial_request_paths = json.loads(trial_request_paths_path.read_text(encoding="utf-8"))
    trial_output_paths = json.loads(trial_output_paths_path.read_text(encoding="utf-8"))
    ingestion_suite_config = json.loads(ingestion_suite_config_path.read_text(encoding="utf-8"))
    commands = json.loads(commands_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")

    assert len(trial_request_paths) == 3
    assert len(trial_output_paths) == 3
    assert ingestion_suite_config["replay_mode"] == "dry_run"
    assert ingestion_suite_config["expected_min_ingested"] == 3
    assert ingestion_suite_config["expected_max_rejected"] == 0
    assert len(ingestion_suite_config["captured_outputs"]) == 3
    assert "curl.exe --max-time" in commands_md
    assert "Codex must not launch models." in commands_md
    assert "Do not use Invoke-RestMethod for planner generation." in commands_md
    assert "planner_prompt.compact.txt" in commands_md
    assert any(command["id"] == "run_ingestion_suite_fixture" for command in commands["commands"])
    assert any(command["id"] == "run_pytest" for command in commands["commands"])


def test_packet_builder_rejects_unsafe_config(tmp_path: Path) -> None:
    config = _config()
    config["trial_count"] = 2

    summary = build_autonomous_browser_local_planner_repeated_trials_packet(config, repo_root=tmp_path)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"
    assert summary["no_runtime_execution"] is True


def test_packet_builder_output_has_no_absolute_paths_or_secrets(tmp_path: Path) -> None:
    summary = build_autonomous_browser_local_planner_repeated_trials_packet(_config(), repo_root=tmp_path)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "supersecret" not in encoded
    assert "api_key" not in encoded
    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = build_autonomous_browser_local_planner_repeated_trials_packet(_config(), repo_root=tmp_path)

    assert summary["status"] == "succeeded"

