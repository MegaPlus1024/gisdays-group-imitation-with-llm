from __future__ import annotations

import builtins
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_stateful_readonly_planner_variance import (
    EVALUATOR_SUMMARY_SCHEMA_VERSION,
    MATERIALIZER_SUMMARY_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
    PACKET_SUMMARY_SCHEMA_VERSION,
    RUNTIME_CONFIG_SCHEMA_VERSION,
    build_autonomous_browser_stateful_readonly_planner_variance_packet,
    run_autonomous_browser_stateful_readonly_planner_variance_evaluator,
    run_autonomous_browser_stateful_readonly_planner_variance_materializer,
)
from src.agent.autonomous_browser_stateful_readonly_workflow import build_default_stateful_readonly_workflow_scenarios

from tests import test_autonomous_browser_stateful_readonly_planner_evaluator as planner_evaluator_tests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_stateful_readonly_planner_variance.example.json"
PACKET_CLI_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_stateful_readonly_planner_variance_packet.py"
EVALUATOR_CLI_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_stateful_readonly_planner_variance_evaluator.py"
MATERIALIZER_CLI_PATH = PROJECT_ROOT / "scripts" / "materialize_autonomous_browser_stateful_readonly_planner_variance_outputs.py"
PACKET_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner_variance"
MATERIALIZED_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_planner_variance_materialized"
BASE_PACKET_CONFIG_RELATIVE = Path("configs/autonomous_runtime/browser_stateful_readonly_planner_packet.example.json")


def _config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _stage_base_packet_config(repo_root: Path) -> None:
    destination = repo_root / BASE_PACKET_CONFIG_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT_ROOT / BASE_PACKET_CONFIG_RELATIVE, destination)


