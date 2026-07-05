from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.agent.orchestrator_executor_pipeline import (
    _ARTIFACT_WORKSPACE_WRITE_ACTIONS,
    _scenario_action_constraint_issue,
)
from src.agent.schemas import NextAction
from src.agent.script_execution_bridge import (
    SUPPORTED_ACTIONS,
    ScriptExecutionBridge,
    ScriptExecutionBridgeConfig,
)
from src.agent.script_registry import load_script_registry, validate_next_action_against_registry


OFFICE_REAL_DOCUMENT_ACTIONS = {
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

OFFICE_REAL_DOCUMENT_WRITE_ACTIONS = {
    "office_create_docx",
    "office_append_docx_section",
    "office_create_xlsx",
    "office_update_xlsx_cell",
    "office_append_xlsx_row",
    "office_create_pptx",
    "office_add_pptx_slide",
}

OFFICE_REAL_DOCUMENT_READ_ACTIONS = OFFICE_REAL_DOCUMENT_ACTIONS - OFFICE_REAL_DOCUMENT_WRITE_ACTIONS

VALID_PARAMETERS = {
    "office_create_docx": {"path": "artifacts/office/report.docx"},
    "office_append_docx_section": {
        "path": "artifacts/office/report.docx",
        "paragraphs": ["Follow-up."],
    },
    "office_extract_docx_text": {"path": "artifacts/office/report.docx"},
    "office_create_xlsx": {"path": "artifacts/office/book.xlsx"},
    "office_update_xlsx_cell": {
        "path": "artifacts/office/book.xlsx",
        "cell": "B2",
        "value": "Done",
    },
    "office_append_xlsx_row": {
        "path": "artifacts/office/book.xlsx",
        "values": ["Task", "Queued"],
    },
    "office_read_xlsx_summary": {"path": "artifacts/office/book.xlsx"},
    "office_create_pptx": {"path": "artifacts/office/deck.pptx", "title": "Summary"},
    "office_add_pptx_slide": {
        "path": "artifacts/office/deck.pptx",
        "bullets": ["Local-only note."],
    },
    "office_extract_pptx_text": {"path": "artifacts/office/deck.pptx"},
}


def _registry() -> Any:
    return load_script_registry("configs/script_registry.example.json")


def _next_action(action: str, parameters: dict[str, Any] | None = None) -> NextAction:
    return NextAction(
        action=action,
        parameters=parameters or VALID_PARAMETERS.get(action, {}),
        reason="wiring test",
        expected_result="controlled result",
    )


def _bridge(tmp_path: Path, **overrides: Any) -> ScriptExecutionBridge:
    payload: dict[str, Any] = {
        "project_root": tmp_path,
        "validate_with_registry": True,
    }
    payload.update(overrides.pop("config_overrides", {}))
    return ScriptExecutionBridge(
        ScriptExecutionBridgeConfig(**payload),
        registry=_registry(),
        **overrides,
    )


def test_registry_contains_all_office_real_document_actions() -> None:
    names = _registry().script_names()

    assert OFFICE_REAL_DOCUMENT_ACTIONS.issubset(names)


def test_registry_descriptors_are_document_file_only_and_tagged() -> None:
    registry = _registry()

    for action in OFFICE_REAL_DOCUMENT_ACTIONS:
        descriptor = registry.get_script(action)
        assert descriptor is not None
        rendered = " ".join(
            [
                descriptor.description,
                *(descriptor.safety.notes or []),
            ]
        )
        assert "document-file" in rendered
        assert "Microsoft Office" not in rendered
        assert "LibreOffice" not in rendered
        assert "optional_office" in descriptor.tags
        assert "document_file" in descriptor.tags

        if action in OFFICE_REAL_DOCUMENT_WRITE_ACTIONS:
            assert descriptor.safety.read_only is False
            assert "write" in descriptor.tags
        else:
            assert descriptor.safety.read_only is True
            assert "read" in descriptor.tags


def test_registry_still_contains_existing_office_stub_action() -> None:
    descriptor = _registry().get_script("office_create_document_stub")

    assert descriptor is not None
    assert "office" in descriptor.tags


@pytest.mark.parametrize(
    "action",
    ["office_create_docx", "office_create_xlsx", "office_create_pptx"],
)
def test_bridge_routes_office_real_document_actions_disabled_by_default(
    action: str,
    tmp_path: Path,
) -> None:
    called = {"value": False}

    def fail_loader() -> dict[str, object]:
        called["value"] = True
        raise AssertionError("disabled bridge action must not load optional dependencies")

    output = _bridge(
        tmp_path,
        office_real_document_dependency_loader=fail_loader,
    ).execute_next_action(_next_action(action))

    assert output.dispatched is True
    assert output.success is False
    assert output.raw_result.error_type == "real_office_document_automation_disabled"
    assert called["value"] is False


def test_bridge_missing_optional_dependency_returns_controlled_error(tmp_path: Path) -> None:
    def missing_loader() -> dict[str, object]:
        raise ImportError("optional office dependency unavailable for wiring test")

    output = _bridge(
        tmp_path,
        config_overrides={
            "office_real_document_enabled": True,
            "office_real_document_artifact_root": "artifacts",
        },
        office_real_document_dependency_loader=missing_loader,
    ).execute_next_action(_next_action("office_create_docx"))

    assert output.dispatched is True
    assert output.success is False
    assert output.raw_result.error_type == "office_dependency_missing"
    assert output.raw_result.metadata["office_app_opened"] is False


def test_existing_office_stub_bridge_behavior_still_works(tmp_path: Path) -> None:
    output = _bridge(tmp_path).execute_next_action(
        NextAction(
            action="office_create_document_stub",
            parameters={"path": "docs/stub.txt", "title": "Stub", "body": "Body"},
            reason="existing behavior",
            expected_result="stub file",
        )
    )

    assert output.dispatched is True
    assert output.success is True
    assert output.raw_result.metadata["simulated"] is True
    assert (tmp_path / "docs" / "stub.txt").is_file()


def test_artifact_workspace_policy_includes_office_real_document_write_actions(tmp_path: Path) -> None:
    scenario = SimpleNamespace(metadata={"write_path_policy": "artifact_workspace_only"})

    for action in OFFICE_REAL_DOCUMENT_WRITE_ACTIONS:
        issue = _scenario_action_constraint_issue(
            next_action=_next_action(action, {"path": "docs/outside_workspace.docx"}),
            scenario=scenario,  # type: ignore[arg-type]
            out_dir=tmp_path / "run",
            project_root=tmp_path,
        )
        assert issue is not None, action
        assert issue["code"] == "write_path_outside_artifact_workspace"
        assert action in _ARTIFACT_WORKSPACE_WRITE_ACTIONS


def test_artifact_workspace_policy_does_not_classify_office_read_actions_as_writes(
    tmp_path: Path,
) -> None:
    scenario = SimpleNamespace(metadata={"write_path_policy": "artifact_workspace_only"})

    for action in OFFICE_REAL_DOCUMENT_READ_ACTIONS:
        issue = _scenario_action_constraint_issue(
            next_action=_next_action(action, {"path": "docs/read_only_source.docx"}),
            scenario=scenario,  # type: ignore[arg-type]
            out_dir=tmp_path / "run",
            project_root=tmp_path,
        )
        assert issue is None, action
        assert action not in _ARTIFACT_WORKSPACE_WRITE_ACTIONS


def test_registry_validation_accepts_synthetic_office_real_document_actions() -> None:
    registry = _registry()

    for action in sorted(OFFICE_REAL_DOCUMENT_ACTIONS):
        result = validate_next_action_against_registry(_next_action(action), registry)
        assert result.accepted is True, action


def test_unknown_office_real_document_action_remains_rejected() -> None:
    result = validate_next_action_against_registry(
        _next_action("office_convert_docx_to_pdf", {"path": "artifacts/office/report.docx"}),
        _registry(),
    )

    assert result.accepted is False
    assert any(issue.code == "unknown_action" for issue in result.issues)


def test_supported_bridge_actions_include_office_real_document_actions() -> None:
    assert OFFICE_REAL_DOCUMENT_ACTIONS.issubset(set(SUPPORTED_ACTIONS))
