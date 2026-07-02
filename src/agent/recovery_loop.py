from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .action_selector import ActionSelectionResult
from .execution_history import ExecutionHistoryLogger
from .recovery import FailureCategory, FailureEvent, RecoveryDecision, RecoveryPolicy
from .script_execution_bridge import ScriptExecutionBridgeOutput
from .script_registry import ScriptValidationResult
from .state import AgentState

RecoveryLoopAttemptStatus = Literal[
    "selection_succeeded",
    "selection_failed",
    "bridge_succeeded",
    "bridge_failed",
    "recovery_decision_made",
    "retry_scheduled",
    "retry_skipped",
    "stopped",
]

RecoveryLoopRunStatus = Literal[
    "succeeded_without_recovery",
    "recovered_after_retry",
    "failed_step",
    "retry_budget_exhausted",
    "aborted_run",
    "skipped_agent",
    "marked_for_review",
    "failed_unknown",
]


class RecoveryLoopConfig(BaseModel):
    loop_id: str = "recovery_loop_v1"
    max_attempts: int = 2
    enable_retry: bool = True
    stop_on_abort_run: bool = True
    stop_on_skip_agent: bool = True
    write_history_logs: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("loop_id")
    @classmethod
    def validate_loop_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("loop_id must be non-empty.")
        return value

    @field_validator("max_attempts")
    @classmethod
    def validate_max_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_attempts must be >= 1.")
        return value


