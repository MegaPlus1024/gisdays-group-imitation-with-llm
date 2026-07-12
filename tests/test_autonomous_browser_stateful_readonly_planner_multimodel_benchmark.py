from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_stateful_readonly_planner_multimodel_benchmark import (
    BUILD_CONFIG_SCHEMA_VERSION,
    EVALUATOR_SUMMARY_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
    PACKET_SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet,
    run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator,
)
from src.agent.autonomous_browser_stateful_readonly_workflow import (
    build_default_stateful_readonly_workflow_scenarios,
)

from tests import test_autonomous_browser_stateful_readonly_planner_evaluator as planner_evaluator_tests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    PROJECT_ROOT
    / "configs"
    / "autonomous_runtime"
    / "browser_stateful_readonly_planner_multimodel_benchmark.example.json"
)
EXTENDED_CONFIG_PATH = (
    PROJECT_ROOT
    / "configs"
    / "autonomous_runtime"
    / "browser_stateful_readonly_planner_multimodel_benchmark_extended.example.json"
)
BASE_PACKET_CONFIG = (
    PROJECT_ROOT
    / "configs"
    / "autonomous_runtime"
    / "browser_stateful_readonly_planner_packet.example.json"
)
EVALUATION_MODELS_CONFIG = PROJECT_ROOT / "configs" / "evaluation_models.json"
PACKET_CLI_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet.py"
)
EVALUATOR_CLI_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator.py"
)
PACKET_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner_multimodel_benchmark"
CAPTURED_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner_multimodel_benchmark"
EVALUATOR_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_summaries/stateful_readonly_planner_multimodel_benchmark"


def _config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _extended_config() -> dict[str, Any]:
    return json.loads(EXTENDED_CONFIG_PATH.read_text(encoding="utf-8"))


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage_support_files(
    repo_root: Path,
    *,
    bom: bool = False,
    config_path: Path = CONFIG_PATH,
) -> Path:
    packet_destination = repo_root / "configs" / "autonomous_runtime" / BASE_PACKET_CONFIG.name
    packet_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE_PACKET_CONFIG, packet_destination)

    eval_destination = repo_root / "configs" / EVALUATION_MODELS_CONFIG.name
    eval_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EVALUATION_MODELS_CONFIG, eval_destination)

    config_destination = repo_root / "configs" / "autonomous_runtime" / config_path.name
    config_destination.parent.mkdir(parents=True, exist_ok=True)
    config_text = config_path.read_text(encoding="utf-8")
    config_destination.write_text(config_text, encoding="utf-8-sig" if bom else "utf-8")
    return config_destination


def _build_packet(
    repo_root: Path,
    config: dict[str, Any] | None = None,
    *,
    config_path: Path = CONFIG_PATH,
) -> tuple[dict[str, Any], Path]:
    _stage_support_files(repo_root, config_path=config_path)
    summary = build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet(
        config or json.loads(config_path.read_text(encoding="utf-8")),
        repo_root=repo_root,
    )
    return summary, repo_root / str(summary["output_dir"])


