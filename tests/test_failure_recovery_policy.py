from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_contract import NextActionJSONError, NextActionValidationError
from agent.llm_client import (
    LocalLLMJSONError,
    LocalLLMRequestError,
    LocalLLMResponseError,
    LocalLLMValidationError,
)
from agent.recovery import (
    FailureEvent,
    RecoveryDecision,
    RecoveryPolicy,
    RecoveryPolicyConfig,
    RecoveryPolicyRule,
    default_recovery_policy,
    failure_event_from_exception,
    load_recovery_policy,
)


def test_default_policy_contains_all_required_categories() -> None:
    required = {
        "invalid_json",
        "invalid_next_action_schema",
        "malformed_model_response",
        "model_request_error",
        "model_timeout",
        "llama_server_unreachable",
        "empty_model_output",
        "unknown_action",
        "invalid_action_parameters",
        "unsafe_action",
        "execution_error",
        "file_not_found",
        "permission_denied",
        "repeated_action_loop",
        "max_steps_exceeded",
        "unknown_error",
    }
    cfg = default_recovery_policy()
    found = {r.category for r in cfg.rules}
    assert found == required


def test_duplicate_categories_in_config_rejected() -> None:
    with pytest.raises(ValidationError):
        RecoveryPolicyConfig(
            policy_id="x",
            rules=[
                RecoveryPolicyRule(category="invalid_json", action="fail_step", reason="a"),
                RecoveryPolicyRule(category="invalid_json", action="fail_step", reason="b"),
            ],
        )


def test_invalid_json_maps_to_retry_with_repair_prompt() -> None:
    policy = RecoveryPolicy()
    event = FailureEvent(category="invalid_json", source="x", message="bad")
    decision = policy.decide(event)
    assert decision.action == "retry_with_repair_prompt"
    assert decision.max_retries == 1


def test_invalid_next_action_schema_maps_to_fail_step() -> None:
    decision = RecoveryPolicy().decide(
        FailureEvent(category="invalid_next_action_schema", source="x", message="bad")
    )
    assert decision.action == "fail_step"


def test_llama_server_unreachable_maps_to_abort_run() -> None:
    decision = RecoveryPolicy().decide(
        FailureEvent(category="llama_server_unreachable", source="x", message="down")
    )
    assert decision.action == "abort_run"
    assert decision.stop_run is True


def test_permission_denied_maps_to_skip_agent() -> None:
    decision = RecoveryPolicy().decide(
        FailureEvent(category="permission_denied", source="x", message="denied")
    )
    assert decision.action == "skip_agent"
    assert decision.stop_agent is True


def test_repeated_action_loop_maps_to_skip_agent() -> None:
    decision = RecoveryPolicy().decide(
        FailureEvent(category="repeated_action_loop", source="x", message="loop")
    )
    assert decision.action == "skip_agent"


def test_unknown_error_maps_to_mark_for_review() -> None:
    decision = RecoveryPolicy().decide(
        FailureEvent(category="unknown_error", source="x", message="err")
    )
    assert decision.action == "mark_for_review"


def test_retry_budget_exhausted_converts_to_fail_step() -> None:
    policy = RecoveryPolicy()
    event = FailureEvent(
        category="invalid_json", source="x", message="bad", retry_count=1
    )
    decision = policy.decide(event)
    assert decision.action == "fail_step"
    assert "Retry budget exhausted" in decision.reason


def test_failure_event_rejects_empty_source() -> None:
    with pytest.raises(ValidationError):
        FailureEvent(category="unknown_error", source="", message="x")


def test_failure_event_rejects_empty_message() -> None:
    with pytest.raises(ValidationError):
        FailureEvent(category="unknown_error", source="x", message="")


def test_failure_event_rejects_negative_retry_count() -> None:
    with pytest.raises(ValidationError):
        FailureEvent(category="unknown_error", source="x", message="m", retry_count=-1)


def test_recovery_decision_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        RecoveryDecision(action="fail_step", reason="")


def test_load_recovery_policy_loads_example_config() -> None:
    cfg = load_recovery_policy("configs/failure_recovery_policy.example.json")
    assert cfg.policy_id == "failure_recovery_policy_v1"
    assert len(cfg.rules) > 0


def test_decide_does_not_mutate_input_event() -> None:
    event = FailureEvent(
        category="invalid_json",
        source="LocalLLMClient",
        message="bad",
        retry_count=0,
    )
    before = event.model_dump()
    _ = RecoveryPolicy().decide(event)
    after = event.model_dump()
    assert before == after


def test_failure_event_from_exception_known_mappings() -> None:
    e1 = failure_event_from_exception(LocalLLMRequestError("connection refused"), "x")
    assert e1.category == "llama_server_unreachable"

    e2 = failure_event_from_exception(LocalLLMResponseError("missing content"), "x")
    assert e2.category == "malformed_model_response"

    e3 = failure_event_from_exception(LocalLLMJSONError("bad json"), "x")
    assert e3.category == "invalid_json"

    e4 = failure_event_from_exception(LocalLLMValidationError("bad schema"), "x")
    assert e4.category == "invalid_next_action_schema"

    e5 = failure_event_from_exception(NextActionJSONError("bad json"), "x")
    assert e5.category == "invalid_json"

    e6 = failure_event_from_exception(NextActionValidationError("bad schema"), "x")
    assert e6.category == "invalid_next_action_schema"
