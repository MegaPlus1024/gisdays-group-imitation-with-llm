from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .activity_evaluator import (
    ActivityEvaluationResult,
    ActivityTrajectoryEvaluator,
    ActivityTrajectoryStep,
)
from .activity_profile import NormalActivityProfile

ModelBehaviorEvaluationVerdict = Literal["pass", "warning", "fail", "insufficient_data"]
ModelBehaviorRunMode = Literal["synthetic", "dry_run", "local_model"]


class ModelBehaviorModelSpec(BaseModel):
    model_id: str
    model_name: str
    model_path: str | None = None
    model_family: str | None = None
    size_class: str | None = None
    quantization: str | None = None
    runtime: str = "llama.cpp / llama-server"
    cpu_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_id", "model_name", "runtime")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model_id/model_name/runtime must be non-empty.")
        return value


class ModelBehaviorResourceMetrics(BaseModel):
    wall_time_seconds_avg: float | None = None
    wall_time_seconds_min: float | None = None
    wall_time_seconds_max: float | None = None
    average_selection_latency_seconds: float | None = None
    average_total_step_latency_seconds: float | None = None
    cpu_percent_avg: float | None = None
    cpu_percent_max: float | None = None
    ram_delta_mb_avg: float | None = None
    tokens_per_second_avg: float | None = None
    prompt_tokens_avg: float | None = None
    completion_tokens_avg: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "wall_time_seconds_avg",
        "wall_time_seconds_min",
        "wall_time_seconds_max",
        "average_selection_latency_seconds",
        "average_total_step_latency_seconds",
        "cpu_percent_avg",
        "cpu_percent_max",
        "ram_delta_mb_avg",
        "tokens_per_second_avg",
        "prompt_tokens_avg",
        "completion_tokens_avg",
    )
    @classmethod
    def validate_non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Resource metrics must be >= 0 when present.")
        return value


class ModelBehaviorValidationMetrics(BaseModel):
    total_steps: int = 0
    json_valid_count: int = 0
    next_action_parse_success_count: int = 0
    registry_accepted_count: int = 0
    role_compliant_count: int = 0
    validation_failure_count: int = 0
    unsafe_action_count: int = 0
    execution_success_count: int | None = None
    execution_failure_count: int | None = None
    recovery_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_counts(self) -> ModelBehaviorValidationMetrics:
        counts = [
            self.total_steps,
            self.json_valid_count,
            self.next_action_parse_success_count,
            self.registry_accepted_count,
            self.role_compliant_count,
            self.validation_failure_count,
            self.unsafe_action_count,
            self.recovery_count,
        ]
        if any(v < 0 for v in counts):
            raise ValueError("Validation counts must be >= 0.")
        if self.execution_success_count is not None and self.execution_success_count < 0:
            raise ValueError("execution_success_count must be >= 0 when present.")
        if self.execution_failure_count is not None and self.execution_failure_count < 0:
            raise ValueError("execution_failure_count must be >= 0 when present.")
        if self.total_steps > 0:
            bounded = [
                self.json_valid_count,
                self.next_action_parse_success_count,
                self.registry_accepted_count,
                self.role_compliant_count,
                self.validation_failure_count,
                self.unsafe_action_count,
            ]
            if any(v > self.total_steps for v in bounded):
                raise ValueError("Validation counts must not exceed total_steps.")
            if self.execution_success_count is not None and self.execution_success_count > self.total_steps:
                raise ValueError("execution_success_count must not exceed total_steps.")
            if self.execution_failure_count is not None and self.execution_failure_count > self.total_steps:
                raise ValueError("execution_failure_count must not exceed total_steps.")
        return self

    def _rate(self, value: int) -> float:
        if self.total_steps == 0:
            return 0.0
        return value / self.total_steps

    def json_validity_rate(self) -> float:
        return self._rate(self.json_valid_count)

    def next_action_parse_success_rate(self) -> float:
        return self._rate(self.next_action_parse_success_count)

    def registry_acceptance_rate(self) -> float:
        return self._rate(self.registry_accepted_count)

    def role_compliance_rate(self) -> float:
        return self._rate(self.role_compliant_count)

    def validation_failure_rate(self) -> float:
        return self._rate(self.validation_failure_count)

    def unsafe_action_rate(self) -> float:
        return self._rate(self.unsafe_action_count)


