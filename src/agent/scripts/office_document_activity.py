from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .results import ScriptExecutionResult


class OfficeDocumentActivityError(Exception):
    pass


class UnsafeOfficeDocumentPathError(OfficeDocumentActivityError):
    pass


class OfficeDocumentTooLargeError(OfficeDocumentActivityError):
    pass


class OfficeDocumentNotFoundError(OfficeDocumentActivityError):
    pass


class OfficeDocumentParameterError(OfficeDocumentActivityError):
    pass


class OfficeDocumentActivityConfig(BaseModel):
    project_root: Path
    allowed_file_roots: list[str] = Field(
        default_factory=lambda: ["docs/", "experiments/", "configs/", "tests/"]
    )
    forbidden_file_roots: list[str] = Field(
        default_factory=lambda: ["models/gguf/", ".venv/", ".git/"]
    )
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".md", ".txt", ".json"]
    )
    max_document_bytes: int = 200_000
    default_encoding: str = "utf-8"
    create_parent_dirs: bool = True
    allow_overwrite: bool = True
    simulated_only: bool = True

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("max_document_bytes")
    @classmethod
    def validate_max_document_bytes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_document_bytes must be > 0.")
        return value

    @model_validator(mode="after")
    def validate_lists_and_mode(self) -> OfficeDocumentActivityConfig:
        if len(self.allowed_file_roots) != len(set(self.allowed_file_roots)):
            raise ValueError("allowed_file_roots must not contain duplicates.")
        if len(self.forbidden_file_roots) != len(set(self.forbidden_file_roots)):
            raise ValueError("forbidden_file_roots must not contain duplicates.")
        if len(self.allowed_extensions) != len(set(self.allowed_extensions)):
            raise ValueError("allowed_extensions must not contain duplicates.")
        if not self.simulated_only:
            raise ValueError(
                "OfficeDocumentActivityConfig v1 supports simulated_only=True only."
            )
        return self


def normalize_office_document_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise UnsafeOfficeDocumentPathError("Path must be a non-empty string.")

    raw = path.strip().replace("\\", "/")
    if raw.startswith("/") or raw.startswith("\\"):
        raise UnsafeOfficeDocumentPathError("Absolute paths are not allowed.")
    if len(raw) >= 2 and raw[1] == ":":
        raise UnsafeOfficeDocumentPathError("Drive-prefixed paths are not allowed.")

    normalized = str(PurePosixPath(raw))
    if normalized == ".":
        raise UnsafeOfficeDocumentPathError("Path must not be current directory only.")
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise UnsafeOfficeDocumentPathError("Path traversal is not allowed.")
    return normalized


def resolve_safe_office_document_path(
    path: str, config: OfficeDocumentActivityConfig
) -> Path:
    normalized = normalize_office_document_path(path)

    for root in config.forbidden_file_roots:
        if normalized.startswith(root):
            raise UnsafeOfficeDocumentPathError(
                f"Path '{normalized}' is under forbidden root '{root}'."
            )

    if config.allowed_file_roots and not any(
        normalized.startswith(root) for root in config.allowed_file_roots
    ):
        raise UnsafeOfficeDocumentPathError(
            f"Path '{normalized}' is outside allowed roots."
        )

    suffix = Path(normalized).suffix.lower()
    if suffix not in {ext.lower() for ext in config.allowed_extensions}:
        raise UnsafeOfficeDocumentPathError(
            f"Extension '{suffix}' is not allowed for office document activity."
        )

    resolved = (config.project_root / normalized).resolve()
    try:
        resolved.relative_to(config.project_root)
    except ValueError as exc:
        raise UnsafeOfficeDocumentPathError(
            "Resolved office document path escaped project root."
        ) from exc
    return resolved


def _error(action: str, error_type: str, error_message: str, **metadata: Any) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        action=action,
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata=metadata,
    )


