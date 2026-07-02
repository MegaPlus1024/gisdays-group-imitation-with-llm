from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .scripts.results import ScriptExecutionResult

ScriptRunnerErrorCategory = Literal[
    "none",
    "unknown_action",
    "missing_parameter",
    "invalid_parameter",
    "unsafe_action",
    "unsafe_path",
    "unsafe_url",
    "file_not_found",
    "document_not_found",
    "directory_not_found",
    "not_a_file",
    "not_a_directory",
    "file_too_large",
    "document_too_large",
    "permission_denied",
    "command_failed",
    "command_timeout",
    "executable_not_found",
    "script_timeout",
    "execution_error",
    "internal_error",
    "unknown_error",
]

ScriptRunnerErrorSeverity = Literal["debug", "info", "warning", "error", "critical"]


class NormalizedScriptError(BaseModel):
    category: ScriptRunnerErrorCategory
    original_error_type: str | None = None
    message: str
    action: str | None = None
    source: str | None = None
    severity: ScriptRunnerErrorSeverity = "error"
    retryable: bool = False
    recovery_category: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def validate_non_empty_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> NormalizedScriptError:
        if self.category == "none" and self.severity not in {"info", "debug"}:
            raise ValueError("category='none' should use info/debug severity.")
        if self.severity == "critical" and self.retryable:
            raise ValueError("critical errors should not be retryable.")
        return self


class NormalizedScriptResult(BaseModel):
    action: str
    success: bool
    output: str | None = None
    error: NormalizedScriptError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> NormalizedScriptResult:
        if self.success and self.error is not None:
            raise ValueError("success=True requires error=None.")
        if not self.success and self.error is None:
            raise ValueError("success=False requires a non-null error.")
        return self


def normalize_error_type(error_type: str | None) -> ScriptRunnerErrorCategory:
    mapping: dict[str, ScriptRunnerErrorCategory] = {
        "unknown_file_action": "unknown_action",
        "unknown_browser_action": "unknown_action",
        "unknown_office_document_action": "unknown_action",
        "unknown_shell_action": "unknown_action",
        "missing_parameter": "missing_parameter",
        "invalid_parameter": "invalid_parameter",
        "parent_missing": "invalid_parameter",
        "file_exists": "invalid_parameter",
        "unsafe_path": "unsafe_path",
        "unsafe_url": "unsafe_url",
        "unsafe_command": "unsafe_action",
        "unsafe_action": "unsafe_action",
        "file_not_found": "file_not_found",
        "document_not_found": "document_not_found",
        "directory_not_found": "directory_not_found",
        "not_a_file": "not_a_file",
        "not_a_directory": "not_a_directory",
        "file_too_large": "file_too_large",
        "document_too_large": "document_too_large",
        "command_failed": "command_failed",
        "command_timeout": "command_timeout",
        "executable_not_found": "executable_not_found",
        "permission_denied": "permission_denied",
        "execution_error": "execution_error",
        "internal_error": "internal_error",
    }
    if error_type is None:
        return "unknown_error"
    return mapping.get(error_type, "unknown_error")


def severity_for_category(category: ScriptRunnerErrorCategory) -> ScriptRunnerErrorSeverity:
    mapping: dict[ScriptRunnerErrorCategory, ScriptRunnerErrorSeverity] = {
        "none": "info",
        "missing_parameter": "warning",
        "invalid_parameter": "warning",
        "unknown_action": "warning",
        "unsafe_action": "error",
        "unsafe_path": "error",
        "unsafe_url": "error",
        "file_not_found": "warning",
        "document_not_found": "warning",
        "directory_not_found": "warning",
        "not_a_file": "warning",
        "not_a_directory": "warning",
        "file_too_large": "warning",
        "document_too_large": "warning",
        "permission_denied": "error",
        "command_failed": "error",
        "command_timeout": "error",
        "executable_not_found": "error",
        "script_timeout": "error",
        "execution_error": "error",
        "internal_error": "error",
        "unknown_error": "error",
    }
    return mapping[category]


def is_retryable_category(category: ScriptRunnerErrorCategory) -> bool:
    return category in {"command_timeout", "script_timeout", "execution_error"}


def recovery_category_for_script_error(category: ScriptRunnerErrorCategory) -> str:
    mapping: dict[ScriptRunnerErrorCategory, str] = {
        "none": "unknown_error",
        "unknown_action": "unknown_action",
        "missing_parameter": "invalid_action_parameters",
        "invalid_parameter": "invalid_action_parameters",
        "unsafe_action": "unsafe_action",
        "unsafe_path": "unsafe_action",
        "unsafe_url": "unsafe_action",
        "file_not_found": "file_not_found",
        "document_not_found": "file_not_found",
        "directory_not_found": "file_not_found",
        "not_a_file": "file_not_found",
        "not_a_directory": "file_not_found",
        "file_too_large": "invalid_action_parameters",
        "document_too_large": "invalid_action_parameters",
        "permission_denied": "permission_denied",
        "command_timeout": "execution_error",
        "script_timeout": "execution_error",
        "command_failed": "execution_error",
        "executable_not_found": "execution_error",
        "execution_error": "execution_error",
        "internal_error": "unknown_error",
        "unknown_error": "unknown_error",
    }
    return mapping[category]


def normalize_script_execution_result(
    result: ScriptExecutionResult, source: str | None = None
) -> NormalizedScriptResult:
    if result.success:
        return NormalizedScriptResult(
            action=result.action,
            success=True,
            output=result.output,
            error=None,
            metadata=dict(result.metadata),
        )

    category = normalize_error_type(result.error_type)
    message = result.error_message or "Script execution failed without error_message."
    error = NormalizedScriptError(
        category=category,
        original_error_type=result.error_type,
        message=message,
        action=result.action,
        source=source,
        severity=severity_for_category(category),
        retryable=is_retryable_category(category),
        recovery_category=recovery_category_for_script_error(category),
        metadata=dict(result.metadata),
    )
    return NormalizedScriptResult(
        action=result.action,
        success=False,
        output=result.output,
        error=error,
        metadata=dict(result.metadata),
    )


def normalize_script_exception(
    exc: Exception,
    action: str,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedScriptResult:
    if not action.strip():
        raise ValueError("action must be non-empty.")

    if isinstance(exc, TimeoutError):
        category: ScriptRunnerErrorCategory = "script_timeout"
    elif isinstance(exc, PermissionError):
        category = "permission_denied"
    elif isinstance(exc, FileNotFoundError):
        category = "file_not_found"
    else:
        category = "internal_error"

    error = NormalizedScriptError(
        category=category,
        original_error_type=exc.__class__.__name__,
        message=str(exc) if str(exc).strip() else exc.__class__.__name__,
        action=action,
        source=source,
        severity=severity_for_category(category),
        retryable=is_retryable_category(category),
        recovery_category=recovery_category_for_script_error(category),
        metadata=dict(metadata or {}),
    )
    return NormalizedScriptResult(
        action=action,
        success=False,
        output=None,
        error=error,
        metadata=dict(metadata or {}),
    )


def normalize_many_script_results(
    results: list[ScriptExecutionResult], source: str | None = None
) -> list[NormalizedScriptResult]:
    return [normalize_script_execution_result(r, source=source) for r in results]
