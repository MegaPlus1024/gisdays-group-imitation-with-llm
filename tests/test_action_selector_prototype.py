from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_contract import parse_next_action_text
from agent.action_selector import (
    ActionSelectionResult,
    ActionSelector,
    ActionSelectorConfig,
    load_action_selector_config,
)
from agent.script_registry import load_script_registry
from agent.state import AgentState, load_agent_state


class FakeClientReturnAction:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def generate_next_action(self, agent_state: dict[str, Any]) -> Any:
        return self.payload


class FakeClientRaises:
    def generate_next_action(self, agent_state: dict[str, Any]) -> Any:
        raise RuntimeError("fake client failure")


def _state() -> AgentState:
    return load_agent_state("configs/agent_state.example.json")


def _registry():
    return load_script_registry("configs/script_registry.example.json")


def _fixture_action(filename: str) -> dict[str, Any]:
    path = Path("tests/fixtures/registry/next_actions") / filename
    return json.loads(path.read_text(encoding="utf-8"))


def test_action_selector_config_defaults_are_valid() -> None:
    cfg = ActionSelectorConfig()
    assert cfg.selector_id == "action_selector_v1"
    assert cfg.validate_actions is True


def test_load_action_selector_config_loads_example() -> None:
    cfg = load_action_selector_config("configs/action_selector.example.json")
    assert cfg.selector_id == "action_selector_v1"
    assert cfg.registry_path == "configs/script_registry.example.json"


def test_action_selection_result_success_requires_next_action() -> None:
    with pytest.raises(ValidationError):
        ActionSelectionResult(
            selector_id="x",
            agent_id="a",
            success=True,
            status="selected",
        )


def test_action_selection_result_failure_requires_error_fields() -> None:
    with pytest.raises(ValidationError):
        ActionSelectionResult(
            selector_id="x",
            agent_id="a",
            success=False,
            status="selection_failed",
        )


def test_select_action_returns_selected_for_valid_read_file_next_action() -> None:
    action_payload = _fixture_action("valid_read_file.json")
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(action_payload),
        registry=_registry(),
    )
    result = selector.select_action(_state())
    assert result.success is True
    assert result.status == "selected"
    assert result.validation_result is not None
    assert result.validation_result.accepted is True


def test_select_action_returns_validation_failed_for_unknown_action() -> None:
    action_payload = _fixture_action("invalid_unknown_action.json")
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(action_payload),
        registry=_registry(),
    )
    result = selector.select_action(_state())
    assert result.success is False
    assert result.status == "validation_failed"
    assert result.validation_result is not None


def test_select_action_returns_validation_failed_for_forbidden_path() -> None:
    action_payload = _fixture_action("invalid_forbidden_path.json")
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(action_payload),
        registry=_registry(),
    )
    result = selector.select_action(_state())
    assert result.success is False
    assert result.status == "validation_failed"
    assert result.validation_result is not None


def test_select_action_returns_selection_failed_when_client_raises() -> None:
    selector = ActionSelector(llm_client=FakeClientRaises(), registry=_registry())
    result = selector.select_action(_state())
    assert result.success is False
    assert result.status == "selection_failed"
    assert result.error_type == "RuntimeError"


def test_select_action_does_not_mutate_agent_state_history() -> None:
    state = _state()
    before = [entry.model_dump() for entry in state.history]
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(_fixture_action("valid_read_file.json")),
        registry=_registry(),
    )
    _ = selector.select_action(state)
    after = [entry.model_dump() for entry in state.history]
    assert before == after


def test_validate_actions_false_skips_validation_for_unknown_but_well_formed_action() -> None:
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(
            {
                "action_name": "unknown_action_name",
                "parameters": {},
            }
        ),
        config=ActionSelectorConfig(validate_actions=False),
        registry=None,
    )
    result = selector.select_action(_state())
    assert result.success is True
    assert result.status == "validation_skipped"


def test_require_validation_for_success_false_can_return_success_with_warning() -> None:
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(_fixture_action("invalid_unknown_action.json")),
        config=ActionSelectorConfig(require_validation_for_success=False),
        registry=_registry(),
    )
    result = selector.select_action(_state())
    assert result.success is True
    assert result.status == "selected"
    assert result.validation_result is not None
    assert result.validation_result.accepted is False
    assert "validation_warning" in result.metadata


def test_missing_registry_when_validation_required_returns_registry_missing() -> None:
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(_fixture_action("valid_read_file.json")),
        config=ActionSelectorConfig(validate_actions=True, registry_path=None),
        registry=None,
    )
    result = selector.select_action(_state())
    assert result.success is False
    assert result.status == "validation_failed"
    assert result.error_type == "registry_missing"


def test_selector_uses_provided_registry_instead_of_loading_path() -> None:
    selector = ActionSelector(
        llm_client=FakeClientReturnAction(_fixture_action("valid_read_file.json")),
        config=ActionSelectorConfig(registry_path="configs/does_not_exist.json"),
        registry=_registry(),
    )
    result = selector.select_action(_state())
    assert result.success is True
    assert result.status == "selected"
