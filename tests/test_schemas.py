from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.schemas import NextAction


def test_next_action_accepts_valid_minimal_data() -> None:
    action = NextAction(
        action="open_app",
        reason="Need to launch the target application.",
        expected_result="The application window is visible.",
    )

    assert action.action == "open_app"
    assert action.reason == "Need to launch the target application."
    assert action.expected_result == "The application window is visible."


def test_parameters_defaults_to_empty_dict() -> None:
    action = NextAction(
        action="open_app",
        reason="Need to launch the target application.",
        expected_result="The application window is visible.",
    )

    assert action.parameters == {}


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("action", ""),
        ("reason", ""),
        ("expected_result", ""),
    ],
)
def test_empty_required_text_fields_are_rejected(field_name: str, value: str) -> None:
    payload = {
        "action": "open_app",
        "parameters": {},
        "reason": "Need to launch the target application.",
        "expected_result": "The application window is visible.",
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        NextAction(**payload)
