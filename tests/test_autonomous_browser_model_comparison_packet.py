from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_model_comparison_evaluator import (
    SUMMARY_SCHEMA_VERSION as EVALUATOR_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_model_comparison_evaluator,
)
from src.agent.autonomous_browser_model_comparison_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_model_comparison_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_model_comparison_packet.example.json"
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


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["packet_id"] == "browser_model_comparison_packet_v1"
    assert summary["model_count"] == 3
    assert summary["scenario_count"] == 3
    assert summary["model_aliases"] == ["first_model", "second_model", "third_model"]
    assert summary["scenario_ids"] == [
        "browser_intranet_policy_research",
        "browser_ticket_triage_review",
        "browser_approval_form_review",
    ]
    assert summary["commands_count"] >= 11
    assert len(summary["expected_raw_output_paths"]) == 9
    assert all(not Path(path).is_absolute() for path in summary["packet_files"])

    output_dir = tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_comparison_packet"
    packet_json_path = output_dir / "model_comparison_packet.json"
    readme_path = output_dir / "README.md"
    commands_path = output_dir / "commands.json"
    commands_md_path = output_dir / "commands.md"
    request_paths_path = output_dir / "request_paths.json"
    output_paths_path = output_dir / "output_paths.json"
    comparison_config_path = output_dir / "comparison_config.local.json"
    prompt_policy_path = output_dir / "prompts" / "policy_family" / "planner_prompt.policy_family.compact.txt"
    prompt_ticket_path = output_dir / "prompts" / "ticket_triage" / "planner_prompt.ticket_triage.compact.txt"
    prompt_approval_path = output_dir / "prompts" / "approval_review" / "planner_prompt.approval_review.compact.txt"

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
    assert request_paths["first_model"]["policy_family"].endswith("first_model/policy_family/request.json")
    assert request_paths["second_model"]["ticket_triage"].endswith("second_model/ticket_triage/request.json")
    assert request_paths["third_model"]["approval_review"].endswith("third_model/approval_review/request.json")
    assert output_paths["third_model"]["approval_review"].endswith("third_model/approval_review/raw_planner_output.txt")
    assert comparison_config["models"][2]["model_path"] == "models/gguf/third_model.gguf"
    assert comparison_config["models"][2]["prompt_prefix"] == "/no_think"
    assert comparison_config["scenarios"][2]["max_tokens"] >= 1200
    assert "third_model" in commands_md
    assert "models/gguf/third_model.gguf" in commands_md
    assert "planner_prompt.policy_family.compact.txt" in commands_md
    assert "planner_prompt.ticket_triage.compact.txt" in commands_md
    assert "planner_prompt.approval_review.compact.txt" in commands_md
    assert any(command["id"] == "run_model_comparison_evaluator" for command in commands["commands"])

    policy_prompt = prompt_policy_path.read_text(encoding="utf-8")
    ticket_prompt = prompt_ticket_path.read_text(encoding="utf-8")
    approval_prompt = prompt_approval_path.read_text(encoding="utf-8")
    third_model_request = json.loads(
        (output_dir / "third_model" / "policy_family" / "request.json").read_text(encoding="utf-8")
    )
    assert "Return only valid JSON." in policy_prompt
    assert "No markdown." in ticket_prompt
    assert "No markdown." in approval_prompt
    assert third_model_request["messages"][1]["content"].startswith("/no_think\n")
    assert "local.intranet" in policy_prompt
    assert "Ticket 1" in ticket_prompt
    assert "Approvals queue" in approval_prompt

    encoded = json.dumps(summary, ensure_ascii=False)
    assert "supersecret" not in encoded
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_packet_builder_rejects_invalid_config(tmp_path: Path) -> None:
    config = _packet_config()
    config["no_runtime_execution"] = False

    summary = build_autonomous_browser_model_comparison_packet(config, repo_root=tmp_path)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"
    assert summary["no_runtime_execution"] is True


def test_third_model_path_is_documentation_only(tmp_path: Path) -> None:
    config = _packet_config()

    summary = build_autonomous_browser_model_comparison_packet(config, repo_root=tmp_path)
    comparison_config = json.loads(
        (tmp_path / summary["comparison_config_path"]).read_text(encoding="utf-8")
    )

    assert comparison_config["models"][2]["alias"] == "third_model"
    assert comparison_config["models"][2]["model_path"] == "models/gguf/third_model.gguf"


