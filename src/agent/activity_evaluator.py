from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .activity_profile import NormalActivityProfile
from .schemas import NextAction

ActivityEvaluationVerdict = Literal["normal", "suspicious", "failed", "insufficient_data"]


class ActivityTrajectoryStep(BaseModel):
    step_index: int
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    status: str | None = None
    issue_codes: list[str] = Field(default_factory=list)
    reason: str | None = None
    expected_result: str | None = None
    used_history: bool | None = None
    progress_signal: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_index must be >= 1.")
        return value

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_issue_codes(self) -> ActivityTrajectoryStep:
        if len(self.issue_codes) != len(set(self.issue_codes)):
            raise ValueError("issue_codes must not contain duplicates.")
        return self


class ActivityEvaluationConfig(BaseModel):
    evaluator_id: str = "normal_activity_trajectory_evaluator_v1"
    suspicious_score_threshold: float = 0.6
    normal_score_threshold: float = 0.8
    min_steps_for_full_score: int = 2
    penalize_failed_steps: bool = True
    penalize_atypical_actions: bool = True
    penalize_forbidden_for_normality: bool = True
    penalize_repetition: bool = True
    reward_expected_sequences: bool = True
    reward_history_usage: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evaluator_id")
    @classmethod
    def validate_evaluator_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evaluator_id must be non-empty.")
        return value

    @field_validator("suspicious_score_threshold", "normal_score_threshold")
    @classmethod
    def validate_thresholds(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("Score thresholds must be between 0 and 1.")
        return value

    @field_validator("min_steps_for_full_score")
    @classmethod
    def validate_min_steps(cls, value: int) -> int:
        if value < 1:
            raise ValueError("min_steps_for_full_score must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_threshold_order(self) -> ActivityEvaluationConfig:
        if self.normal_score_threshold < self.suspicious_score_threshold:
            raise ValueError("normal_score_threshold must be >= suspicious_score_threshold.")
        return self


class ActivityMetricBreakdown(BaseModel):
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    typical_action_count: int = 0
    atypical_action_count: int = 0
    forbidden_for_normality_count: int = 0
    unique_action_count: int = 0
    action_family_count: int = 0
    repeated_action_count: int = 0
    repeated_same_parameters_count: int = 0
    expected_sequence_matches: int = 0
    history_usage_count: int = 0
    role_fit_score: float = 0.0
    diversity_score: float = 0.0
    repetition_score: float = 0.0
    sequence_coherence_score: float = 0.0
    history_usage_score: float = 0.0
    normal_activity_score: float = 0.0
    flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ranges(self) -> ActivityMetricBreakdown:
        count_fields = [
            self.total_steps,
            self.successful_steps,
            self.failed_steps,
            self.typical_action_count,
            self.atypical_action_count,
            self.forbidden_for_normality_count,
            self.unique_action_count,
            self.action_family_count,
            self.repeated_action_count,
            self.repeated_same_parameters_count,
            self.expected_sequence_matches,
            self.history_usage_count,
        ]
        if any(v < 0 for v in count_fields):
            raise ValueError("Counts must be >= 0.")
        score_fields = [
            self.role_fit_score,
            self.diversity_score,
            self.repetition_score,
            self.sequence_coherence_score,
            self.history_usage_score,
            self.normal_activity_score,
        ]
        if any((v < 0.0 or v > 1.0) for v in score_fields):
            raise ValueError("Scores must be between 0 and 1.")
        if len(self.flags) != len(set(self.flags)):
            raise ValueError("flags must not contain duplicates.")
        return self


class ActivityEvaluationResult(BaseModel):
    evaluator_id: str
    profile_id: str
    role_id: str
    verdict: ActivityEvaluationVerdict
    score: float
    metrics: ActivityMetricBreakdown
    explanations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evaluator_id", "profile_id", "role_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evaluator_id/profile_id/role_id must be non-empty.")
        return value

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("score must be between 0 and 1.")
        return value

    @model_validator(mode="after")
    def validate_explanations(self) -> ActivityEvaluationResult:
        if len(self.explanations) != len(set(self.explanations)):
            raise ValueError("explanations must not contain duplicates.")
        return self


def action_family(action: str) -> str:
    file_actions = {"read_file", "create_file", "append_file", "list_directory"}
    browser_actions = {"browser_open_url", "open_url", "search_web", "read_page_summary", "fill_form_stub"}
    office_actions = {
        "office_create_document_stub",
        "create_document_stub",
        "append_document_section",
        "read_document_stub",
        "extract_document_outline_stub",
        "create_table_note_stub",
    }
    shell_actions = {"run_shell_command", "simulate_shell_command"}
    if action in file_actions:
        return "file"
    if action in browser_actions:
        return "browser"
    if action in office_actions:
        return "office"
    if action in shell_actions:
        return "shell"
    return "unknown"


def action_fingerprint(action: str, parameters: dict[str, Any]) -> str:
    params = json.dumps(parameters, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"{action}|{params}"


def count_repeated_actions(steps: list[ActivityTrajectoryStep]) -> int:
    seen: set[str] = set()
    repeated = 0
    for step in steps:
        if step.action in seen:
            repeated += 1
        else:
            seen.add(step.action)
    return repeated


def count_repeated_same_parameters(steps: list[ActivityTrajectoryStep]) -> int:
    seen: set[str] = set()
    repeated = 0
    for step in steps:
        fp = action_fingerprint(step.action, step.parameters)
        if fp in seen:
            repeated += 1
        else:
            seen.add(fp)
    return repeated


def find_expected_sequence_matches(
    steps: list[ActivityTrajectoryStep],
    profile: NormalActivityProfile,
) -> list[str]:
    trajectory_actions = [step.action for step in steps]
    matched: list[str] = []
    for pattern in profile.expected_sequences:
        if _is_ordered_subsequence(pattern.action_sequence, trajectory_actions):
            matched.append(pattern.pattern_id)
    return matched


def trajectory_steps_from_next_actions(next_actions: list[NextAction]) -> list[ActivityTrajectoryStep]:
    out: list[ActivityTrajectoryStep] = []
    for i, action in enumerate(next_actions, start=1):
        out.append(
            ActivityTrajectoryStep(
                step_index=i,
                action=action.action,
                parameters=dict(action.parameters),
                success=True,
                reason=action.reason,
                expected_result=action.expected_result,
            )
        )
    return out


class ActivityTrajectoryEvaluator:
    def __init__(self, config: ActivityEvaluationConfig | None = None) -> None:
        self.config = config or ActivityEvaluationConfig()

    def evaluate(
        self,
        steps: list[ActivityTrajectoryStep],
        profile: NormalActivityProfile,
    ) -> ActivityEvaluationResult:
        if not steps:
            metrics = ActivityMetricBreakdown(
                total_steps=0,
                normal_activity_score=0.0,
            )
            return ActivityEvaluationResult(
                evaluator_id=self.config.evaluator_id,
                profile_id=profile.profile_id,
                role_id=profile.role_id,
                verdict="insufficient_data",
                score=0.0,
                metrics=metrics,
                explanations=["No trajectory steps available."],
            )

        total_steps = len(steps)
        successful_steps = sum(1 for step in steps if step.success)
        failed_steps = total_steps - successful_steps

        typical_action_count = sum(1 for step in steps if profile.is_typical_action(step.action))
        atypical_action_count = sum(1 for step in steps if profile.is_atypical_action(step.action))
        forbidden_count = sum(1 for step in steps if profile.is_forbidden_for_normality(step.action))
        unique_action_count = len({step.action for step in steps})
        action_family_count = len({action_family(step.action) for step in steps})
        repeated_action_count = count_repeated_actions(steps)
        repeated_same_parameters_count = count_repeated_same_parameters(steps)
        sequence_matches = find_expected_sequence_matches(steps, profile)
        expected_sequence_matches = len(sequence_matches)
        history_usage_count = _history_usage_count(steps)

        role_fit_score = _clamp01(typical_action_count / total_steps)
        if self.config.penalize_forbidden_for_normality and forbidden_count > 0:
            role_fit_score -= min(0.8, 0.4 * forbidden_count)
        if self.config.penalize_atypical_actions and atypical_action_count > 0:
            role_fit_score -= min(0.4, 0.1 * atypical_action_count)
        role_fit_score = _clamp01(role_fit_score)

        diversity_actions = _clamp01(
            unique_action_count / max(profile.diversity_policy.min_unique_actions, 1)
        )
        diversity_families = _clamp01(
            action_family_count / max(profile.diversity_policy.min_action_families, 1)
        )
        diversity_score = _clamp01((diversity_actions + diversity_families) / 2)

        repetition_score = 1.0
        if self.config.penalize_repetition:
            rep_param_limit = max(profile.repetition_policy.max_same_action_same_parameters, 1)
            rep_total_limit = max(profile.repetition_policy.max_same_action_total, 1)
            repetition_score -= min(0.6, repeated_same_parameters_count / rep_param_limit * 0.4)
            repetition_score -= min(0.4, repeated_action_count / rep_total_limit * 0.3)
        repetition_score = _clamp01(repetition_score)

        if profile.expected_sequences and self.config.reward_expected_sequences:
            sequence_coherence_score = _clamp01(
                expected_sequence_matches / len(profile.expected_sequences)
            )
        elif profile.expected_sequences:
            sequence_coherence_score = 0.5
        else:
            sequence_coherence_score = 0.5

        if total_steps <= 1:
            history_usage_score = 0.5
        elif self.config.reward_history_usage:
            history_usage_score = _clamp01(history_usage_count / max(total_steps - 1, 1))
        else:
            history_usage_score = 0.5

        normal_activity_score = _clamp01(
            role_fit_score * 0.35
            + diversity_score * 0.20
            + repetition_score * 0.20
            + sequence_coherence_score * 0.15
            + history_usage_score * 0.10
        )
        if self.config.penalize_failed_steps:
            normal_activity_score = _clamp01(normal_activity_score * (successful_steps / total_steps))

        flags: list[str] = []
        if forbidden_count > 0:
            flags.append("forbidden_for_normality_action")
        if atypical_action_count > 0:
            flags.append("atypical_actions_present")
        if repeated_same_parameters_count > 0:
            flags.append("repeated_same_parameters")
        if diversity_score < 0.5:
            flags.append("low_diversity")
        if sequence_coherence_score < 0.5:
            flags.append("low_sequence_coherence")
        if failed_steps > 0:
            flags.append("failed_steps_present")

        metrics = ActivityMetricBreakdown(
            total_steps=total_steps,
            successful_steps=successful_steps,
            failed_steps=failed_steps,
            typical_action_count=typical_action_count,
            atypical_action_count=atypical_action_count,
            forbidden_for_normality_count=forbidden_count,
            unique_action_count=unique_action_count,
            action_family_count=action_family_count,
            repeated_action_count=repeated_action_count,
            repeated_same_parameters_count=repeated_same_parameters_count,
            expected_sequence_matches=expected_sequence_matches,
            history_usage_count=history_usage_count,
            role_fit_score=role_fit_score,
            diversity_score=diversity_score,
            repetition_score=repetition_score,
            sequence_coherence_score=sequence_coherence_score,
            history_usage_score=history_usage_score,
            normal_activity_score=normal_activity_score,
            flags=flags,
            metadata={"sequence_matches": sequence_matches},
        )

        verdict: ActivityEvaluationVerdict
        if (
            (forbidden_count > 0 and normal_activity_score < self.config.suspicious_score_threshold)
            or normal_activity_score < self.config.suspicious_score_threshold
        ):
            verdict = "failed"
        elif normal_activity_score < self.config.normal_score_threshold:
            verdict = "suspicious"
        else:
            verdict = "normal"

        explanations = _build_explanations(metrics, verdict)
        return ActivityEvaluationResult(
            evaluator_id=self.config.evaluator_id,
            profile_id=profile.profile_id,
            role_id=profile.role_id,
            verdict=verdict,
            score=normal_activity_score,
            metrics=metrics,
            explanations=explanations,
        )


def load_activity_evaluation_config(path: str | Path) -> ActivityEvaluationConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ActivityEvaluationConfig.model_validate(payload)


def _is_ordered_subsequence(pattern: list[str], sequence: list[str]) -> bool:
    if not pattern:
        return True
    idx = 0
    for action in sequence:
        if action == pattern[idx]:
            idx += 1
            if idx == len(pattern):
                return True
    return False


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _history_usage_count(steps: list[ActivityTrajectoryStep]) -> int:
    tokens = ("history", "previous", "prior", "earlier", "step")
    count = 0
    for step in steps:
        if step.used_history is True:
            count += 1
            continue
        reason = (step.reason or "").lower()
        if any(token in reason for token in tokens):
            count += 1
    return count


def _build_explanations(metrics: ActivityMetricBreakdown, verdict: ActivityEvaluationVerdict) -> list[str]:
    explanations = [f"Verdict: {verdict}.", f"Normal activity score: {metrics.normal_activity_score:.3f}."]
    if metrics.forbidden_for_normality_count:
        explanations.append("Forbidden-for-normality actions were detected.")
    if metrics.atypical_action_count:
        explanations.append("Atypical actions are present in the trajectory.")
    if metrics.repeated_same_parameters_count:
        explanations.append("Repeated action+parameter patterns were detected.")
    if metrics.expected_sequence_matches:
        explanations.append("Expected sequence patterns were matched.")
    if metrics.failed_steps:
        explanations.append("Failed steps reduced the final score.")
    return list(dict.fromkeys(explanations))
