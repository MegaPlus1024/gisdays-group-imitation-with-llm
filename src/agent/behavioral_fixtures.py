from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .activity_evaluator import (
    ActivityEvaluationResult,
    ActivityTrajectoryEvaluator,
    ActivityTrajectoryStep,
)
from .activity_profile import load_activity_profile

BEHAVIORAL_FIXTURE_ROOT = Path("tests/fixtures/behavioral_trajectories")
BEHAVIORAL_FIXTURE_PACK_ID = "behavioral_validation_fixtures_v1"


class BehavioralTrajectoryFixture(BaseModel):
    trajectory_id: str
    role_id: str
    activity_profile_path: str
    description: str
    expected_verdict_hint: str | None = None
    steps: list[ActivityTrajectoryStep]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trajectory_id", "role_id", "activity_profile_path", "description")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("trajectory_id/role_id/activity_profile_path/description must be non-empty.")
        return value

    @field_validator("steps")
    @classmethod
    def validate_steps_not_empty(cls, value: list[ActivityTrajectoryStep]) -> list[ActivityTrajectoryStep]:
        if not value:
            raise ValueError("steps must not be empty.")
        return value


class MultiAgentBehavioralTrajectoryFixture(BaseModel):
    fixture_id: str
    description: str
    agent_trajectories: list[BehavioralTrajectoryFixture]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fixture_id", "description")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("fixture_id and description must be non-empty.")
        return value

    @field_validator("agent_trajectories")
    @classmethod
    def validate_non_empty_trajs(
        cls, value: list[BehavioralTrajectoryFixture]
    ) -> list[BehavioralTrajectoryFixture]:
        if not value:
            raise ValueError("agent_trajectories must not be empty.")
        return value


class BehavioralExpectation(BaseModel):
    case_id: str
    trajectory_path: str
    activity_profile_path: str
    expected_verdicts: list[str]
    min_score: float = 0.0
    max_score: float = 1.0
    required_flags: list[str] = Field(default_factory=list)
    forbidden_flags: list[str] = Field(default_factory=list)
    score_should_exceed_case: str | None = None
    min_history_usage_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id", "trajectory_path", "activity_profile_path")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case_id/trajectory_path/activity_profile_path must be non-empty.")
        return value

    @field_validator("expected_verdicts")
    @classmethod
    def validate_expected_verdicts(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("expected_verdicts must not be empty.")
        return value

    @field_validator("min_score", "max_score", "min_history_usage_score")
    @classmethod
    def validate_score_range(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not (0.0 <= value <= 1.0):
            raise ValueError("score thresholds must be between 0 and 1.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> BehavioralExpectation:
        if self.max_score < self.min_score:
            raise ValueError("max_score must be >= min_score.")
        if len(self.required_flags) != len(set(self.required_flags)):
            raise ValueError("required_flags must not contain duplicates.")
        if len(self.forbidden_flags) != len(set(self.forbidden_flags)):
            raise ValueError("forbidden_flags must not contain duplicates.")
        return self


class BehavioralExpectationSuite(BaseModel):
    fixture_pack_id: str
    expectations: list[BehavioralExpectation]

    @field_validator("fixture_pack_id")
    @classmethod
    def validate_fixture_pack_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("fixture_pack_id must be non-empty.")
        return value

    @field_validator("expectations")
    @classmethod
    def validate_non_empty(cls, value: list[BehavioralExpectation]) -> list[BehavioralExpectation]:
        if not value:
            raise ValueError("expectations must not be empty.")
        return value

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> BehavioralExpectationSuite:
        case_ids = [item.case_id for item in self.expectations]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("expectation case_id values must be unique.")
        return self


def behavioral_fixture_path(relative_path: str | Path) -> Path:
    rel = Path(relative_path)
    candidate = (BEHAVIORAL_FIXTURE_ROOT / rel).resolve()
    root = BEHAVIORAL_FIXTURE_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Fixture path traversal is not allowed: {relative_path}") from exc
    return candidate


def load_behavioral_json_fixture(relative_path: str | Path) -> Any:
    path = behavioral_fixture_path(relative_path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_behavioral_trajectory_fixture(relative_path: str | Path) -> BehavioralTrajectoryFixture:
    payload = load_behavioral_json_fixture(relative_path)
    return BehavioralTrajectoryFixture.model_validate(payload)


def load_multi_agent_behavioral_fixture(
    relative_path: str | Path,
) -> MultiAgentBehavioralTrajectoryFixture:
    payload = load_behavioral_json_fixture(relative_path)
    return MultiAgentBehavioralTrajectoryFixture.model_validate(payload)


def load_behavioral_expectations(
    relative_path: str | Path = "expected_results/behavioral_expectations.json",
) -> BehavioralExpectationSuite:
    payload = load_behavioral_json_fixture(relative_path)
    return BehavioralExpectationSuite.model_validate(payload)


def evaluate_behavioral_fixture(
    fixture: BehavioralTrajectoryFixture,
    evaluator: ActivityTrajectoryEvaluator | None = None,
) -> ActivityEvaluationResult:
    evaluator_obj = evaluator or ActivityTrajectoryEvaluator()
    profile = load_activity_profile(fixture.activity_profile_path)
    return evaluator_obj.evaluate(fixture.steps, profile)
