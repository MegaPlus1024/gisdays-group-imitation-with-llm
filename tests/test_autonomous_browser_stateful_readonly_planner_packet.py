from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_stateful_readonly_planner_packet import (
    CONFIG_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    build_autonomous_browser_stateful_readonly_planner_packet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_stateful_readonly_planner_packet.example.json"
CLI_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_stateful_readonly_planner_packet.py"
PACKET_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner"


def _config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    summary = build_autonomous_browser_stateful_readonly_planner_packet(_config(), repo_root=tmp_path)
    output_dir = tmp_path / PACKET_OUTPUT_DIR

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["packet_id"] == "phase_13e2_stateful_readonly_local_planner"
    assert summary["planner_backend"] == "local_model_manual"
    assert summary["model_aliases"] == ["third_model"]
    assert summary["scenarios_total"] == 5
    assert summary["requests_total"] == 5
    assert summary["commands_count"] == 18
    assert len(summary["request_records"]) == 5
    assert len(summary["packet_files"]) >= 8
    assert all(not Path(item).is_absolute() for item in summary["packet_files"])
    assert summary["request_records"][0]["max_tokens"] == 1800

    packet_path = output_dir / "autonomous_browser_stateful_readonly_planner_packet.json"
    summary_path = output_dir / "autonomous_browser_stateful_readonly_planner_packet_summary.json"
    commands_path = output_dir / "commands.json"
    commands_md_path = output_dir / "commands.md"
    schema_doc_path = output_dir / "expected_output_schema.md"
    prompt_path = output_dir / "prompts" / "stateful_policy_ticket_crosscheck" / "planner_prompt.compact.txt"
    approval_prompt_path = output_dir / "prompts" / "stateful_approval_policy_crosscheck" / "planner_prompt.compact.txt"
    ticket_priority_prompt_path = output_dir / "prompts" / "stateful_ticket_priority_digest" / "planner_prompt.compact.txt"

    assert packet_path.exists()
    assert summary_path.exists()
    assert commands_path.exists()
    assert commands_md_path.exists()
    assert schema_doc_path.exists()
    assert prompt_path.exists()
    assert approval_prompt_path.exists()
    assert ticket_priority_prompt_path.exists()

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    commands = json.loads(commands_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")
    prompt_text = prompt_path.read_text(encoding="utf-8")
    approval_prompt_text = approval_prompt_path.read_text(encoding="utf-8")
    ticket_priority_prompt_text = ticket_priority_prompt_path.read_text(encoding="utf-8")

    assert packet["schema_version"] == PACKET_SCHEMA_VERSION
    assert packet["packet_id"] == "phase_13e2_stateful_readonly_local_planner"
    assert packet["planner_backend"] == "local_model_manual"
    assert packet["model_aliases"] == ["third_model"]
    assert packet["scenarios"] == [
        "stateful_policy_ticket_crosscheck",
        "stateful_approval_policy_crosscheck",
        "stateful_intranet_overview_digest",
        "stateful_ticket_priority_digest",
        "stateful_policy_search_marker_review",
    ]
    assert packet["prompt_prefixes"]["third_model"] == "/no_think"
    assert packet["output_dir"] == PACKET_OUTPUT_DIR
    assert packet["captured_output_dir"] == "artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner"

    assert "planner_prompt.compact.txt" in commands_md
    assert "Use `planner_prompt.compact.txt` as the prompt source for each trial." in commands_md
    assert "--execute-fixture" in commands_md
    assert "models/gguf/third_model.gguf" in commands_md
    assert "Codex must not launch models." in commands_md
    assert "run_autonomous_browser_stateful_readonly_planner_evaluator.py" in commands_md

    evaluator_command = next(item for item in commands["commands"] if item["id"] == "run_stateful_readonly_planner_evaluator")
    assert "--execute-fixture" in evaluator_command["command"]
    assert evaluator_command["manual_only"] is False
    assert any(item["id"] == "run_pytest" for item in commands["commands"])

    assert "Stateful Read-Only Planner Prompt" in prompt_text
    assert "Return valid strict JSON with no trailing commas." in prompt_text
    assert '"action_name": "browser_open_url"' in prompt_text
    assert '"parameters": {' in prompt_text
    assert "Do NOT use the field name `action`." in prompt_text
    assert "For `browser_click` use `parameters.target_text`, not `selector`." in prompt_text
    assert "Ticket board" in prompt_text
    assert "Workspace Policy" in prompt_text
    assert "browser_click" in prompt_text
    assert "confidence` is optional" in prompt_text
    assert "low`, `medium`, or `high`" in prompt_text
    assert "fixture-backed" in prompt_text
    assert "a[href" not in prompt_text
    assert "queryselector" not in prompt_text.lower()
    assert "https://local.intranet/tickets/hardboard" in ticket_priority_prompt_text
    assert "Priority cross-check board" in ticket_priority_prompt_text
    assert "Requester tier: facilities." in ticket_priority_prompt_text
    assert "After Ticket 7, reopen the hardboard with browser_open_url before continuing to Ticket 8." in ticket_priority_prompt_text
    assert "policy_marker must be copied exactly from the visible Workspace Policy search marker text: fixture-backed result for workspace policy review." in prompt_text
    assert "Do not invent policy sections, approval rules, or admin approval language unless the fixture page visibly shows them." in prompt_text
    assert "Workspace Policy facts and evidence should come from https://local.intranet/docs/policy." in prompt_text
    assert "evidence text_preview must be a visible text span from the replayed page." in prompt_text
    assert "The required ticket_8_requester_tier value is exactly office worker." in ticket_priority_prompt_text
    assert 'Do not use general unless the Ticket 8 page visibly shows general.' in ticket_priority_prompt_text
    assert "Ticket 8 is the decoy; still copy its actual visible facts exactly." in ticket_priority_prompt_text
    assert "Ticket 7 facts and evidence should come from https://local.intranet/tickets/7." in ticket_priority_prompt_text
    assert "Ticket 8 facts and evidence should come from https://local.intranet/tickets/8." in ticket_priority_prompt_text
    assert "evidence text_preview must quote visible text from the Ticket 8 page." in ticket_priority_prompt_text
    assert "Cite the collected fact ids and evidence item ids." in ticket_priority_prompt_text

    assert "Approval required facts" in approval_prompt_text
    assert "Do not omit approval_decision_note." in approval_prompt_text
    assert '"key": "approval_request"' in approval_prompt_text
    assert '"key": "approval_policy_anchor"' in approval_prompt_text
    assert '"key": "approval_policy_marker"' in approval_prompt_text
    assert '"key": "approval_decision_note"' in approval_prompt_text
    assert "portal/approval-match" in approval_prompt_text
    assert "Approvals queue" in approval_prompt_text
    assert "Approval Policy Match" in approval_prompt_text
    assert "Workspace Policy" not in approval_prompt_text
    assert "Cite the collected fact ids and evidence item ids." in prompt_text

    schema_text = schema_doc_path.read_text(encoding="utf-8")
    assert "Forbidden aliases" in schema_text
    assert "- `action`" in schema_text
    assert "- `tool`" in schema_text
    assert "facts` must be an array" in schema_text.lower()
    assert "evidence_items` must be an array" in schema_text.lower()
    assert "cited_fact_ids" in schema_text
    assert "cited_evidence_item_ids" in schema_text
    assert "confidence` (optional)" in schema_text
    assert "low`, `medium`, or `high`" in schema_text
    assert "Missing citations are invalid." in schema_text


def test_cli_accepts_bom_config_and_prints_compact_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "browser_stateful_readonly_planner_packet.example.json"
    config_path.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8-sig")

    module = _load_cli_module(CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
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


def test_cli_rejects_invalid_config_with_structured_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "invalid_stateful_packet.json"
    config_path.write_text(json.dumps({"schema_version": "wrong"}, ensure_ascii=False, indent=2), encoding="utf-8")

    module = _load_cli_module(CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--config", str(config_path)])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
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

    summary = build_autonomous_browser_stateful_readonly_planner_packet(_config(), repo_root=tmp_path)

    assert summary["status"] == "succeeded"