def _build_packet(tmp_path: Path, config: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
    _stage_base_packet_config(tmp_path)
    summary = build_autonomous_browser_stateful_readonly_planner_variance_packet(config or _config(), repo_root=tmp_path)
    return summary, tmp_path / PACKET_OUTPUT_DIR


def _write_outputs(packet_summary: dict[str, Any], repo_root: Path) -> None:
    scenarios = build_default_stateful_readonly_workflow_scenarios()
    for record in packet_summary["request_records"]:
        scenario = scenarios[str(record["scenario_id"])]
        payload = planner_evaluator_tests._output_for_scenario(scenario)
        raw_output_path = repo_root / str(record["raw_output_path"])
        response_path = repo_root / str(record["response_path"])
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output = json.dumps(payload, ensure_ascii=False, indent=2)
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


def _rewrite_runtime_config_with_bom(packet_dir: Path) -> Path:
    runtime_config_path = packet_dir / "variance_config.local.json"
    runtime_config = runtime_config_path.read_text(encoding="utf-8")
    runtime_config_path.write_text(runtime_config, encoding="utf-8-sig")
    return runtime_config_path


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    _stage_base_packet_config(tmp_path)
    summary = build_autonomous_browser_stateful_readonly_planner_variance_packet(_config(), repo_root=tmp_path)
    output_dir = tmp_path / PACKET_OUTPUT_DIR

    assert summary["schema_version"] == PACKET_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["packet_id"] == "phase_13e4_stateful_readonly_planner_variance"
    assert summary["models_total"] == 1
    assert summary["scenarios_total"] == 5
    assert summary["trials_per_scenario"] == 3
    assert summary["trials_total"] == 15
    assert summary["model_aliases"] == ["third_model"]
    assert summary["scenario_ids"] == [
        "stateful_policy_ticket_crosscheck",
        "stateful_approval_policy_crosscheck",
        "stateful_intranet_overview_digest",
        "stateful_ticket_priority_digest",
        "stateful_policy_search_marker_review",
    ]
    assert summary["trial_ids"] == ["trial_01", "trial_02", "trial_03"]
    assert summary["commands_count"] == 40
    assert len(summary["request_records"]) == 15
    assert len(summary["packet_files"]) >= 12
    assert all(not Path(item).is_absolute() for item in summary["packet_files"])

    packet_path = output_dir / "autonomous_browser_stateful_readonly_planner_variance_packet.json"
    summary_path = output_dir / "autonomous_browser_stateful_readonly_planner_variance_packet_summary.json"
    commands_path = output_dir / "commands.json"
    commands_md_path = output_dir / "commands.md"
    request_paths_path = output_dir / "request_paths.json"
    output_paths_path = output_dir / "output_paths.json"
    trial_records_path = output_dir / "request_records.json"
    runtime_config_path = output_dir / "variance_config.local.json"
    schema_doc_path = output_dir / "expected_output_schema.md"
    prompt_path = output_dir / "prompts" / "stateful_policy_ticket_crosscheck" / "planner_prompt.compact.txt"

    for path in (
        packet_path,
        summary_path,
        commands_path,
        commands_md_path,
        request_paths_path,
        output_paths_path,
        trial_records_path,
        runtime_config_path,
        schema_doc_path,
        prompt_path,
    ):
        assert path.exists()

    packet_json = json.loads(packet_path.read_text(encoding="utf-8"))
    commands = json.loads(commands_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")
    request_paths = json.loads(request_paths_path.read_text(encoding="utf-8"))
    output_paths = json.loads(output_paths_path.read_text(encoding="utf-8"))
    trial_records = json.loads(trial_records_path.read_text(encoding="utf-8"))
    runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert packet_json["schema_version"] == PACKET_SCHEMA_VERSION
    assert packet_json["packet_id"] == "phase_13e4_stateful_readonly_planner_variance"
    assert packet_json["model_aliases"] == ["third_model"]
    assert packet_json["trials_per_scenario"] == 3
    assert packet_json["request_count"] == 15
    assert request_paths["third_model"]["stateful_ticket_priority_digest"]["trial_03"].endswith(
        "third_model/stateful_ticket_priority_digest/trial_03/request.json"
    )
    assert output_paths["third_model"]["stateful_approval_policy_crosscheck"]["trial_02"].endswith(
        "third_model/stateful_approval_policy_crosscheck/trial_02/raw_planner_output.txt"
    )
    assert len(trial_records) == 15
    assert runtime_config["schema_version"] == RUNTIME_CONFIG_SCHEMA_VERSION
    assert runtime_config["packet_id"] == "phase_13e4_stateful_readonly_planner_variance"
    assert len(runtime_config["trial_records"]) == 15
    assert len(runtime_config["captured_outputs"]) == 15
    assert runtime_config["models"][0]["alias"] == "third_model"
    assert runtime_config["models"][0]["model_path"] == "models/gguf/third_model.gguf"
    assert runtime_config["models"][0]["prompt_prefix"] == "/no_think"
    assert "planner_prompt.compact.txt" in commands_md
    assert "Use `planner_prompt.compact.txt` as the prompt source for each trial." in commands_md
    assert "models/gguf/third_model.gguf" in commands_md
    assert "run_autonomous_browser_stateful_readonly_planner_variance_evaluator.py" in commands_md
    assert "materialize_autonomous_browser_stateful_readonly_planner_variance_outputs.py" in commands_md
    assert "Get-Content" in commands_md
    assert "trial_03" in commands_md
    assert any(command["id"] == "build_stateful_readonly_planner_variance_packet" for command in commands["commands"])
    assert any(command["id"] == "run_stateful_readonly_planner_variance_evaluator" for command in commands["commands"])
    assert any(command["id"] == "run_stateful_readonly_planner_variance_materializer" for command in commands["commands"])
    assert any(command["id"] == "run_pytest" for command in commands["commands"])
    assert "Return exactly one JSON object" in prompt_text
    assert "Ticket board" in prompt_text
    assert "Workspace Policy" in prompt_text
    assert "final_answer.answer_text" in prompt_text


def test_build_cli_accepts_bom_config_and_prints_compact_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "browser_stateful_readonly_planner_variance.example.json"
    config_path.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8-sig")
    _stage_base_packet_config(tmp_path)

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
    assert payload["no_runtime_execution"] is True
    assert payload["model_execution"] is False
    assert payload["real_browser_execution"] is False


def test_evaluator_and_materializer_accept_bom_runtime_config_and_replay() -> None:
    short_root = Path("C:/tmp")
    short_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="variance_", dir=short_root) as temp_dir:
        repo_root = Path(temp_dir)
        packet_summary, packet_dir = _build_packet(repo_root)
        _write_outputs(packet_summary, repo_root)
        runtime_config_path = _rewrite_runtime_config_with_bom(packet_dir)

        evaluation = run_autonomous_browser_stateful_readonly_planner_variance_evaluator(runtime_config_path, repo_root=repo_root)
        materialized = run_autonomous_browser_stateful_readonly_planner_variance_materializer(runtime_config_path, repo_root=repo_root)

        assert evaluation["schema_version"] == EVALUATOR_SUMMARY_SCHEMA_VERSION
        assert evaluation["status"] == "succeeded"
        assert evaluation["error_code"] is None
        assert evaluation["outputs_total"] == 15
        assert evaluation["outputs_present"] == 15
        assert evaluation["outputs_missing"] == 0
        assert evaluation["outputs_ingested"] == 15
        assert evaluation["outputs_rejected"] == 0
        assert evaluation["workflows_succeeded"] == 15
        assert evaluation["workflows_failed"] == 0
        assert evaluation["finish_reason_counts"] == {"stop": 15}
        assert evaluation["no_runtime_execution"] is True
        assert evaluation["model_execution"] is False
        assert evaluation["real_browser_execution"] is False
        assert evaluation["playwright_execution"] is False
        assert evaluation["browser_opened"] is False
        assert evaluation["real_network_traffic"] is False
        assert evaluation["fixture_only"] is True
        assert len(evaluation["scenario_summaries"]) == 5
        assert len(evaluation["trial_summaries"]) == 15
        assert len(evaluation["output_summaries"]) == 15

        assert materialized["schema_version"] == MATERIALIZER_SUMMARY_SCHEMA_VERSION
        assert materialized["status"] == "succeeded"
        assert materialized["error_code"] is None
        assert materialized["outputs_total"] == 15
        assert materialized["outputs_present"] == 15
        assert materialized["outputs_missing"] == 0
        assert materialized["outputs_accepted"] == 15
        assert materialized["outputs_rejected"] == 0
        assert materialized["workflows_materialized"] == 15
        assert materialized["workflows_failed"] == 0
        assert materialized["actions_total"] > 0
        assert materialized["facts_total"] > 0
        assert materialized["evidence_items_total"] > 0
        assert materialized["final_answers_total"] == 15
        assert materialized["no_runtime_execution"] is True
        assert materialized["model_execution"] is False
        assert materialized["real_browser_execution"] is False
        assert materialized["playwright_execution"] is False
        assert materialized["browser_opened"] is False
        assert materialized["real_network_traffic"] is False
        assert materialized["fixture_only"] is True
        assert len(materialized["scenario_summaries"]) == 5
        assert len(materialized["trial_summaries"]) == 15
        assert len(materialized["output_summaries"]) == 15

        first_output = materialized["output_summaries"][0]
        assert not Path(first_output["state_path"]).is_absolute()
        assert not Path(first_output["trace_path"]).is_absolute()
        assert not Path(first_output["workflow_summary_path"]).is_absolute()
        assert first_output["state_path"].endswith("materialized_state.json")
        assert first_output["trace_path"].endswith("materialized_trace.json")
        assert first_output["workflow_summary_path"].endswith("materialized_workflow_summary.json")


def test_cli_invalid_config_returns_structured_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "invalid_variance.json"
    _write_json(config_path, {"schema_version": "wrong"})

    module = _load_cli_module(PACKET_CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--config", str(config_path)])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["schema_version"] == "autonomous_browser_stateful_readonly_planner_variance_packet_summary_v1"
    assert payload["status"] == "failed"
    assert payload["error_code"] == "config_validation_failed"


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    _stage_base_packet_config(tmp_path)
    summary = build_autonomous_browser_stateful_readonly_planner_variance_packet(_config(), repo_root=tmp_path)

    assert summary["status"] == "succeeded"
