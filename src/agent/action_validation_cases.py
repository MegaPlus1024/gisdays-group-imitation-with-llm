from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .action_contract import parse_next_action_text

ValidationLayer = Literal[
    "next_action_contract",
    "script_registry",
    "role_constraints",
    "safety_policy",
    "executor",
    "not_applicable",
]

ActionValidationFailureCategory = Literal[
    "invalid_json",
    "invalid_next_action_schema",
    "multiple_actions",
    "markdown_fenced_json",
    "unknown_action",
    "missing_required_parameter",
    "wrong_parameter_type",
    "invalid_action_parameters",
    "unsafe_action",
    "forbidden_path",
    "forbidden_by_role",
    "execution_error",
    "none",
]


class ActionValidationExpectedOutcome(BaseModel):
    should_accept: bool
    rejection_layer: ValidationLayer = "not_applicable"
    failure_category: ActionValidationFailureCategory = "none"
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_outcome(self) -> ActionValidationExpectedOutcome:
        if self.should_accept:
            if self.rejection_layer != "not_applicable":
                raise ValueError(
                    "If should_accept is true, rejection_layer must be not_applicable."
                )
            if self.failure_category != "none":
                raise ValueError(
                    "If should_accept is true, failure_category must be none."
                )
        else:
            if self.rejection_layer == "not_applicable":
                raise ValueError(
                    "If should_accept is false, rejection_layer must not be not_applicable."
                )
            if self.failure_category == "none":
                raise ValueError(
                    "If should_accept is false, failure_category must not be none."
                )
        return self


class ActionValidationTestCase(BaseModel):
    case_id: str
    title: str
    description: str
    agent_state_path: str | None = None
    role_template_path: str | None = None
    model_output_text: str
    expected: ActionValidationExpectedOutcome
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("case_id", "title", "description", "model_output_text")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case_id/title/description/model_output_text must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_unique_tags(self) -> ActionValidationTestCase:
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates.")
        return self


class ActionValidationCaseSuite(BaseModel):
    suite_id: str
    schema_version: str = "action_validation_cases_v1"
    cases: list[ActionValidationTestCase]

    @field_validator("suite_id")
    @classmethod
    def validate_suite_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("suite_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_cases(self) -> ActionValidationCaseSuite:
        if not self.cases:
            raise ValueError("cases must not be empty.")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique.")
        return self


def load_action_validation_cases(path: str | Path) -> ActionValidationCaseSuite:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return ActionValidationCaseSuite.model_validate(payload)


def cases_by_tag(
    suite: ActionValidationCaseSuite, tag: str
) -> list[ActionValidationTestCase]:
    return [case for case in suite.cases if tag in case.tags]


def summarize_cases(suite: ActionValidationCaseSuite) -> dict[str, Any]:
    rejection_layers: dict[str, int] = {}
    failure_categories: dict[str, int] = {}
    accepted = 0
    rejected = 0
    for case in suite.cases:
        if case.expected.should_accept:
            accepted += 1
        else:
            rejected += 1
        layer = case.expected.rejection_layer
        cat = case.expected.failure_category
        rejection_layers[layer] = rejection_layers.get(layer, 0) + 1
        failure_categories[cat] = failure_categories.get(cat, 0) + 1

    return {
        "suite_id": suite.suite_id,
        "total_cases": len(suite.cases),
        "accepted_cases": accepted,
        "rejected_cases": rejected,
        "rejection_layers": rejection_layers,
        "failure_category_counts": failure_categories,
    }


def probe_next_action_contract(case: ActionValidationTestCase) -> dict[str, Any]:
    try:
        parse_next_action_text(case.model_output_text)
        return {
            "case_id": case.case_id,
            "contract_parse_success": True,
            "error_type": None,
            "error_message": None,
        }
    except Exception as exc:
        return {
            "case_id": case.case_id,
            "contract_parse_success": False,
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        }
