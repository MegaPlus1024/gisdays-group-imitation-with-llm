from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

FailureCategory = Literal[
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
]

RecoveryAction = Literal[
    "retry",
    "retry_with_repair_prompt",
    "fail_step",
    "skip_agent",
    "abort_run",
    "continue_run",
    "mark_for_review",
]

LogLevel = Literal["debug", "info", "warning", "error", "critical"]


class FailureEvent(BaseModel):
    category: FailureCategory
    source: str
    message: str
    agent_id: str | None = None
    run_id: str | None = None
    step_index: int | None = None
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source", "message")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source and message must be non-empty.")
        return value

    @field_validator("retry_count")
    @classmethod
    def validate_retry_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retry_count must be >= 0.")
        return value

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("step_index must be >= 1 when provided.")
        return value


class RecoveryDecision(BaseModel):
    action: RecoveryAction
    reason: str
    max_retries: int = 0
    should_log: bool = True
    log_level: LogLevel = "warning"
    stop_agent: bool = False
    stop_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must be non-empty.")
        return value

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_retries must be >= 0.")
        return value

    @model_validator(mode="after")
    def validate_decision_shape(self) -> RecoveryDecision:
        if self.action == "abort_run" and not self.stop_run:
            raise ValueError("abort_run decisions must set stop_run=True.")
        if self.action == "skip_agent" and not self.stop_agent:
            raise ValueError("skip_agent decisions must set stop_agent=True.")
        if self.stop_run and self.log_level not in {"error", "critical"}:
            raise ValueError("stop_run decisions should use error or critical log level.")
        return self


class RecoveryPolicyRule(BaseModel):
    category: FailureCategory
    action: RecoveryAction
    reason: str
    max_retries: int = 0
    log_level: LogLevel = "warning"
    stop_agent: bool = False
    stop_run: bool = False

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rule reason must be non-empty.")
        return value

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("rule max_retries must be >= 0.")
        return value


