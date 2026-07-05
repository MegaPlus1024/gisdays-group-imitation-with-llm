from __future__ import annotations

import importlib
from pathlib import Path

from src.agent.scripts.office_real_document_activity import (
    SUPPORTED_OFFICE_REAL_DOCUMENT_ACTIONS,
    OfficeFormulaLikeValueError,
    OfficeRealDocumentActivityConfig,
    OfficeRealDocumentPathError,
    normalize_office_real_document_path,
    resolve_safe_office_real_document_path,
    run_office_real_document_activity,
    text_preview,
    validate_spreadsheet_text_value,
)


def _config(tmp_path: Path, **overrides: object) -> OfficeRealDocumentActivityConfig:
    payload: dict[str, object] = {
        "project_root": tmp_path,
        "artifact_root": "artifacts",
    }
    payload.update(overrides)
    return OfficeRealDocumentActivityConfig(**payload)


def test_module_imports_without_optional_office_dependencies() -> None:
    module = importlib.import_module("src.agent.scripts.office_real_document_activity")

    assert hasattr(module, "OfficeRealDocumentActivityConfig")
    assert hasattr(module, "run_office_real_document_activity")


def test_disabled_by_default_returns_controlled_denial(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_docx",
        {"path": "artifacts/report.docx"},
        _config(tmp_path, enabled=False),
    )

    assert result.success is False
    assert result.error_type == "real_office_document_automation_disabled"
    assert result.metadata["office_app_opened"] is False
    assert result.metadata["real_office_document_automation"] is False