class ModelBehaviorSelectedAction(BaseModel):
    step_index: int
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    expected_result: str | None = None
    registry_accepted: bool | None = None
    role_compliant: bool | None = None
    executed: bool = False
    success: bool | None = None
    issue_codes: list[str] = Field(default_factory=list)
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
    def validate_issue_codes(self) -> ModelBehaviorSelectedAction:
        if len(self.issue_codes) != len(set(self.issue_codes)):
            raise ValueError("issue_codes must not contain duplicates.")
        return self


class ModelBehaviorEvaluationResult(BaseModel):
    evaluation_id: str
    run_id: str
    scenario_id: str
    model: ModelBehaviorModelSpec
    run_mode: ModelBehaviorRunMode = "synthetic"
    verdict: ModelBehaviorEvaluationVerdict
    selected_actions: list[ModelBehaviorSelectedAction] = Field(default_factory=list)
    validation_metrics: ModelBehaviorValidationMetrics
    behavioral_evaluation: ActivityEvaluationResult | None = None
    resource_metrics: ModelBehaviorResourceMetrics = Field(default_factory=ModelBehaviorResourceMetrics)
    started_at: str | None = None
    completed_at: str | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evaluation_id", "run_id", "scenario_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evaluation_id/run_id/scenario_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_notes(self) -> ModelBehaviorEvaluationResult:
        if len(self.notes) != len(set(self.notes)):
            raise ValueError("notes must not contain duplicates.")
        return self

    def selected_action_names(self) -> list[str]:
        return [a.action for a in self.selected_actions]

    def step_count(self) -> int:
        return len(self.selected_actions)

    def normal_activity_score(self) -> float | None:
        if self.behavioral_evaluation is None:
            return None
        return self.behavioral_evaluation.score

    def summary_dict(self) -> dict[str, Any]:
        metrics = self.behavioral_evaluation.metrics if self.behavioral_evaluation else None
        return {
            "evaluation_id": self.evaluation_id,
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "model_id": self.model.model_id,
            "model_name": self.model.model_name,
            "run_mode": self.run_mode,
            "verdict": self.verdict,
            "step_count": self.step_count(),
            "selected_actions": self.selected_action_names(),
            "json_validity_rate": self.validation_metrics.json_validity_rate(),
            "registry_acceptance_rate": self.validation_metrics.registry_acceptance_rate(),
            "role_compliance_rate": self.validation_metrics.role_compliance_rate(),
            "normal_activity_score": self.normal_activity_score(),
            "diversity_score": metrics.diversity_score if metrics else None,
            "repetition_score": metrics.repetition_score if metrics else None,
            "wall_time_seconds_avg": self.resource_metrics.wall_time_seconds_avg,
            "cpu_percent_avg": self.resource_metrics.cpu_percent_avg,
            "ram_delta_mb_avg": self.resource_metrics.ram_delta_mb_avg,
        }