def create_document_stub(
    path: str, title: str, body: str, config: OfficeDocumentActivityConfig
) -> ScriptExecutionResult:
    action = "create_document_stub"
    if not isinstance(title, str):
        return _error(action, "invalid_parameter", "title must be a string.", path=path)
    if not isinstance(body, str):
        return _error(action, "invalid_parameter", "body must be a string.", path=path)

    try:
        resolved = resolve_safe_office_document_path(path, config)
    except UnsafeOfficeDocumentPathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    if not resolved.parent.exists():
        if config.create_parent_dirs:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        else:
            return _error(
                action,
                "parent_missing",
                f"Parent directory does not exist: {resolved.parent}",
                path=path,
                resolved_path=str(resolved),
            )

    overwritten = resolved.exists()
    if overwritten and not config.allow_overwrite:
        return _error(
            action,
            "file_exists",
            f"File already exists and allow_overwrite is False: {path}",
            path=path,
            resolved_path=str(resolved),
        )

    content = f"# {title}\n\n{body}"
    resolved.write_text(content, encoding=config.default_encoding)
    return ScriptExecutionResult(
        action=action,
        success=True,
        metadata={
            "path": path,
            "resolved_path": str(resolved),
            "title": title,
            "bytes_written": len(content.encode(config.default_encoding)),
            "overwritten": overwritten,
            "simulated": True,
            "office_app_opened": False,
        },
    )


def append_document_section(
    path: str, heading: str, content: str, config: OfficeDocumentActivityConfig
) -> ScriptExecutionResult:
    action = "append_document_section"
    if not isinstance(heading, str):
        return _error(
            action, "invalid_parameter", "heading must be a string.", path=path
        )
    if not isinstance(content, str):
        return _error(
            action, "invalid_parameter", "content must be a string.", path=path
        )

    try:
        resolved = resolve_safe_office_document_path(path, config)
    except UnsafeOfficeDocumentPathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    if not resolved.exists():
        return _error(
            action,
            "document_not_found",
            f"Document not found: {path}",
            path=path,
            resolved_path=str(resolved),
        )
    size = resolved.stat().st_size
    if size > config.max_document_bytes:
        return _error(
            action,
            "document_too_large",
            f"Document exceeds max_document_bytes ({size} > {config.max_document_bytes}).",
            path=path,
            resolved_path=str(resolved),
            max_document_bytes=config.max_document_bytes,
        )

    append_text = f"\n\n## {heading}\n\n{content}"
    with resolved.open("a", encoding=config.default_encoding) as f:
        f.write(append_text)

    return ScriptExecutionResult(
        action=action,
        success=True,
        metadata={
            "path": path,
            "resolved_path": str(resolved),
            "heading": heading,
            "bytes_written": len(append_text.encode(config.default_encoding)),
            "simulated": True,
            "office_app_opened": False,
        },
    )


def read_document_stub(path: str, config: OfficeDocumentActivityConfig) -> ScriptExecutionResult:
    action = "read_document_stub"
    try:
        resolved = resolve_safe_office_document_path(path, config)
    except UnsafeOfficeDocumentPathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    if not resolved.exists():
        return _error(
            action,
            "document_not_found",
            f"Document not found: {path}",
            path=path,
            resolved_path=str(resolved),
        )
    if not resolved.is_file():
        return _error(
            action,
            "not_a_file",
            f"Path is not a file: {path}",
            path=path,
            resolved_path=str(resolved),
        )

    size = resolved.stat().st_size
    if size > config.max_document_bytes:
        return _error(
            action,
            "document_too_large",
            f"Document exceeds max_document_bytes ({size} > {config.max_document_bytes}).",
            path=path,
            resolved_path=str(resolved),
            max_document_bytes=config.max_document_bytes,
        )

    text = resolved.read_text(encoding=config.default_encoding)
    return ScriptExecutionResult(
        action=action,
        success=True,
        output=text,
        metadata={
            "path": path,
            "resolved_path": str(resolved),
            "bytes_read": size,
            "simulated": True,
            "office_app_opened": False,
        },
    )


def extract_document_outline_stub(
    path: str, config: OfficeDocumentActivityConfig
) -> ScriptExecutionResult:
    action = "extract_document_outline_stub"
    read_result = read_document_stub(path, config)
    if not read_result.success:
        return ScriptExecutionResult(
            action=action,
            success=False,
            error_type=read_result.error_type,
            error_message=read_result.error_message,
            metadata=read_result.metadata,
        )

    text = read_result.output or ""
    headings = [line.strip() for line in text.splitlines() if line.strip().startswith("#")]
    output = "\n".join(headings) if headings else ""
    metadata = dict(read_result.metadata)
    metadata.update({"heading_count": len(headings)})
    return ScriptExecutionResult(
        action=action,
        success=True,
        output=output,
        metadata=metadata,
    )


