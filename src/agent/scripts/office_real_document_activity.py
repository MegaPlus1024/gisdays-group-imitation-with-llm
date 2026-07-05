from __future__ import annotations

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

    @field_validator("max_file_bytes", "max_text_preview_chars")
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

    loader = dependency_loader or load_office_document_dependencies
    try:
        loader()
    except ImportError as exc:
        return _error(
            normalized_action,
            "office_dependency_missing",
            "Optional office document dependencies are not installed.",
            cfg,
            dependency_error_type=exc.__class__.__name__,
        )
    except Exception as exc:
        return _error(
            normalized_action,
            "office_dependency_missing",
            "Optional office document dependencies are unavailable.",
            cfg,
            dependency_error_type=exc.__class__.__name__,
        )

    return _error(
        normalized_action,
        "office_backend_not_implemented",
        "Real DOCX/XLSX/PPTX document operations are scaffolded but not implemented.",
        cfg,
    )


def load_office_document_dependencies() -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for module_name, package_name in OFFICE_DOCUMENT_DEPENDENCY_MODULES.items():
        try:
            loaded[module_name] = __import__(module_name)
        except ImportError as exc:
            raise OfficeDependencyMissingError(package_name) from exc
    return loaded


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
        return _error(action, exc.code, str(exc), config, path=path)
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
