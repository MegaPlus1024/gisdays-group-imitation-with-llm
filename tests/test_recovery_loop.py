from __future__ import annotations

from src.agent.action_selector import ActionSelectionResult
from src.agent.recovery import (
    FailureEvent,
    RecoveryPolicy,
    RecoveryPolicyConfig,
    RecoveryPolicyRule,
)
from src.agent.recovery_loop import (
    RecoveryLoopConfig,
    RecoveryLoopHarness,
    RecoveryLoopResult,
    failure_event_from_bridge_result,
    failure_event_from_selection_result,
    load_recovery_loop_config,
)
from src.agent.schemas import NextAction
from src.agent.script_execution_bridge import ScriptExecutionBridgeOutput
from src.agent.script_registry import ScriptValidationIssue, ScriptValidationResult
from src.agent.script_runner_errors import NormalizedScriptError, NormalizedScriptResult
from src.agent.state import load_agent_state
from src.agent.scripts.results import ScriptExecutionResult


class FakeSelector:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def select_action(self, state):
        self.calls += 1
        return self.results.pop(0)


class FakeBridge:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0
        self.seen_actions = []

    def execute_next_action(self, next_action, run_id=None, agent_id=None, step_index=None):
        self.calls += 1
        self.seen_actions.append(next_action)
        return self.results.pop(0)


def _selection_success() -> ActionSelectionResult:
    return ActionSelectionResult(
        selector_id="selector",
        agent_id="student_researcher_001",
        success=True,
        status="selected",
        next_action=NextAction(
            action="read_file",
            parameters={"path": "docs/ai/runtime_path_v1.md"},
            reason="Need context.",
            expected_result="Read file content.",
        ),
    )


def _selection_failed(error_type: str, error_message: str) -> ActionSelectionResult:
    return ActionSelectionResult(
        selector_id="selector",
        agent_id="student_researcher_001",
        success=False,
        status="selection_failed",
        error_type=error_type,
        error_message=error_message,
    )


def _selection_validation_failed(issue_code: str) -> ActionSelectionResult:
    validation = ScriptValidationResult(
        accepted=False,
        action="read_file",
        issues=[ScriptValidationIssue(code=issue_code, message="x", layer="safety_policy")],
        metadata={},
    )
    return ActionSelectionResult(
        selector_id="selector",
        agent_id="student_researcher_001",
        success=False,
        status="validation_failed",
        next_action=NextAction(
            action="read_file",
            parameters={"path": "docs/x.md"},
            reason="r",
            expected_result="e",
        ),
        validation_result=validation,
        error_type="validation_failed",
        error_message="validation failed",
    )


def _bridge_success() -> ScriptExecutionBridgeOutput:
    raw = ScriptExecutionResult(action="read_file", success=True, output="ok")
    normalized = NormalizedScriptResult(action="read_file", success=True, output="ok")
    return ScriptExecutionBridgeOutput(
        action="read_file",
        success=True,
        dispatched=True,
        validation_passed=True,
        raw_result=raw,
        normalized_result=normalized,
    )


def _bridge_failed_with_recovery_category(category: str) -> ScriptExecutionBridgeOutput:
    raw = ScriptExecutionResult(
        action="run_shell_command",
        success=False,
        error_type="command_failed",
        error_message="failed",
    )
    error = NormalizedScriptError(
        category="command_failed",
        message="failed",
        recovery_category=category,
    )
    normalized = NormalizedScriptResult(
        action="run_shell_command", success=False, error=error
    )
    return ScriptExecutionBridgeOutput(
        action="run_shell_command",
        success=False,
        dispatched=True,
        validation_passed=True,
        raw_result=raw,
        normalized_result=normalized,
    )


def _bridge_validation_failed(issue_code: str) -> ScriptExecutionBridgeOutput:
    validation = ScriptValidationResult(
        accepted=False,
        action="read_file",
        issues=[ScriptValidationIssue(code=issue_code, message="x", layer="script_registry")],
        metadata={},
    )
    raw = ScriptExecutionResult(
        action="read_file",
        success=False,
        error_type="validation_failed",
        error_message="invalid",
    )
    return ScriptExecutionBridgeOutput(
        action="read_file",
        success=False,
        dispatched=False,
        validation_passed=False,
        validation_result=validation,
        raw_result=raw,
    )


def _custom_policy(category: str, action: str) -> RecoveryPolicy:
    log_level = "warning"
    if action == "abort_run":
        log_level = "critical"
    elif action == "skip_agent":
        log_level = "error"
    cfg = RecoveryPolicyConfig(
        policy_id="x",
        rules=[
            RecoveryPolicyRule(
                category=category,
                action=action,  # type: ignore[arg-type]
                reason="forced",
                log_level=log_level,  # type: ignore[arg-type]
                stop_run=(action == "abort_run"),
                stop_agent=(action == "skip_agent"),
            )
        ],
        default_action="fail_step",
        default_log_level="error",
    )
    return RecoveryPolicy(cfg)


def test_recovery_loop_config_defaults_are_valid() -> None:
    cfg = RecoveryLoopConfig()
    assert cfg.loop_id == "recovery_loop_v1"
    assert cfg.max_attempts == 2


