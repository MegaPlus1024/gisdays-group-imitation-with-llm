from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ActivitySequencePattern(BaseModel):
    pattern_id: str
    description: str
    action_sequence: list[str]
    min_length: int | None = None
    max_length: int | None = None
    examples: list[str] = Field(default_factory=list)
    non_examples: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("pattern_id", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pattern_id and description must be non-empty.")
        return value

    @field_validator("action_sequence")
    @classmethod
    def validate_action_sequence(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("action_sequence must contain at least one action.")
        for action in value:
            if not isinstance(action, str) or not action.strip():
                raise ValueError("action_sequence values must be non-empty strings.")
        return value

    @field_validator("min_length", "max_length")
    @classmethod
    def validate_lengths(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("min_length/max_length must be >= 1 when present.")
        return value

    @model_validator(mode="after")
    def validate_length_bounds(self) -> ActivitySequencePattern:
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.max_length < self.min_length
        ):
            raise ValueError("max_length must be >= min_length.")
        return self


class ActivityRepetitionPolicy(BaseModel):
    max_same_action_consecutive: int = 2
    max_same_action_total: int = 4
    max_same_action_same_parameters: int = 2
    repeated_action_warning_threshold: int = 2
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "max_same_action_consecutive",
        "max_same_action_total",
        "max_same_action_same_parameters",
        "repeated_action_warning_threshold",
    )
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("All repetition policy numeric fields must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_warning_threshold(self) -> ActivityRepetitionPolicy:
        if self.repeated_action_warning_threshold > self.max_same_action_total:
            raise ValueError(
                "repeated_action_warning_threshold must be <= max_same_action_total."
            )
        return self


class ActivityDiversityPolicy(BaseModel):
    min_unique_actions: int = 2
    min_action_families: int = 2
    preferred_action_families: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_unique_actions", "min_action_families")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("min_unique_actions and min_action_families must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_unique_families(self) -> ActivityDiversityPolicy:
        if len(self.preferred_action_families) != len(set(self.preferred_action_families)):
            raise ValueError("preferred_action_families must not contain duplicates.")
        return self


class NormalActivityProfile(BaseModel):
    profile_id: str
    role_id: str
    name: str
    description: str
    typical_actions: list[str]
    atypical_actions: list[str] = Field(default_factory=list)
    forbidden_for_normality: list[str] = Field(default_factory=list)
    expected_sequences: list[ActivitySequencePattern] = Field(default_factory=list)
    repetition_policy: ActivityRepetitionPolicy = Field(
        default_factory=ActivityRepetitionPolicy
    )
    diversity_policy: ActivityDiversityPolicy = Field(
        default_factory=ActivityDiversityPolicy
    )
    role_notes: list[str] = Field(default_factory=list)
    normality_notes: list[str] = Field(default_factory=list)
    evaluation_hints: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile_id", "role_id", "name", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("profile_id/role_id/name/description must be non-empty.")
        return value

    @field_validator("typical_actions")
    @classmethod
    def validate_typical_actions(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("typical_actions must contain at least one action.")
        for action in value:
            if not isinstance(action, str) or not action.strip():
                raise ValueError("typical_actions must contain non-empty strings.")
        return value

    @model_validator(mode="after")
    def validate_sets_and_sequences(self) -> NormalActivityProfile:
        if len(self.typical_actions) != len(set(self.typical_actions)):
            raise ValueError("typical_actions must not contain duplicates.")
        if len(self.atypical_actions) != len(set(self.atypical_actions)):
            raise ValueError("atypical_actions must not contain duplicates.")
        if len(self.forbidden_for_normality) != len(set(self.forbidden_for_normality)):
            raise ValueError("forbidden_for_normality must not contain duplicates.")

        overlap_typical_atypical = set(self.typical_actions) & set(self.atypical_actions)
        if overlap_typical_atypical:
            raise ValueError("An action cannot be both typical_actions and atypical_actions.")

        overlap_typical_forbidden = set(self.typical_actions) & set(
            self.forbidden_for_normality
        )
        if overlap_typical_forbidden:
            raise ValueError(
                "An action cannot be both typical_actions and forbidden_for_normality."
            )

        pattern_ids = [pattern.pattern_id for pattern in self.expected_sequences]
        if len(pattern_ids) != len(set(pattern_ids)):
            raise ValueError("expected_sequences must not contain duplicate pattern_id values.")
        return self

    def typical_action_set(self) -> set[str]:
        return set(self.typical_actions)

    def atypical_action_set(self) -> set[str]:
        return set(self.atypical_actions)

    def forbidden_action_set(self) -> set[str]:
        return set(self.forbidden_for_normality)

    def is_typical_action(self, action: str) -> bool:
        return action in self.typical_action_set()

    def is_atypical_action(self, action: str) -> bool:
        return action in self.atypical_action_set()

    def is_forbidden_for_normality(self, action: str) -> bool:
        return action in self.forbidden_action_set()

    def expected_action_names(self) -> set[str]:
        names = set(self.typical_actions) | set(self.atypical_actions) | set(
            self.forbidden_for_normality
        )
        for pattern in self.expected_sequences:
            names.update(pattern.action_sequence)
        return names


def load_activity_profile(path: str | Path) -> NormalActivityProfile:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return NormalActivityProfile.model_validate(payload)


def load_activity_profiles_from_dir(path: str | Path) -> list[NormalActivityProfile]:
    path_obj = Path(path)
    profiles: list[NormalActivityProfile] = []
    for file_path in sorted(path_obj.glob("*.json"), key=lambda p: p.name):
        profiles.append(load_activity_profile(file_path))
    return sorted(profiles, key=lambda p: p.profile_id)


def activity_profile_summary(profile: NormalActivityProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "role_id": profile.role_id,
        "typical_action_count": len(profile.typical_actions),
        "atypical_action_count": len(profile.atypical_actions),
        "sequence_count": len(profile.expected_sequences),
        "min_unique_actions": profile.diversity_policy.min_unique_actions,
        "min_action_families": profile.diversity_policy.min_action_families,
    }