def test_disabled_behavior_does_not_call_dependency_loader(tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("disabled office scaffold must not import dependencies")

    result = run_office_real_document_activity(
        "office_extract_docx_text",
        {"path": "artifacts/report.docx"},
        _config(tmp_path, enabled=False),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == "real_office_document_automation_disabled"


def test_enabled_with_missing_dependency_returns_controlled_error(tmp_path: Path) -> None:
    def missing_loader() -> dict[str, object]:
        raise ImportError("office dependency missing for test")

    result = run_office_real_document_activity(
        "office_create_docx",
        {"path": "artifacts/report.docx"},
        _config(tmp_path, enabled=True),
        dependency_loader=missing_loader,
    )

    assert result.success is False
    assert result.error_type == "office_dependency_missing"
    assert result.metadata["office_app_opened"] is False
    assert result.metadata["real_office_document_automation"] is False


def test_enabled_pptx_action_with_missing_dependency_returns_controlled_error(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_pptx",
        {"path": "artifacts/deck.pptx"},
        _config(tmp_path, enabled=True),
        dependency_loader=lambda: {"docx": object(), "openpyxl": object(), "pptx": object()},
    )

    assert result.success is False
    assert result.error_type == "office_dependency_missing"


def test_supported_action_names_are_recognized(tmp_path: Path) -> None:
    for action in sorted(SUPPORTED_OFFICE_REAL_DOCUMENT_ACTIONS):
        result = run_office_real_document_activity(
            action,
            {"path": "artifacts/file.docx"},
            _config(tmp_path),
        )
        assert result.error_type == "real_office_document_automation_disabled"


def test_unsupported_action_returns_controlled_error(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_unknown",
        {},
        _config(tmp_path, enabled=True),
        dependency_loader=lambda: {"docx": object()},
    )

    assert result.success is False
    assert result.error_type == "unknown_office_real_document_action"


def test_rejects_absolute_windows_path() -> None:
    try:
        normalize_office_real_document_path(r"C:\Temp\report.docx")
    except OfficeRealDocumentPathError as exc:
        assert exc.code == "office_path_absolute_denied"
    else:  # pragma: no cover - defensive
        raise AssertionError("absolute Windows path must be rejected")


def test_rejects_absolute_posix_path() -> None:
    try:
        normalize_office_real_document_path("/tmp/report.docx")
    except OfficeRealDocumentPathError as exc:
        assert exc.code == "office_path_absolute_denied"
    else:  # pragma: no cover - defensive
        raise AssertionError("absolute POSIX path must be rejected")


def test_rejects_traversal_path() -> None:
    try:
        normalize_office_real_document_path("artifacts/../report.docx")
    except OfficeRealDocumentPathError as exc:
        assert exc.code == "office_path_traversal_denied"
    else:  # pragma: no cover - defensive
        raise AssertionError("traversal path must be rejected")


def test_rejects_forbidden_root(tmp_path: Path) -> None:
    try:
        resolve_safe_office_real_document_path(
            "models/gguf/test.docx",
            _config(tmp_path),
        )
    except OfficeRealDocumentPathError as exc:
        assert exc.code == "office_path_forbidden_root_denied"
    else:  # pragma: no cover - defensive
        raise AssertionError("forbidden root must be rejected")


def test_rejects_macro_enabled_extensions(tmp_path: Path) -> None:
    for path in ["artifacts/a.docm", "artifacts/b.xlsm", "artifacts/c.pptm"]:
        try:
            resolve_safe_office_real_document_path(path, _config(tmp_path))
        except OfficeRealDocumentPathError as exc:
            assert exc.code == "office_macro_extension_denied"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"macro-enabled path must be rejected: {path}")


def test_rejects_unsupported_extension(tmp_path: Path) -> None:
    try:
        resolve_safe_office_real_document_path("artifacts/report.txt", _config(tmp_path))
    except OfficeRealDocumentPathError as exc:
        assert exc.code == "office_extension_denied"
    else:  # pragma: no cover - defensive
        raise AssertionError("unsupported extension must be rejected")


def test_accepts_safe_relative_office_extensions_under_artifact_root(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    for path in ["artifacts/report.docx", "artifacts/book.xlsx", "artifacts/deck.pptx"]:
        resolved = resolve_safe_office_real_document_path(path, cfg)
        assert resolved.relative_path == path
        assert resolved.resolved_path == tmp_path / path


def test_rejects_path_outside_artifact_root(tmp_path: Path) -> None:
    try:
        resolve_safe_office_real_document_path("docs/report.docx", _config(tmp_path))
    except OfficeRealDocumentPathError as exc:
        assert exc.code == "office_path_outside_artifact_root"
    else:  # pragma: no cover - defensive
        raise AssertionError("path outside artifact root must be rejected")


def test_requires_artifact_root(tmp_path: Path) -> None:
    try:
        resolve_safe_office_real_document_path(
            "artifacts/report.docx",
            OfficeRealDocumentActivityConfig(project_root=tmp_path),
        )
    except OfficeRealDocumentPathError as exc:
        assert exc.code == "office_artifact_root_required"
    else:  # pragma: no cover - defensive
        raise AssertionError("artifact_root must be required")


def test_formula_like_values_rejected_when_formulas_disabled(tmp_path: Path) -> None:
    cfg = _config(tmp_path, allow_formulas=False)

    for value in ["=SUM(A1:A2)", "+A1", "-A1", "@cmd"]:
        try:
            validate_spreadsheet_text_value(value, cfg)
        except OfficeFormulaLikeValueError as exc:
            assert exc.code == "office_formula_like_value_denied"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"formula-like value must be rejected: {value!r}")


def test_formula_like_values_allowed_when_formulas_enabled(tmp_path: Path) -> None:
    cfg = _config(tmp_path, allow_formulas=True)

    assert validate_spreadsheet_text_value("=SUM(A1:A2)", cfg) == "=SUM(A1:A2)"


def test_formula_like_action_parameter_returns_controlled_error(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_update_xlsx_cell",
        {"path": "artifacts/book.xlsx", "value": "=SUM(A1:A2)"},
        _config(tmp_path, enabled=True),
        dependency_loader=lambda: {"docx": object(), "openpyxl": object(), "pptx": object()},
    )

    assert result.success is False
    assert result.error_type == "office_formula_like_value_denied"


def test_text_preview_truncates_and_normalizes_whitespace() -> None:
    assert text_preview("alpha   beta\n gamma", 12) == "alpha bet..."