def create_table_note_stub(
    path: str,
    title: str,
    columns: list[str],
    rows: list[list[str]],
    config: OfficeDocumentActivityConfig,
) -> ScriptExecutionResult:
    action = "create_table_note_stub"
    if not isinstance(title, str):
        return _error(action, "invalid_parameter", "title must be a string.", path=path)
    if not isinstance(columns, list) or any(not isinstance(c, str) for c in columns):
        return _error(
            action,
            "invalid_parameter",
            "columns must be a list of strings.",
            path=path,
        )
    if not isinstance(rows, list) or any(not isinstance(r, list) for r in rows):
        return _error(
            action, "invalid_parameter", "rows must be a list of string rows.", path=path
        )
    for row in rows:
        if any(not isinstance(cell, str) for cell in row):
            return _error(
                action,
                "invalid_parameter",
                "Each table cell must be a string.",
                path=path,
            )
        if len(row) != len(columns):
            return _error(
                action,
                "invalid_parameter",
                "Each row must match columns length.",
                path=path,
            )

    try:
        resolved = resolve_safe_office_document_path(path, config)
    except UnsafeOfficeDocumentPathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    if not resolved.parent.exists():
        if config.create_parent_dirs:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        else:
            return _error(
                action,
                "parent_missing",
                f"Parent directory does not exist: {resolved.parent}",
                path=path,
                resolved_path=str(resolved),
            )

    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    row_lines = ["| " + " | ".join(row) + " |" for row in rows]
    content_lines = [f"# {title}", "", header, separator] + row_lines
    content = "\n".join(content_lines) + "\n"

    overwritten = resolved.exists()
    if overwritten and not config.allow_overwrite:
        return _error(
            action,
            "file_exists",
            f"File already exists and allow_overwrite is False: {path}",
            path=path,
            resolved_path=str(resolved),
        )

    resolved.write_text(content, encoding=config.default_encoding)
    return ScriptExecutionResult(
        action=action,
        success=True,
        metadata={
            "path": path,
            "resolved_path": str(resolved),
            "title": title,
            "column_count": len(columns),
            "row_count": len(rows),
            "simulated": True,
            "office_app_opened": False,
        },
    )


def run_office_document_activity(
    action: str, parameters: dict[str, Any], config: OfficeDocumentActivityConfig
) -> ScriptExecutionResult:
    safe_action = action if isinstance(action, str) and action.strip() else "unknown"

    def missing(param: str) -> ScriptExecutionResult:
        return _error(safe_action, "missing_parameter", f"Missing required parameter: {param}")

    def invalid(msg: str) -> ScriptExecutionResult:
        return _error(safe_action, "invalid_parameter", msg)

    try:
        if action == "create_document_stub":
            if "path" not in parameters:
                return missing("path")
            if "title" not in parameters:
                return missing("title")
            if "body" not in parameters:
                return missing("body")
            if not isinstance(parameters["path"], str):
                return invalid("path must be a string.")
            return create_document_stub(
                parameters["path"], parameters["title"], parameters["body"], config
            )

        if action == "append_document_section":
            if "path" not in parameters:
                return missing("path")
            if "heading" not in parameters:
                return missing("heading")
            if "content" not in parameters:
                return missing("content")
            if not isinstance(parameters["path"], str):
                return invalid("path must be a string.")
            return append_document_section(
                parameters["path"], parameters["heading"], parameters["content"], config
            )

        if action == "read_document_stub":
            if "path" not in parameters:
                return missing("path")
            if not isinstance(parameters["path"], str):
                return invalid("path must be a string.")
            return read_document_stub(parameters["path"], config)

        if action == "extract_document_outline_stub":
            if "path" not in parameters:
                return missing("path")
            if not isinstance(parameters["path"], str):
                return invalid("path must be a string.")
            return extract_document_outline_stub(parameters["path"], config)

        if action == "create_table_note_stub":
            for p in ("path", "title", "columns", "rows"):
                if p not in parameters:
                    return missing(p)
            if not isinstance(parameters["path"], str):
                return invalid("path must be a string.")
            return create_table_note_stub(
                parameters["path"],
                parameters["title"],
                parameters["columns"],
                parameters["rows"],
                config,
            )

        return _error(
            safe_action,
            "unknown_office_document_action",
            f"Unknown office document activity action: {action}",
        )
    except UnsafeOfficeDocumentPathError as exc:
        return _error(safe_action, "unsafe_path", str(exc))