class RecoveryPolicyConfig(BaseModel):
    policy_id: str
    rules: list[RecoveryPolicyRule]
    default_action: RecoveryAction = "fail_step"
    default_log_level: LogLevel = "error"

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("policy_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_unique_categories(self) -> RecoveryPolicyConfig:
        categories = [rule.category for rule in self.rules]
        if len(categories) != len(set(categories)):
            raise ValueError("rules must not contain duplicate categories.")
        return self


def default_recovery_policy() -> RecoveryPolicyConfig:
    rules = [
        RecoveryPolicyRule(
            category="invalid_json",
            action="retry_with_repair_prompt",
            reason="The model output was not valid JSON. Retry once later with stricter output-format instruction.",
            max_retries=1,
            log_level="warning",
        ),
        RecoveryPolicyRule(
            category="invalid_next_action_schema",
            action="fail_step",
            reason="The model returned JSON but it did not satisfy the NextAction contract.",
            max_retries=0,
            log_level="warning",
        ),
        RecoveryPolicyRule(
            category="malformed_model_response",
            action="fail_step",
            reason="Model response shape was malformed and output content could not be extracted.",
            max_retries=0,
            log_level="error",
        ),
        RecoveryPolicyRule(
            category="model_request_error",
            action="retry",
            reason="Model request failed due to runtime/transport issue.",
            max_retries=1,
            log_level="error",
        ),
        RecoveryPolicyRule(
            category="model_timeout",
            action="retry",
            reason="Model call timed out.",
            max_retries=1,
            log_level="error",
        ),
        RecoveryPolicyRule(
            category="llama_server_unreachable",
            action="abort_run",
            reason="Local llama-server is unreachable; run cannot continue reliably.",
            max_retries=0,
            log_level="critical",
            stop_run=True,
        ),
        RecoveryPolicyRule(
            category="empty_model_output",
            action="retry_with_repair_prompt",
            reason="Model returned empty output.",
            max_retries=1,
            log_level="warning",
        ),
        RecoveryPolicyRule(
            category="unknown_action",
            action="fail_step",
            reason="Action name is not recognized by higher-level policy/registry.",
            max_retries=0,
            log_level="warning",
        ),
        RecoveryPolicyRule(
            category="invalid_action_parameters",
            action="fail_step",
            reason="Action parameters do not satisfy future semantic requirements.",
            max_retries=0,
            log_level="warning",
        ),
        RecoveryPolicyRule(
            category="unsafe_action",
            action="fail_step",
            reason="Action was classified as unsafe.",
            max_retries=0,
            log_level="error",
        ),
        RecoveryPolicyRule(
            category="execution_error",
            action="continue_run",
            reason="Execution error occurred; record failure and continue run.",
            max_retries=0,
            log_level="error",
        ),
        RecoveryPolicyRule(
            category="file_not_found",
            action="fail_step",
            reason="Referenced file was not found.",
            max_retries=0,
            log_level="warning",
        ),
        RecoveryPolicyRule(
            category="permission_denied",
            action="skip_agent",
            reason="Permission denied; skip agent for this run.",
            max_retries=0,
            log_level="error",
            stop_agent=True,
        ),
        RecoveryPolicyRule(
            category="repeated_action_loop",
            action="skip_agent",
            reason="Repeated action loop detected.",
            max_retries=0,
            log_level="warning",
            stop_agent=True,
        ),
        RecoveryPolicyRule(
            category="max_steps_exceeded",
            action="skip_agent",
            reason="Maximum allowed steps exceeded for this agent.",
            max_retries=0,
            log_level="info",
            stop_agent=True,
        ),
        RecoveryPolicyRule(
            category="unknown_error",
            action="mark_for_review",
            reason="Unknown error type requires manual review.",
            max_retries=0,
            log_level="error",
        ),
    ]
    return RecoveryPolicyConfig(
        policy_id="failure_recovery_policy_v1",
        rules=rules,
        default_action="fail_step",
        default_log_level="error",
    )


class RecoveryPolicy:
    def __init__(self, config: RecoveryPolicyConfig | None = None) -> None:
        self.config = config or default_recovery_policy()
        self._rule_map = {rule.category: rule for rule in self.config.rules}

    def decide(self, event: FailureEvent) -> RecoveryDecision:
        rule = self._rule_map.get(event.category)
        if rule is None:
            return RecoveryDecision(
                action=self.config.default_action,
                reason=f"No specific policy rule for category '{event.category}'.",
                max_retries=0,
                log_level=self.config.default_log_level,
            )

        action = rule.action
        reason = rule.reason
        max_retries = rule.max_retries
        if action in {"retry", "retry_with_repair_prompt"} and event.retry_count >= max_retries:
            action = "fail_step"
            reason = (
                f"Retry budget exhausted for category '{event.category}' "
                f"(retry_count={event.retry_count}, max_retries={max_retries})."
            )
            max_retries = 0

        return RecoveryDecision(
            action=action,
            reason=reason,
            max_retries=max_retries,
            log_level=rule.log_level,
            stop_agent=rule.stop_agent,
            stop_run=rule.stop_run,
        )


def load_recovery_policy(path: str | Path) -> RecoveryPolicyConfig:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return RecoveryPolicyConfig.model_validate(payload)


def failure_event_from_exception(
    exc: Exception, source: str, **context: Any
) -> FailureEvent:
    from .action_contract import NextActionJSONError, NextActionValidationError
    from .llm_client import (
        LocalLLMJSONError,
        LocalLLMRequestError,
        LocalLLMResponseError,
        LocalLLMValidationError,
    )

    if isinstance(exc, (LocalLLMJSONError, NextActionJSONError)):
        category: FailureCategory = "invalid_json"
    elif isinstance(exc, (LocalLLMValidationError, NextActionValidationError)):
        category = "invalid_next_action_schema"
    elif isinstance(exc, LocalLLMResponseError):
        category = "malformed_model_response"
    elif isinstance(exc, LocalLLMRequestError):
        text = str(exc).lower()
        if "timed out" in text or "timeout" in text:
            category = "model_timeout"
        elif "connection refused" in text or "unreachable" in text:
            category = "llama_server_unreachable"
        else:
            category = "model_request_error"
    else:
        category = "unknown_error"

    event_kwargs = {
        "category": category,
        "source": source,
        "message": str(exc),
    }
    event_kwargs.update(context)
    return FailureEvent(**event_kwargs)
