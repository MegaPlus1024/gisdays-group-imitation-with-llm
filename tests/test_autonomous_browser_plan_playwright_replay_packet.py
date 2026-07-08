from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_plan_playwright_replay_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_plan_playwright_replay_packet,
)
from src.agent.autonomous_browser_planner_output_ingestion import extract_autonomous_browser_plan_candidate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_OUTPUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "valid_candidate_output.txt"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_plan_playwright_replay_packet.py"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_packet_tests"
SOURCE_OUTPUT_PATH = "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/trial_01/raw_planner_output.txt"


def _candidate_plan() -> dict[str, Any]:
    extracted = extract_autonomous_browser_plan_candidate(FIXTURE_OUTPUT_PATH.read_text(encoding="utf-8"))
    assert extracted["status"] == "accepted"
    assert isinstance(extracted["candidate_plan"], dict)
    return dict(extracted["candidate_plan"])


def _config(*, source_output_path: str = SOURCE_OUTPUT_PATH, output_dir: str = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    return {
        "schema_version": PACKET_CONFIG_SCHEMA_VERSION,
        "no_runtime_execution": True,
        "packet_id": "browser_plan_playwright_replay_packet_v1",
        "source_output_path": source_output_path,
        "output_dir": output_dir,
        "limitations": ["test fixture"],
    }


def _write_fixture_capture(repo_root: Path, *, source_output_path: str = SOURCE_OUTPUT_PATH, payload: dict[str, Any] | None = None, bom: bool = False) -> Path:
    output_path = repo_root / source_output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = payload if payload is not None else _candidate_plan()
    data = json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
    output_path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
    return output_path


def _load_script_module() -> Any:
    spec = importlib.util.spec_from_file_location("build_autonomous_browser_plan_playwright_replay_packet_cli", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builder_creates_packet_from_captured_fixture_output(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write_fixture_capture(repo_root)

    summary = build_autonomous_browser_plan_playwright_replay_packet(_config(), repo_root=repo_root)
    output_dir = repo_root / DEFAULT_OUTPUT_DIR
    normalized_plan_path = output_dir / "normalized_plan.json"
    replay_plan_path = output_dir / "playwright_replay_plan.json"
    commands_md_path = output_dir / "commands.md"
    commands_json_path = output_dir / "commands.json"
    readme_path = output_dir / "README.md"
    summary_path = output_dir / "autonomous_browser_plan_playwright_replay_packet_summary.json"

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["future_operator_guard_required"] is True
    assert summary["source_output_path"] == SOURCE_OUTPUT_PATH
    assert summary["output_dir"] == DEFAULT_OUTPUT_DIR
    assert summary["validation_status"] == "accepted"
    assert summary["actions_total"] == 3
    assert summary["extracted_plan_id"]
    assert len(summary["packet_files"]) == 6
    assert all(not Path(item).is_absolute() for item in summary["packet_files"])
    assert normalized_plan_path.exists()
    assert replay_plan_path.exists()
    assert commands_md_path.exists()
    assert commands_json_path.exists()
    assert readme_path.exists()
    assert summary_path.exists()

    normalized_plan = json.loads(normalized_plan_path.read_text(encoding="utf-8"))
    replay_plan = json.loads(replay_plan_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")
    commands_json = json.loads(commands_json_path.read_text(encoding="utf-8"))

    assert normalized_plan["plan_id"] == summary["extracted_plan_id"]
    assert len(normalized_plan["actions"]) == 3
    assert replay_plan["normalized_plan"]["plan_id"] == summary["extracted_plan_id"]
    assert len(replay_plan["normalized_plan"]["actions"]) == 3
    assert replay_plan["future_operator_guard_required"] is True
    assert replay_plan["local_fixture_only_scope"] is True
    assert replay_plan["no_external_urls"] is True
    assert commands_json["future_operator_guard_required"] is True
    assert commands_json["no_runtime_execution"] is True
    assert "Codex must not launch browser/server/model." in commands_md
    assert "Future guarded operator execution requires explicit flags" in commands_md
    assert ".\\.venv\\Scripts\\python.exe" in commands_md
    assert str(tmp_path) not in json.dumps(summary, ensure_ascii=False)
    assert str(tmp_path) not in commands_md
    assert "C:\\" not in json.dumps(summary, ensure_ascii=False)


def test_cli_accepts_bom_config_and_bom_raw_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_root = tmp_path
    _write_fixture_capture(repo_root, bom=True)
    config_path = repo_root / "bom_config.json"
    config_path.write_bytes(b"\xef\xbb\xbf" + json.dumps(_config(), ensure_ascii=False, indent=2).encode("utf-8"))

    module = _load_script_module()
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = repo_root
    try:
        exit_code = module.main(["--config", str(config_path)])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["no_runtime_execution"] is True
    assert payload["model_execution"] is False
    assert payload["real_browser_execution"] is False
    assert payload["future_operator_guard_required"] is True
    assert payload["validation_status"] == "accepted"
    assert payload["actions_total"] == 3


def test_validation_failure_produces_safe_failed_summary(tmp_path: Path) -> None:
    repo_root = tmp_path
    bad_plan = _candidate_plan()
    bad_plan["actions"][0]["parameters"]["query"] = "api_key=supersecret"
    _write_fixture_capture(repo_root, payload=bad_plan)

    summary = build_autonomous_browser_plan_playwright_replay_packet(_config(), repo_root=repo_root)
    summary_text = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "secret_like_parameter_value"
    assert summary["validation_status"] == "rejected"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["future_operator_guard_required"] is True
    assert "supersecret" not in summary_text
    assert "api_key" in summary_text
    assert str(tmp_path) not in summary_text
    assert summary["packet_files"] == [f"{DEFAULT_OUTPUT_DIR}/autonomous_browser_plan_playwright_replay_packet_summary.json"]
    assert (repo_root / DEFAULT_OUTPUT_DIR / "autonomous_browser_plan_playwright_replay_packet_summary.json").exists()


def test_builder_does_not_import_playwright_or_browser_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _write_fixture_capture(repo_root)
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "selenium", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = build_autonomous_browser_plan_playwright_replay_packet(_config(), repo_root=repo_root)

    assert summary["status"] == "succeeded"
