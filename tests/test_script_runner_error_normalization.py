from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.script_runner_errors import (
    NormalizedScriptError,
    NormalizedScriptResult,
    is_retryable_category,
    normalize_error_type,
    normalize_many_script_results,
    normalize_script_exception,
    normalize_script_execution_result,
    recovery_category_for_script_error,
    severity_for_category,
)
from agent.scripts.results import ScriptExecutionResult


def _failed_result(error_type: str, error_message: str = "err") -> ScriptExecutionResult:
    return ScriptExecutionResult(
        action="run_shell_command",
        success=False,
        output=None,
        error_type=error_type,
        error_message=error_message,
        metadata={"k": "v"},
    )


def test_normalize_error_type_unknown_file_action() -> None:
    assert normalize_error_type("unknown_file_action") == "unknown_action"


def test_normalize_error_type_unknown_browser_action() -> None:
    assert normalize_error_type("unknown_browser_action") == "unknown_action"


def test_normalize_error_type_unknown_office_action() -> None:
    assert normalize_error_type("unknown_office_document_action") == "unknown_action"


def test_normalize_error_type_unknown_shell_action() -> None:
    assert normalize_error_type("unknown_shell_action") == "unknown_action"


def test_normalize_error_type_missing_parameter() -> None:
    assert normalize_error_type("missing_parameter") == "missing_parameter"


def test_normalize_error_type_invalid_parameter() -> None:
    assert normalize_error_type("invalid_parameter") == "invalid_parameter"


def test_normalize_error_type_unsafe_command() -> None:
    assert normalize_error_type("unsafe_command") == "unsafe_action"


def test_normalize_error_type_unsafe_path() -> None:
    assert normalize_error_type("unsafe_path") == "unsafe_path"


def test_normalize_error_type_unsafe_url() -> None:
    assert normalize_error_type("unsafe_url") == "unsafe_url"


def test_normalize_error_type_file_not_found() -> None:
    assert normalize_error_type("file_not_found") == "file_not_found"


def test_normalize_error_type_document_not_found() -> None:
    assert normalize_error_type("document_not_found") == "document_not_found"


def test_normalize_error_type_command_timeout() -> None:
    assert normalize_error_type("command_timeout") == "command_timeout"


def test_normalize_error_type_unknown_string_fallback() -> None:
    assert normalize_error_type("some_new_error") == "unknown_error"


def test_severity_mapping() -> None:
    assert severity_for_category("unsafe_action") == "error"
    assert severity_for_category("file_not_found") == "warning"


def test_retryable_mapping() -> None:
    assert is_retryable_category("command_timeout") is True
    assert is_retryable_category("unsafe_action") is False


def test_recovery_category_mapping() -> None:
    assert recovery_category_for_script_error("unsafe_path") == "unsafe_action"
    assert recovery_category_for_script_error("missing_parameter") == "invalid_action_parameters"
    assert recovery_category_for_script_error("command_failed") == "execution_error"


def test_normalize_script_execution_result_success_preserves_output() -> None:
    src = ScriptExecutionResult(
        action="read_file",
        success=True,
        output="ok",
        error_type=None,
        error_message=None,
        metadata={"x": 1},
    )
    normalized = normalize_script_execution_result(src, source="file_activity")
    assert normalized.success is True
    assert normalized.output == "ok"
    assert normalized.error is None


def test_normalize_script_execution_result_failure_converts_to_error() -> None:
    src = _failed_result("unsafe_command", "blocked command")
    normalized = normalize_script_execution_result(src, source="shell_command_activity")
    assert normalized.success is False
    assert normalized.error is not None
    assert normalized.error.category == "unsafe_action"
    assert normalized.error.recovery_category == "unsafe_action"


def test_normalize_script_execution_result_does_not_mutate_original() -> None:
    src = _failed_result("file_not_found", "missing")
    before = copy.deepcopy(src.model_dump())
    _ = normalize_script_execution_result(src, source="file_activity")
    after = src.model_dump()
    assert before == after


def test_normalize_script_exception_timeout() -> None:
    normalized = normalize_script_exception(
        TimeoutError("too slow"), action="run_shell_command", source="shell"
    )
    assert normalized.error is not None
    assert normalized.error.category == "script_timeout"


def test_normalize_script_exception_permission() -> None:
    normalized = normalize_script_exception(
        PermissionError("denied"), action="read_file", source="file"
    )
    assert normalized.error is not None
    assert normalized.error.category == "permission_denied"


def test_normalize_script_exception_file_not_found() -> None:
    normalized = normalize_script_exception(
        FileNotFoundError("missing"), action="read_file", source="file"
    )
    assert normalized.error is not None
    assert normalized.error.category == "file_not_found"


def test_normalize_script_exception_generic_exception() -> None:
    normalized = normalize_script_exception(
        RuntimeError("boom"), action="read_file", source="file"
    )
    assert normalized.error is not None
    assert normalized.error.category == "internal_error"


def test_normalize_many_script_results_preserves_order() -> None:
    one = ScriptExecutionResult(action="a", success=True, output="1")
    two = ScriptExecutionResult(
        action="b",
        success=False,
        error_type="command_failed",
        error_message="bad",
    )
    out = normalize_many_script_results([one, two], source="x")
    assert [r.action for r in out] == ["a", "b"]


def test_normalized_script_result_success_rejects_non_null_error() -> None:
    with pytest.raises(ValidationError):
        NormalizedScriptResult(
            action="x",
            success=True,
            error=NormalizedScriptError(category="unknown_error", message="m"),
        )


def test_normalized_script_result_failure_requires_error() -> None:
    with pytest.raises(ValidationError):
        NormalizedScriptResult(action="x", success=False, error=None)


def test_normalized_script_error_rejects_empty_message() -> None:
    with pytest.raises(ValidationError):
        NormalizedScriptError(category="unknown_error", message="")
