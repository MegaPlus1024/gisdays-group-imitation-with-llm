from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .results import ScriptExecutionResult


SUPPORTED_OFFICE_REAL_DOCUMENT_ACTIONS = frozenset(
    {
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
)

OFFICE_DOCUMENT_DEPENDENCY_MODULES = {
    "docx": "python-docx",
    "openpyxl": "openpyxl",
    "pptx": "python-pptx",
}

DOCX_ACTIONS = frozenset(
    {
        "office_create_docx",
        "office_append_docx_section",
        "office_extract_docx_text",
    }
)

XLSX_ACTIONS = frozenset(
    {
        "office_create_xlsx",
        "office_update_xlsx_cell",
        "office_append_xlsx_row",
        "office_read_xlsx_summary",
    }
)

PPTX_ACTIONS = frozenset(
    {
        "office_create_pptx",
        "office_add_pptx_slide",
        "office_extract_pptx_text",
    }
)

MACRO_ENABLED_EXTENSIONS = frozenset({".docm", ".xlsm", ".pptm"})
FORMULA_PREFIXES = ("=", "+", "-", "@")
INVALID_SHEET_NAME_CHARS = frozenset("[]:*?/\\")
CELL_COORDINATE_RE = re.compile(r"^[A-Za-z]{1,3}[1-9][0-9]{0,6}$")


class OfficeRealDocumentActivityError(Exception):
    """Base error for controlled real office document scaffold failures."""


class OfficeDependencyMissingError(OfficeRealDocumentActivityError, ImportError):
    """Raised when an optional office dependency is requested but unavailable."""


class OfficeRealDocumentPathError(OfficeRealDocumentActivityError, ValueError):
    """Raised when a requested office document path is unsafe."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OfficeFormulaLikeValueError(OfficeRealDocumentActivityError, ValueError):
    """Raised when a spreadsheet value looks like a formula and formulas are disabled."""

    code = "office_formula_like_value_denied"


@dataclass(frozen=True, slots=True)
class OfficeDocumentPathResolution:
    requested_path: str
    normalized_path: str
    resolved_path: Path
    relative_path: str


class OfficeRealDocumentActivityConfig(BaseModel):
    enabled: bool = False
    project_root: Path = Path(".")
    artifact_root: str | None = None
    max_file_bytes: int = 5_000_000
    max_text_preview_chars: int = 500
    max_paragraphs: int = 100
    max_paragraph_chars: int = 5_000
    max_xlsx_rows: int = 1_000
    max_xlsx_columns: int = 50
    max_xlsx_cell_chars: int = 5_000
    max_xlsx_preview_rows: int = 10
    max_xlsx_preview_columns: int = 8
    max_pptx_slides: int = 50
    max_pptx_bullets: int = 20
    max_pptx_text_chars: int = 5_000
    allow_formulas: bool = False
    allowed_extensions: tuple[str, ...] = (".docx", ".xlsx", ".pptx")
    forbidden_roots: tuple[str, ...] = (
        "models/",
        "models/gguf/",
        ".venv/",
        "venv/",
        ".git/",
        "logs/",
        "secrets/",
        "credentials/",
        "tokens/",
    )

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("artifact_root")
    @classmethod
    def validate_artifact_root(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("artifact_root must be non-empty when provided.")
        normalized = value.strip().replace("\\", "/")
        if "\x00" in normalized:
            raise ValueError("artifact_root must not contain NUL bytes.")
        if normalized.startswith("/") or _is_windows_drive_path(normalized):
            raise ValueError("artifact_root must be a safe relative path.")
        parts = PurePosixPath(normalized).parts
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("artifact_root must not contain traversal.")
        return str(PurePosixPath(normalized))

    @field_validator(
        "max_file_bytes",
        "max_text_preview_chars",
        "max_paragraphs",
        "max_paragraph_chars",
        "max_xlsx_rows",
        "max_xlsx_columns",
        "max_xlsx_cell_chars",
        "max_xlsx_preview_rows",
        "max_xlsx_preview_columns",
        "max_pptx_slides",
        "max_pptx_bullets",
        "max_pptx_text_chars",
    )
    @classmethod
    def validate_positive_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("office document limits must be > 0.")
        return value

    @model_validator(mode="after")
    def validate_lists(self) -> OfficeRealDocumentActivityConfig:
        normalized_extensions = tuple(ext.lower() for ext in self.allowed_extensions)
        if len(normalized_extensions) != len(set(normalized_extensions)):
            raise ValueError("allowed_extensions must not contain duplicates.")
        if any(ext in MACRO_ENABLED_EXTENSIONS for ext in normalized_extensions):
            raise ValueError("allowed_extensions must not include macro-enabled formats.")
        for extension in normalized_extensions:
            if not extension.startswith(".") or "/" in extension or "\\" in extension:
                raise ValueError("allowed_extensions must be simple suffixes.")

        normalized_roots = tuple(_normalize_root(root) for root in self.forbidden_roots)
        if len(normalized_roots) != len(set(normalized_roots)):
            raise ValueError("forbidden_roots must not contain duplicates.")
        object.__setattr__(self, "allowed_extensions", normalized_extensions)
        object.__setattr__(self, "forbidden_roots", normalized_roots)
        return self


class OfficeRealDocumentActionResult(ScriptExecutionResult):
    """Script result shape for the optional real office document scaffold."""


def run_office_real_document_activity(
    action: str,
    parameters: dict[str, Any] | None = None,
    config: OfficeRealDocumentActivityConfig | None = None,
    *,
    dependency_loader: Callable[[], dict[str, Any]] | None = None,
) -> OfficeRealDocumentActionResult:
    cfg = config or OfficeRealDocumentActivityConfig()
    params = parameters or {}
    normalized_action = action if isinstance(action, str) and action.strip() else "unknown"
    if normalized_action not in SUPPORTED_OFFICE_REAL_DOCUMENT_ACTIONS:
        return _error(
            normalized_action,
            "unknown_office_real_document_action",
            f"Unknown real office document action: {action}",
            cfg,
        )

    if not cfg.enabled:
        return _error(
            normalized_action,
            "real_office_document_automation_disabled",
            "Real office document automation is disabled by default.",
            cfg,
        )

    path_result = _validate_action_path(normalized_action, params, cfg)
    if path_result is not None and not path_result.success:
        return path_result

    formula_result = _validate_action_formula_values(normalized_action, params, cfg)
    if formula_result is not None and not formula_result.success:
        return formula_result

    if normalized_action in DOCX_ACTIONS:
        try:
            docx_module = _load_docx_dependency(dependency_loader)
        except ImportError as exc:
            return _error(
                normalized_action,
                "office_dependency_missing",
                "Optional python-docx dependency is not installed.",
                cfg,
                dependency_error_type=exc.__class__.__name__,
            )
        except Exception as exc:
            return _error(
                normalized_action,
                "office_dependency_missing",
                "Optional python-docx dependency is unavailable.",
                cfg,
                dependency_error_type=exc.__class__.__name__,
            )
        return _run_docx_action(normalized_action, params, cfg, docx_module)

    if normalized_action in XLSX_ACTIONS:
        try:
            openpyxl_module = _load_xlsx_dependency(dependency_loader)
        except ImportError as exc:
            return _error(
                normalized_action,
                "office_dependency_missing",
                "Optional openpyxl dependency is not installed.",
                cfg,
                dependency_error_type=exc.__class__.__name__,
            )
        except Exception as exc:
            return _error(
                normalized_action,
                "office_dependency_missing",
                "Optional openpyxl dependency is unavailable.",
                cfg,
                dependency_error_type=exc.__class__.__name__,
            )
        return _run_xlsx_action(normalized_action, params, cfg, openpyxl_module)

    if normalized_action in PPTX_ACTIONS:
        try:
            pptx_module = _load_pptx_dependency(dependency_loader)
        except ImportError as exc:
            return _error(
                normalized_action,
                "office_dependency_missing",
                "Optional python-pptx dependency is not installed.",
                cfg,
                dependency_error_type=exc.__class__.__name__,
            )
        except Exception as exc:
            return _error(
                normalized_action,
                "office_dependency_missing",
                "Optional python-pptx dependency is unavailable.",
                cfg,
                dependency_error_type=exc.__class__.__name__,
            )
        return _run_pptx_action(normalized_action, params, cfg, pptx_module)

    return _error(
        normalized_action,
        "office_backend_not_implemented",
        "Office document action is not implemented.",
        cfg,
    )


def _load_docx_dependency(
    dependency_loader: Callable[[], dict[str, Any]] | None,
) -> Any:
    if dependency_loader is None:
        return load_docx_document_dependency()

    loaded = dependency_loader()
    if isinstance(loaded, dict):
        docx_module = loaded.get("docx")
    else:
        docx_module = getattr(loaded, "docx", loaded)
    if docx_module is None or not hasattr(docx_module, "Document"):
        raise OfficeDependencyMissingError("python-docx")
    return docx_module


def load_docx_document_dependency() -> Any:
    try:
        return __import__("docx")
    except ImportError as exc:
        raise OfficeDependencyMissingError("python-docx") from exc


def _load_xlsx_dependency(
    dependency_loader: Callable[[], dict[str, Any]] | None,
) -> Any:
    if dependency_loader is None:
        return load_xlsx_document_dependency()

    loaded = dependency_loader()
    if isinstance(loaded, dict):
        openpyxl_module = loaded.get("openpyxl")
    else:
        openpyxl_module = getattr(loaded, "openpyxl", loaded)
    if (
        openpyxl_module is None
        or not hasattr(openpyxl_module, "Workbook")
        or not hasattr(openpyxl_module, "load_workbook")
    ):
        raise OfficeDependencyMissingError("openpyxl")
    return openpyxl_module


def load_xlsx_document_dependency() -> Any:
    try:
        return __import__("openpyxl")
    except ImportError as exc:
        raise OfficeDependencyMissingError("openpyxl") from exc


def _load_pptx_dependency(
    dependency_loader: Callable[[], dict[str, Any]] | None,
) -> Any:
    if dependency_loader is None:
        return load_pptx_document_dependency()

    loaded = dependency_loader()
    if isinstance(loaded, dict):
        pptx_module = loaded.get("pptx")
    else:
        pptx_module = getattr(loaded, "pptx", loaded)
    if pptx_module is None or not hasattr(pptx_module, "Presentation"):
        raise OfficeDependencyMissingError("python-pptx")
    return pptx_module


def load_pptx_document_dependency() -> Any:
    try:
        return __import__("pptx")
    except ImportError as exc:
        raise OfficeDependencyMissingError("python-pptx") from exc


def load_office_document_dependencies() -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for module_name, package_name in OFFICE_DOCUMENT_DEPENDENCY_MODULES.items():
        try:
            loaded[module_name] = __import__(module_name)
        except ImportError as exc:
            raise OfficeDependencyMissingError(package_name) from exc
    return loaded


def _run_docx_action(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    docx_module: Any,
) -> OfficeRealDocumentActionResult:
    if action == "office_create_docx":
        return _create_docx(parameters, config, docx_module)
    if action == "office_append_docx_section":
        return _append_docx_section(parameters, config, docx_module)
    if action == "office_extract_docx_text":
        return _extract_docx_text(parameters, config, docx_module)
    return _error(
        action,
        "office_backend_not_implemented",
        "DOCX action is not implemented.",
        config,
    )


def _create_docx(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    docx_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_create_docx"
    resolution = _resolve_action_docx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    paragraphs_result = _paragraph_list(action, parameters.get("paragraphs", []), "paragraphs", config)
    if isinstance(paragraphs_result, OfficeRealDocumentActionResult):
        return paragraphs_result
    paragraphs = paragraphs_result

    title_result = _optional_text(action, parameters.get("title"), "title", config)
    if isinstance(title_result, OfficeRealDocumentActionResult):
        return title_result
    title = title_result

    metadata = parameters.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return _error(action, "invalid_parameter", "metadata must be a dict when provided.", config)

    document = docx_module.Document()
    if title:
        document.add_heading(title, level=1)
        try:
            document.core_properties.title = title
        except Exception:
            pass
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)

    try:
        _save_docx_atomically(document, resolution.resolved_path, config)
    except OfficeRealDocumentPathError as exc:
        return _error(
            action,
            exc.code,
            str(exc),
            config,
            path_relative=resolution.relative_path,
        )
    except Exception as exc:
        return _error(
            action,
            "office_docx_write_failed",
            "DOCX document could not be written.",
            config,
            error_class=exc.__class__.__name__,
        )

    text = _document_text(document)
    return _docx_success(
        action,
        config,
        resolution,
        text,
        paragraph_count=_paragraph_count(document),
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _append_docx_section(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    docx_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_append_docx_section"
    resolution = _resolve_existing_docx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    heading_result = _optional_text(action, parameters.get("heading"), "heading", config)
    if isinstance(heading_result, OfficeRealDocumentActionResult):
        return heading_result
    heading = heading_result

    paragraphs_result = _paragraph_list(action, parameters.get("paragraphs"), "paragraphs", config)
    if isinstance(paragraphs_result, OfficeRealDocumentActionResult):
        return paragraphs_result
    paragraphs = paragraphs_result
    if not paragraphs:
        return _error(action, "office_docx_invalid_content", "paragraphs must not be empty.", config)

    try:
        document = docx_module.Document(str(resolution.resolved_path))
    except OfficeRealDocumentPathError as exc:
        return _error(
            action,
            exc.code,
            str(exc),
            config,
            path_relative=resolution.relative_path,
        )
    except Exception as exc:
        return _error(
            action,
            "office_docx_read_failed",
            "DOCX document could not be read.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )

    if heading:
        document.add_heading(heading, level=1)
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)

    try:
        _save_docx_atomically(document, resolution.resolved_path, config)
    except Exception as exc:
        return _error(
            action,
            "office_docx_write_failed",
            "DOCX document could not be written.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )

    text = _document_text(document)
    return _docx_success(
        action,
        config,
        resolution,
        text,
        paragraph_count=_paragraph_count(document),
        appended_paragraph_count=len(paragraphs),
        heading_added=bool(heading),
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _extract_docx_text(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    docx_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_extract_docx_text"
    resolution = _resolve_existing_docx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    preview_limit_result = _preview_limit(action, parameters.get("max_chars"), config)
    if isinstance(preview_limit_result, OfficeRealDocumentActionResult):
        return preview_limit_result
    preview_limit = preview_limit_result

    try:
        document = docx_module.Document(str(resolution.resolved_path))
    except Exception as exc:
        return _error(
            action,
            "office_docx_read_failed",
            "DOCX document could not be read.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )

    text = _document_text(document)
    preview, truncated = _preview_with_limit(text, preview_limit)
    return OfficeRealDocumentActionResult(
        action=action,
        success=True,
        output=preview,
        metadata={
            "document_type": "docx",
            "path_relative": resolution.relative_path,
            "paragraph_count": _paragraph_count(document),
            "character_count": len(text),
            "text_preview": preview,
            "truncated": truncated,
            "file_size_bytes": resolution.resolved_path.stat().st_size,
            **_success_metadata(config),
        },
    )


def _run_xlsx_action(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    openpyxl_module: Any,
) -> OfficeRealDocumentActionResult:
    if action == "office_create_xlsx":
        return _create_xlsx(parameters, config, openpyxl_module)
    if action == "office_update_xlsx_cell":
        return _update_xlsx_cell(parameters, config, openpyxl_module)
    if action == "office_append_xlsx_row":
        return _append_xlsx_row(parameters, config, openpyxl_module)
    if action == "office_read_xlsx_summary":
        return _read_xlsx_summary(parameters, config, openpyxl_module)
    return _error(
        action,
        "office_backend_not_implemented",
        "XLSX action is not implemented.",
        config,
    )


def _run_pptx_action(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    pptx_module: Any,
) -> OfficeRealDocumentActionResult:
    if action == "office_create_pptx":
        return _create_pptx(parameters, config, pptx_module)
    if action == "office_add_pptx_slide":
        return _add_pptx_slide(parameters, config, pptx_module)
    if action == "office_extract_pptx_text":
        return _extract_pptx_text(parameters, config, pptx_module)
    return _error(
        action,
        "office_backend_not_implemented",
        "PPTX action is not implemented.",
        config,
    )


def _create_pptx(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    pptx_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_create_pptx"
    resolution = _resolve_action_pptx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    title_result = _optional_pptx_text(action, parameters.get("title"), "title", config)
    if isinstance(title_result, OfficeRealDocumentActionResult):
        return title_result
    subtitle_result = _optional_pptx_text(action, parameters.get("subtitle"), "subtitle", config)
    if isinstance(subtitle_result, OfficeRealDocumentActionResult):
        return subtitle_result

    slides_result = _pptx_slide_specs(action, parameters.get("slides"), config)
    if isinstance(slides_result, OfficeRealDocumentActionResult):
        return slides_result
    slides = slides_result

    metadata = parameters.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return _error(action, "invalid_parameter", "metadata must be a dict when provided.", config)

    title_slide_count = 1 if title_result or subtitle_result else 0
    if title_slide_count + len(slides) > config.max_pptx_slides:
        return _error(action, "office_pptx_too_many_slides", "PPTX exceeds max_pptx_slides.", config)

    presentation = pptx_module.Presentation()
    if title_result or subtitle_result:
        _add_pptx_title_slide(presentation, title_result or "", subtitle_result or "")
    for slide in slides:
        _add_pptx_content_slide(presentation, slide["title"], slide["bullets"])

    try:
        _save_pptx_atomically(presentation, resolution.resolved_path, config)
    except OfficeRealDocumentPathError as exc:
        return _error(action, exc.code, str(exc), config, path_relative=resolution.relative_path)
    except Exception as exc:
        return _error(
            action,
            "office_pptx_write_failed",
            "PPTX presentation could not be written.",
            config,
            error_class=exc.__class__.__name__,
        )

    text = _presentation_text(presentation)
    return _pptx_success(
        action,
        config,
        resolution,
        text,
        slide_count=_presentation_slide_count(presentation),
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _add_pptx_slide(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    pptx_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_add_pptx_slide"
    resolution = _resolve_existing_pptx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    presentation_result = _load_existing_pptx_presentation(action, resolution, config, pptx_module)
    if isinstance(presentation_result, OfficeRealDocumentActionResult):
        return presentation_result
    presentation = presentation_result

    if _presentation_slide_count(presentation) + 1 > config.max_pptx_slides:
        return _error(
            action,
            "office_pptx_too_many_slides",
            "Adding slide would exceed max_pptx_slides.",
            config,
            path_relative=resolution.relative_path,
        )

    slide_result = _pptx_slide_spec_from_parameters(action, parameters, config)
    if isinstance(slide_result, OfficeRealDocumentActionResult):
        return slide_result
    _add_pptx_content_slide(presentation, slide_result["title"], slide_result["bullets"])

    try:
        _save_pptx_atomically(presentation, resolution.resolved_path, config)
    except OfficeRealDocumentPathError as exc:
        return _error(action, exc.code, str(exc), config, path_relative=resolution.relative_path)
    except Exception as exc:
        return _error(
            action,
            "office_pptx_write_failed",
            "PPTX presentation could not be written.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )

    text = _presentation_text(presentation)
    return _pptx_success(
        action,
        config,
        resolution,
        text,
        slide_count=_presentation_slide_count(presentation),
        added_slide_title=slide_result["title"],
        added_bullet_count=len(slide_result["bullets"]),
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _extract_pptx_text(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    pptx_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_extract_pptx_text"
    resolution = _resolve_existing_pptx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    preview_limit_result = _preview_limit(action, parameters.get("max_chars"), config)
    if isinstance(preview_limit_result, OfficeRealDocumentActionResult):
        return preview_limit_result

    presentation_result = _load_existing_pptx_presentation(action, resolution, config, pptx_module)
    if isinstance(presentation_result, OfficeRealDocumentActionResult):
        return presentation_result

    text = _presentation_text(presentation_result)
    preview, truncated = _preview_with_limit(text, preview_limit_result)
    return OfficeRealDocumentActionResult(
        action=action,
        success=True,
        output=preview,
        metadata={
            "document_type": "pptx",
            "path_relative": resolution.relative_path,
            "slide_count": _presentation_slide_count(presentation_result),
            "character_count": len(text),
            "text_preview": preview,
            "truncated": truncated,
            "file_size_bytes": resolution.resolved_path.stat().st_size,
            **_success_metadata(config),
        },
    )


def _create_xlsx(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    openpyxl_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_create_xlsx"
    resolution = _resolve_action_xlsx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    sheet_result = _sheet_name(action, parameters.get("sheet_name"), config)
    if isinstance(sheet_result, OfficeRealDocumentActionResult):
        return sheet_result
    sheet_name = sheet_result

    headers_result = _xlsx_row(action, parameters.get("headers", []), "headers", config)
    if isinstance(headers_result, OfficeRealDocumentActionResult):
        return headers_result
    headers = headers_result

    rows_result = _xlsx_rows(action, parameters.get("rows", []), config)
    if isinstance(rows_result, OfficeRealDocumentActionResult):
        return rows_result
    rows = rows_result

    metadata = parameters.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return _error(action, "invalid_parameter", "metadata must be a dict when provided.", config)

    shape_result = _validate_xlsx_shape(action, headers, rows, config)
    if shape_result is not None:
        return shape_result

    workbook = openpyxl_module.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    if headers:
        worksheet.append(headers)
    for row in rows:
        worksheet.append(row)

    try:
        _save_xlsx_atomically(workbook, resolution.resolved_path, config)
    except OfficeRealDocumentPathError as exc:
        _close_workbook(workbook)
        return _error(
            action,
            exc.code,
            str(exc),
            config,
            path_relative=resolution.relative_path,
        )
    except Exception as exc:
        _close_workbook(workbook)
        return _error(
            action,
            "office_xlsx_write_failed",
            "XLSX workbook could not be written.",
            config,
            error_class=exc.__class__.__name__,
        )

    summary = _worksheet_summary(worksheet, config)
    _close_workbook(workbook)
    return _xlsx_success(
        action,
        config,
        resolution,
        sheet_name=sheet_name,
        row_count=summary["row_count"],
        column_count=summary["column_count"],
        table_preview=summary["table_preview"],
        truncated=summary["truncated"],
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _update_xlsx_cell(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    openpyxl_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_update_xlsx_cell"
    resolution = _resolve_existing_xlsx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    cell_result = _xlsx_cell_coordinate(parameters.get("cell"), config)
    if isinstance(cell_result, OfficeRealDocumentActionResult):
        return cell_result
    cell = cell_result

    if "value" not in parameters:
        return _error(action, "missing_parameter", "Missing required parameter: value.", config)
    value_result = _xlsx_cell_value(action, parameters["value"], config)
    if isinstance(value_result, OfficeRealDocumentActionResult):
        return value_result

    workbook_result = _load_existing_xlsx_workbook(action, resolution, config, openpyxl_module)
    if isinstance(workbook_result, OfficeRealDocumentActionResult):
        return workbook_result
    workbook = workbook_result

    worksheet_result = _worksheet_for_action(action, workbook, parameters.get("sheet_name"), config)
    if isinstance(worksheet_result, OfficeRealDocumentActionResult):
        _close_workbook(workbook)
        return worksheet_result
    worksheet = worksheet_result

    worksheet[cell] = value_result
    try:
        _save_xlsx_atomically(workbook, resolution.resolved_path, config)
    except OfficeRealDocumentPathError as exc:
        _close_workbook(workbook)
        return _error(action, exc.code, str(exc), config, path_relative=resolution.relative_path)
    except Exception as exc:
        _close_workbook(workbook)
        return _error(
            action,
            "office_xlsx_write_failed",
            "XLSX workbook could not be written.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )

    summary = _worksheet_summary(worksheet, config)
    sheet_name = worksheet.title
    _close_workbook(workbook)
    return _xlsx_success(
        action,
        config,
        resolution,
        sheet_name=sheet_name,
        updated_cell=cell.upper(),
        row_count=summary["row_count"],
        column_count=summary["column_count"],
        table_preview=summary["table_preview"],
        truncated=summary["truncated"],
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _append_xlsx_row(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    openpyxl_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_append_xlsx_row"
    resolution = _resolve_existing_xlsx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    row_result = _xlsx_row(action, parameters.get("values"), "values", config)
    if isinstance(row_result, OfficeRealDocumentActionResult):
        return row_result
    if not row_result:
        return _error(action, "office_xlsx_invalid_content", "values must not be empty.", config)
    if len(row_result) > config.max_xlsx_columns:
        return _error(
            action,
            "office_xlsx_too_many_columns",
            "values exceeds max_xlsx_columns.",
            config,
        )

    workbook_result = _load_existing_xlsx_workbook(action, resolution, config, openpyxl_module)
    if isinstance(workbook_result, OfficeRealDocumentActionResult):
        return workbook_result
    workbook = workbook_result

    worksheet_result = _worksheet_for_action(action, workbook, parameters.get("sheet_name"), config)
    if isinstance(worksheet_result, OfficeRealDocumentActionResult):
        _close_workbook(workbook)
        return worksheet_result
    worksheet = worksheet_result

    if _effective_row_count(worksheet) + 1 > config.max_xlsx_rows:
        _close_workbook(workbook)
        return _error(
            action,
            "office_xlsx_too_many_rows",
            "Appending row would exceed max_xlsx_rows.",
            config,
            path_relative=resolution.relative_path,
        )

    worksheet.append(row_result)
    row_index = worksheet.max_row
    try:
        _save_xlsx_atomically(workbook, resolution.resolved_path, config)
    except OfficeRealDocumentPathError as exc:
        _close_workbook(workbook)
        return _error(action, exc.code, str(exc), config, path_relative=resolution.relative_path)
    except Exception as exc:
        _close_workbook(workbook)
        return _error(
            action,
            "office_xlsx_write_failed",
            "XLSX workbook could not be written.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )

    summary = _worksheet_summary(worksheet, config)
    sheet_name = worksheet.title
    _close_workbook(workbook)
    return _xlsx_success(
        action,
        config,
        resolution,
        sheet_name=sheet_name,
        appended_row_index=row_index,
        row_count=summary["row_count"],
        column_count=summary["column_count"],
        table_preview=summary["table_preview"],
        truncated=summary["truncated"],
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _read_xlsx_summary(
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
    openpyxl_module: Any,
) -> OfficeRealDocumentActionResult:
    action = "office_read_xlsx_summary"
    resolution = _resolve_existing_xlsx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution

    preview_rows_result = _xlsx_preview_limit(
        action,
        parameters.get("max_rows"),
        config.max_xlsx_preview_rows,
        config.max_xlsx_rows,
        "max_rows",
        config,
    )
    if isinstance(preview_rows_result, OfficeRealDocumentActionResult):
        return preview_rows_result
    preview_columns_result = _xlsx_preview_limit(
        action,
        parameters.get("max_columns"),
        config.max_xlsx_preview_columns,
        config.max_xlsx_columns,
        "max_columns",
        config,
    )
    if isinstance(preview_columns_result, OfficeRealDocumentActionResult):
        return preview_columns_result

    workbook_result = _load_existing_xlsx_workbook(
        action,
        resolution,
        config,
        openpyxl_module,
        read_only=True,
    )
    if isinstance(workbook_result, OfficeRealDocumentActionResult):
        return workbook_result
    workbook = workbook_result

    worksheet_result = _worksheet_for_action(action, workbook, parameters.get("sheet_name"), config)
    if isinstance(worksheet_result, OfficeRealDocumentActionResult):
        _close_workbook(workbook)
        return worksheet_result
    worksheet = worksheet_result

    summary = _worksheet_summary(
        worksheet,
        config,
        preview_rows=preview_rows_result,
        preview_columns=preview_columns_result,
    )
    sheet_names = list(workbook.sheetnames)
    active_sheet = workbook.active.title if workbook.active is not None else worksheet.title
    sheet_name = worksheet.title
    _close_workbook(workbook)
    return _xlsx_success(
        action,
        config,
        resolution,
        sheet_name=sheet_name,
        active_sheet=active_sheet,
        sheet_names=sheet_names,
        row_count=summary["row_count"],
        column_count=summary["column_count"],
        table_preview=summary["table_preview"],
        truncated=summary["truncated"],
        file_size_bytes=resolution.resolved_path.stat().st_size,
    )


def _resolve_action_xlsx_path(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeDocumentPathResolution | OfficeRealDocumentActionResult:
    path = parameters.get("path")
    if path is None:
        return _error(action, "missing_parameter", "Missing required parameter: path.", config)
    if not isinstance(path, str):
        return _error(action, "invalid_parameter", "path must be a string.", config)
    try:
        resolution = resolve_safe_office_real_document_path(path, config)
    except OfficeRealDocumentPathError as exc:
        return _error(action, exc.code, str(exc), config)
    if Path(resolution.normalized_path).suffix.lower() != ".xlsx":
        return _error(action, "office_extension_denied", "XLSX action requires a .xlsx path.", config)
    return resolution


def _resolve_existing_xlsx_path(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeDocumentPathResolution | OfficeRealDocumentActionResult:
    resolution = _resolve_action_xlsx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution
    if not resolution.resolved_path.exists() or not resolution.resolved_path.is_file():
        return _error(
            action,
            "office_xlsx_file_missing",
            "XLSX workbook does not exist.",
            config,
            path_relative=resolution.relative_path,
        )
    size = resolution.resolved_path.stat().st_size
    if size > config.max_file_bytes:
        return _error(
            action,
            "office_xlsx_file_too_large",
            "XLSX workbook exceeds max_file_bytes.",
            config,
            path_relative=resolution.relative_path,
            file_size_bytes=size,
            max_file_bytes=config.max_file_bytes,
        )
    return resolution


def _load_existing_xlsx_workbook(
    action: str,
    resolution: OfficeDocumentPathResolution,
    config: OfficeRealDocumentActivityConfig,
    openpyxl_module: Any,
    *,
    read_only: bool = False,
) -> Any | OfficeRealDocumentActionResult:
    try:
        return openpyxl_module.load_workbook(
            str(resolution.resolved_path),
            read_only=read_only,
            data_only=False,
            keep_links=False,
        )
    except Exception as exc:
        return _error(
            action,
            "office_xlsx_read_failed",
            "XLSX workbook could not be read.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )


def _save_xlsx_atomically(
    workbook: Any,
    destination: Path,
    config: OfficeRealDocumentActivityConfig,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            temp_path = Path(tmp.name)
        workbook.save(str(temp_path))
        if temp_path.stat().st_size > config.max_file_bytes:
            raise OfficeRealDocumentPathError(
                "office_xlsx_file_too_large",
                "XLSX workbook exceeds max_file_bytes.",
            )
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _worksheet_for_action(
    action: str,
    workbook: Any,
    sheet_name: Any,
    config: OfficeRealDocumentActivityConfig,
) -> Any | OfficeRealDocumentActionResult:
    if sheet_name is None:
        worksheet = workbook.active
    else:
        sheet_result = _sheet_name(action, sheet_name, config)
        if isinstance(sheet_result, OfficeRealDocumentActionResult):
            return sheet_result
        if sheet_result not in workbook.sheetnames:
            return _error(
                action,
                "office_xlsx_invalid_sheet",
                "Requested sheet does not exist.",
                config,
            )
        worksheet = workbook[sheet_result]

    row_count, column_count = _worksheet_bounds(worksheet)
    if row_count > config.max_xlsx_rows:
        return _error(
            action,
            "office_xlsx_too_many_rows",
            "Worksheet exceeds max_xlsx_rows.",
            config,
            sheet_name=worksheet.title,
            row_count=row_count,
            max_xlsx_rows=config.max_xlsx_rows,
        )
    if column_count > config.max_xlsx_columns:
        return _error(
            action,
            "office_xlsx_too_many_columns",
            "Worksheet exceeds max_xlsx_columns.",
            config,
            sheet_name=worksheet.title,
            column_count=column_count,
            max_xlsx_columns=config.max_xlsx_columns,
        )
    return worksheet


def _sheet_name(
    action: str,
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> str | OfficeRealDocumentActionResult:
    if value is None:
        return "Sheet"
    if not isinstance(value, str):
        return _error(action, "office_xlsx_invalid_sheet", "sheet_name must be a string.", config)
    if not value.strip():
        return _error(action, "office_xlsx_invalid_sheet", "sheet_name must be non-empty.", config)
    if "\x00" in value:
        return _error(action, "office_xlsx_invalid_sheet", "sheet_name must not contain NUL.", config)
    normalized = value.strip()
    if len(normalized) > 31:
        return _error(action, "office_xlsx_invalid_sheet", "sheet_name is too long.", config)
    if any(char in INVALID_SHEET_NAME_CHARS for char in normalized):
        return _error(action, "office_xlsx_invalid_sheet", "sheet_name contains invalid characters.", config)
    return normalized


def _xlsx_cell_coordinate(
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> str | OfficeRealDocumentActionResult:
    action = "office_update_xlsx_cell"
    if not isinstance(value, str) or not value.strip():
        return _error(action, "office_xlsx_invalid_cell", "cell must be a non-empty string.", config)
    cell = value.strip().upper()
    if len(cell) > 10 or not CELL_COORDINATE_RE.fullmatch(cell):
        return _error(action, "office_xlsx_invalid_cell", "cell must be an A1-style coordinate.", config)
    column = _column_index(cell.rstrip("0123456789"))
    row = int(cell[len(cell.rstrip("0123456789")) :])
    if row > config.max_xlsx_rows:
        return _error(action, "office_xlsx_too_many_rows", "cell row exceeds max_xlsx_rows.", config)
    if column > config.max_xlsx_columns:
        return _error(action, "office_xlsx_too_many_columns", "cell column exceeds max_xlsx_columns.", config)
    return cell


def _column_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index


def _xlsx_rows(
    action: str,
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> list[list[Any]] | OfficeRealDocumentActionResult:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, list) for row in value):
        return _error(action, "invalid_parameter", "rows must be a list of rows.", config)
    if len(value) > config.max_xlsx_rows:
        return _error(action, "office_xlsx_too_many_rows", "rows exceeds max_xlsx_rows.", config)
    rows: list[list[Any]] = []
    for row in value:
        row_result = _xlsx_row(action, row, "row", config)
        if isinstance(row_result, OfficeRealDocumentActionResult):
            return row_result
        rows.append(row_result)
    return rows


def _xlsx_row(
    action: str,
    value: Any,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> list[Any] | OfficeRealDocumentActionResult:
    if value is None:
        return _error(action, "invalid_parameter", f"{field_name} must be a list.", config)
    if not isinstance(value, list):
        return _error(action, "invalid_parameter", f"{field_name} must be a list.", config)
    if len(value) > config.max_xlsx_columns:
        return _error(
            action,
            "office_xlsx_too_many_columns",
            f"{field_name} exceeds max_xlsx_columns.",
            config,
        )
    row: list[Any] = []
    for item in value:
        value_result = _xlsx_cell_value(action, item, config)
        if isinstance(value_result, OfficeRealDocumentActionResult):
            return value_result
        row.append(value_result)
    return row


def _xlsx_cell_value(
    action: str,
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> Any | OfficeRealDocumentActionResult:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if "\x00" in value:
            return _error(
                action,
                "office_xlsx_invalid_content",
                "XLSX cell values must not contain NUL characters.",
                config,
            )
        if len(value) > config.max_xlsx_cell_chars:
            return _error(
                action,
                "office_xlsx_invalid_content",
                "XLSX cell value exceeds max_xlsx_cell_chars.",
                config,
            )
        try:
            validate_spreadsheet_text_value(value, config)
        except OfficeFormulaLikeValueError as exc:
            return _error(action, exc.code, str(exc), config)
        return value
    return _error(
        action,
        "invalid_parameter",
        "XLSX cell values must be scalar strings, numbers, booleans, or null.",
        config,
    )


def _validate_xlsx_shape(
    action: str,
    headers: list[Any],
    rows: list[list[Any]],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeRealDocumentActionResult | None:
    row_count = len(rows) + (1 if headers else 0)
    column_count = max([len(headers), *(len(row) for row in rows)], default=0)
    if row_count > config.max_xlsx_rows:
        return _error(action, "office_xlsx_too_many_rows", "Workbook exceeds max_xlsx_rows.", config)
    if column_count > config.max_xlsx_columns:
        return _error(
            action,
            "office_xlsx_too_many_columns",
            "Workbook exceeds max_xlsx_columns.",
            config,
        )
    return None


def _xlsx_preview_limit(
    action: str,
    value: Any,
    default: int,
    maximum: int,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> int | OfficeRealDocumentActionResult:
    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        return _error(action, "invalid_parameter", f"{field_name} must be a positive integer.", config)
    return min(value, maximum)


def _worksheet_bounds(worksheet: Any) -> tuple[int, int]:
    row_count = int(worksheet.max_row or 0)
    column_count = int(worksheet.max_column or 0)
    if row_count == 1 and column_count == 1:
        try:
            first = next(worksheet.iter_rows(min_row=1, max_row=1, max_col=1, values_only=True))
        except StopIteration:
            return 0, 0
        if not first or first[0] is None:
            return 0, 0
    return row_count, column_count


def _effective_row_count(worksheet: Any) -> int:
    return _worksheet_bounds(worksheet)[0]


def _worksheet_summary(
    worksheet: Any,
    config: OfficeRealDocumentActivityConfig,
    *,
    preview_rows: int | None = None,
    preview_columns: int | None = None,
) -> dict[str, Any]:
    row_count, column_count = _worksheet_bounds(worksheet)
    max_rows = preview_rows or config.max_xlsx_preview_rows
    max_columns = preview_columns or config.max_xlsx_preview_columns
    preview = _worksheet_preview(worksheet, min(max_rows, row_count), min(max_columns, column_count))
    return {
        "row_count": row_count,
        "column_count": column_count,
        "table_preview": preview,
        "truncated": row_count > max_rows or column_count > max_columns,
    }


def _worksheet_preview(
    worksheet: Any,
    max_rows: int,
    max_columns: int,
) -> list[list[Any]]:
    if max_rows <= 0 or max_columns <= 0:
        return []
    rows: list[list[Any]] = []
    for row in worksheet.iter_rows(
        min_row=1,
        max_row=max_rows,
        min_col=1,
        max_col=max_columns,
        values_only=True,
    ):
        rows.append([_preview_cell(value) for value in row])
    return rows


def _preview_cell(value: Any) -> Any:
    if isinstance(value, str):
        return text_preview(value, 120)
    return value


def _xlsx_preview_text(table_preview: list[list[Any]], config: OfficeRealDocumentActivityConfig) -> str:
    rendered_rows = [
        " | ".join("" if value is None else str(value) for value in row)
        for row in table_preview
    ]
    return text_preview("\n".join(rendered_rows), config.max_text_preview_chars)


def _xlsx_success(
    action: str,
    config: OfficeRealDocumentActivityConfig,
    resolution: OfficeDocumentPathResolution,
    *,
    sheet_name: str,
    row_count: int,
    column_count: int,
    table_preview: list[list[Any]],
    truncated: bool,
    **metadata: Any,
) -> OfficeRealDocumentActionResult:
    preview = _xlsx_preview_text(table_preview, config)
    return OfficeRealDocumentActionResult(
        action=action,
        success=True,
        output=preview,
        metadata={
            "document_type": "xlsx",
            "path_relative": resolution.relative_path,
            "sheet_name": sheet_name,
            "row_count": row_count,
            "column_count": column_count,
            "table_preview": table_preview,
            "text_preview": preview,
            "truncated": truncated,
            **metadata,
            **_success_metadata(config),
        },
    )


def _close_workbook(workbook: Any) -> None:
    close = getattr(workbook, "close", None)
    if callable(close):
        close()


def _resolve_action_pptx_path(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeDocumentPathResolution | OfficeRealDocumentActionResult:
    path = parameters.get("path")
    if path is None:
        return _error(action, "missing_parameter", "Missing required parameter: path.", config)
    if not isinstance(path, str):
        return _error(action, "invalid_parameter", "path must be a string.", config)
    try:
        resolution = resolve_safe_office_real_document_path(path, config)
    except OfficeRealDocumentPathError as exc:
        return _error(action, exc.code, str(exc), config)
    if Path(resolution.normalized_path).suffix.lower() != ".pptx":
        return _error(action, "office_extension_denied", "PPTX action requires a .pptx path.", config)
    return resolution


def _resolve_existing_pptx_path(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeDocumentPathResolution | OfficeRealDocumentActionResult:
    resolution = _resolve_action_pptx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution
    if not resolution.resolved_path.exists() or not resolution.resolved_path.is_file():
        return _error(
            action,
            "office_pptx_file_missing",
            "PPTX presentation does not exist.",
            config,
            path_relative=resolution.relative_path,
        )
    size = resolution.resolved_path.stat().st_size
    if size > config.max_file_bytes:
        return _error(
            action,
            "office_pptx_file_too_large",
            "PPTX presentation exceeds max_file_bytes.",
            config,
            path_relative=resolution.relative_path,
            file_size_bytes=size,
            max_file_bytes=config.max_file_bytes,
        )
    return resolution


def _load_existing_pptx_presentation(
    action: str,
    resolution: OfficeDocumentPathResolution,
    config: OfficeRealDocumentActivityConfig,
    pptx_module: Any,
) -> Any | OfficeRealDocumentActionResult:
    try:
        presentation = pptx_module.Presentation(str(resolution.resolved_path))
    except Exception as exc:
        return _error(
            action,
            "office_pptx_read_failed",
            "PPTX presentation could not be read.",
            config,
            path_relative=resolution.relative_path,
            error_class=exc.__class__.__name__,
        )
    slide_count = _presentation_slide_count(presentation)
    if slide_count > config.max_pptx_slides:
        return _error(
            action,
            "office_pptx_too_many_slides",
            "PPTX presentation exceeds max_pptx_slides.",
            config,
            path_relative=resolution.relative_path,
            slide_count=slide_count,
            max_pptx_slides=config.max_pptx_slides,
        )
    return presentation


def _save_pptx_atomically(
    presentation: Any,
    destination: Path,
    config: OfficeRealDocumentActivityConfig,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            temp_path = Path(tmp.name)
        presentation.save(str(temp_path))
        if temp_path.stat().st_size > config.max_file_bytes:
            raise OfficeRealDocumentPathError(
                "office_pptx_file_too_large",
                "PPTX presentation exceeds max_file_bytes.",
            )
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _pptx_slide_specs(
    action: str,
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> list[dict[str, Any]] | OfficeRealDocumentActionResult:
    if value is None:
        return []
    if not isinstance(value, list):
        return _error(action, "invalid_parameter", "slides must be a list.", config)
    if len(value) > config.max_pptx_slides:
        return _error(action, "office_pptx_too_many_slides", "slides exceeds max_pptx_slides.", config)

    slides: list[dict[str, Any]] = []
    for slide in value:
        if not isinstance(slide, dict):
            return _error(action, "invalid_parameter", "slides must contain objects.", config)
        slide_result = _pptx_slide_spec_from_parameters(action, slide, config)
        if isinstance(slide_result, OfficeRealDocumentActionResult):
            return slide_result
        slides.append(slide_result)
    return slides


def _pptx_slide_spec_from_parameters(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> dict[str, Any] | OfficeRealDocumentActionResult:
    title_result = _optional_pptx_text(action, parameters.get("title"), "title", config)
    if isinstance(title_result, OfficeRealDocumentActionResult):
        return title_result

    bullets_result = _pptx_bullet_list(action, parameters.get("bullets"), "bullets", config)
    if isinstance(bullets_result, OfficeRealDocumentActionResult):
        return bullets_result
    bullets = list(bullets_result)

    body_result = _optional_pptx_text(action, parameters.get("body"), "body", config)
    if isinstance(body_result, OfficeRealDocumentActionResult):
        return body_result
    if body_result:
        bullets.insert(0, body_result)

    paragraphs_result = _pptx_bullet_list(action, parameters.get("paragraphs"), "paragraphs", config)
    if isinstance(paragraphs_result, OfficeRealDocumentActionResult):
        return paragraphs_result
    bullets.extend(paragraphs_result)

    notes_result = _optional_pptx_text(action, parameters.get("notes"), "notes", config)
    if isinstance(notes_result, OfficeRealDocumentActionResult):
        return notes_result

    if len(bullets) > config.max_pptx_bullets:
        return _error(action, "office_pptx_too_many_bullets", "bullets exceeds max_pptx_bullets.", config)

    return {"title": title_result or "", "bullets": bullets}


def _pptx_bullet_list(
    action: str,
    value: Any,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> list[str] | OfficeRealDocumentActionResult:
    if value is None:
        return []
    if not isinstance(value, list):
        return _error(action, "invalid_parameter", f"{field_name} must be a list.", config)
    if len(value) > config.max_pptx_bullets:
        return _error(
            action,
            "office_pptx_too_many_bullets",
            f"{field_name} exceeds max_pptx_bullets.",
            config,
        )

    bullets: list[str] = []
    for item in value:
        text_result = _pptx_text_or_error(action, item, field_name, config)
        if isinstance(text_result, OfficeRealDocumentActionResult):
            return text_result
        bullets.append(text_result)
    return bullets


def _optional_pptx_text(
    action: str,
    value: Any,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> str | None | OfficeRealDocumentActionResult:
    if value is None:
        return None
    return _pptx_text_or_error(action, value, field_name, config)


def _pptx_text_or_error(
    action: str,
    value: Any,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> str | OfficeRealDocumentActionResult:
    if not isinstance(value, str):
        return _error(action, "invalid_parameter", f"{field_name} must contain strings only.", config)
    if "\x00" in value:
        return _error(
            action,
            "office_pptx_invalid_content",
            f"{field_name} must not contain NUL characters.",
            config,
        )
    if len(value) > config.max_pptx_text_chars:
        return _error(
            action,
            "office_pptx_invalid_content",
            f"{field_name} exceeds max_pptx_text_chars.",
            config,
        )
    return value


def _add_pptx_title_slide(presentation: Any, title: str, subtitle: str) -> None:
    slide = presentation.slides.add_slide(_pptx_slide_layout(presentation, 0))
    title_shape = getattr(slide.shapes, "title", None)
    if title_shape is not None:
        title_shape.text = title
    elif title:
        _add_pptx_textbox(slide, title, left=0.8, top=0.7, width=8.4, height=1.0)

    subtitle_shape = _pptx_placeholder(slide, 1)
    if subtitle_shape is not None:
        subtitle_shape.text = subtitle
    elif subtitle:
        _add_pptx_textbox(slide, subtitle, left=1.0, top=2.0, width=8.0, height=1.0)


def _add_pptx_content_slide(presentation: Any, title: str, bullets: list[str]) -> None:
    slide = presentation.slides.add_slide(_pptx_slide_layout(presentation, 1))
    title_shape = getattr(slide.shapes, "title", None)
    if title_shape is not None:
        title_shape.text = title
    elif title:
        _add_pptx_textbox(slide, title, left=0.7, top=0.4, width=8.6, height=0.8)

    body_shape = _pptx_placeholder(slide, 1)
    if body_shape is not None and getattr(body_shape, "has_text_frame", False):
        text_frame = body_shape.text_frame
        text_frame.clear()
        for index, bullet in enumerate(bullets):
            paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
            paragraph.text = bullet
            paragraph.level = 0
    elif bullets:
        _add_pptx_textbox(slide, "\n".join(bullets), left=0.9, top=1.5, width=8.2, height=4.5)


def _pptx_slide_layout(presentation: Any, index: int) -> Any:
    try:
        return presentation.slide_layouts[index]
    except Exception:
        return presentation.slide_layouts[0]


def _pptx_placeholder(slide: Any, index: int) -> Any | None:
    try:
        return slide.placeholders[index]
    except Exception:
        return None


def _add_pptx_textbox(
    slide: Any,
    text: str,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> None:
    inches = _pptx_inches()
    textbox = slide.shapes.add_textbox(inches(left), inches(top), inches(width), inches(height))
    textbox.text = text


def _pptx_inches() -> Any:
    try:
        util_module = __import__("pptx.util", fromlist=["Inches"])
        return util_module.Inches
    except Exception:
        return lambda value: int(float(value) * 914400)


def _presentation_text(presentation: Any) -> str:
    pieces: list[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = getattr(shape, "text", "")
                if text:
                    pieces.append(text)
    return "\n".join(pieces)


def _presentation_slide_count(presentation: Any) -> int:
    return len(presentation.slides)


def _pptx_success(
    action: str,
    config: OfficeRealDocumentActivityConfig,
    resolution: OfficeDocumentPathResolution,
    text: str,
    **metadata: Any,
) -> OfficeRealDocumentActionResult:
    preview, truncated = _preview_with_limit(text, config.max_text_preview_chars)
    return OfficeRealDocumentActionResult(
        action=action,
        success=True,
        output=preview,
        metadata={
            "document_type": "pptx",
            "path_relative": resolution.relative_path,
            "slide_count": metadata.pop("slide_count"),
            "text_preview": preview,
            "truncated": truncated,
            **metadata,
            **_success_metadata(config),
        },
    )


def _resolve_action_docx_path(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeDocumentPathResolution | OfficeRealDocumentActionResult:
    path = parameters.get("path")
    if path is None:
        return _error(action, "missing_parameter", "Missing required parameter: path.", config)
    if not isinstance(path, str):
        return _error(action, "invalid_parameter", "path must be a string.", config)
    try:
        resolution = resolve_safe_office_real_document_path(path, config)
    except OfficeRealDocumentPathError as exc:
        return _error(action, exc.code, str(exc), config)
    if Path(resolution.normalized_path).suffix.lower() != ".docx":
        return _error(action, "office_extension_denied", "DOCX action requires a .docx path.", config)
    return resolution


def _resolve_existing_docx_path(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeDocumentPathResolution | OfficeRealDocumentActionResult:
    resolution = _resolve_action_docx_path(action, parameters, config)
    if isinstance(resolution, OfficeRealDocumentActionResult):
        return resolution
    if not resolution.resolved_path.exists() or not resolution.resolved_path.is_file():
        return _error(
            action,
            "office_docx_file_missing",
            "DOCX document does not exist.",
            config,
            path_relative=resolution.relative_path,
        )
    size = resolution.resolved_path.stat().st_size
    if size > config.max_file_bytes:
        return _error(
            action,
            "office_docx_file_too_large",
            "DOCX document exceeds max_file_bytes.",
            config,
            path_relative=resolution.relative_path,
            file_size_bytes=size,
            max_file_bytes=config.max_file_bytes,
        )
    return resolution


def _save_docx_atomically(
    document: Any,
    destination: Path,
    config: OfficeRealDocumentActivityConfig,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            temp_path = Path(tmp.name)
        document.save(str(temp_path))
        if temp_path.stat().st_size > config.max_file_bytes:
            raise OfficeRealDocumentPathError(
                "office_docx_file_too_large",
                "DOCX document exceeds max_file_bytes.",
            )
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _paragraph_list(
    action: str,
    value: Any,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> list[str] | OfficeRealDocumentActionResult:
    if value is None:
        return _error(
            action,
            "invalid_parameter",
            f"{field_name} must be a list of strings.",
            config,
        )
    if not isinstance(value, list):
        return _error(
            action,
            "invalid_parameter",
            f"{field_name} must be a list of strings.",
            config,
        )
    if len(value) > config.max_paragraphs:
        return _error(
            action,
            "office_docx_invalid_content",
            f"{field_name} exceeds max_paragraphs.",
            config,
        )
    paragraphs: list[str] = []
    for item in value:
        text = _text_or_error(action, item, field_name, config)
        if isinstance(text, OfficeRealDocumentActionResult):
            return text
        paragraphs.append(text)
    return paragraphs


def _optional_text(
    action: str,
    value: Any,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> str | None | OfficeRealDocumentActionResult:
    if value is None:
        return None
    return _text_or_error(action, value, field_name, config)


def _text_or_error(
    action: str,
    value: Any,
    field_name: str,
    config: OfficeRealDocumentActivityConfig,
) -> str | OfficeRealDocumentActionResult:
    if not isinstance(value, str):
        return _error(
            action,
            "invalid_parameter",
            f"{field_name} must contain strings only.",
            config,
        )
    if "\x00" in value:
        return _error(
            action,
            "office_docx_invalid_content",
            f"{field_name} must not contain NUL characters.",
            config,
        )
    if len(value) > config.max_paragraph_chars:
        return _error(
            action,
            "office_docx_invalid_content",
            f"{field_name} exceeds max_paragraph_chars.",
            config,
        )
    return value


def _preview_limit(
    action: str,
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> int | OfficeRealDocumentActionResult:
    if value is None:
        return config.max_text_preview_chars
    if not isinstance(value, int) or value <= 0:
        return _error(
            action,
            "invalid_parameter",
            "max_chars must be a positive integer.",
            config,
        )
    return min(value, config.max_text_preview_chars)


def _document_text(document: Any) -> str:
    return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text)


def _paragraph_count(document: Any) -> int:
    return sum(1 for paragraph in document.paragraphs if paragraph.text)


def _preview_with_limit(text: str, max_chars: int) -> tuple[str, bool]:
    preview = text_preview(text, max_chars)
    normalized = " ".join(str(text).split())
    return preview, len(preview) < len(normalized)


def _docx_success(
    action: str,
    config: OfficeRealDocumentActivityConfig,
    resolution: OfficeDocumentPathResolution,
    text: str,
    **metadata: Any,
) -> OfficeRealDocumentActionResult:
    preview, truncated = _preview_with_limit(text, config.max_text_preview_chars)
    return OfficeRealDocumentActionResult(
        action=action,
        success=True,
        output=preview,
        metadata={
            "document_type": "docx",
            "path_relative": resolution.relative_path,
            "paragraph_count": metadata.pop("paragraph_count"),
            "text_preview": preview,
            "truncated": truncated,
            **metadata,
            **_success_metadata(config),
        },
    )


def _success_metadata(config: OfficeRealDocumentActivityConfig) -> dict[str, Any]:
    return {
        "real_office_document_automation": True,
        "office_app_opened": False,
        "office_dependencies_optional": True,
        "office_enabled": config.enabled,
        "artifact_root_configured": config.artifact_root is not None,
    }


def normalize_office_real_document_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise OfficeRealDocumentPathError(
            "office_path_traversal_denied",
            "Office document path must be a non-empty string.",
        )
    raw = path.strip()
    if "\x00" in raw:
        raise OfficeRealDocumentPathError(
            "office_path_traversal_denied",
            "Office document path must not contain NUL bytes.",
        )
    if raw.startswith("/") or _is_windows_drive_path(raw):
        raise OfficeRealDocumentPathError(
            "office_path_absolute_denied",
            "Office document paths must be relative.",
        )
    if "\\" in raw:
        raise OfficeRealDocumentPathError(
            "office_path_traversal_denied",
            "Office document paths must use forward slashes only.",
        )

    normalized = str(PurePosixPath(raw))
    parts = PurePosixPath(normalized).parts
    if normalized == "." or any(part in {"", ".", ".."} for part in parts):
        raise OfficeRealDocumentPathError(
            "office_path_traversal_denied",
            "Office document paths must not contain traversal.",
        )
    return normalized


def resolve_safe_office_real_document_path(
    path: str,
    config: OfficeRealDocumentActivityConfig,
) -> OfficeDocumentPathResolution:
    if config.artifact_root is None:
        raise OfficeRealDocumentPathError(
            "office_artifact_root_required",
            "artifact_root is required for real office document artifacts.",
        )

    normalized = normalize_office_real_document_path(path)
    suffix = Path(normalized).suffix.lower()
    if suffix in MACRO_ENABLED_EXTENSIONS:
        raise OfficeRealDocumentPathError(
            "office_macro_extension_denied",
            "Macro-enabled Office document extensions are not allowed.",
        )
    if suffix not in set(config.allowed_extensions):
        raise OfficeRealDocumentPathError(
            "office_extension_denied",
            "Office document extension is not allowed.",
        )
    for root in config.forbidden_roots:
        if normalized == root.rstrip("/") or normalized.startswith(root):
            raise OfficeRealDocumentPathError(
                "office_path_forbidden_root_denied",
                "Office document path is under a forbidden root.",
            )

    project_root = config.project_root.resolve()
    artifact_root = (project_root / config.artifact_root).resolve()
    resolved = (project_root / normalized).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise OfficeRealDocumentPathError(
            "office_path_traversal_denied",
            "Resolved office document path escaped project root.",
        ) from exc
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise OfficeRealDocumentPathError(
            "office_path_outside_artifact_root",
            "Office document path must stay under artifact_root.",
        ) from exc
    return OfficeDocumentPathResolution(
        requested_path=path,
        normalized_path=normalized,
        resolved_path=resolved,
        relative_path=resolved.relative_to(project_root).as_posix(),
    )


def validate_spreadsheet_text_value(
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    if not config.allow_formulas and value.startswith(FORMULA_PREFIXES):
        raise OfficeFormulaLikeValueError("Spreadsheet formula-like value is not allowed.")
    return value


def text_preview(text: str, max_chars: int) -> str:
    if not isinstance(text, str):
        text = str(text)
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 3:
        return normalized[:max_chars]
    return f"{normalized[: max_chars - 3]}..."


def _validate_action_path(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeRealDocumentActionResult | None:
    path = parameters.get("path")
    if path is None:
        return None
    if not isinstance(path, str):
        return _error(action, "invalid_parameter", "path must be a string.", config)
    try:
        resolution = resolve_safe_office_real_document_path(path, config)
    except OfficeRealDocumentPathError as exc:
        return _error(action, exc.code, str(exc), config, path_provided=True)
    return OfficeRealDocumentActionResult(
        action=action,
        success=True,
        metadata={
            "path": resolution.relative_path,
            "path_validated": True,
        },
    )


def _validate_action_formula_values(
    action: str,
    parameters: dict[str, Any],
    config: OfficeRealDocumentActivityConfig,
) -> OfficeRealDocumentActionResult | None:
    candidate_values: list[Any] = []
    if "value" in parameters:
        candidate_values.append(parameters["value"])
    row = parameters.get("row")
    if isinstance(row, list):
        candidate_values.extend(row)
    values = parameters.get("values")
    if isinstance(values, list):
        candidate_values.extend(values)
    headers = parameters.get("headers")
    if isinstance(headers, list):
        candidate_values.extend(headers)
    rows = parameters.get("rows")
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, list):
                candidate_values.extend(item)

    for value in candidate_values:
        try:
            validate_spreadsheet_text_value(value, config)
        except OfficeFormulaLikeValueError as exc:
            return _error(action, exc.code, str(exc), config)
    return None


def _normalize_root(root: str) -> str:
    if not isinstance(root, str) or not root.strip():
        raise ValueError("forbidden_roots entries must be non-empty strings.")
    normalized = root.strip().replace("\\", "/")
    if "\x00" in normalized or normalized.startswith("/") or _is_windows_drive_path(normalized):
        raise ValueError("forbidden_roots entries must be safe relative paths.")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError("forbidden_roots entries must not contain traversal.")
    if not normalized.endswith("/"):
        normalized += "/"
    return normalized


def _is_windows_drive_path(path: str) -> bool:
    return len(path) >= 2 and path[1] == ":" and path[0].isalpha()


def _error(
    action: str,
    error_type: str,
    error_message: str,
    config: OfficeRealDocumentActivityConfig,
    **metadata: Any,
) -> OfficeRealDocumentActionResult:
    return OfficeRealDocumentActionResult(
        action=action,
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata={
            "real_office_document_automation": False,
            "office_app_opened": False,
            "office_dependencies_optional": True,
            "office_enabled": config.enabled,
            "artifact_root_configured": config.artifact_root is not None,
            **metadata,
        },
    )
