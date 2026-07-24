from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_selector import ActionSelectionResult
from agent.history_aware_selection import (
    HistoryAwareSecondActionRunner,
    HistoryAwareSelectionConfig,
    actions_exactly_equal,
    build_state_with_history_entry,
    load_history_aware_selection_config,
    next_action_to_history_entry,
)
from agent.schemas import NextAction
from agent.state import load_agent_state


class FakeSelector:
    def __init__(self, results: list[ActionSelectionResult]) -> None:
        self.results = list(results)
        self.seen_states = []

    def select_action(self, state: Any) -> ActionSelectionResult:
        self.seen_states.append(state)
        return self.results.pop(0)


def _state():
    return load_agent_state("configs/agent_state.example.json")


def _success_result(action: str, params: dict[str, Any], status: str = "selected") -> ActionSelectionResult:
    return ActionSelectionResult(
        selector_id="selector_v1",
        agent_id="student_researcher_001",
        success=True,
        status=status,  # type: ignore[arg-type]
        next_action=NextAction(
            action_name=action,
            parameters=params,
        ),
    )


def _failure_result(status: str, error_type: str = "selection_failed") -> ActionSelectionResult:
    payload: dict[str, Any] = {
        "selector_id": "selector_v1",
        "agent_id": "student_researcher_001",
        "success": False,
        "status": status,  # type: ignore[arg-type]
        "error_type": error_type,
        "error_message": f"{status} message",
    }
    if status == "validation_failed":
        payload["validation_result"] = {
            "accepted": False,
            "action": "read_file",
            "issues": [
                {
                    "code": "schema_validation_failed",
                    "message": "schema validation failed",
                    "layer": "script_registry",
                }
            ],
            "metadata": {},
        }
    return ActionSelectionResult(
        **payload
    )


def test_history_aware_selection_config_defaults_valid() -> None:
    cfg = HistoryAwareSelectionConfig()
    assert cfg.config_id == "history_aware_second_action_v1"
    assert cfg.second_step_index == 2


def test_load_history_aware_selection_config() -> None:
    cfg = load_history_aware_selection_config(
        "configs/history_aware_second_action.example.json"
    )
    assert cfg.config_id == "history_aware_second_action_v1"


def test_next_action_to_history_entry_fields() -> None:
    action = NextAction(
        action_name="read_file",
        parameters={"path": "docs/ai/runtime_path_v1.md"},
    )
    entry = next_action_to_history_entry(action, step_index=2)
    assert entry.step == 2
    assert entry.action == "read_file"
    assert entry.parameters == {"path": "docs/ai/runtime_path_v1.md"}


def test_build_state_with_history_entry_returns_new_state_and_preserves_original() -> None:
    state = _state()
    original_history = copy.deepcopy(state.history)
    action = NextAction(
        action_name="read_file", parameters={"path": "a"}
    )
    entry = next_action_to_history_entry(action, step_index=state.current_step)
    new_state = build_state_with_history_entry(state, entry)
    assert new_state is not state
    assert state.history == original_history
    assert len(new_state.history) == len(original_history) + 1


def test_build_state_with_history_entry_increments_current_step() -> None:
    state = _state()
    action = NextAction(
        action_name="read_file", parameters={"path": "a"}
    )
    entry = next_action_to_history_entry(action, step_index=state.current_step)
    new_state = build_state_with_history_entry(state, entry)
    assert new_state.current_step == state.current_step + 1


def test_actions_exactly_equal_true_for_same_action_and_parameters() -> None:
    a = NextAction(action_name="x", parameters={"p": 1})
    b = NextAction(action_name="x", parameters={"p": 1})
    assert actions_exactly_equal(a, b) is True


def test_actions_exactly_equal_false_for_different_parameters() -> None:
    a = NextAction(action_name="x", parameters={"p": 1})
    b = NextAction(action_name="x", parameters={"p": 2})
    assert actions_exactly_equal(a, b) is False


def test_runner_selects_second_action_successfully() -> None:
    selector = FakeSelector(
        [
            _success_result("read_file", {"path": "a"}),
            _success_result("run_shell_command", {"command": "echo test"}),
        ]
    )
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    result = runner.select_second_action(_state())
    assert result.success is True
    assert result.status == "second_action_selected"
    assert result.second_selection is not None


def test_second_selector_call_state_contains_first_action_in_history() -> None:
    selector = FakeSelector(
        [
            _success_result("read_file", {"path": "a"}),
            _success_result("run_shell_command", {"command": "echo test"}),
        ]
    )
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    _ = runner.select_second_action(_state())
    assert len(selector.seen_states) == 2
    second_state = selector.seen_states[1]
    assert second_state.history[-1].action == "read_file"


def test_second_selector_call_sees_current_step_2() -> None:
    selector = FakeSelector(
        [
            _success_result("read_file", {"path": "a"}),
            _success_result("run_shell_command", {"command": "echo test"}),
        ]
    )
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    _ = runner.select_second_action(_state())
    assert selector.seen_states[1].current_step == 2


def test_runner_returns_first_action_failed_when_first_fails() -> None:
    selector = FakeSelector([_failure_result("selection_failed")])
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    result = runner.select_second_action(_state())
    assert result.success is False
    assert result.status == "first_action_failed"


def test_runner_returns_second_action_failed_when_second_fails() -> None:
    selector = FakeSelector(
        [
            _success_result("read_file", {"path": "a"}),
            _failure_result("selection_failed"),
        ]
    )
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    result = runner.select_second_action(_state())
    assert result.success is False
    assert result.status == "second_action_failed"


def test_runner_returns_validation_failed_when_second_validation_fails() -> None:
    selector = FakeSelector(
        [
            _success_result("read_file", {"path": "a"}),
            _failure_result("validation_failed", error_type="validation_failed"),
        ]
    )
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    result = runner.select_second_action(_state())
    assert result.success is False
    assert result.status == "validation_failed"


def test_runner_detects_repeated_exact_action() -> None:
    selector = FakeSelector(
        [
            _success_result("read_file", {"path": "a"}),
            _success_result("read_file", {"path": "a"}),
        ]
    )
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    result = runner.select_second_action(_state())
    assert result.success is False
    assert result.status == "repeated_action_detected"
    assert result.repeated_action is True


def test_runner_does_not_mutate_original_state() -> None:
    state = _state()
    before = copy.deepcopy(state.history)
    selector = FakeSelector(
        [
            _success_result("read_file", {"path": "a"}),
            _success_result("run_shell_command", {"command": "echo test"}),
        ]
    )
    runner = HistoryAwareSecondActionRunner(selector=selector)  # type: ignore[arg-type]
    _ = runner.select_second_action(state)
    assert state.history == before