class ModelBehaviorEvaluationConfig(BaseModel):
    harness_id: str = "model_behavior_evaluation_v1"
    default_run_mode: ModelBehaviorRunMode = "synthetic"
    require_behavioral_evaluation: bool = True
    pass_normal_activity_score_threshold: float = 0.8
    warning_normal_activity_score_threshold: float = 0.6
    pass_registry_acceptance_rate_threshold: float = 0.9
    pass_role_compliance_rate_threshold: float = 0.9
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("harness_id")
    @classmethod
    def validate_harness_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("harness_id must be non-empty.")
        return value

    @field_validator(
        "pass_normal_activity_score_threshold",
        "warning_normal_activity_score_threshold",
        "pass_registry_acceptance_rate_threshold",
        "pass_role_compliance_rate_threshold",
    )
    @classmethod
    def validate_threshold(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("thresholds must be between 0 and 1.")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> ModelBehaviorEvaluationConfig:
        if self.pass_normal_activity_score_threshold < self.warning_normal_activity_score_threshold:
            raise ValueError(
                "pass_normal_activity_score_threshold must be >= warning_normal_activity_score_threshold."
            )
        return self


def derive_model_behavior_verdict(
    validation_metrics: ModelBehaviorValidationMetrics,
    behavioral_evaluation: ActivityEvaluationResult | None,
    config: ModelBehaviorEvaluationConfig | None = None,
) -> ModelBehaviorEvaluationVerdict:
    cfg = config or ModelBehaviorEvaluationConfig()
    if validation_metrics.total_steps == 0:
        return "insufficient_data"
    if validation_metrics.registry_acceptance_rate() < cfg.pass_registry_acceptance_rate_threshold:
        return "fail"
    if validation_metrics.role_compliance_rate() < cfg.pass_role_compliance_rate_threshold:
        return "fail"
    if cfg.require_behavioral_evaluation and behavioral_evaluation is None:
        return "insufficient_data"
    if behavioral_evaluation is None:
        return "warning"

    score = behavioral_evaluation.score
    if score >= cfg.pass_normal_activity_score_threshold and behavioral_evaluation.verdict != "failed":
        return "pass"
    if score >= cfg.warning_normal_activity_score_threshold:
        return "warning"
    return "fail"


def build_validation_metrics_from_actions(
    actions: list[ModelBehaviorSelectedAction],
) -> ModelBehaviorValidationMetrics:
    total = len(actions)
    registry_accepted_count = sum(1 for a in actions if a.registry_accepted is True)
    role_compliant_count = sum(1 for a in actions if a.role_compliant is True)
    validation_failure_count = sum(
        1
        for a in actions
        if (a.registry_accepted is False) or (a.role_compliant is False)
    )
    unsafe_action_count = sum(1 for a in actions if "unsafe_action" in a.issue_codes)
    execution_success_count = sum(1 for a in actions if a.executed and a.success is True)
    execution_failure_count = sum(1 for a in actions if a.executed and a.success is False)

    return ModelBehaviorValidationMetrics(
        total_steps=total,
        json_valid_count=total,
        next_action_parse_success_count=total,
        registry_accepted_count=registry_accepted_count,
        role_compliant_count=role_compliant_count,
        validation_failure_count=validation_failure_count,
        unsafe_action_count=unsafe_action_count,
        execution_success_count=execution_success_count,
        execution_failure_count=execution_failure_count,
        recovery_count=0,
    )


def activity_steps_from_model_actions(
    actions: list[ModelBehaviorSelectedAction],
) -> list[ActivityTrajectoryStep]:
    tokens = ("previous", "history", "earlier", "prior", "last step")
    steps: list[ActivityTrajectoryStep] = []
    for action in actions:
        reason_text = (action.reason or "").lower()
        used_history = any(token in reason_text for token in tokens)
        success = True if action.success is None else action.success
        steps.append(
            ActivityTrajectoryStep(
                step_index=action.step_index,
                action=action.action,
                parameters=dict(action.parameters),
                success=success,
                issue_codes=list(action.issue_codes),
                reason=action.reason,
                expected_result=action.expected_result,
                used_history=used_history,
            )
        )
    return steps


def build_synthetic_model_behavior_result(
    evaluation_id: str,
    run_id: str,
    scenario_id: str,
    model: ModelBehaviorModelSpec,
    actions: list[ModelBehaviorSelectedAction],
    activity_profile: NormalActivityProfile | None = None,
    evaluator: ActivityTrajectoryEvaluator | None = None,
    config: ModelBehaviorEvaluationConfig | None = None,
) -> ModelBehaviorEvaluationResult:
    cfg = config or ModelBehaviorEvaluationConfig()
    validation_metrics = build_validation_metrics_from_actions(actions)

    behavioral_evaluation: ActivityEvaluationResult | None = None
    if activity_profile is not None:
        evaluator_obj = evaluator or ActivityTrajectoryEvaluator()
        steps = activity_steps_from_model_actions(actions)
        behavioral_evaluation = evaluator_obj.evaluate(steps, activity_profile)

    verdict = derive_model_behavior_verdict(validation_metrics, behavioral_evaluation, cfg)
    return ModelBehaviorEvaluationResult(
        evaluation_id=evaluation_id,
        run_id=run_id,
        scenario_id=scenario_id,
        model=model,
        run_mode=cfg.default_run_mode,
        verdict=verdict,
        selected_actions=actions,
        validation_metrics=validation_metrics,
        behavioral_evaluation=behavioral_evaluation,
        resource_metrics=ModelBehaviorResourceMetrics(),
        notes=["Synthetic result: no model execution performed."],
    )


def load_model_behavior_evaluation_config(path: str | Path) -> ModelBehaviorEvaluationConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ModelBehaviorEvaluationConfig.model_validate(payload)


def load_model_behavior_result(path: str | Path) -> ModelBehaviorEvaluationResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ModelBehaviorEvaluationResult.model_validate(payload)


def save_model_behavior_result(result: ModelBehaviorEvaluationResult, path: str | Path) -> Path:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path_obj
