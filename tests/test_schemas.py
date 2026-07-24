from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.schemas import NextAction


def test_next_action_accepts_valid_minimal_data() -> None:
    action = NextAction(
        action_name="open_app",
    )

    assert action.action_name == "open_app"
    assert action.action == "open_app"
    assert action.reason == ""
    assert action.expected_result == ""


def test_parameters_defaults_to_empty_dict() -> None:
    action = NextAction(
        action_name="open_app",
    )

    assert action.parameters == {}


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("action_name", ""),
    ],
)
def test_empty_required_text_fields_are_rejected(field_name: str, value: str) -> None:
    payload = {
        "action_name": "open_app",
        "parameters": {},
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        NextAction(**payload)


def test_legacy_action_wire_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NextAction.model_validate({"action": "open_app", "parameters": {}})


def test_reason_and_expected_result_are_rejected_as_wire_fields() -> None:
    with pytest.raises(ValidationError):
        NextAction.model_validate(
            {
                "action_name": "open_app",
                "parameters": {},
                "reason": "legacy",
                "expected_result": "legacy",
            }
        )
