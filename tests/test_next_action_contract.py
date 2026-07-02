from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_contract import (
    NextActionJSONError,
    NextActionValidationError,
    parse_next_action_text,
)
from agent.schemas import NextAction


def test_parse_next_action_text_accepts_valid_object() -> None:
    text = (
        '{"action":"read_file","parameters":{"path":"docs/ai/model_registry.md"},'
        '"reason":"Need model registry context.","expected_result":"File read completes."}'
    )
    result = parse_next_action_text(text)
    assert isinstance(result, NextAction)
    assert result.action == "read_file"


def test_parse_next_action_text_rejects_invalid_json() -> None:
    with pytest.raises(NextActionJSONError):
        parse_next_action_text("{bad-json}")


def test_parse_next_action_text_rejects_non_object_json() -> None:
    with pytest.raises(NextActionValidationError):
        parse_next_action_text('["not","an","object"]')


def test_parse_next_action_text_rejects_markdown_fenced_json() -> None:
    fenced = '```json\n{"action":"read_file","parameters":{},"reason":"r","expected_result":"e"}\n```'
    with pytest.raises(NextActionJSONError):
        parse_next_action_text(fenced)


def test_parse_next_action_text_rejects_empty_required_fields() -> None:
    with pytest.raises(NextActionValidationError):
        parse_next_action_text(
            '{"action":"   ","parameters":{},"reason":"ok","expected_result":"ok"}'
        )


def test_parse_next_action_text_rejects_extra_fields() -> None:
    with pytest.raises(NextActionValidationError):
        parse_next_action_text(
            '{"action":"read_file","parameters":{},"reason":"ok","expected_result":"ok","extra":"x"}'
        )


def test_next_action_contract_example_json_is_valid() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "configs"
        / "next_action_contract.example.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = NextAction.model_validate(payload)
    assert result.action == "read_file"
