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


def _openpyxl_module() -> Any:
    return pytest.importorskip("openpyxl")


def _openpyxl_loader() -> dict[str, Any]:
    return {"openpyxl": _openpyxl_module()}


def _assert_no_absolute_root(result: object, tmp_path: Path) -> None:
    metadata = getattr(result, "metadata")
    root = str(tmp_path)
    for value in metadata.values():
        if isinstance(value, str):
            assert root not in value


def _create_workbook(tmp_path: Path) -> OfficeRealDocumentActivityConfig:
    cfg = _config(tmp_path)
    result = run_office_real_document_activity(
        "office_create_xlsx",
        {
            "path": "artifacts/books/summary.xlsx",
            "sheet_name": "Summary",
            "headers": ["Task", "Status"],
            "rows": [["Review", "Done"], ["Follow-up", "Open"]],
        },
        cfg,
        dependency_loader=_openpyxl_loader,
    )
    assert result.success is True
    return cfg


def test_create_xlsx_writes_under_artifact_root_when_dependency_available(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    result = run_office_real_document_activity(
        "office_create_xlsx",
        {
            "path": "artifacts/books/summary.xlsx",
            "sheet_name": "Summary",
            "headers": ["Task", "Status"],
            "rows": [["Review", "Done"], ["Follow-up", "Open"]],
        },
        cfg,
        dependency_loader=_openpyxl_loader,
    )

    assert result.success is True
    assert (tmp_path / "artifacts" / "books" / "summary.xlsx").is_file()
    assert result.metadata["document_type"] == "xlsx"
    assert result.metadata["path_relative"] == "artifacts/books/summary.xlsx"
    assert result.metadata["sheet_name"] == "Summary"
    assert result.metadata["row_count"] == 3
    assert result.metadata["column_count"] == 2
    assert result.metadata["real_office_document_automation"] is True
    assert result.metadata["office_app_opened"] is False
    assert "Review" in result.metadata["text_preview"]
    _assert_no_absolute_root(result, tmp_path)


def test_read_xlsx_summary_returns_counts_and_preview(tmp_path: Path) -> None:
    cfg = _create_workbook(tmp_path)

    result = run_office_real_document_activity(
        "office_read_xlsx_summary",
        {"path": "artifacts/books/summary.xlsx", "sheet_name": "Summary"},
        cfg,
        dependency_loader=_openpyxl_loader,
    )

    assert result.success is True
    assert result.metadata["sheet_name"] == "Summary"
    assert result.metadata["active_sheet"] == "Summary"
    assert result.metadata["sheet_names"] == ["Summary"]
    assert result.metadata["row_count"] == 3
    assert result.metadata["column_count"] == 2
    assert result.metadata["table_preview"][1] == ["Review", "Done"]
    assert result.metadata["truncated"] is False
    _assert_no_absolute_root(result, tmp_path)


def test_update_xlsx_cell_and_append_row_are_visible_in_summary(tmp_path: Path) -> None:
    cfg = _create_workbook(tmp_path)

    updated = run_office_real_document_activity(
        "office_update_xlsx_cell",
        {
            "path": "artifacts/books/summary.xlsx",
            "sheet_name": "Summary",
            "cell": "B2",
            "value": "Reopened",
        },
        cfg,
        dependency_loader=_openpyxl_loader,
    )
    assert updated.success is True
    assert updated.metadata["updated_cell"] == "B2"

    appended = run_office_real_document_activity(
        "office_append_xlsx_row",
        {
            "path": "artifacts/books/summary.xlsx",
            "sheet_name": "Summary",
            "values": ["Write report", "Queued"],
        },
        cfg,
        dependency_loader=_openpyxl_loader,
    )
    assert appended.success is True
    assert appended.metadata["appended_row_index"] == 4

    summary = run_office_real_document_activity(
        "office_read_xlsx_summary",
        {"path": "artifacts/books/summary.xlsx", "sheet_name": "Summary"},
        cfg,
        dependency_loader=_openpyxl_loader,
    )
    assert summary.success is True
    assert summary.metadata["row_count"] == 4
    assert summary.metadata["column_count"] == 2
    assert "Reopened" in summary.metadata["text_preview"]
    assert "Write report" in summary.metadata["text_preview"]


def test_missing_xlsx_dependency_returns_controlled_error(tmp_path: Path) -> None:
    def missing_loader() -> dict[str, object]:
        raise ImportError("openpyxl unavailable for test")

    result = run_office_real_document_activity(
        "office_create_xlsx",
        {"path": "artifacts/book.xlsx", "headers": ["A"], "rows": [["B"]]},
        _config(tmp_path),
        dependency_loader=missing_loader,
    )

    assert result.success is False
    assert result.error_type == "office_dependency_missing"
    assert result.metadata["real_office_document_automation"] is False
    assert result.metadata["office_app_opened"] is False


def test_disabled_xlsx_action_still_returns_controlled_denial(tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("disabled actions must not load openpyxl")

    result = run_office_real_document_activity(
        "office_create_xlsx",
        {"path": "artifacts/book.xlsx", "headers": ["A"], "rows": [["B"]]},
        _config(tmp_path, enabled=False),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == "real_office_document_automation_disabled"


@pytest.mark.parametrize(
    ("path", "expected_error"),
    [
        (r"C:\Temp\book.xlsx", "office_path_absolute_denied"),
        ("artifacts/../book.xlsx", "office_path_traversal_denied"),
        ("models/gguf/book.xlsx", "office_path_forbidden_root_denied"),
        ("artifacts/book.xlsm", "office_macro_extension_denied"),
    ],
)
def test_xlsx_actions_keep_path_safety(path: str, expected_error: str, tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("unsafe paths must be rejected before dependency loading")

    result = run_office_real_document_activity(
        "office_create_xlsx",
        {"path": path, "headers": ["A"], "rows": [["B"]]},
        _config(tmp_path),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == expected_error


def test_read_missing_xlsx_file_returns_controlled_error(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_read_xlsx_summary",
        {"path": "artifacts/missing.xlsx"},
        _config(tmp_path),
        dependency_loader=_openpyxl_loader,
    )

    assert result.success is False
    assert result.error_type == "office_xlsx_file_missing"
    assert result.metadata["path_relative"] == "artifacts/missing.xlsx"


def test_read_oversized_xlsx_file_is_rejected_before_read(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "large.xlsx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not xlsx but intentionally larger than limit")

    result = run_office_real_document_activity(
        "office_read_xlsx_summary",
        {"path": "artifacts/large.xlsx"},
        _config(tmp_path, max_file_bytes=4),
        dependency_loader=_openpyxl_loader,
    )

    assert result.success is False
    assert result.error_type == "office_xlsx_file_too_large"
    assert result.metadata["path_relative"] == "artifacts/large.xlsx"


@pytest.mark.parametrize("value", ["=SUM(A1:A2)", "+cmd", "-danger", "@HYPERLINK(...)"])
def test_formula_like_xlsx_values_rejected_by_default(value: str, tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("formula-like values must be rejected before dependency loading")

    result = run_office_real_document_activity(
        "office_update_xlsx_cell",
        {"path": "artifacts/book.xlsx", "cell": "A1", "value": value},
        _config(tmp_path),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == "office_formula_like_value_denied"


def test_formula_like_xlsx_values_allowed_when_formulas_enabled(tmp_path: Path) -> None:
    cfg = _config(tmp_path, allow_formulas=True)
    create = run_office_real_document_activity(
        "office_create_xlsx",
        {"path": "artifacts/book.xlsx", "headers": ["Formula"], "rows": [["=SUM(1,2)"]]},
        cfg,
        dependency_loader=_openpyxl_loader,
    )

    assert create.success is True


def test_invalid_xlsx_cell_coordinate_is_rejected(tmp_path: Path) -> None:
    cfg = _create_workbook(tmp_path)

    result = run_office_real_document_activity(
        "office_update_xlsx_cell",
        {"path": "artifacts/books/summary.xlsx", "cell": "1A", "value": "bad"},
        cfg,
        dependency_loader=_openpyxl_loader,
    )

    assert result.success is False
    assert result.error_type == "office_xlsx_invalid_cell"


def test_invalid_xlsx_sheet_name_is_rejected(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_xlsx",
        {"path": "artifacts/book.xlsx", "sheet_name": "bad/name", "rows": [["body"]]},
        _config(tmp_path),
        dependency_loader=_openpyxl_loader,
    )

    assert result.success is False
    assert result.error_type == "office_xlsx_invalid_sheet"


def test_xlsx_result_does_not_include_absolute_artifact_root(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_xlsx",
        {"path": "artifacts/book.xlsx", "headers": ["A"], "rows": [["B"]]},
        _config(tmp_path),
        dependency_loader=_openpyxl_loader,
    )

    assert result.success is True
    _assert_no_absolute_root(result, tmp_path)


def test_pptx_action_uses_separate_optional_dependency(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_pptx",
        {"path": "artifacts/deck.pptx"},
        _config(tmp_path),
        dependency_loader=lambda: {"openpyxl": object()},
    )

    assert result.success is False
    assert result.error_type == "office_dependency_missing"