def test_cli_success_exits_zero_and_prints_compact_json(tmp_path: Path) -> None:
    config_path = tmp_path / "browser_model_comparison_packet.example.json"
    _write_json(config_path, _packet_config())
    cli_module = _load_cli_module(CLI_BUILD_PATH)
    original_project_root = cli_module.PROJECT_ROOT
    cli_module.PROJECT_ROOT = tmp_path
    try:
        exit_code = cli_module.main(["--config", str(config_path)])
    finally:
        cli_module.PROJECT_ROOT = original_project_root

    payload = json.loads((tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_comparison_packet" / "autonomous_browser_model_comparison_packet_summary.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "succeeded"
    assert payload["packet_id"] == "browser_model_comparison_packet_v1"


def test_evaluator_missing_outputs_are_marked_without_crashing(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)
    comparison_config_path = tmp_path / summary["comparison_config_path"]

    evaluation = run_autonomous_browser_model_comparison_evaluator(comparison_config_path, repo_root=tmp_path)
    encoded = json.dumps(evaluation, ensure_ascii=False)

    assert evaluation["schema_version"] == EVALUATOR_SUMMARY_SCHEMA_VERSION
    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["error_code"] == "missing_captured_outputs"
    assert evaluation["outputs_total"] == 9
    assert evaluation["outputs_present"] == 0
    assert evaluation["outputs_missing"] == 9
    assert evaluation["outputs_ingested"] == 0
    assert evaluation["outputs_rejected"] == 0
    assert evaluation["no_runtime_execution"] is True
    assert evaluation["model_execution"] is False
    assert evaluation["real_browser_execution"] is False
    assert evaluation["playwright_execution"] is False
    assert evaluation["browser_opened"] is False
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_evaluator_one_valid_captured_output_aggregates_metrics(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)
    output_dir = tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_comparison_packet"
    raw_output_path = output_dir / "first_model" / "policy_family" / "raw_planner_output.txt"
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

    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["outputs_present"] == 1
    assert evaluation["outputs_missing"] == 8
    assert evaluation["outputs_ingested"] == 1
    assert evaluation["outputs_rejected"] == 0
    assert evaluation["dry_runs_succeeded"] == 1
    assert evaluation["fixture_runs_succeeded"] == 1
    assert evaluation["actions_attempted_total"] == 3
    assert evaluation["expected_results_passed_total"] == 3

    first_model = next(item for item in evaluation["model_summaries"] if item["alias"] == "first_model")
    third_model = next(item for item in evaluation["model_summaries"] if item["alias"] == "third_model")
    policy_result = next(
        item
        for item in evaluation["scenario_results"]
        if item["model_alias"] == "first_model" and item["scenario_label"] == "policy_family"
    )

    assert first_model["outputs_present"] == 1
    assert first_model["outputs_missing"] == 2
    assert first_model["outputs_ingested"] == 1
    assert first_model["actions_attempted_total"] == 3
    assert first_model["expected_results_passed_total"] == 3
    assert third_model["outputs_present"] == 0
    assert policy_result["captured_output_present"] is True
    assert policy_result["finish_reason"] == "stop"
    assert policy_result["prompt_tokens"] == 312
    assert policy_result["completion_tokens"] == 185
    assert policy_result["total_tokens"] == 497
    assert policy_result["response_metadata_path"] == "artifacts/autonomous_runtime_summaries/model_comparison_packet/first_model/policy_family/response.json"
    assert not Path(policy_result["response_metadata_path"]).is_absolute()


def test_fixture_root_fallback_uses_repo_local_manifest_for_temp_packet_root(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_comparison_packet(_packet_config(), repo_root=tmp_path)
    output_dir = tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_comparison_packet"
    raw_output_path = output_dir / "first_model" / "policy_family" / "raw_planner_output.txt"
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

    assert not (tmp_path / "tests" / "fixtures" / "local_intranet" / "office_site_v1" / "site_manifest.json").exists()
    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["outputs_ingested"] == 1
    assert evaluation["fixture_runs_succeeded"] == 1
    first_result = next(
        item
        for item in evaluation["scenario_results"]
        if item["model_alias"] == "first_model" and item["scenario_label"] == "policy_family"
    )
    assert first_result["status"] == "succeeded"
    assert first_result["model_execution"] is False
    assert first_result["real_browser_execution"] is False
    assert first_result["playwright_execution"] is False
    assert first_result["browser_opened"] is False


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_cli_evaluator_smoke_with_missing_outputs_exits_zero(tmp_path: Path) -> None:
    config_path = tmp_path / "browser_model_comparison_packet.example.json"
    _write_json(config_path, _packet_config())
    build_module = _load_cli_module(CLI_BUILD_PATH)
    original_project_root = build_module.PROJECT_ROOT
    build_module.PROJECT_ROOT = tmp_path
    try:
        build_module.main(["--config", str(config_path)])
    finally:
        build_module.PROJECT_ROOT = original_project_root

    evaluator_module = _load_cli_module(CLI_EVALUATOR_PATH)
    original_project_root = evaluator_module.PROJECT_ROOT
    evaluator_module.PROJECT_ROOT = tmp_path
    try:
        exit_code = evaluator_module.main(
            [
                "--config",
                str(tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_comparison_packet" / "comparison_config.local.json"),
            ]
        )
    finally:
        evaluator_module.PROJECT_ROOT = original_project_root

    payload = json.loads(
        (tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_comparison_packet" / "evaluation_runs" / "autonomous_browser_model_comparison_evaluator_summary.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert payload["status"] == "completed_with_missing_outputs"
    assert payload["outputs_missing"] == 9