def test_load_recovery_loop_config() -> None:
    cfg = load_recovery_loop_config("configs/recovery_loop.example.json")
    assert cfg.loop_id == "recovery_loop_v1"


def test_recovery_loop_result_counts() -> None:
    res = RecoveryLoopResult.model_validate(
        {
            "loop_id": "x",
            "success": True,
            "status": "recovered_after_retry",
            "attempts": [
                {"loop_id": "x", "attempt_index": 1, "status": "selection_failed", "success": False, "error_type": "e", "error_message": "m"},
                {"loop_id": "x", "attempt_index": 2, "status": "bridge_succeeded", "success": True},
            ],
        }
    )
    assert res.attempt_count() == 2
    assert res.retry_count() == 1


def test_failure_event_from_selection_maps_invalid_json() -> None:
    event = failure_event_from_selection_result(_selection_failed("JSONDecodeError", "bad json"))
    assert event.category == "invalid_json"


def test_failure_event_from_selection_maps_unsafe_action() -> None:
    event = failure_event_from_selection_result(_selection_validation_failed("unsafe_action"))
    assert event.category == "unsafe_action"


def test_failure_event_from_bridge_maps_unknown_action_issue() -> None:
    event = failure_event_from_bridge_result(_bridge_validation_failed("unknown_action"))
    assert event.category == "unknown_action"


def test_failure_event_from_bridge_maps_execution_error_category() -> None:
    event = failure_event_from_bridge_result(_bridge_failed_with_recovery_category("execution_error"))
    assert event.category == "execution_error"


def test_run_once_succeeds_without_recovery() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_success()])
    bridge = FakeBridge([_bridge_success()])
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge)
    result = harness.run_once_with_recovery(state)
    assert result.success is True
    assert result.status == "succeeded_without_recovery"


def test_run_once_recovers_after_retry() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector(
        [
            _selection_failed("JSONDecodeError", "invalid json"),
            _selection_success(),
        ]
    )
    bridge = FakeBridge([_bridge_success()])
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge)
    result = harness.run_once_with_recovery(state)
    assert result.success is True
    assert result.status == "recovered_after_retry"
    assert selector.calls == 2


def test_retry_budget_exhausted() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector(
        [
            _selection_failed("JSONDecodeError", "invalid json"),
            _selection_failed("JSONDecodeError", "invalid json"),
        ]
    )
    bridge = FakeBridge([])
    harness = RecoveryLoopHarness(
        selector=selector, bridge=bridge, config=RecoveryLoopConfig(max_attempts=2)
    )
    result = harness.run_once_with_recovery(state)
    assert result.success is False
    assert result.status == "retry_budget_exhausted"


def test_fail_step_for_unsafe_action() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_validation_failed("unsafe_action")])
    bridge = FakeBridge([])
    policy = _custom_policy("unsafe_action", "fail_step")
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge, recovery_policy=policy)
    result = harness.run_once_with_recovery(state)
    assert result.status == "failed_step"


def test_aborted_run_status() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_failed("ConnError", "server unreachable")])
    bridge = FakeBridge([])
    policy = _custom_policy("malformed_model_response", "abort_run")
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge, recovery_policy=policy)
    result = harness.run_once_with_recovery(state)
    assert result.status == "aborted_run"


def test_skipped_agent_status() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_failed("x", "x")])
    bridge = FakeBridge([])
    policy = _custom_policy("malformed_model_response", "skip_agent")
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge, recovery_policy=policy)
    result = harness.run_once_with_recovery(state)
    assert result.status == "skipped_agent"


def test_mark_for_review_status() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_failed("x", "x")])
    bridge = FakeBridge([])
    policy = _custom_policy("malformed_model_response", "mark_for_review")
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge, recovery_policy=policy)
    result = harness.run_once_with_recovery(state)
    assert result.status == "marked_for_review"


def test_enable_retry_false_skips_second_call() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_failed("JSONDecodeError", "invalid json")])
    bridge = FakeBridge([])
    harness = RecoveryLoopHarness(
        selector=selector,
        bridge=bridge,
        config=RecoveryLoopConfig(enable_retry=False, max_attempts=2),
    )
    result = harness.run_once_with_recovery(state)
    assert result.success is False
    assert selector.calls == 1


def test_bridge_not_called_when_selection_fails() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_failed("x", "x")])
    bridge = FakeBridge([])
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge)
    harness.run_once_with_recovery(state)
    assert bridge.calls == 0


def test_bridge_called_after_successful_selection() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    selector = FakeSelector([_selection_success()])
    bridge = FakeBridge([_bridge_success()])
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge)
    harness.run_once_with_recovery(state)
    assert bridge.calls == 1


def test_agent_state_not_mutated() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    before = state.model_dump()
    selector = FakeSelector([_selection_success()])
    bridge = FakeBridge([_bridge_success()])
    harness = RecoveryLoopHarness(selector=selector, bridge=bridge)
    harness.run_once_with_recovery(state)
    assert state.model_dump() == before
