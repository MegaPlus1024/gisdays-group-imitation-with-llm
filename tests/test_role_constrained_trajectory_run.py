from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_selector import ActionSelectionResult
from agent.execution_history import ExecutionHistoryConfig, ExecutionHistoryLogger
from agent.role_constrained_trajectory import (
    RoleConstrainedTrajectoryConfig,
    RoleConstrainedTrajectoryRunner,
    TrajectoryRunResult,
    TrajectoryStepResult,
    load_role_constrained_trajectory_config,
    next_action_repeated,
)
from agent.schemas import NextAction
from agent.script_registry import ScriptValidationIssue, ScriptValidationResult
from agent.state import AgentState, load_agent_state


class FakeSelector:
    def __init__(self, results: list[ActionSelectionResult]) -> None:
        self.results = list(results)
        self.seen_states: list[AgentState] = []

    def select_action(self, state: AgentState) -> ActionSelectionResult:
        self.seen_states.append(state)
        return self.results.pop(0)


def mk_selected(agent_id: str, action: str, params: dict[str, Any] | None = None) -> ActionSelectionResult:
    return ActionSelectionResult(
        selector_id="fake_selector",
        agent_id=agent_id,
        success=True,
        status="selected",
        next_action=NextAction(
            action=action,
            parameters=params or {},
            reason=f"Choose {action}",
            expected_result=f"{action} planned",
        ),
        metadata={},
    )


def mk_selection_failed(agent_id: str, message: str = "selection failed") -> ActionSelectionResult:
    return ActionSelectionResult(
        selector_id="fake_selector",
        agent_id=agent_id,
        success=False,
        status="selection_failed",
        error_type="selection_failed",
        error_message=message,
        metadata={},
    )


def mk_validation_failed(agent_id: str, action: str = "run_shell_command") -> ActionSelectionResult:
    validation = ScriptValidationResult(
        accepted=False,
        action=action,
        issues=[
            ScriptValidationIssue(
                code="forbidden_by_role",
                message="Action forbidden by role constraints.",
                layer="role_constraints",
            )
        ],
    )
    return ActionSelectionResult(
        selector_id="fake_selector",
        agent_id=agent_id,
        success=False,
        status="validation_failed",
        next_action=NextAction(
            action=action,
            parameters={},
            reason="test",
            expected_result="test",
        ),
        validation_result=validation,
        error_type="validation_failed",
        error_message="validation failed: forbidden_by_role",
    )


def example_state() -> AgentState:
    return load_agent_state("configs/agent_state.example.json")


def test_role_constrained_trajectory_config_defaults_valid() -> None:
    cfg = RoleConstrainedTrajectoryConfig()
    assert cfg.max_steps == 3
    assert cfg.trajectory_id == "role_constrained_trajectory_v1"


def test_load_role_constrained_trajectory_config_loads_example() -> None:
    cfg = load_role_constrained_trajectory_config(
        "configs/role_constrained_trajectory.example.json"
    )
    assert cfg.trajectory_id == "role_constrained_trajectory_v1"


def test_trajectory_step_result_failure_requires_error_fields() -> None:
    with pytest.raises(ValidationError):
        TrajectoryStepResult(
            trajectory_id="t1",
            run_id="r1",
            agent_id="a1",
            step_index=1,
            status="selection_failed",
            success=False,
        )


def test_trajectory_run_result_selected_actions_returns_names() -> None:
    state = example_state()
    selector = FakeSelector(
        [
            mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"}),
            mk_selected(state.agent_id, "create_file", {"path": "docs/b.md", "content": "x"}),
            mk_selected(state.agent_id, "read_file", {"path": "docs/c.md"}),
        ]
    )
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector, config=RoleConstrainedTrajectoryConfig(max_steps=3)
    )
    result = runner.run_trajectory(state, "run1")
    assert result.selected_actions() == ["read_file", "create_file", "read_file"]


def test_next_action_repeated_detects_exact_repeat() -> None:
    n1 = NextAction(action="read_file", parameters={"path": "a"}, reason="r", expected_result="e")
    n2 = NextAction(action="read_file", parameters={"path": "a"}, reason="r2", expected_result="e2")
    assert next_action_repeated(n2, [n1]) is True


def test_runner_completes_three_step_trajectory() -> None:
    state = example_state()
    selector = FakeSelector(
        [
            mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"}),
            mk_selected(state.agent_id, "create_file", {"path": "docs/b.md", "content": "x"}),
            mk_selected(state.agent_id, "run_shell_command", {"command": "dir"}),
        ]
    )
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector, config=RoleConstrainedTrajectoryConfig(max_steps=3)
    )
    result = runner.run_trajectory(state, "run1")
    assert result.status == "completed"
    assert result.success is True
    assert result.successful_steps_count() == 3


