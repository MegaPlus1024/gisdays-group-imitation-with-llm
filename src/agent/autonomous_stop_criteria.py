from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .activity_profile import NormalActivityProfile, load_activity_profile
from .schemas import NextAction

AutonomousStopDecisionAction = Literal[
    "continue_session",
    "stop_success",
    "stop_max_steps",
    "stop_consecutive_failures",
    "stop_total_failures",
    "stop_repeated_action",
    "stop_validation_failure",
    "stop_unsafe_action",
    "stop_recovery_abort_run",
    "stop_recovery_skip_agent",
    "stop_mark_for_review",
    "stop_no_progress",
    "stop_forbidden_for_normality",
    "stop_excessive_atypical_actions",
    "stop_unknown_failure",
]

AutonomousStopReasonCategory = Literal[
    "none",
    "success",
    "limit",
    "failure",
    "safety",
    "recovery",
    "repetition",
    "progress",
    "normality",
    "unknown",
]


class AutonomousStopCriteriaConfig(BaseModel):
    criteria_id: str = "autonomous_stop_criteria_v1"
    max_steps: int = 10
    max_consecutive_failures: int = 2
    max_total_failures: int = 3
    max_repeated_action_count: int = 2
    max_atypical_action_count: int = 2
    stop_on_success: bool = True
    stop_on_validation_failure: bool = True
    stop_on_unsafe_action: bool = True
    stop_on_recovery_abort_run: bool = True
    stop_on_recovery_skip_agent: bool = True
    stop_on_mark_for_review: bool = True
    stop_on_forbidden_for_normality: bool = True
    stop_on_excessive_atypical_actions: bool = True
    stop_on_repeated_action: bool = True
    require_progress_signal: bool = False
    activity_profile_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("criteria_id")
    @classmethod
    def validate_criteria_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("criteria_id must be non-empty.")
        return value

    @field_validator(
        "max_steps",
        "max_consecutive_failures",
        "max_total_failures",
        "max_repeated_action_count",
        "max_atypical_action_count",
    )
    @classmethod
    def validate_positive_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Stop criteria numeric limits must be >= 1.")
        return value


class AutonomousSessionStepSummary(BaseModel):
    step_index: int
    success: bool
    action: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    error_type: str | None = None
    issue_codes: list[str] = Field(default_factory=list)
    recovery_action: str | None = None
    progress_signal: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_index must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_issue_codes_unique(self) -> AutonomousSessionStepSummary:
        if len(self.issue_codes) != len(set(self.issue_codes)):
            raise ValueError("issue_codes must not contain duplicates.")
        return self


