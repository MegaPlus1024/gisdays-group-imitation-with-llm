from __future__ import annotations

import builtins
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_local_planner_operator_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_local_planner_operator_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKET_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_local_planner_operator_packet.example.json"
PACKET_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "autonomous_runtime_summaries" / "local_planner_operator_packet"
CLI_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_local_planner_operator_packet.py"


def _config() -> dict[str, Any]:
    return {
        "schema_version": PACKET_CONFIG_SCHEMA_VERSION,
        "no_runtime_execution": True,
        "operator_packet_id": "browser_local_planner_operator_packet_v1",
        "prompt_profile": "compact_schema_following",
        "planner_packet_config_path": "configs/autonomous_runtime/browser_planner_packet.example.json",
        "expected_raw_output_path": "artifacts/autonomous_runtime_summaries/local_planner_operator_packet/raw_planner_output.txt",
        "expected_ingestion_suite_config_path": "configs/autonomous_runtime/browser_planner_output_ingestion_suite.example.json",
        "model_ids_allowed": ["first_model", "second_model"],
        "default_recommended_planner_model": "second_model",
        "output_dir": "artifacts/autonomous_runtime_summaries/local_planner_operator_packet",
        "limitations": ["test fixture"],
    }


def _prepare_repo_root(repo_root: Path) -> None:
    planner_packet_src = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_packet.example.json"
    ingestion_suite_src = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_planner_output_ingestion_suite.example.json"
    planner_packet_dst = repo_root / "configs" / "autonomous_runtime" / "browser_planner_packet.example.json"
    ingestion_suite_dst = repo_root / "configs" / "autonomous_runtime" / "browser_planner_output_ingestion_suite.example.json"
    planner_packet_dst.parent.mkdir(parents=True, exist_ok=True)
    ingestion_suite_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(planner_packet_src, planner_packet_dst)
    shutil.copy2(ingestion_suite_src, ingestion_suite_dst)


def _cleanup_artifacts() -> None:
    shutil.rmtree(PACKET_OUTPUT_DIR, ignore_errors=True)


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    _prepare_repo_root(repo_root)

    summary = build_autonomous_browser_local_planner_operator_packet(_config(), repo_root=repo_root)

    try:
        assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
        assert summary["status"] == "succeeded"
        assert summary["no_runtime_execution"] is True
        assert summary["model_execution"] is False
        assert summary["real_browser_execution"] is False
        assert summary["operator_packet_id"] == "browser_local_planner_operator_packet_v1"
        assert summary["post_run_commands_count"] == 7
        assert summary["packet_files"]
        for relative_path in summary["packet_files"]:
            assert not Path(relative_path).is_absolute()

        output_dir = repo_root / "artifacts" / "autonomous_runtime_summaries" / "local_planner_operator_packet"
        packet_path = output_dir / "operator_packet.json"
        readme_path = output_dir / "README.md"
        prompt_path = output_dir / "planner_prompt.txt"
        compact_prompt_path = output_dir / "planner_prompt.compact.txt"
        commands_path = output_dir / "commands.json"
        commands_md_path = output_dir / "commands.md"
        expected_paths_path = output_dir / "expected_output_paths.json"
        summary_path = output_dir / "autonomous_browser_local_planner_operator_packet_summary.json"

        assert packet_path.exists()
        assert readme_path.exists()
        assert prompt_path.exists()
        assert compact_prompt_path.exists()
        assert commands_path.exists()
        assert commands_md_path.exists()
        assert expected_paths_path.exists()
        assert summary_path.exists()

        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        assert packet["schema_version"] == PACKET_SCHEMA_VERSION
        assert packet["prompt_profile"] == "compact_schema_following"
        assert packet["model_ids_allowed"] == ["first_model", "second_model"]
        assert "Codex must not launch models." in readme_path.read_text(encoding="utf-8")
        assert "autonomous_browser_plan_v1" in prompt_path.read_text(encoding="utf-8")
        compact_prompt = compact_prompt_path.read_text(encoding="utf-8")
        assert '"schema_version": "autonomous_browser_plan_v1"' in compact_prompt
        assert "No markdown." in compact_prompt
        assert "No code fences." in compact_prompt
        assert '"actions": [' in compact_prompt
        assert "browser_open_url" in compact_prompt
        assert "browser_extract_text" in compact_prompt
        assert "local.intranet" in compact_prompt
        assert "docs.local" in compact_prompt
        assert "portal.local" in compact_prompt
        assert "```" not in compact_prompt
        assert "supersecret" not in compact_prompt
        assert "C:\\" not in compact_prompt
        commands = json.loads(commands_path.read_text(encoding="utf-8"))
        assert any(command["id"] == "read_compact_prompt" for command in commands["commands"])
        assert any(command["id"] == "ingest_dry_run" for command in commands["commands"])
        assert any(command["id"] == "run_ingestion_suite" for command in commands["commands"])
        commands_md = commands_md_path.read_text(encoding="utf-8")
        assert "planner_prompt.compact.txt" in commands_md
        assert "Get-Content" in commands_md
    finally:
        _cleanup_artifacts()


def test_packet_builder_rejects_unsafe_config(tmp_path: Path) -> None:
    repo_root = tmp_path
    _prepare_repo_root(repo_root)
    config = _config()
    config["planner_packet_config_path"] = "../secret.txt"

    summary = build_autonomous_browser_local_planner_operator_packet(config, repo_root=repo_root)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"
    assert summary["no_runtime_execution"] is True


def test_packet_builder_output_has_no_absolute_paths_or_secrets(tmp_path: Path) -> None:
    repo_root = tmp_path
    _prepare_repo_root(repo_root)

    summary = build_autonomous_browser_local_planner_operator_packet(_config(), repo_root=repo_root)
    encoded = json.dumps(summary, ensure_ascii=False)

    try:
        assert "supersecret" not in encoded
        assert "C:\\" not in encoded
        assert str(PROJECT_ROOT) not in encoded
    finally:
        _cleanup_artifacts()


def test_cli_success_exits_zero_and_prints_compact_json(tmp_path: Path) -> None:
    repo_root = tmp_path
    _prepare_repo_root(repo_root)
    config_path = repo_root / "configs" / "autonomous_runtime" / "browser_local_planner_operator_packet.example.json"
    config_path.write_text(json.dumps(_config(), ensure_ascii=False, indent=2), encoding="utf-8")

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
    config_path = tmp_path / "invalid_local_operator_packet.json"
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
    repo_root = tmp_path
    _prepare_repo_root(repo_root)

    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = build_autonomous_browser_local_planner_operator_packet(_config(), repo_root=repo_root)

    assert summary["status"] == "succeeded"