def test_runner_updates_copied_state_history_and_not_original() -> None:
    state = example_state()
    original_history_len = len(state.history)
    selector = FakeSelector(
        [
            mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"}),
            mk_selected(state.agent_id, "create_file", {"path": "docs/b.md", "content": "x"}),
            mk_selected(state.agent_id, "run_shell_command", {"command": "dir"}),
        ]
    )
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector, config=RoleConstrainedTrajectoryConfig(max_steps=3)
    )
    result = runner.run_trajectory(state, "run1")
    assert len(state.history) == original_history_len
    assert result.final_state is not None
    assert len(result.final_state.history) == original_history_len + 3


def test_selector_second_and_third_calls_see_updated_history_lengths() -> None:
    state = example_state()
    selector = FakeSelector(
        [
            mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"}),
            mk_selected(state.agent_id, "create_file", {"path": "docs/b.md", "content": "x"}),
            mk_selected(state.agent_id, "run_shell_command", {"command": "dir"}),
        ]
    )
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector, config=RoleConstrainedTrajectoryConfig(max_steps=3)
    )
    _ = runner.run_trajectory(state, "run1")
    base = len(state.history)
    assert len(selector.seen_states[1].history) == base + 1
    assert len(selector.seen_states[2].history) == base + 2


def test_runner_stops_on_selection_failed_when_configured() -> None:
    state = example_state()
    selector = FakeSelector([mk_selection_failed(state.agent_id)])
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector,
        config=RoleConstrainedTrajectoryConfig(
            max_steps=3, stop_on_selection_failure=True
        ),
    )
    result = runner.run_trajectory(state, "run1")
    assert result.status == "stopped_on_selection_failure"
    assert result.success is False


def test_runner_stops_on_validation_failed_when_configured() -> None:
    state = example_state()
    selector = FakeSelector([mk_validation_failed(state.agent_id)])
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector,
        config=RoleConstrainedTrajectoryConfig(
            max_steps=3, stop_on_validation_failure=True
        ),
    )
    result = runner.run_trajectory(state, "run1")
    assert result.status == "stopped_on_validation_failure"
    assert result.success is False


def test_runner_stops_on_repeated_action_detected() -> None:
    state = example_state()
    selector = FakeSelector(
        [
            mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"}),
            mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"}),
        ]
    )
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector,
        config=RoleConstrainedTrajectoryConfig(max_steps=3, stop_on_repeated_action=True),
    )
    result = runner.run_trajectory(state, "run1")
    assert result.status == "stopped_on_repeated_action"
    assert result.success is False


def test_runner_can_load_role_template_from_config_path() -> None:
    state = example_state()
    selector = FakeSelector([mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"})])
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector,
        config=RoleConstrainedTrajectoryConfig(max_steps=1, role_template_path="configs/roles/office_worker.example.json"),
    )
    assert runner.role_template is not None


def test_runner_does_not_execute_script_helpers() -> None:
    state = example_state()
    selector = FakeSelector([mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"})])
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector, config=RoleConstrainedTrajectoryConfig(max_steps=1)
    )
    result = runner.run_trajectory(state, "run1")
    assert result.steps[0].status == "selected"


def test_no_logs_written_when_write_history_logs_false(tmp_path: Path) -> None:
    state = example_state()
    selector = FakeSelector([mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"})])
    logger = ExecutionHistoryLogger(
        config=ExecutionHistoryConfig(create_parent_dirs=True),
        log_root=tmp_path / "logs",
    )
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector,
        config=RoleConstrainedTrajectoryConfig(max_steps=1, write_history_logs=False),
        history_logger=logger,
    )
    _ = runner.run_trajectory(state, "run1")
    assert not logger.history_path.exists()
    assert not logger.error_path.exists()


def test_logs_written_when_enabled_without_execution(tmp_path: Path) -> None:
    state = example_state()
    selector = FakeSelector(
        [
            mk_selected(state.agent_id, "read_file", {"path": "docs/a.md"}),
            mk_selection_failed(state.agent_id, "boom"),
        ]
    )
    logger = ExecutionHistoryLogger(
        config=ExecutionHistoryConfig(create_parent_dirs=True),
        log_root=tmp_path / "logs",
    )
    runner = RoleConstrainedTrajectoryRunner(
        selector=selector,
        config=RoleConstrainedTrajectoryConfig(
            max_steps=2,
            write_history_logs=True,
            stop_on_selection_failure=True,
        ),
        history_logger=logger,
    )
    result = runner.run_trajectory(state, "run1")
    assert result.status == "stopped_on_selection_failure"
    assert logger.history_path.exists()
    lines = logger.read_history()
    assert len(lines) >= 1