class AutonomousStopDecision(BaseModel):
    criteria_id: str
    should_stop: bool
    action: AutonomousStopDecisionAction
    reason_category: AutonomousStopReasonCategory
    reason: str
    step_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("criteria_id", "reason")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("criteria_id and reason must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_continue_shape(self) -> AutonomousStopDecision:
        if not self.should_stop:
            if self.action != "continue_session":
                raise ValueError("should_stop=False requires action='continue_session'.")
            if self.reason_category != "none":
                raise ValueError("should_stop=False requires reason_category='none'.")
        return self


class AutonomousSessionSummary(BaseModel):
    session_id: str
    agent_id: str
    steps: list[AutonomousSessionStepSummary] = Field(default_factory=list)
    goal_satisfied: bool = False
    marked_for_review: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_id and agent_id must be non-empty.")
        return value

    def step_count(self) -> int:
        return len(self.steps)

    def failure_count(self) -> int:
        return sum(1 for step in self.steps if not step.success)

    def consecutive_failure_count(self) -> int:
        count = 0
        for step in reversed(self.steps):
            if step.success:
                break
            count += 1
        return count

    def selected_actions(self) -> list[str]:
        return [step.action for step in self.steps if step.action is not None]

    def action_count(self, action: str) -> int:
        return sum(1 for step in self.steps if step.action == action)

    def atypical_action_count(self, profile: NormalActivityProfile) -> int:
        return sum(
            1 for step in self.steps if step.action is not None and profile.is_atypical_action(step.action)
        )

    def forbidden_for_normality_count(self, profile: NormalActivityProfile) -> int:
        return sum(
            1
            for step in self.steps
            if step.action is not None and profile.is_forbidden_for_normality(step.action)
        )


class AutonomousStopCriteriaEvaluator:
    def __init__(
        self,
        config: AutonomousStopCriteriaConfig | None = None,
        activity_profile: NormalActivityProfile | None = None,
    ) -> None:
        self.config = config or AutonomousStopCriteriaConfig()
        if activity_profile is not None:
            self.activity_profile = activity_profile
        elif self.config.activity_profile_path:
            self.activity_profile = load_activity_profile(self.config.activity_profile_path)
        else:
            self.activity_profile = None

    def evaluate(self, summary: AutonomousSessionSummary) -> AutonomousStopDecision:
        latest = latest_step(summary)

        if self.config.stop_on_success and summary.goal_satisfied:
            return self._stop("stop_success", "success", "Session goal is satisfied.", latest)

        if self.config.stop_on_mark_for_review and summary.marked_for_review:
            return self._stop(
                "stop_mark_for_review", "recovery", "Session is marked for manual review.", latest
            )

        if latest is not None:
            if (
                latest.recovery_action == "abort_run"
                and self.config.stop_on_recovery_abort_run
            ):
                return self._stop(
                    "stop_recovery_abort_run",
                    "recovery",
                    "Latest recovery action requested abort_run.",
                    latest,
                )
            if (
                latest.recovery_action == "skip_agent"
                and self.config.stop_on_recovery_skip_agent
            ):
                return self._stop(
                    "stop_recovery_skip_agent",
                    "recovery",
                    "Latest recovery action requested skip_agent.",
                    latest,
                )
            if (
                latest.recovery_action == "mark_for_review"
                and self.config.stop_on_mark_for_review
            ):
                return self._stop(
                    "stop_mark_for_review",
                    "recovery",
                    "Latest recovery action requested mark_for_review.",
                    latest,
                )

            unsafe_tokens = {"unsafe_action", "unsafe_path", "unsafe_url", "unsafe_command"}
            if self.config.stop_on_unsafe_action:
                if any(code in unsafe_tokens for code in latest.issue_codes):
                    return self._stop(
                        "stop_unsafe_action",
                        "safety",
                        "Latest step contains unsafe issue code.",
                        latest,
                    )
                if latest.error_type in unsafe_tokens:
                    return self._stop(
                        "stop_unsafe_action",
                        "safety",
                        "Latest step error_type indicates unsafe behavior.",
                        latest,
                    )

            if self.config.stop_on_validation_failure:
                if latest.status == "validation_failed" or latest.error_type == "validation_failed":
                    return self._stop(
                        "stop_validation_failure",
                        "failure",
                        "Latest step indicates validation failure.",
                        latest,
                    )

        if self.activity_profile is not None and latest is not None:
            if (
                self.config.stop_on_forbidden_for_normality
                and latest.action is not None
                and self.activity_profile.is_forbidden_for_normality(latest.action)
            ):
                return self._stop(
                    "stop_forbidden_for_normality",
                    "normality",
                    "Latest step action is forbidden-for-normality for this profile.",
                    latest,
                    metadata={"action": latest.action, "profile_id": self.activity_profile.profile_id},
                )

            if (
                self.config.stop_on_excessive_atypical_actions
                and summary.atypical_action_count(self.activity_profile) > self.config.max_atypical_action_count
            ):
                return self._stop(
                    "stop_excessive_atypical_actions",
                    "normality",
                    "Atypical action count exceeds configured threshold.",
                    latest,
                    metadata={
                        "atypical_action_count": summary.atypical_action_count(self.activity_profile),
                        "max_atypical_action_count": self.config.max_atypical_action_count,
                        "profile_id": self.activity_profile.profile_id,
                    },
                )

        if summary.step_count() >= self.config.max_steps:
            return self._stop("stop_max_steps", "limit", "Reached max_steps limit.", latest)
        if summary.consecutive_failure_count() >= self.config.max_consecutive_failures:
            return self._stop(
                "stop_consecutive_failures",
                "failure",
                "Reached max_consecutive_failures limit.",
                latest,
            )
        if summary.failure_count() >= self.config.max_total_failures:
            return self._stop(
                "stop_total_failures", "failure", "Reached max_total_failures limit.", latest
            )

        if self.config.stop_on_repeated_action and _repeated_action_threshold_exceeded(
            summary.steps, self.config.max_repeated_action_count
        ):
            return self._stop(
                "stop_repeated_action",
                "repetition",
                "Repeated exact action+parameters exceeds threshold.",
                latest,
            )
        if (
            self.config.stop_on_repeated_action
            and self.activity_profile is not None
            and _repeated_action_threshold_exceeded(
                summary.steps,
                self.activity_profile.repetition_policy.max_same_action_same_parameters,
            )
        ):
            return self._stop(
                "stop_repeated_action",
                "repetition",
                "Repeated exact action+parameters exceeds profile repetition policy.",
                latest,
                metadata={"profile_id": self.activity_profile.profile_id},
            )

        if (
            self.config.require_progress_signal
            and latest is not None
            and latest.progress_signal is False
        ):
            return self._stop(
                "stop_no_progress", "progress", "Latest step reports no progress signal.", latest
            )

        return AutonomousStopDecision(
            criteria_id=self.config.criteria_id,
            should_stop=False,
            action="continue_session",
            reason_category="none",
            reason="Continue session: no stop criteria triggered.",
            step_index=latest.step_index if latest is not None else None,
        )

    def _stop(
        self,
        action: AutonomousStopDecisionAction,
        category: AutonomousStopReasonCategory,
        reason: str,
        latest: AutonomousSessionStepSummary | None,
        metadata: dict[str, Any] | None = None,
    ) -> AutonomousStopDecision:
        return AutonomousStopDecision(
            criteria_id=self.config.criteria_id,
            should_stop=True,
            action=action,
            reason_category=category,
            reason=reason,
            step_index=latest.step_index if latest is not None else None,
            metadata=metadata or {},
        )


def make_action_fingerprint(action: str | None, parameters: dict[str, Any]) -> str:
    safe_action = action if action is not None else "<none>"
    params_text = json.dumps(parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{safe_action}|{params_text}"


def latest_step(summary: AutonomousSessionSummary) -> AutonomousSessionStepSummary | None:
    if not summary.steps:
        return None
    return summary.steps[-1]


def step_from_next_action(
    step_index: int,
    next_action: NextAction,
    success: bool = True,
    status: str | None = None,
    error_type: str | None = None,
    issue_codes: list[str] | None = None,
    recovery_action: str | None = None,
    progress_signal: bool | None = None,
) -> AutonomousSessionStepSummary:
    return AutonomousSessionStepSummary(
        step_index=step_index,
        success=success,
        action=next_action.action,
        parameters=dict(next_action.parameters),
        status=status,
        error_type=error_type,
        issue_codes=list(issue_codes or []),
        recovery_action=recovery_action,
        progress_signal=progress_signal,
    )


def load_autonomous_stop_criteria_config(path: str | Path) -> AutonomousStopCriteriaConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return AutonomousStopCriteriaConfig.model_validate(payload)


def _repeated_action_threshold_exceeded(
    steps: list[AutonomousSessionStepSummary], threshold: int
) -> bool:
    counts: dict[str, int] = {}
    for step in steps:
        fingerprint = make_action_fingerprint(step.action, step.parameters)
        counts[fingerprint] = counts.get(fingerprint, 0) + 1
        if counts[fingerprint] > threshold:
            return True
    return False
