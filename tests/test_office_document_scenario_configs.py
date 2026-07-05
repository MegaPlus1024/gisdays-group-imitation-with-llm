from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
from typing import Any

from src.agent.orchestrator_executor_pipeline import (
    OrchestratorExecutorRunConfig,
    load_orchestrator_executor_scenario,
)
from src.agent.role_template import load_role_template
from src.agent.schemas import NextAction
from src.agent.script_registry import load_script_registry, validate_next_action_against_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLE_PATH = "configs/roles/office_document_worker.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"

OFFICE_DOCUMENT_ACTIONS = {
    "office_create_docx",
    "office_append_docx_section",
    "office_extract_docx_text",
    "office_create_xlsx",
    "office_update_xlsx_cell",
    "office_append_xlsx_row",
    "office_read_xlsx_summary",
    "office_create_pptx",
    "office_add_pptx_slide",
    "office_extract_pptx_text",
}

FORBIDDEN_RUNTIME_ACTIONS = {
    "run_shell_command",
    "browser_open_url",
    "browser_click",
    "browser_read_page",
}

VALID_PARAMETERS = {
    "office_create_docx": {
        "path": "artifacts/office_documents/offline_basic/summary.docx",
        "title": "Offline Summary",
        "paragraphs": ["Local-only summary."],
    },
    "office_append_docx_section": {
        "path": "artifacts/office_documents/offline_basic/summary.docx",
        "heading": "Follow-up",
        "paragraphs": ["Continue with offline validation."],
    },
    "office_extract_docx_text": {
        "path": "artifacts/office_documents/offline_basic/summary.docx"
    },
    "office_create_xlsx": {
        "path": "artifacts/office_documents/offline_basic/tasks.xlsx",
        "sheet_name": "Tasks",
        "headers": ["Task", "Status"],
        "rows": [["Draft", "Ready"]],
    },
    "office_update_xlsx_cell": {
        "path": "artifacts/office_documents/offline_basic/tasks.xlsx",
        "sheet_name": "Tasks",
        "cell": "B2",
        "value": "Ready",
    },
    "office_append_xlsx_row": {
        "path": "artifacts/office_documents/offline_basic/tasks.xlsx",
        "sheet_name": "Tasks",
        "values": ["Review", "Queued"],
    },
    "office_read_xlsx_summary": {
        "path": "artifacts/office_documents/offline_basic/tasks.xlsx",
        "sheet_name": "Tasks",
    },
    "office_create_pptx": {
        "path": "artifacts/office_documents/offline_basic/brief.pptx",
        "title": "Offline Brief",
        "slides": [{"title": "Status", "bullets": ["Config-only scenario."]}],
    },
    "office_add_pptx_slide": {
        "path": "artifacts/office_documents/offline_basic/brief.pptx",
        "title": "Next Steps",
        "bullets": ["Keep validation offline."],
    },
    "office_extract_pptx_text": {
        "path": "artifacts/office_documents/offline_basic/brief.pptx"
    },
}


def _json(relative_path: str) -> dict[str, Any]:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def _dumped(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _assert_safe_relative_reference(value: str) -> None:
    assert not Path(value).is_absolute()
    assert not PureWindowsPath(value).is_absolute()
    assert "://" not in value
    assert ".." not in Path(value).parts


def _next_action(action: str) -> NextAction:
    return NextAction(
        action=action,
        parameters=VALID_PARAMETERS[action],
        reason="config validation",
        expected_result="action validates against registry and role allowlists",
    )


def test_office_document_role_loads_with_expected_action_allowlist() -> None:
    role = load_role_template(PROJECT_ROOT / ROLE_PATH)

    assert role.role_id == "office_document_worker"
    assert role.metadata["offline_fake_compatible"] is True
    assert role.metadata["office_real_document_backend_required"] is False
    assert role.metadata["desktop_office_required"] is False
    assert role.constraints.no_internet is True
    assert role.constraints.no_model_download is True
    assert set(role.constraints.allowed_action_names) == OFFICE_DOCUMENT_ACTIONS
    assert not (set(role.constraints.allowed_action_names) & FORBIDDEN_RUNTIME_ACTIONS)
    assert FORBIDDEN_RUNTIME_ACTIONS.issubset(set(role.constraints.forbidden_action_names))
    assert role.constraints.allowed_file_roots == ["artifacts/", "experiments/", "tests/"]
    assert {"models/gguf/", ".venv/", ".git/", "logs/"}.issubset(
        set(role.constraints.forbidden_file_roots)
    )


def test_office_document_role_text_does_not_claim_desktop_or_runtime_requirements() -> None:
    role_text = _dumped(_json(ROLE_PATH))

    assert "Microsoft Office" not in role_text
    assert "LibreOffice" not in role_text
    assert "RUN_BROWSER_TESTS" not in role_text
    assert "llama-server" not in role_text
    assert "gpu" not in role_text.lower()


def test_office_document_scenario_loads_and_is_offline_fake_compatible() -> None:
    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / SCENARIO_PATH)

    assert scenario.scenario_id == "office_document_file_workflow_basic_v1"
    assert scenario.virtual_network is None
    assert scenario.execute_actions is False
    assert scenario.metadata["offline_fake_compatible"] is True
    assert scenario.metadata["network_required"] is False
    assert scenario.metadata["external_network_required"] is False
    assert scenario.metadata["browser_real_automation_required"] is False
    assert scenario.metadata["office_real_automation_required"] is False
    assert scenario.metadata["office_real_document_backend_required"] is False
    assert scenario.metadata["office_real_document_backend_enabled_by_default"] is False
    assert scenario.metadata["optional_office_dependencies_required"] is False
    assert scenario.metadata["write_path_policy"] == "artifact_workspace_only"
    assert set(scenario.metadata["expected_safe_actions"]) == OFFICE_DOCUMENT_ACTIONS
    assert len(scenario.agents) == 2