def _write_outputs(packet_summary: dict[str, Any], repo_root: Path, *, model_aliases: set[str]) -> None:
    scenarios = build_default_stateful_readonly_workflow_scenarios()
    for record in packet_summary["request_records"]:
        if str(record["model_alias"]) not in model_aliases:
            continue
        scenario = scenarios[str(record["scenario_id"])]
        payload = planner_evaluator_tests._output_for_scenario(scenario)
        raw_output_path = repo_root / str(record["raw_output_path"])
        response_path = repo_root / str(record["response_path"])
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_text = json.dumps(payload, ensure_ascii=False, indent=2)
        raw_output_path.write_text(raw_text, encoding="utf-8")
        response_path.write_text(
            json.dumps(
                {
                    "choices": [{"finish_reason": "stop", "message": {"content": raw_text}}],
                    "usage": {"prompt_tokens": 312, "completion_tokens": 185, "total_tokens": 497},
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    summary, output_dir = _build_packet(tmp_path)

    assert summary["schema_version"] == PACKET_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["packet_id"] == "phase_14_stateful_readonly_planner_multimodel_benchmark"
    assert summary["models_total"] == 2
    assert summary["model_aliases"] == ["second_model", "third_model"]
    assert summary["scenarios_total"] == 5
    assert summary["trials_per_scenario"] == 3
    assert summary["requests_total"] == 30
    assert summary["fixture_only"] is True
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert len(summary["request_records"]) == 30

    manifest_path = output_dir / "benchmark_packet.json"
    summary_path = output_dir / "benchmark_packet_summary.json"
    commands_md_path = output_dir / "commands.md"
    request_paths_path = output_dir / "request_paths.json"
    output_paths_path = output_dir / "output_paths.json"
    request_records_path = output_dir / "request_records.json"
    schema_doc_path = output_dir / "expected_output_schema.md"

    for path in (
        manifest_path,
        summary_path,
        commands_md_path,
        request_paths_path,
        output_paths_path,
        request_records_path,
        schema_doc_path,
    ):
        assert path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    request_paths = json.loads(request_paths_path.read_text(encoding="utf-8"))
    output_paths = json.loads(output_paths_path.read_text(encoding="utf-8"))
    request_records = json.loads(request_records_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")

    assert manifest["schema_version"] == PACKET_SCHEMA_VERSION
    assert manifest["model_aliases"] == ["second_model", "third_model"]
    assert manifest["requests_total"] == 30
    assert request_paths["second_model"]["stateful_policy_ticket_crosscheck"]["trial_01"].endswith(
        "second_model/stateful_policy_ticket_crosscheck/trial_01/request.json"
    )
    assert request_paths["third_model"]["stateful_ticket_priority_digest"]["trial_03"].endswith(
        "third_model/stateful_ticket_priority_digest/trial_03/request.json"
    )
    assert output_paths["third_model"]["stateful_approval_policy_crosscheck"]["trial_02"].endswith(
        "third_model/stateful_approval_policy_crosscheck/trial_02/raw_planner_output.txt"
    )
    assert len(request_records) == 30
    assert any(item["model_alias"] == "second_model" for item in request_records)
    assert any(item["model_alias"] == "third_model" for item in request_records)
    assert "planner_prompt.compact.txt" in commands_md
    assert "second_model" in commands_md
    assert "third_model" in commands_md
    assert "models/gguf/second_model.gguf" in commands_md
    assert "models/gguf/third_model.gguf" in commands_md
    assert "must not be committed" in commands_md
    assert all(not Path(item).is_absolute() for item in summary["packet_files"])


def test_builder_cli_accepts_bom_config_and_prints_compact_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _stage_support_files(tmp_path, bom=True)

    module = _load_cli_module(PACKET_CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--config", str(config_path)])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == PACKET_SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["requests_total"] == 30
    assert payload["model_aliases"] == ["second_model", "third_model"]


def test_evaluator_reports_missing_outputs_per_model(tmp_path: Path) -> None:
    _, packet_dir = _build_packet(tmp_path)
    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator(
        packet_dir=packet_dir,
        repo_root=tmp_path,
    )

    second_model = next(item for item in summary["model_summaries"] if item["alias"] == "second_model")
    third_model = next(item for item in summary["model_summaries"] if item["alias"] == "third_model")

    assert summary["schema_version"] == EVALUATOR_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "completed_with_missing_outputs"
    assert summary["error_code"] == "missing_captured_outputs"
    assert summary["outputs_total"] == 30
    assert summary["outputs_present"] == 0
    assert summary["outputs_missing"] == 30
    assert summary["outputs_ingested"] == 0
    assert summary["outputs_rejected"] == 0
    assert summary["validation_accepted"] == 0
    assert summary["validation_rejected"] == 0
    assert summary["workflows_succeeded"] == 0
    assert summary["workflows_failed"] == 30
    assert summary["best_model_by_pass_rate"] == "second_model"
    assert summary["fully_successful_models"] == []
    assert summary["missing_output_models"] == ["second_model", "third_model"]
    assert second_model["outputs_total"] == 15
    assert second_model["outputs_missing"] == 15
    assert second_model["pass_rate_overall"] == 0.0
    assert third_model["outputs_total"] == 15
    assert third_model["outputs_missing"] == 15
    assert third_model["pass_rate_overall"] == 0.0
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_network_traffic"] is False
    assert summary["fixture_only"] is True


def test_evaluator_mixed_models_and_best_model_selection(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_outputs(packet_summary, tmp_path, model_aliases={"third_model"})

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator(
        packet_dir=packet_dir,
        repo_root=tmp_path,
    )

    second_model = next(item for item in summary["model_summaries"] if item["alias"] == "second_model")
    third_model = next(item for item in summary["model_summaries"] if item["alias"] == "third_model")

    assert summary["status"] == "completed_with_missing_outputs"
    assert summary["error_code"] == "missing_captured_outputs"
    assert summary["outputs_total"] == 30
    assert summary["outputs_present"] == 15
    assert summary["outputs_missing"] == 15
    assert summary["outputs_ingested"] == 15
    assert summary["outputs_rejected"] == 0
    assert summary["validation_accepted"] == 15
    assert summary["validation_rejected"] == 0
    assert summary["workflows_succeeded"] == 15
    assert summary["workflows_failed"] == 15
    assert summary["pass_rate_overall"] == 0.5
    assert summary["validation_acceptance_rate"] == 1.0
    assert summary["best_model_by_pass_rate"] == "third_model"
    assert summary["fully_successful_models"] == ["third_model"]
    assert summary["missing_output_models"] == ["second_model"]
    assert second_model["outputs_present"] == 0
    assert second_model["outputs_missing"] == 15
    assert second_model["validation_accepted"] == 0
    assert second_model["workflows_succeeded"] == 0
    assert second_model["pass_rate_overall"] == 0.0
    assert third_model["outputs_present"] == 15
    assert third_model["outputs_missing"] == 0
    assert third_model["outputs_ingested"] == 15
    assert third_model["validation_accepted"] == 15
    assert third_model["workflows_succeeded"] == 15
    assert third_model["workflows_failed"] == 0
    assert third_model["pass_rate_overall"] == 1.0
    assert third_model["validation_acceptance_rate"] == 1.0
    assert len(summary["output_summaries"]) == 30


def test_evaluator_cli_reports_missing_outputs_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _build_packet(tmp_path)

    module = _load_cli_module(EVALUATOR_CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--packet-dir", PACKET_OUTPUT_DIR])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["schema_version"] == EVALUATOR_SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "completed_with_missing_outputs"
    assert payload["error_code"] == "missing_captured_outputs"
    assert payload["best_model_by_pass_rate"] == "second_model"
    assert payload["no_runtime_execution"] is True
    assert payload["model_execution"] is False


def test_extended_config_includes_four_model_aliases() -> None:
    config = _extended_config()

    assert config["schema_version"] == BUILD_CONFIG_SCHEMA_VERSION
    assert config["model_aliases"] == ["second_model", "third_model", "fourth_model", "fifth_model"]
    assert config["trials_per_scenario"] == 3


def test_extended_packet_builder_creates_sixty_requests_without_model_calls(tmp_path: Path) -> None:
    summary, output_dir = _build_packet(tmp_path, _extended_config(), config_path=EXTENDED_CONFIG_PATH)

    assert summary["status"] == "succeeded"
    assert summary["models_total"] == 4
    assert summary["model_aliases"] == ["second_model", "third_model", "fourth_model", "fifth_model"]
    assert summary["scenarios_total"] == 5
    assert summary["trials_per_scenario"] == 3
    assert summary["requests_total"] == 60
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["fixture_only"] is True
    assert output_dir.name == "stateful_readonly_planner_multimodel_benchmark_extended"

    manifest = json.loads(
        (output_dir / "benchmark_packet.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["requests_total"] == 60
    assert manifest["model_aliases"] == ["second_model", "third_model", "fourth_model", "fifth_model"]


def test_extended_evaluator_classifies_missing_outputs_for_all_aliases(tmp_path: Path) -> None:
    _, packet_dir = _build_packet(tmp_path, _extended_config(), config_path=EXTENDED_CONFIG_PATH)

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator(
        packet_dir=packet_dir,
        repo_root=tmp_path,
    )

    aliases = [item["alias"] for item in summary["model_summaries"]]
    assert summary["status"] == "completed_with_missing_outputs"
    assert summary["error_code"] == "missing_captured_outputs"
    assert summary["models_total"] == 4
    assert summary["outputs_total"] == 60
    assert summary["outputs_present"] == 0
    assert summary["outputs_missing"] == 60
    assert summary["outputs_ingested"] == 0
    assert summary["outputs_rejected"] == 0
    assert aliases == ["second_model", "third_model", "fourth_model", "fifth_model"]
    assert summary["missing_output_models"] == ["second_model", "third_model", "fourth_model", "fifth_model"]
    assert summary["best_model_by_pass_rate"] == "fifth_model"
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_network_traffic"] is False
    assert summary["fixture_only"] is True
    assert all(item["outputs_total"] == 15 for item in summary["model_summaries"])
    assert all(item["outputs_missing"] == 15 for item in summary["model_summaries"])
