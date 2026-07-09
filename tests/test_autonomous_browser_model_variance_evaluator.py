from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_model_variance_evaluator import (
    SUMMARY_SCHEMA_VERSION as EVALUATOR_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_model_variance_evaluator,
)
from src.agent.autonomous_browser_model_variance_packet import (
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_model_variance_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_model_variance_packet.example.json"
CLI_VARIANCE_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_model_variance_evaluator.py"
VALID_OUTPUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "browser_planner_outputs" / "valid_candidate_output.txt"


def _packet_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_valid_trial_output(output_dir: Path, model_alias: str, scenario_id: str, trial_id: str) -> None:
    trial_dir = output_dir / model_alias / scenario_id / trial_id
    trial_dir.mkdir(parents=True, exist_ok=True)
    raw_output_path = trial_dir / "raw_planner_output.txt"
    response_path = trial_dir / "response.json"
    raw_output = VALID_OUTPUT_PATH.read_text(encoding="utf-8")
    raw_output_path.write_text(raw_output, encoding="utf-8")
    _write_json(
        response_path,
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": raw_output},
                }
            ],
            "usage": {"prompt_tokens": 312, "completion_tokens": 185, "total_tokens": 497},
        },
    )


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_outputs_are_marked_without_crashing(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_variance_packet(_packet_config(), repo_root=tmp_path)
    evaluation = run_autonomous_browser_model_variance_evaluator(
        tmp_path / summary["variance_config_path"],
        repo_root=tmp_path,
    )
    encoded = json.dumps(evaluation, ensure_ascii=False)

    assert evaluation["schema_version"] == EVALUATOR_SUMMARY_SCHEMA_VERSION
    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["error_code"] == "missing_captured_outputs"
    assert evaluation["outputs_total"] == 18
    assert evaluation["outputs_present"] == 0
    assert evaluation["outputs_missing"] == 18
    assert evaluation["outputs_ingested"] == 0
    assert evaluation["outputs_rejected"] == 0
    assert evaluation["no_runtime_execution"] is True
    assert evaluation["model_execution"] is False
    assert evaluation["real_browser_execution"] is False
    assert evaluation["playwright_execution"] is False
    assert evaluation["browser_opened"] is False
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_three_repeated_trials_for_one_model_scenario_are_stable(tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_variance_packet(_packet_config(), repo_root=tmp_path)
    output_dir = tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_variance_packet"
    for trial_id in ("trial_01", "trial_02", "trial_03"):
        _write_valid_trial_output(output_dir, "second_model", "hard_policy_disambiguation", trial_id)

    evaluation = run_autonomous_browser_model_variance_evaluator(
        tmp_path / summary["variance_config_path"],
        repo_root=tmp_path,
        execute_fixture=True,
    )

    second_model = next(item for item in evaluation["model_summaries"] if item["alias"] == "second_model")
    policy_scenario = next(
        item
        for item in evaluation["scenario_model_summaries"]
        if item["model_alias"] == "second_model" and item["scenario_id"] == "hard_policy_disambiguation"
    )
    trial_results = [
        item
        for item in evaluation["trial_results"]
        if item["model_alias"] == "second_model" and item["scenario_id"] == "hard_policy_disambiguation"
    ]

    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["outputs_present"] == 3
    assert evaluation["outputs_missing"] == 15
    assert evaluation["outputs_ingested"] == 3
    assert evaluation["dry_runs_succeeded"] == 3
    assert evaluation["fixture_runs_succeeded"] == 3
    assert evaluation["actions_attempted_total"] == 9
    assert evaluation["expected_results_passed_total"] == 9
    assert second_model["outputs_present"] == 3
    assert second_model["outputs_ingested"] == 3
    assert second_model["unique_plan_fingerprints_total"] == 1
    assert second_model["pass_rate_validation"] == 1.0
    assert second_model["pass_rate_fixture"] == 1.0
    assert policy_scenario["trials_total"] == 3
    assert policy_scenario["stable_plan"] is True
    assert len(policy_scenario["unique_plan_fingerprints"]) == 1
    assert all(item["plan_fingerprint"] == policy_scenario["unique_plan_fingerprints"][0] for item in trial_results)
    assert all(item["fixture_execution_status"] == "succeeded" for item in trial_results)


def test_cli_missing_outputs_exits_zero_and_prints_compact_json(tmp_path: Path) -> None:
    config_path = tmp_path / "browser_model_variance_packet.example.json"
    _write_json(config_path, _packet_config())
    build_module = _load_cli_module(PROJECT_ROOT / "scripts" / "build_autonomous_browser_model_variance_packet.py")
    original_project_root = build_module.PROJECT_ROOT
    build_module.PROJECT_ROOT = tmp_path
    try:
        build_module.main(["--config", str(config_path)])
    finally:
        build_module.PROJECT_ROOT = original_project_root

    cli_module = _load_cli_module(CLI_VARIANCE_PATH)
    original_project_root = cli_module.PROJECT_ROOT
    cli_module.PROJECT_ROOT = tmp_path
    try:
        exit_code = cli_module.main(
            [
                "--config",
                str(tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_variance_packet" / "variance_config.local.json"),
            ]
        )
    finally:
        cli_module.PROJECT_ROOT = original_project_root

    payload = json.loads(
        (
            tmp_path
            / "artifacts"
            / "autonomous_runtime_summaries"
            / "model_variance_packet"
            / "evaluation_runs"
            / "autonomous_browser_model_variance_evaluator_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert payload["status"] == "completed_with_missing_outputs"
    assert payload["outputs_missing"] == 18
    assert cli_module._load_config(Path(tmp_path / "artifacts" / "autonomous_runtime_summaries" / "model_variance_packet" / "variance_config.local.json"))["packet_id"] == "browser_model_variance_packet_v1"


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    summary = build_autonomous_browser_model_variance_packet(_packet_config(), repo_root=tmp_path)
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    evaluation = run_autonomous_browser_model_variance_evaluator(
        tmp_path / summary["variance_config_path"],
        repo_root=tmp_path,
    )

    assert evaluation["status"] == "completed_with_missing_outputs"
