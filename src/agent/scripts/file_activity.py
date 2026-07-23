from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .results import ScriptExecutionResult


class FileActivityError(Exception):
    pass


class UnsafePathError(FileActivityError):
    pass


class FileTooLargeError(FileActivityError):
    pass


class FileActivityNotFoundError(FileActivityError):
    pass


class FileActivityConfig(BaseModel):
    project_root: Path
    allowed_file_roots: list[str] = Field(
        default_factory=lambda: [
            "artifacts/",
            "docs/",
            "configs/",
            "experiments/",
            "tests/",
        ]
    )
    forbidden_file_roots: list[str] = Field(
        default_factory=lambda: ["models/gguf/", ".venv/", ".git/"]
    )
    max_read_bytes: int = 200_000
    default_encoding: str = "utf-8"
    create_parent_dirs: bool = True
    allow_overwrite: bool = True

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("max_read_bytes")
    @classmethod
    def validate_max_read_bytes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_read_bytes must be > 0.")
        return value

    @model_validator(mode="after")
    def validate_unique_roots(self) -> FileActivityConfig:
        if len(self.allowed_file_roots) != len(set(self.allowed_file_roots)):
            raise ValueError("allowed_file_roots must not contain duplicates.")
        if len(self.forbidden_file_roots) != len(set(self.forbidden_file_roots)):
            raise ValueError("forbidden_file_roots must not contain duplicates.")
        return self


def normalize_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise UnsafePathError("Path must be a non-empty string.")

    raw = path.strip().replace("\\", "/")
    lower = raw.lower()

    if raw.startswith("/") or raw.startswith("\\"):
        raise UnsafePathError("Absolute paths are not allowed.")
    if len(raw) >= 2 and raw[1] == ":":
        raise UnsafePathError("Drive-prefixed paths are not allowed.")

    normalized = str(PurePosixPath(raw))
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise UnsafePathError("Path traversal is not allowed.")
    if normalized == ".":
        raise UnsafePathError("Path must not resolve to current directory only.")
    if lower.startswith("file://"):
        raise UnsafePathError("file:// paths are not allowed.")
    return normalized


def resolve_safe_project_path(path: str, config: FileActivityConfig) -> Path:
    normalized = normalize_relative_path(path)

    for root in config.forbidden_file_roots:
        if normalized.startswith(root):
            raise UnsafePathError(f"Path '{normalized}' is under forbidden root '{root}'.")

    if config.allowed_file_roots:
        if not any(normalized.startswith(root) for root in config.allowed_file_roots):
            raise UnsafePathError(f"Path '{normalized}' is outside allowed roots.")

    resolved = (config.project_root / normalized).resolve()
    try:
        resolved.relative_to(config.project_root)
    except ValueError as exc:
        raise UnsafePathError("Resolved path escaped project root.") from exc
    return resolved


def _error(action: str, error_type: str, error_message: str, **metadata: Any) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        action=action,
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata=metadata,
    )


def read_file(path: str, config: FileActivityConfig) -> ScriptExecutionResult:
    action = "read_file"
    try:
        resolved = resolve_safe_project_path(path, config)
    except UnsafePathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    if not resolved.exists():
        return _error(action, "file_not_found", f"File not found: {path}", path=path, resolved_path=str(resolved))
    if not resolved.is_file():
        return _error(action, "not_a_file", f"Path is not a file: {path}", path=path, resolved_path=str(resolved))

    size = resolved.stat().st_size
    if size > config.max_read_bytes:
        return _error(
            action,
            "file_too_large",
            f"File exceeds max_read_bytes ({size} > {config.max_read_bytes}).",
            path=path,
            resolved_path=str(resolved),
            max_read_bytes=config.max_read_bytes,
        )

    content = resolved.read_text(encoding=config.default_encoding)
    return ScriptExecutionResult(
        action=action,
        success=True,
        output=content,
        metadata={"path": path, "resolved_path": str(resolved), "bytes_read": size},
    )


def create_file(path: str, content: str, config: FileActivityConfig) -> ScriptExecutionResult:
    action = "create_file"
    if not isinstance(content, str):
        return _error(action, "invalid_parameter", "content must be a string.", path=path)

    try:
        resolved = resolve_safe_project_path(path, config)
    except UnsafePathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    parent = resolved.parent
    if not parent.exists():
        if config.create_parent_dirs:
            parent.mkdir(parents=True, exist_ok=True)
        else:
            return _error(
                action,
                "parent_missing",
                f"Parent directory does not exist: {parent}",
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

    resolved.write_text(content, encoding=config.default_encoding)
    return ScriptExecutionResult(
        action=action,
        success=True,
        metadata={
            "path": path,
            "resolved_path": str(resolved),
            "bytes_written": len(content.encode(config.default_encoding)),
            "overwritten": overwritten,
        },
    )


def append_file(path: str, content: str, config: FileActivityConfig) -> ScriptExecutionResult:
    action = "append_file"
    if not isinstance(content, str):
        return _error(action, "invalid_parameter", "content must be a string.", path=path)

    try:
        resolved = resolve_safe_project_path(path, config)
    except UnsafePathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    parent = resolved.parent
    if not parent.exists():
        if config.create_parent_dirs:
            parent.mkdir(parents=True, exist_ok=True)
        else:
            return _error(
                action,
                "parent_missing",
                f"Parent directory does not exist: {parent}",
                path=path,
                resolved_path=str(resolved),
            )

    with resolved.open("a", encoding=config.default_encoding) as f:
        f.write(content)

    return ScriptExecutionResult(
        action=action,
        success=True,
        metadata={
            "path": path,
            "resolved_path": str(resolved),
            "bytes_written": len(content.encode(config.default_encoding)),
        },
    )


def list_directory(path: str, config: FileActivityConfig) -> ScriptExecutionResult:
    action = "list_directory"
    try:
        resolved = resolve_safe_project_path(path, config)
    except UnsafePathError as exc:
        return _error(action, "unsafe_path", str(exc), path=path)

    if not resolved.exists():
        return _error(
            action,
            "directory_not_found",
            f"Directory not found: {path}",
            path=path,
            resolved_path=str(resolved),
        )
    if not resolved.is_dir():
        return _error(
            action,
            "not_a_directory",
            f"Path is not a directory: {path}",
            path=path,
            resolved_path=str(resolved),
        )

    names = sorted(p.name for p in resolved.iterdir())
    return ScriptExecutionResult(
        action=action,
        success=True,
        output="\n".join(names),
        metadata={"path": path, "resolved_path": str(resolved), "entry_count": len(names)},
    )


def run_file_activity(
    action: str, parameters: dict[str, Any], config: FileActivityConfig
) -> ScriptExecutionResult:
    if action == "read_file":
        if "path" not in parameters:
            return _error(action, "invalid_parameter", "Missing required parameter: path")
        return read_file(parameters["path"], config)
    if action == "create_file":
        if "path" not in parameters or "content" not in parameters:
            return _error(action, "invalid_parameter", "Missing required parameters: path/content")
        return create_file(parameters["path"], parameters["content"], config)
    if action == "append_file":
        if "path" not in parameters or "content" not in parameters:
            return _error(action, "invalid_parameter", "Missing required parameters: path/content")
        return append_file(parameters["path"], parameters["content"], config)
    if action == "list_directory":
        if "path" not in parameters:
            return _error(action, "invalid_parameter", "Missing required parameter: path")
        return list_directory(parameters["path"], config)

    return _error(
        action if isinstance(action, str) and action.strip() else "unknown",
        "unknown_file_action",
        f"Unknown file activity action: {action}",
    )
