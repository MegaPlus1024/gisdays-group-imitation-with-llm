from __future__ import annotations

import os
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

MACRO_ENABLED_EXTENSIONS = frozenset({".docm", ".xlsm", ".pptm"})
FORMULA_PREFIXES = ("=", "+", "-", "@")


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

    return _error(
        normalized_action,
        "office_backend_not_implemented",
        "Real XLSX/PPTX document operations are scaffolded but not implemented.",
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

    preview_limit_result = _preview_limit(parameters.get("max_chars"), config)
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
    value: Any,
    config: OfficeRealDocumentActivityConfig,
) -> int | OfficeRealDocumentActionResult:
    if value is None:
        return config.max_text_preview_chars
    if not isinstance(value, int) or value <= 0:
        return _error(
            "office_extract_docx_text",
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
