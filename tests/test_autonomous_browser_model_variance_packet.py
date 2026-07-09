from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_model_variance_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_model_variance_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_model_variance_packet.example.json"
CLI_BUILD_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_model_variance_packet.py"


def _packet_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_variance_packet(_packet_config(), repo_root=tmp_path)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["packet_id"] == "browser_model_variance_packet_v1"
    assert summary["models_total"] == 2
    assert summary["scenarios_total"] == 3
    assert summary["trial_count"] == 3
    assert summary["trials_total"] == 18
    assert summary["model_aliases"] == ["second_model", "third_model"]
    assert summary["scenario_ids"] == [
        "hard_policy_disambiguation",
        "hard_ticket_priority_crosscheck",
        "hard_approval_policy_match",
    ]
    assert summary["trial_ids"] == ["trial_01", "trial_02", "trial_03"]
    assert summary["commands_count"] >= 43
    assert len(summary["expected_raw_output_paths"]) == 18
    assert all(not Path(path).is_absolute() for path in summary["packet_files"])

    output_dir = tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_variance_packet"
    packet_json_path = output_dir / "autonomous_browser_model_variance_packet.json"
    readme_path = output_dir / "README.md"
    commands_path = output_dir / "commands.json"
    commands_md_path = output_dir / "commands.md"
    request_paths_path = output_dir / "request_paths.json"
    output_paths_path = output_dir / "output_paths.json"
    trial_records_path = output_dir / "trial_records.json"
    variance_config_path = output_dir / "variance_config.local.json"
    prompt_policy_path = output_dir / "prompts" / "hard_policy_disambiguation" / "planner_prompt.compact.txt"
    prompt_ticket_path = output_dir / "prompts" / "hard_ticket_priority_crosscheck" / "planner_prompt.compact.txt"
    prompt_approval_path = output_dir / "prompts" / "hard_approval_policy_match" / "planner_prompt.compact.txt"

    for path in (
        packet_json_path,
        readme_path,
        commands_path,
        commands_md_path,
        request_paths_path,
        output_paths_path,
        trial_records_path,
        variance_config_path,
        prompt_policy_path,
        prompt_ticket_path,
        prompt_approval_path,
    ):
        assert path.exists()

    packet_json = json.loads(packet_json_path.read_text(encoding="utf-8"))
    request_paths = json.loads(request_paths_path.read_text(encoding="utf-8"))
    output_paths = json.loads(output_paths_path.read_text(encoding="utf-8"))
    trial_records = json.loads(trial_records_path.read_text(encoding="utf-8"))
    variance_config = json.loads(variance_config_path.read_text(encoding="utf-8"))
    commands = json.loads(commands_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")

    assert packet_json["schema_version"] == "autonomous_browser_model_variance_packet_v1"
    assert request_paths["second_model"]["hard_policy_disambiguation"]["trial_01"].endswith(
        "second_model/hard_policy_disambiguation/trial_01/request.json"
    )
    assert request_paths["third_model"]["hard_ticket_priority_crosscheck"]["trial_03"].endswith(
        "third_model/hard_ticket_priority_crosscheck/trial_03/request.json"
    )
    assert output_paths["third_model"]["hard_approval_policy_match"]["trial_02"].endswith(
        "third_model/hard_approval_policy_match/trial_02/raw_planner_output.txt"
    )
    assert len(trial_records) == 18
    assert variance_config["schema_version"] == "autonomous_browser_model_variance_evaluator_config_v1"
    assert len(variance_config["trial_records"]) == 18
    assert len(variance_config["captured_outputs"]) == 18
    assert variance_config["models"][1]["alias"] == "third_model"
    assert variance_config["models"][1]["prompt_prefix"] == "/no_think"
    assert "planner_prompt.compact.txt" in commands_md
    assert "Use `planner_prompt.compact.txt` as the prompt source for each trial." in commands_md
    assert "second_model" in commands_md
    assert "third_model" in commands_md
    assert "models/gguf/third_model.gguf" in commands_md
    assert any(command["id"] == "run_variance_evaluator_fixture" for command in commands["commands"])
    assert any(command["id"] == "run_pytest" for command in commands["commands"])

    policy_prompt = prompt_policy_path.read_text(encoding="utf-8")
    ticket_prompt = prompt_ticket_path.read_text(encoding="utf-8")
    approval_prompt = prompt_approval_path.read_text(encoding="utf-8")
    second_model_request = json.loads(
        (output_dir / "second_model" / "hard_policy_disambiguation" / "trial_01" / "request.json").read_text(encoding="utf-8")
    )
    third_model_request = json.loads(
        (output_dir / "third_model" / "hard_policy_disambiguation" / "trial_01" / "request.json").read_text(encoding="utf-8")
    )
    assert "schema_version must be \"autonomous_browser_plan_v1\"." in policy_prompt
    assert "schema_version must be \"autonomous_browser_plan_v1\"." in ticket_prompt
    assert "autonomous_browser_plan_v1" in approval_prompt
    assert "Return exactly one JSON object only." in policy_prompt
    assert "Do not return a JSON array." in ticket_prompt
    assert "Return exactly one JSON object with only the plan fields." in approval_prompt
    assert "Use exactly 3 actions." in policy_prompt
    assert "Use exactly 5 actions." in ticket_prompt
    assert "Suggested action count: 4." in approval_prompt
    assert "Allowed activity" in policy_prompt
    assert "Cross-check marker: the board summary is intentionally misleading." in ticket_prompt
    assert "Policy match: confirmed." in approval_prompt
    assert second_model_request["messages"][1]["content"].startswith("You are generating one offline browser plan")
    assert not second_model_request["messages"][1]["content"].startswith("/no_think\n")
    assert third_model_request["messages"][1]["content"].startswith("/no_think\n")
    assert "autonomous_browser_plan_v1" in third_model_request["messages"][1]["content"]

    encoded = json.dumps(summary, ensure_ascii=False)
    assert "supersecret" not in encoded
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_packet_builder_rejects_invalid_config(tmp_path: Path) -> None:
    config = _packet_config()
    config["trial_ids"] = ["trial_01", "trial_02"]

    summary = build_autonomous_browser_model_variance_packet(config, repo_root=tmp_path)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"
    assert summary["no_runtime_execution"] is True


def test_cli_success_exits_zero_and_prints_compact_json(tmp_path: Path) -> None:
    config_path = tmp_path / "browser_model_variance_packet.example.json"
    _write_json(config_path, _packet_config())
    cli_module = _load_cli_module(CLI_BUILD_PATH)
    original_project_root = cli_module.PROJECT_ROOT
    cli_module.PROJECT_ROOT = tmp_path
    try:
        exit_code = cli_module.main(["--config", str(config_path)])
    finally:
        cli_module.PROJECT_ROOT = original_project_root

    payload = json.loads(
        (
            tmp_path
            / "artifacts"
            / "autonomous_runtime_summaries"
            / "model_variance_packet"
            / "autonomous_browser_model_variance_packet_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert payload["status"] == "succeeded"
    assert payload["packet_id"] == "browser_model_variance_packet_v1"


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = build_autonomous_browser_model_variance_packet(_packet_config(), repo_root=tmp_path)

    assert summary["status"] == "succeeded"