class RecoveryLoopAttemptResult(BaseModel):
    loop_id: str
    attempt_index: int
    status: RecoveryLoopAttemptStatus
    success: bool
    selection_result: ActionSelectionResult | None = None
    bridge_result: ScriptExecutionBridgeOutput | None = None
    failure_event: FailureEvent | None = None
    recovery_decision: RecoveryDecision | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("loop_id")
    @classmethod
    def validate_loop_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("loop_id must be non-empty.")
        return value

    @field_validator("attempt_index")
    @classmethod
    def validate_attempt_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("attempt_index must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_error_shape(self) -> RecoveryLoopAttemptResult:
        if not self.success and self.recovery_decision is None:
            if not self.error_type or not self.error_message:
                raise ValueError(
                    "Failed attempt requires error_type and error_message unless recovery_decision is present."
                )
        return self


class RecoveryLoopResult(BaseModel):
    loop_id: str
    success: bool
    status: RecoveryLoopRunStatus
    attempts: list[RecoveryLoopAttemptResult]
    final_selection: ActionSelectionResult | None = None
    final_bridge_result: ScriptExecutionBridgeOutput | None = None
    stopped_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("loop_id")
    @classmethod
    def validate_loop_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("loop_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> RecoveryLoopResult:
        if not self.attempts:
            raise ValueError("attempts must not be empty.")
        if not self.success and (self.stopped_reason is None or not self.stopped_reason.strip()):
            raise ValueError("stopped_reason must be non-empty when success=False.")
        return self

    def attempt_count(self) -> int:
        return len(self.attempts)

    def retry_count(self) -> int:
        return max(0, len(self.attempts) - 1)


def failure_event_from_selection_result(
    result: ActionSelectionResult,
    source: str = "ActionSelector",
    retry_count: int = 0,
) -> FailureEvent:
    category: FailureCategory = "unknown_error"
    issue_codes = _issue_codes(result.validation_result)

    if result.status == "selection_failed":
        lower = (result.error_type or "").lower() + " " + (result.error_message or "").lower()
        if "json" in lower or "parse" in lower:
            category = "invalid_json"
        elif "empty" in lower and "output" in lower:
            category = "empty_model_output"
        else:
            category = "malformed_model_response"
    elif result.status == "validation_failed":
        category = "invalid_action_parameters"
        if "unsafe_action" in issue_codes or "forbidden_path" in issue_codes or "unsafe_path" in issue_codes:
            category = "unsafe_action"
        elif "unknown_action" in issue_codes:
            category = "unknown_action"

    return FailureEvent(
        category=category,
        source=source,
        message=result.error_message or "Action selection failed.",
        agent_id=result.agent_id,
        retry_count=retry_count,
        metadata={"selection_status": result.status, "issue_codes": issue_codes},
    )


def failure_event_from_bridge_result(
    result: ScriptExecutionBridgeOutput,
    source: str = "ScriptExecutionBridge",
    retry_count: int = 0,
) -> FailureEvent:
    bridge_status = _bridge_status(result)
    issue_codes = _issue_codes(result.validation_result)
    category: FailureCategory = "unknown_error"

    if bridge_status == "validation_failed":
        category = "invalid_action_parameters"
        if "unsafe_action" in issue_codes or "forbidden_path" in issue_codes or "unsafe_path" in issue_codes:
            category = "unsafe_action"
        elif "unknown_action" in issue_codes:
            category = "unknown_action"
    elif bridge_status == "execution_failed":
        recovery_category = (
            result.normalized_result.error.recovery_category
            if result.normalized_result and result.normalized_result.error
            else None
        )
        category = recovery_category if recovery_category in _FAILURE_CATEGORY_SET else "execution_error"
    elif bridge_status == "dispatch_failed":
        if result.raw_result.error_type in {"unknown_action", "dispatch_failed"}:
            category = "unknown_action"
        else:
            category = "invalid_action_parameters"

    return FailureEvent(
        category=category,
        source=source,
        message=result.raw_result.error_message or "Script execution bridge failed.",
        retry_count=retry_count,
        metadata={
            "bridge_status": bridge_status,
            "issue_codes": issue_codes,
            "bridge_error_type": result.raw_result.error_type,
        },
    )


class RecoveryLoopHarness:
    def __init__(
        self,
        selector: Any,
        bridge: Any,
        recovery_policy: RecoveryPolicy | None = None,
        config: RecoveryLoopConfig | None = None,
        history_logger: ExecutionHistoryLogger | None = None,
    ) -> None:
        self.selector = selector
        self.bridge = bridge
        self.recovery_policy = recovery_policy or RecoveryPolicy()
        self.config = config or RecoveryLoopConfig()
        self.history_logger = history_logger

    def run_once_with_recovery(
        self,
        agent_state: AgentState,
        run_id: str = "recovery_loop_demo",
        step_index: int | None = None,
    ) -> RecoveryLoopResult:
        attempts: list[RecoveryLoopAttemptResult] = []
        final_selection: ActionSelectionResult | None = None
        final_bridge: ScriptExecutionBridgeOutput | None = None

        for attempt_index in range(1, self.config.max_attempts + 1):
            selection_result = self.selector.select_action(agent_state)
            final_selection = selection_result

            if not selection_result.success:
                event = failure_event_from_selection_result(
                    selection_result, retry_count=attempt_index - 1
                )
                decision = self.recovery_policy.decide(event)
                attempts.append(
                    RecoveryLoopAttemptResult(
                        loop_id=self.config.loop_id,
                        attempt_index=attempt_index,
                        status="recovery_decision_made",
                        success=False,
                        selection_result=selection_result,
                        failure_event=event,
                        recovery_decision=decision,
                        error_type=selection_result.error_type,
                        error_message=selection_result.error_message,
                    )
                )
                if self._should_retry(decision, attempt_index):
                    continue
                return self._finalize_failure(
                    attempts, final_selection, final_bridge, decision
                )

            if selection_result.next_action is None:
                event = FailureEvent(
                    category="malformed_model_response",
                    source="ActionSelector",
                    message="ActionSelector returned success=True with missing next_action.",
                    agent_id=selection_result.agent_id,
                    retry_count=attempt_index - 1,
                )
                decision = self.recovery_policy.decide(event)
                attempts.append(
                    RecoveryLoopAttemptResult(
                        loop_id=self.config.loop_id,
                        attempt_index=attempt_index,
                        status="recovery_decision_made",
                        success=False,
                        selection_result=selection_result,
                        failure_event=event,
                        recovery_decision=decision,
                        error_type="malformed_model_response",
                        error_message=event.message,
                    )
                )
                if self._should_retry(decision, attempt_index):
                    continue
                return self._finalize_failure(
                    attempts, final_selection, final_bridge, decision
                )

            bridge_result = self.bridge.execute_next_action(
                selection_result.next_action,
                run_id=run_id,
                agent_id=agent_state.agent_id,
                step_index=step_index,
            )
            final_bridge = bridge_result
            if bridge_result.success:
                attempts.append(
                    RecoveryLoopAttemptResult(
                        loop_id=self.config.loop_id,
                        attempt_index=attempt_index,
                        status="bridge_succeeded",
                        success=True,
                        selection_result=selection_result,
                        bridge_result=bridge_result,
                    )
                )
                return RecoveryLoopResult(
                    loop_id=self.config.loop_id,
                    success=True,
                    status=(
                        "succeeded_without_recovery"
                        if attempt_index == 1
                        else "recovered_after_retry"
                    ),
                    attempts=attempts,
                    final_selection=final_selection,
                    final_bridge_result=final_bridge,
                    metadata={"run_id": run_id},
                )

            event = failure_event_from_bridge_result(
                bridge_result, retry_count=attempt_index - 1
            )
            decision = self.recovery_policy.decide(event)
            attempts.append(
                RecoveryLoopAttemptResult(
                    loop_id=self.config.loop_id,
                    attempt_index=attempt_index,
                    status="recovery_decision_made",
                    success=False,
                    selection_result=selection_result,
                    bridge_result=bridge_result,
                    failure_event=event,
                    recovery_decision=decision,
                    error_type=bridge_result.raw_result.error_type,
                    error_message=bridge_result.raw_result.error_message,
                )
            )
            if self._should_retry(decision, attempt_index):
                continue
            return self._finalize_failure(
                attempts, final_selection, final_bridge, decision
            )

        return RecoveryLoopResult(
            loop_id=self.config.loop_id,
            success=False,
            status="retry_budget_exhausted",
            attempts=attempts,
            final_selection=final_selection,
            final_bridge_result=final_bridge,
            stopped_reason="Retry budget exhausted.",
            metadata={"run_id": run_id},
        )

    def _should_retry(self, decision: RecoveryDecision, attempt_index: int) -> bool:
        if decision.action not in {"retry", "retry_with_repair_prompt"}:
            return False
        if not self.config.enable_retry:
            return False
        return attempt_index < self.config.max_attempts

    def _finalize_failure(
        self,
        attempts: list[RecoveryLoopAttemptResult],
        final_selection: ActionSelectionResult | None,
        final_bridge: ScriptExecutionBridgeOutput | None,
        decision: RecoveryDecision,
    ) -> RecoveryLoopResult:
        status_map: dict[str, RecoveryLoopRunStatus] = {
            "fail_step": "failed_step",
            "abort_run": "aborted_run",
            "skip_agent": "skipped_agent",
            "mark_for_review": "marked_for_review",
        }
        status = status_map.get(decision.action, "failed_unknown")
        if decision.action in {"retry", "retry_with_repair_prompt"}:
            status = "retry_budget_exhausted"
        elif decision.action == "fail_step" and "Retry budget exhausted" in decision.reason:
            status = "retry_budget_exhausted"
        return RecoveryLoopResult(
            loop_id=self.config.loop_id,
            success=False,
            status=status,
            attempts=attempts,
            final_selection=final_selection,
            final_bridge_result=final_bridge,
            stopped_reason=decision.reason,
        )


def load_recovery_loop_config(path: str | Path) -> RecoveryLoopConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return RecoveryLoopConfig.model_validate(payload)


def _issue_codes(validation_result: ScriptValidationResult | None) -> list[str]:
    if validation_result is None:
        return []
    return [issue.code for issue in validation_result.issues]


def _bridge_status(result: ScriptExecutionBridgeOutput) -> str:
    if not result.validation_passed:
        return "validation_failed"
    if not result.dispatched:
        return "dispatch_failed"
    if not result.success:
        return "execution_failed"
    return "execution_succeeded"


_FAILURE_CATEGORY_SET = {
    "invalid_json",
    "invalid_next_action_schema",
    "malformed_model_response",
    "model_request_error",
    "model_timeout",
    "llama_server_unreachable",
    "empty_model_output",
    "unknown_action",
    "invalid_action_parameters",
    "unsafe_action",
    "execution_error",
    "file_not_found",
    "permission_denied",
    "repeated_action_loop",
    "max_steps_exceeded",
    "unknown_error",
}
