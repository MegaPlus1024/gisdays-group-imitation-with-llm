from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.agent.scripts.office_real_document_activity import (
    OfficeRealDocumentActivityConfig,
    run_office_real_document_activity,
)


def _config(tmp_path: Path, **overrides: object) -> OfficeRealDocumentActivityConfig:
    payload: dict[str, object] = {
        "enabled": True,
        "project_root": tmp_path,
        "artifact_root": "artifacts",
    }
    payload.update(overrides)
    return OfficeRealDocumentActivityConfig(**payload)


def _docx_module() -> Any:
    return pytest.importorskip("docx")


def _docx_loader() -> dict[str, Any]:
    return {"docx": _docx_module()}


def _assert_no_absolute_root(result: object, tmp_path: Path) -> None:
    metadata = getattr(result, "metadata")
    root = str(tmp_path)
    for value in metadata.values():
        if isinstance(value, str):
            assert root not in value


def test_create_docx_writes_under_artifact_root_when_dependency_available(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_docx",
        {
            "path": "artifacts/reports/summary.docx",
            "title": "Weekly Summary",
            "paragraphs": ["Reviewed local fixtures.", "Prepared follow-up tasks."],
        },
        _config(tmp_path),
        dependency_loader=_docx_loader,
    )

    assert result.success is True
    assert (tmp_path / "artifacts" / "reports" / "summary.docx").is_file()
    assert result.metadata["document_type"] == "docx"
    assert result.metadata["path_relative"] == "artifacts/reports/summary.docx"
    assert result.metadata["real_office_document_automation"] is True
    assert result.metadata["office_app_opened"] is False
    assert result.metadata["paragraph_count"] == 3
    assert "Weekly Summary" in result.metadata["text_preview"]
    _assert_no_absolute_root(result, tmp_path)


def test_extract_docx_text_returns_preview_and_counts(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    create = run_office_real_document_activity(
        "office_create_docx",
        {
            "path": "artifacts/report.docx",
            "title": "Incident Notes",
            "paragraphs": ["Initial triage complete.", "No external network actions."],
        },
        cfg,
        dependency_loader=_docx_loader,
    )
    assert create.success is True

    extracted = run_office_real_document_activity(
        "office_extract_docx_text",
        {"path": "artifacts/report.docx"},
        cfg,
        dependency_loader=_docx_loader,
    )

    assert extracted.success is True
    assert extracted.metadata["path_relative"] == "artifacts/report.docx"
    assert extracted.metadata["paragraph_count"] == 3
    assert extracted.metadata["character_count"] > 0
    assert "Incident Notes" in extracted.metadata["text_preview"]
    assert "Initial triage complete." in extracted.output
    _assert_no_absolute_root(extracted, tmp_path)


def test_append_docx_section_then_extract_includes_appended_content(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    create = run_office_real_document_activity(
        "office_create_docx",
        {"path": "artifacts/runbook.docx", "title": "Runbook", "paragraphs": ["Start state."]},
        cfg,
        dependency_loader=_docx_loader,
    )
    assert create.success is True

    appended = run_office_real_document_activity(
        "office_append_docx_section",
        {
            "path": "artifacts/runbook.docx",
            "heading": "Follow-up",
            "paragraphs": ["Check artifact workspace.", "Record local-only result."],
        },
        cfg,
        dependency_loader=_docx_loader,
    )
    assert appended.success is True
    assert appended.metadata["appended_paragraph_count"] == 2
    assert appended.metadata["heading_added"] is True

    extracted = run_office_real_document_activity(
        "office_extract_docx_text",
        {"path": "artifacts/runbook.docx"},
        cfg,
        dependency_loader=_docx_loader,
    )
    assert extracted.success is True
    assert "Follow-up" in extracted.metadata["text_preview"]
    assert "Record local-only result." in extracted.metadata["text_preview"]


def test_missing_docx_dependency_returns_controlled_error(tmp_path: Path) -> None:
    def missing_loader() -> dict[str, object]:
        raise ImportError("python-docx unavailable for test")

    result = run_office_real_document_activity(
        "office_create_docx",
        {"path": "artifacts/report.docx", "paragraphs": ["body"]},
        _config(tmp_path),
        dependency_loader=missing_loader,
    )

    assert result.success is False
    assert result.error_type == "office_dependency_missing"
    assert result.metadata["real_office_document_automation"] is False
    assert result.metadata["office_app_opened"] is False


def test_disabled_docx_action_still_returns_controlled_denial(tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("disabled actions must not load python-docx")

    result = run_office_real_document_activity(
        "office_create_docx",
        {"path": "artifacts/report.docx", "paragraphs": ["body"]},
        _config(tmp_path, enabled=False),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == "real_office_document_automation_disabled"


@pytest.mark.parametrize(
    ("path", "expected_error"),
    [
        (r"C:\Temp\report.docx", "office_path_absolute_denied"),
        ("artifacts/../report.docx", "office_path_traversal_denied"),
        ("models/gguf/report.docx", "office_path_forbidden_root_denied"),
        ("artifacts/report.docm", "office_macro_extension_denied"),
    ],
)
def test_docx_actions_keep_path_safety(path: str, expected_error: str, tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("unsafe paths must be rejected before dependency loading")

    result = run_office_real_document_activity(
        "office_create_docx",
        {"path": path, "paragraphs": ["body"]},
        _config(tmp_path),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == expected_error


def test_extract_missing_docx_file_returns_controlled_error(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_extract_docx_text",
        {"path": "artifacts/missing.docx"},
        _config(tmp_path),
        dependency_loader=_docx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_docx_file_missing"
    assert result.metadata["path_relative"] == "artifacts/missing.docx"


def test_extract_oversized_docx_file_is_rejected_before_read(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "large.docx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a docx but intentionally larger than limit")

    result = run_office_real_document_activity(
        "office_extract_docx_text",
        {"path": "artifacts/large.docx"},
        _config(tmp_path, max_file_bytes=4),
        dependency_loader=_docx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_docx_file_too_large"
    assert result.metadata["path_relative"] == "artifacts/large.docx"


def test_docx_result_does_not_include_absolute_artifact_root(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_docx",
        {"path": "artifacts/report.docx", "paragraphs": ["short body"]},
        _config(tmp_path),
        dependency_loader=_docx_loader,
    )

    assert result.success is True
    _assert_no_absolute_root(result, tmp_path)


def test_pptx_action_remains_not_implemented(tmp_path: Path) -> None:
    for action, path in [
        ("office_create_pptx", "artifacts/deck.pptx"),
    ]:
        result = run_office_real_document_activity(
            action,
            {"path": path},
            _config(tmp_path),
            dependency_loader=lambda: {"docx": object()},
        )

        assert result.success is False
        assert result.error_type == "office_backend_not_implemented"
