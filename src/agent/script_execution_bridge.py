from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .execution_history import (
    ExecutionHistoryLogger,
    history_from_normalized_script_result,
)
from .schemas import NextAction
from .script_registry import (
    ScriptRegistry,
    ScriptValidationIssue,
    ScriptValidationResult,
    load_script_registry,
    validate_next_action_against_registry,
)
from .script_runner_errors import (
    NormalizedScriptResult,
    normalize_script_execution_result,
)
from .scripts.browser_activity import BrowserActivityConfig, run_browser_activity
from .scripts.file_activity import FileActivityConfig, run_file_activity
from .scripts.office_document_activity import (
    OfficeDocumentActivityConfig,
    run_office_document_activity,
)
from .scripts.results import ScriptExecutionResult
from .scripts.shell_command_activity import (
    ShellCommandActivityConfig,
    run_shell_command_activity,
)


class ScriptExecutionBridgeConfig(BaseModel):
    project_root: Path = Path(".")
    registry_path: str = "configs/script_registry.example.json"
    validate_with_registry: bool = True
    normalize_result: bool = True
    write_history: bool = False

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: Path) -> Path:
        return value.resolve()


class ScriptExecutionBridgeOutput(BaseModel):
    action: str
    success: bool
    dispatched: bool
    validation_passed: bool
    validation_result: ScriptValidationResult | None = None
    raw_result: ScriptExecutionResult
    normalized_result: NormalizedScriptResult | None = None
    history_written: bool = False
    history_error: str | None = None


class ScriptExecutionBridge:
    def __init__(
        self,
        config: ScriptExecutionBridgeConfig | None = None,
        *,
        registry: ScriptRegistry | None = None,
        history_logger: ExecutionHistoryLogger | None = None,
    ) -> None:
        self.config = config or ScriptExecutionBridgeConfig()
        self.registry = registry
        self.history_logger = history_logger
        if self.config.validate_with_registry and self.registry is None:
            registry_path = self.config.project_root / self.config.registry_path
            self.registry = load_script_registry(registry_path)

    def execute_next_action(
        self,
        next_action: NextAction,
        *,
        run_id: str | None = None,
        agent_id: str | None = None,
        step_index: int | None = None,
    ) -> ScriptExecutionBridgeOutput:
        validation_result: ScriptValidationResult | None = None
        if self.config.validate_with_registry:
            assert self.registry is not None
            validation_result = validate_next_action_against_registry(
                next_action, self.registry
            )
            if not validation_result.accepted:
                raw_result = ScriptExecutionResult(
                    action=next_action.action,
                    success=False,
                    error_type="validation_failed",
                    error_message=_validation_message(validation_result.issues),
                    metadata={
                        "validation_issues": [
                            issue.model_dump() for issue in validation_result.issues
                        ]
                    },
                )
                normalized_result = normalize_script_execution_result(
                    raw_result, source="ScriptExecutionBridge"
                )
                history_written, history_error = self._maybe_log_history(
                    normalized_result,
                    run_id=run_id,
                    agent_id=agent_id,
                    step_index=step_index,
                )
                return ScriptExecutionBridgeOutput(
                    action=next_action.action,
                    success=False,
                    dispatched=False,
                    validation_passed=False,
                    validation_result=validation_result,
                    raw_result=raw_result,
                    normalized_result=(
                        normalized_result if self.config.normalize_result else None
                    ),
                    history_written=history_written,
                    history_error=history_error,
                )

        raw_result, dispatched = self._dispatch(next_action)
        normalized_result = normalize_script_execution_result(
            raw_result, source="ScriptExecutionBridge"
        )
        history_written, history_error = self._maybe_log_history(
            normalized_result,
            run_id=run_id,
            agent_id=agent_id,
            step_index=step_index,
        )
        return ScriptExecutionBridgeOutput(
            action=next_action.action,
            success=raw_result.success,
            dispatched=dispatched,
            validation_passed=True,
            validation_result=validation_result,
            raw_result=raw_result,
            normalized_result=(
                normalized_result if self.config.normalize_result else None
            ),
            history_written=history_written,
            history_error=history_error,
        )

    def _dispatch(self, next_action: NextAction) -> tuple[ScriptExecutionResult, bool]:
        action = next_action.action
        params = next_action.parameters
        project_root = self.config.project_root

        if action in {"read_file", "create_file", "append_file", "list_directory"}:
            result = run_file_activity(
                action,
                params,
                FileActivityConfig(project_root=project_root),
            )
            return result, True

        if action == "browser_open_url":
            result = run_browser_activity(
                "open_url",
                params,
                BrowserActivityConfig(),
            )
            return result, True

        if action == "office_create_document_stub":
            result = run_office_document_activity(
                "create_document_stub",
                params,
                OfficeDocumentActivityConfig(project_root=project_root),
            )
            return result, True

        if action == "run_shell_command":
            result = run_shell_command_activity(
                params,
                ShellCommandActivityConfig(project_root=project_root),
            )
            return result, True

        result = ScriptExecutionResult(
            action=action,
            success=False,
            error_type="dispatch_failed",
            error_message=f"Unsupported action for ScriptExecutionBridge: {action}",
            metadata={"supported_actions": SUPPORTED_ACTIONS},
        )
        return result, False

    def _maybe_log_history(
        self,
        normalized_result: NormalizedScriptResult,
        *,
        run_id: str | None,
        agent_id: str | None,
        step_index: int | None,
    ) -> tuple[bool, str | None]:
        if not self.config.write_history:
            return False, None
        if self.history_logger is None or not run_id or not agent_id:
            return False, None
        try:
            history_record, error_record = history_from_normalized_script_result(
                normalized_result,
                run_id=run_id,
                agent_id=agent_id,
                step_index=step_index,
            )
            self.history_logger.append_history_and_error(history_record, error_record)
            return True, None
        except Exception as exc:  # pragma: no cover - defensive
            return False, str(exc)


SUPPORTED_ACTIONS = [
    "read_file",
    "create_file",
    "append_file",
    "list_directory",
    "browser_open_url",
    "office_create_document_stub",
    "run_shell_command",
]


def _validation_message(issues: list[ScriptValidationIssue]) -> str:
    if not issues:
        return "Action rejected by script registry validation."
    codes = ", ".join(issue.code for issue in issues)
    return f"Action rejected by script registry validation: {codes}"


def load_script_execution_bridge_config(
    path: str | Path,
) -> ScriptExecutionBridgeConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ScriptExecutionBridgeConfig.model_validate(payload)
