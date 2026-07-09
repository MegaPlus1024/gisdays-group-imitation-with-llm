from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_model_comparison_evaluator import (
    SUMMARY_SCHEMA_VERSION as EVALUATOR_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_model_comparison_evaluator,
)
from src.agent.autonomous_browser_model_comparison_packet import (
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_model_comparison_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_model_discrimination_packet.example.json"
CLI_BUILD_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_model_comparison_packet.py"
CLI_EVALUATOR_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_model_comparison_evaluator.py"
VALID_OUTPUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "valid_candidate_output.txt"


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


def test_model_discrimination_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["packet_id"] == "browser_model_discrimination_packet_v1"
    assert summary["model_count"] == 2
    assert summary["scenario_count"] == 3
    assert summary["model_aliases"] == ["second_model", "third_model"]
    assert summary["scenario_ids"] == [
        "hard_policy_disambiguation",
        "hard_ticket_priority_crosscheck",
        "hard_approval_policy_match",
    ]
    assert summary["commands_count"] == 18
    assert len(summary["expected_raw_output_paths"]) == 6
    assert all(not Path(path).is_absolute() for path in summary["packet_files"])

    output_dir = tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_discrimination_packet"
    packet_json_path = output_dir / "model_comparison_packet.json"
    readme_path = output_dir / "README.md"
    commands_path = output_dir / "commands.json"
    commands_md_path = output_dir / "commands.md"
    request_paths_path = output_dir / "request_paths.json"
    output_paths_path = output_dir / "output_paths.json"
    comparison_config_path = output_dir / "comparison_config.local.json"
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
        comparison_config_path,
        prompt_policy_path,
        prompt_ticket_path,
        prompt_approval_path,
    ):
        assert path.exists()

    packet_json = json.loads(packet_json_path.read_text(encoding="utf-8"))
    request_paths = json.loads(request_paths_path.read_text(encoding="utf-8"))
    output_paths = json.loads(output_paths_path.read_text(encoding="utf-8"))
    comparison_config = json.loads(comparison_config_path.read_text(encoding="utf-8"))
    commands = json.loads(commands_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")

    assert packet_json["schema_version"] == "autonomous_browser_model_comparison_packet_v1"
    assert request_paths["second_model"]["hard_policy_disambiguation"].endswith("second_model/hard_policy_disambiguation/request.json")
    assert request_paths["third_model"]["hard_ticket_priority_crosscheck"].endswith("third_model/hard_ticket_priority_crosscheck/request.json")
    assert output_paths["third_model"]["hard_approval_policy_match"].endswith("third_model/hard_approval_policy_match/raw_planner_output.txt")
    assert comparison_config["models"][0]["alias"] == "second_model"
    assert comparison_config["models"][1]["alias"] == "third_model"
    assert comparison_config["models"][1]["prompt_prefix"] == "/no_think"
    assert comparison_config["scenarios"][0]["prompt_filename"] == "planner_prompt.compact.txt"
    assert "planner_prompt.compact.txt" in commands_md
    assert "second_model" in commands_md
    assert "third_model" in commands_md
    assert "Use `planner_prompt.compact.txt` as the prompt source for each trial." in commands_md
    assert any(command["id"] == "run_model_comparison_evaluator" for command in commands["commands"])

    policy_prompt = prompt_policy_path.read_text(encoding="utf-8")
    ticket_prompt = prompt_ticket_path.read_text(encoding="utf-8")
    approval_prompt = prompt_approval_path.read_text(encoding="utf-8")
    third_model_request = json.loads(
        (output_dir / "third_model" / "hard_policy_disambiguation" / "request.json").read_text(encoding="utf-8")
    )
    assert "policy disambiguation" in policy_prompt
    assert "ticket board" in ticket_prompt
    assert "local-only approval marker" in approval_prompt
    assert third_model_request["messages"][1]["content"].startswith("/no_think\n")
    assert "supersecret" not in json.dumps(summary)
    assert "C:\\" not in json.dumps(summary)
    assert str(tmp_path) not in json.dumps(summary)


def test_model_discrimination_packet_rejects_invalid_config(tmp_path: Path) -> None:
    config = _packet_config()
    config["no_runtime_execution"] = False

    summary = build_autonomous_browser_model_comparison_packet(config, repo_root=tmp_path)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"
    assert summary["no_runtime_execution"] is True


def test_model_discrimination_evaluator_missing_outputs_are_marked_safely(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)
    comparison_config_path = tmp_path / summary["comparison_config_path"]

    evaluation = run_autonomous_browser_model_comparison_evaluator(comparison_config_path, repo_root=tmp_path)
    encoded = json.dumps(evaluation, ensure_ascii=False)

    assert evaluation["schema_version"] == EVALUATOR_SUMMARY_SCHEMA_VERSION
    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["error_code"] == "missing_captured_outputs"
    assert evaluation["outputs_total"] == 6
    assert evaluation["outputs_present"] == 0
    assert evaluation["outputs_missing"] == 6
    assert evaluation["outputs_ingested"] == 0
    assert evaluation["outputs_rejected"] == 0
    assert evaluation["no_runtime_execution"] is True
    assert evaluation["model_execution"] is False
    assert evaluation["real_browser_execution"] is False
    assert evaluation["playwright_execution"] is False
    assert evaluation["browser_opened"] is False
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_model_discrimination_one_valid_output_replays_fixture_offline(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)
    output_dir = tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_discrimination_packet"
    raw_output_path = output_dir / "second_model" / "hard_policy_disambiguation" / "raw_planner_output.txt"
    response_path = raw_output_path.with_name("response.json")
    raw_output_path.write_text(VALID_OUTPUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    _write_json(
        response_path,
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": raw_output_path.read_text(encoding="utf-8")},
                }
            ],
            "usage": {"prompt_tokens": 312, "completion_tokens": 185, "total_tokens": 497},
        },
    )

    evaluation = run_autonomous_browser_model_comparison_evaluator(
        tmp_path / summary["comparison_config_path"],
        repo_root=tmp_path,
        execute_fixture=True,
    )

    second_result = next(
        item
        for item in evaluation["scenario_results"]
        if item["model_alias"] == "second_model" and item["scenario_label"] == "hard_policy_disambiguation"
    )

    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["outputs_present"] == 1
    assert evaluation["outputs_missing"] == 5
    assert evaluation["outputs_ingested"] == 1
    assert evaluation["outputs_rejected"] == 0
    assert evaluation["dry_runs_succeeded"] == 1
    assert evaluation["fixture_runs_succeeded"] == 1
    assert evaluation["actions_attempted_total"] == 3
    assert evaluation["expected_results_passed_total"] == 3
    assert second_result["captured_output_present"] is True
    assert second_result["status"] == "succeeded"
    assert second_result["fixture_execution_status"] == "succeeded"
    assert second_result["response_metadata_path"] == "artifacts/autonomous_runtime_summaries/model_discrimination_packet/second_model/hard_policy_disambiguation/response.json"
    assert not Path(second_result["response_metadata_path"]).is_absolute()


def test_model_discrimination_no_playwright_import_or_browser_server_model_use(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)
    comparison_config_path = tmp_path / summary["comparison_config_path"]
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    evaluation = run_autonomous_browser_model_comparison_evaluator(comparison_config_path, repo_root=tmp_path)

    assert evaluation["status"] == "completed_with_missing_outputs"