def test_office_document_scenario_paths_are_relative_and_existing_config_refs() -> None:
    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / SCENARIO_PATH)

    _assert_safe_relative_reference(scenario.registry_path)
    assert (PROJECT_ROOT / scenario.registry_path).is_file()

    for agent in scenario.agents:
        _assert_safe_relative_reference(agent.role_template_path)
        _assert_safe_relative_reference(agent.activity_profile_path)
        assert (PROJECT_ROOT / agent.role_template_path).is_file()
        assert (PROJECT_ROOT / agent.activity_profile_path).is_file()
        assert agent.role_template_path == ROLE_PATH

        dumped_agent = _dumped(agent.model_dump())
        private_windows_prefix = "C:" + "\\" + "Users" + "\\"
        private_posix_prefix = "C:" + "/" + "Users" + "/"
        assert private_windows_prefix not in dumped_agent
        assert private_posix_prefix not in dumped_agent
        assert "Downloads" not in dumped_agent
        assert "." + "codex" not in dumped_agent

        for artifact_path in agent.state_override.get("artifact_path_examples", []):
            _assert_safe_relative_reference(artifact_path)
            assert artifact_path.startswith("artifacts/office_documents/offline_basic/")


def test_office_document_scenario_expected_actions_validate_against_registry_and_role() -> None:
    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / SCENARIO_PATH)
    registry = load_script_registry(PROJECT_ROOT / scenario.registry_path)
    role = load_role_template(PROJECT_ROOT / ROLE_PATH)

    assert set(scenario.metadata["expected_safe_actions"]).issubset(registry.script_names())
    assert set(scenario.metadata["expected_safe_actions"]).issubset(role.allowed_action_set())

    for action in scenario.metadata["expected_safe_actions"]:
        result = validate_next_action_against_registry(_next_action(action), registry, role)
        assert result.accepted is True, action


def test_office_document_scenario_can_build_fake_run_config_without_execution() -> None:
    config = OrchestratorExecutorRunConfig.model_validate(
        {
            "project_root": PROJECT_ROOT,
            "mode": "fake",
            "models_config_path": "configs/evaluation_models.json",
            "scenario_path": SCENARIO_PATH,
            "out_dir": "artifacts/test_office_document_config_only",
            "run_id": "test_office_document_config_only",
            "orchestrator_model_id": "second_model",
            "executor_model_id": "first_model",
            "execute_actions": False,
            "force": True,
        }
    )

    assert config.mode == "fake"
    assert config.scenario_path == SCENARIO_PATH
    assert config.execute_actions is False


def test_office_document_scenario_text_does_not_claim_runtime_or_desktop_apps() -> None:
    scenario_text = _dumped(_json(SCENARIO_PATH))

    assert "Microsoft Office" not in scenario_text
    assert "LibreOffice" not in scenario_text
    assert "RUN_BROWSER_TESTS" not in scenario_text
    assert "playwright" not in scenario_text.lower()
    assert "chromium" not in scenario_text.lower()
    assert "llama-server" not in scenario_text
    assert "docker" not in scenario_text.lower()
    assert "gpu" not in scenario_text.lower()
