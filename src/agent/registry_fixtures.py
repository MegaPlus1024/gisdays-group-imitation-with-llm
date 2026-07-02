from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .action_contract import (
    NextActionJSONError,
    NextActionValidationError,
    parse_next_action_text,
)
from .role_template import load_role_template
from .script_registry import load_script_registry, validate_next_action_against_registry


class RegistryFixtureExpectation(BaseModel):
    case_id: str
    next_action_path: str
    registry_path: str
    role_template_path: str | None = None
    accepted: bool
    expected_issue_codes: list[str] = Field(default_factory=list)

    @field_validator("case_id", "next_action_path", "registry_path")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Fixture expectation text fields must be non-empty.")
        return value


class RegistryFixtureExpectationPack(BaseModel):
    fixture_pack_id: str
    expectations: list[RegistryFixtureExpectation]

    @field_validator("fixture_pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("fixture_pack_id must be non-empty.")
        return value


class RegistryFixtureCaseResult(BaseModel):
    case_id: str
    accepted: bool
    issue_codes: list[str] = Field(default_factory=list)
    matches_expectation: bool
    expected_issue_codes: list[str] = Field(default_factory=list)


class RegistryFixturePackResult(BaseModel):
    fixture_pack_id: str
    total_cases: int
    matched_cases: int
    mismatches: list[RegistryFixtureCaseResult] = Field(default_factory=list)
    case_results: list[RegistryFixtureCaseResult] = Field(default_factory=list)


def load_validation_expectations(path: str | Path) -> RegistryFixtureExpectationPack:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return RegistryFixtureExpectationPack.model_validate(payload)


def _collect_issue_codes(validation_result: Any) -> list[str]:
    issue_codes: set[str] = set()
    for issue in validation_result.issues:
        issue_codes.add(issue.code)
        specific_reason = issue.metadata.get("specific_reason")
        if isinstance(specific_reason, str) and specific_reason:
            issue_codes.add(specific_reason)
    return sorted(issue_codes)


def evaluate_fixture_case(
    *,
    fixtures_root: str | Path,
    expectation: RegistryFixtureExpectation,
) -> RegistryFixtureCaseResult:
    root = Path(fixtures_root)
    registry = load_script_registry(root / expectation.registry_path)
    next_action_text = (root / expectation.next_action_path).read_text(encoding="utf-8")
    role_template = (
        load_role_template(root / expectation.role_template_path)
        if expectation.role_template_path
        else None
    )

    try:
        next_action = parse_next_action_text(next_action_text)
    except NextActionJSONError:
        actual_accepted = False
        issue_codes = ["invalid_json"]
    except NextActionValidationError:
        actual_accepted = False
        issue_codes = ["invalid_next_action_schema"]
    else:
        result = validate_next_action_against_registry(
            next_action, registry, role_template=role_template
        )
        actual_accepted = result.accepted
        issue_codes = _collect_issue_codes(result)

    expected_codes = sorted(expectation.expected_issue_codes)
    expected_set = set(expected_codes)
    actual_set = set(issue_codes)
    matches = (
        actual_accepted == expectation.accepted
        and expected_set.issubset(actual_set)
        and (expectation.accepted or bool(actual_set))
    )

    return RegistryFixtureCaseResult(
        case_id=expectation.case_id,
        accepted=actual_accepted,
        issue_codes=issue_codes,
        matches_expectation=matches,
        expected_issue_codes=expected_codes,
    )


def evaluate_fixture_pack(
    fixtures_root: str | Path,
    expectations_path: str | Path,
) -> RegistryFixturePackResult:
    pack = load_validation_expectations(expectations_path)
    case_results = [
        evaluate_fixture_case(fixtures_root=fixtures_root, expectation=exp)
        for exp in pack.expectations
    ]
    mismatches = [case for case in case_results if not case.matches_expectation]
    return RegistryFixturePackResult(
        fixture_pack_id=pack.fixture_pack_id,
        total_cases=len(case_results),
        matched_cases=len(case_results) - len(mismatches),
        mismatches=mismatches,
        case_results=case_results,
    )
