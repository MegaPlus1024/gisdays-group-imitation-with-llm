from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_validation_cases import (
    ActionValidationCaseSuite,
    ActionValidationExpectedOutcome,
    ActionValidationTestCase,
    cases_by_tag,
    load_action_validation_cases,
    probe_next_action_contract,
    summarize_cases,
)


def _load_suite() -> ActionValidationCaseSuite:
    return load_action_validation_cases("configs/action_validation_cases.example.json")


def test_load_action_validation_cases_loads_example() -> None:
    suite = _load_suite()
    assert suite.suite_id == "action_validation_cases_v1"


def test_suite_has_at_least_14_cases() -> None:
    suite = _load_suite()
    assert len(suite.cases) >= 14


def test_case_ids_are_unique() -> None:
    suite = _load_suite()
    ids = [c.case_id for c in suite.cases]
    assert len(ids) == len(set(ids))


def test_summarize_cases_counts_match_suite() -> None:
    suite = _load_suite()
    summary = summarize_cases(suite)
    assert summary["total_cases"] == len(suite.cases)
    assert summary["accepted_cases"] == 3
    assert summary["rejected_cases"] == len(suite.cases) - 3


def test_cases_by_tag_works() -> None:
    suite = _load_suite()
    positives = cases_by_tag(suite, "positive")
    assert len(positives) == 3


def test_positive_cases_have_should_accept_true() -> None:
    suite = _load_suite()
    for case in cases_by_tag(suite, "positive"):
        assert case.expected.should_accept is True


def test_negative_cases_have_should_accept_false() -> None:
    suite = _load_suite()
    for case in suite.cases:
        if "negative" in case.tags:
            assert case.expected.should_accept is False


def test_contract_level_invalid_cases_fail_probe() -> None:
    suite = _load_suite()
    for case in cases_by_tag(suite, "contract_invalid"):
        result = probe_next_action_contract(case)
        assert result["contract_parse_success"] is False


def test_future_semantic_invalid_cases_may_pass_contract_probe() -> None:
    suite = _load_suite()
    pass_count = 0
    for case in cases_by_tag(suite, "semantic_future"):
        result = probe_next_action_contract(case)
        if result["contract_parse_success"]:
            pass_count += 1
    assert pass_count >= 4


def test_semantic_unknown_action_passes_contract_but_expected_reject() -> None:
    suite = _load_suite()
    case = next(c for c in suite.cases if c.case_id == "semantic_unknown_action")
    result = probe_next_action_contract(case)
    assert result["contract_parse_success"] is True
    assert case.expected.should_accept is False


def test_semantic_missing_required_parameter_passes_contract_but_expected_reject() -> None:
    suite = _load_suite()
    case = next(
        c for c in suite.cases if c.case_id == "semantic_missing_required_parameter"
    )
    result = probe_next_action_contract(case)
    assert result["contract_parse_success"] is True
    assert case.expected.should_accept is False


def test_semantic_forbidden_path_passes_contract_but_expected_reject() -> None:
    suite = _load_suite()
    case = next(c for c in suite.cases if c.case_id == "semantic_forbidden_path_model_file")
    result = probe_next_action_contract(case)
    assert result["contract_parse_success"] is True
    assert case.expected.should_accept is False


def test_duplicate_case_ids_rejected() -> None:
    suite = _load_suite().model_dump()
    suite["cases"].append(dict(suite["cases"][0]))
    with pytest.raises(ValidationError):
        ActionValidationCaseSuite.model_validate(suite)


def test_duplicate_tags_in_one_case_rejected() -> None:
    case = {
        "case_id": "c1",
        "title": "t",
        "description": "d",
        "model_output_text": '{"action":"read_file","parameters":{},"reason":"r","expected_result":"e"}',
        "expected": {
            "should_accept": True,
            "rejection_layer": "not_applicable",
            "failure_category": "none",
            "reason": "ok",
        },
        "tags": ["x", "x"],
    }
    with pytest.raises(ValidationError):
        ActionValidationTestCase.model_validate(case)


def test_invalid_expected_outcome_combinations_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionValidationExpectedOutcome(
            should_accept=True,
            rejection_layer="not_applicable",
            failure_category="unknown_action",
            reason="bad combo",
        )

    with pytest.raises(ValidationError):
        ActionValidationExpectedOutcome(
            should_accept=False,
            rejection_layer="not_applicable",
            failure_category="unknown_action",
            reason="bad combo",
        )


def test_model_output_text_cannot_be_empty() -> None:
    case = {
        "case_id": "c2",
        "title": "t",
        "description": "d",
        "model_output_text": " ",
        "expected": {
            "should_accept": True,
            "rejection_layer": "not_applicable",
            "failure_category": "none",
            "reason": "ok",
        },
    }
    with pytest.raises(ValidationError):
        ActionValidationTestCase.model_validate(case)
