from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from src.agent import llm_client
from src.agent.autonomous_multi_agent_runtime import (
    Action,
    EarlyStopFakePolicy,
    AgentProfile,
    AgentState,
    HistoryEvent,
    LocalOpenAIModelPolicy,
    Observation,
    PolicyError,
    PerfectFakePolicy,
    RuntimeLimits,
    ToolResult,
    ToolSpec,
)
from src.agent.canonical_multi_agent_experiments import (
    CONFIG_SCHEMA_VERSION,
    EXPERIMENT_SUMMARY_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
    TRIAL_SUMMARY_SCHEMA_VERSION,
    _bounded_value,
    _run_runtime_with_trace,
    _trial_metrics,
    build_long_horizon_trial_runtime,
    load_long_horizon_experiment_config,
    percentile,
    run_long_horizon_experiment,
    run_long_horizon_trial,
)
from src.agent.prompt_contract import PromptBuilder
from src.agent.schemas import NextAction


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    PROJECT_ROOT
    / "configs"
    / "canonical_multi_agent_long_horizon.example.json"
)


@pytest.fixture
def artifact_output_dir() -> str:
    relative = (
        "artifacts/canonical_multi_agent_long_horizon/"
        f"pytest_{uuid.uuid4().hex}"
    )
    try:
        yield relative
    finally:
        shutil.rmtree(PROJECT_ROOT / relative, ignore_errors=True)


def _run_trial(
    scenario_id: str,
    output_dir: str,
    *,
    policy_variant: str = "perfect",
    trial_index: int = 1,
) -> dict[str, object]:
    return run_long_horizon_trial(
        experiment_id="pytest_long_horizon",
        scenario_id=scenario_id,
        trial_index=trial_index,
        model_id="fake_policy",
        output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=24,
        policy_variant=policy_variant,  # type: ignore[arg-type]
    )


def _load_trace(summary: dict[str, object]) -> list[dict[str, object]]:
    relative = summary["group_trace_path"]
    assert isinstance(relative, str)
    return [
        json.loads(line)
        for line in (PROJECT_ROOT / relative).read_text(encoding="utf-8").splitlines()
    ]


def _install_fake_openai_response(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    class FakeHTTPClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def post(self, url: str, json: dict[str, object]):  # type: ignore[no-untyped-def]
            del json
            return llm_client.httpx.Response(
                200,
                json=payload,
                request=llm_client.httpx.Request("POST", url),
            )

    monkeypatch.setattr(llm_client.httpx, "Client", FakeHTTPClient)


def _openai_chat_payload(
    content: str,
    *,
    usage: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "chatcmpl-canonical-test",
        "model": "first_model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


def _step_until_agent_history(
    runtime,
    agent_id: str,
    history_len: int,
    *,
    max_steps: int = 12,
):  # type: ignore[no-untyped-def]
    result = None
    for _ in range(max_steps):
        if runtime.status != "running":
            break
        result = runtime.step()
        if len(runtime.states[agent_id].history) >= history_len:
            return result
    return result


def test_example_config_loads_with_safe_defaults() -> None:
    config = load_long_horizon_experiment_config(CONFIG_PATH)

    assert config.experiment_id == "canonical_multi_agent_long_horizon_v1"
    assert config.scenario_ids == (
        "article_file_handoff",
        "office_shared_fact_recovery",
    )
    assert config.trials_per_scenario == 3
    assert config.scheduler == "round_robin"
    assert config.fixture_only is True
    assert config.model_execution is False
    assert config.agents == {
        "source": "canonical_scenario_definitions",
        "minimum_agents": 2,
    }
    assert config.output_dir.startswith("artifacts/")
    assert json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["schema_version"] == (
        CONFIG_SCHEMA_VERSION
    )


def test_article_contract_advertises_exact_url_without_fixture_values() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="contract",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/contract",
        project_root=PROJECT_ROOT,
    )
    runtime.step()
    state = runtime.states["research_agent"]
    resources = state.memory["available_resources"]
    assert resources["article_urls"] == ["https://fixture.local/articles/long-horizon"]
    assert "office worker" not in json.dumps(resources)
    assert state.memory["task_progress"]["terminal_allowed"] is False


def test_finish_is_rejected_until_declared_requirements_are_met() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="finish_guard",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/finish_guard",
        project_root=PROJECT_ROOT,
    )
    runtime.policies["research_agent"] = PerfectFakePolicy((Action("finish"),))
    result = runtime.step()
    assert result.observation is not None
    assert result.observation.error_code == "completion_requirements_unmet"
    assert runtime.states["research_agent"].status == "ready"


def test_wait_for_dependency_is_non_mutating_and_available_to_consumer() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="wait",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/wait",
        project_root=PROJECT_ROOT,
    )
    runtime.policies["research_agent"] = PerfectFakePolicy((Action("browser_article_open", {"url": "https://fixture.local/articles/long-horizon"}),))
    runtime.policies["operator_agent"] = PerfectFakePolicy((Action("wait_for_dependency", {"dependency_id": "review_owner"}),))
    runtime.step()
    result = runtime.step()
    assert result.observation is not None and result.observation.success is True
    assert runtime.shared_environment.facts == {}
    assert result.action is not None and result.action.tool_name == "wait_for_dependency"


def test_percentile_uses_deterministic_stdlib_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile([], 95) == 0.0
    assert percentile(values, 50) == 25.0
    assert percentile(values, 95) == 38.5
    with pytest.raises(ValueError, match="between 0 and 100"):
        percentile(values, 101)


def test_trial_runtime_reuses_canonical_domain_scheduler_and_registry() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="trial_001",
        trial_output_dir=(
            "artifacts/canonical_multi_agent_long_horizon/pytest_runtime"
        ),
        project_root=PROJECT_ROOT,
    )

    assert len(runtime.states) == 2
    assert all(isinstance(state, AgentState) for state in runtime.states.values())
    assert runtime.tool_registry.get("read_file") is not None
    assert runtime.tool_registry.get("office_fixture_read") is not None
    assert runtime.tool_registry.get("browser_click") is None


def test_article_file_handoff_is_long_and_round_robin(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("article_file_handoff", artifact_output_dir)
    trace = _load_trace(summary)

    assert summary["status"] == "succeeded"
    assert summary["schema_version"] == TRIAL_SUMMARY_SCHEMA_VERSION
    assert summary["trial_metrics"]["total_turns"] == 16  # type: ignore[index]
    assert len(trace) == 16
    assert [event["agent_id"] for event in trace[:8]] == [
        "research_agent",
        "operator_agent",
    ] * 4


def test_article_file_handoff_uses_file_and_explicit_shared_fact(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("article_file_handoff", artifact_output_dir)
    trace = _load_trace(summary)

    action_names = [event["action_name"] for event in trace]
    assert "create_file" in action_names
    assert "read_file" in action_names
    assert "shared_publish_fact" in action_names
    assert "shared_read_fact" in action_names
    assert summary["trial_metrics"]["shared_operations"] == 2  # type: ignore[index]


def test_article_note_resource_state_updates_after_creation(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/article_retry_state"
    note_path = f"{output_dir}/research_note.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="article_retry_state",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=8,
    )
    runtime.policies["research_agent"] = PerfectFakePolicy(
        (
            Action("browser_article_open", {"url": "https://fixture.local/articles/long-horizon"}),
            Action("create_file", {"path": note_path, "content": "Owner: office worker\n"}),
        )
    )
    runtime.policies["operator_agent"] = PerfectFakePolicy(
        (
            Action("read_file", {"path": note_path}),
            Action("finish"),
            Action("read_file", {"path": note_path}),
        )
    )

    runtime.step()
    failed = runtime.step()
    assert failed.observation is not None
    assert failed.observation.error_code == "file_not_found"
    operator = runtime.states["operator_agent"]
    before = {
        item["resource_id"]: item
        for item in operator.memory["available_resources"]["file_resources"]
    }["research_note_txt"]
    assert before["exists"] is False
    assert before["last_failure_error_code"] == "file_not_found"
    assert before["state_changed_since_failure"] is False
    assert before["unchanged_retry_discouraged"] is True
    assert before["retry_now_valid"] is False

    runtime.step()
    after_create = {
        item["resource_id"]: item
        for item in operator.memory["available_resources"]["file_resources"]
    }["research_note_txt"]
    assert after_create["exists"] is True
    assert after_create["readable"] is True
    assert after_create["last_failure_error_code"] == "file_not_found"
    assert after_create["state_changed_since_failure"] is True
    assert after_create["unchanged_retry_discouraged"] is False
    assert after_create["retry_now_valid"] is True

    rejected_finish = runtime.step()
    assert rejected_finish.observation is not None
    assert rejected_finish.observation.error_code == "completion_requirements_unmet"
    unmet = rejected_finish.observation.metadata["unmet_requirement_contracts"]
    note_requirement = next(
        item for item in unmet if item["requirement_id"] == "research_note_read"
    )
    assert note_requirement["related_resource_ids"] == ["research_note_txt"]
    assert note_requirement["resource_state"]["exists"] is True
    assert note_requirement["resource_state"]["state_changed_since_failure"] is True
    assert note_requirement["resource_state"]["retry_now_valid"] is True

    _step_until_agent_history(runtime, "operator_agent", 3)
    progress = runtime.states["operator_agent"].memory["task_progress"]
    assert "research_note_read" in progress["completed_requirements"]
    assert progress["unchanged_failed_actions"] == []


def test_article_note_resource_transition_and_retry_metrics(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/article_retry_metrics"
    note_path = f"{output_dir}/research_note.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="article_retry_metrics",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=8,
    )
    runtime.policies["research_agent"] = PerfectFakePolicy(
        (
            Action("browser_article_open", {"url": "https://fixture.local/articles/long-horizon"}),
            Action("create_file", {"path": note_path, "content": "Owner: office worker\n"}),
        )
    )
    runtime.policies["operator_agent"] = PerfectFakePolicy(
        (
            Action("read_file", {"path": note_path}),
            Action("read_file", {"path": note_path}),
        )
    )
    trace = _run_runtime_with_trace(runtime, started_at=time.perf_counter())
    create_event = next(
        event
        for event in trace
        if event["agent_id"] == "research_agent"
        and event["action_name"] == "create_file"
    )
    retry_event = next(
        event
        for event in trace
        if event["agent_id"] == "operator_agent"
        and event["action_name"] == "read_file"
        and event["tool_status"] == "succeeded"
    )
    assert create_event["resource_status_changes"] == [
        {
            "resource_id": "research_note_txt",
            "path": note_path,
            "previous_exists": False,
            "current_exists": True,
            "producer_agent": "research_agent",
            "event_index": 2,
            "dependencies_unblocked": ["research_note"],
        }
    ]
    assert retry_event["retry_after_resource_state_change"] is True
    assert retry_event["successful_retry_after_resource_state_change"] is True
    metrics = _trial_metrics(runtime, trace, started_at=time.perf_counter())
    assert metrics["resource_state_transitions"] == 1
    assert metrics["retries_after_resource_state_change"] == 1
    assert metrics["successful_retries_after_resource_state_change"] == 1
    assert metrics["generic_recovery_attempts"] == 1
    assert metrics["generic_recovery_successes"] == 1
    assert metrics["unchanged_failed_action_retries"] == 0
    assert runtime.shared_environment.resource_transitions == [
        {
            "resource_id": "research_note_txt",
            "path": note_path,
            "previous_exists": False,
            "current_exists": True,
            "producer_agent": "research_agent",
            "event_index": 2,
            "dependencies_unblocked": ["research_note"],
        }
    ]
    operator = runtime.states["operator_agent"]
    assert "research_note_read" in operator.memory["task_progress"]["completed_requirements"]
    assert operator.memory["task_progress"]["unchanged_failed_actions"] == []


def test_unrelated_read_file_does_not_satisfy_resource_bound_requirement() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="unrelated_read",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/unrelated_read",
        project_root=PROJECT_ROOT,
    )
    operator = runtime.states["operator_agent"]
    runtime.shared_environment.known_files.add(
        "tests/fixtures/canonical_multi_agent/recovery_note.txt"
    )
    operator.history.append(
        # A successful read_file event with the wrong path must not satisfy the
        # research_note_txt-bound requirement.
        HistoryEvent(
            turn_index=1,
            agent_id="operator_agent",
            action=Action(
                "read_file",
                {"path": "tests/fixtures/canonical_multi_agent/recovery_note.txt"},
            ),
            observation=Observation(
                success=True,
                tool_name="read_file",
                output="Recovery note",
            ),
        )
    )
    runtime._refresh_agent_context(operator)

    assert "research_note_read" not in operator.memory["task_progress"]["completed_requirements"]


def test_each_agent_history_is_independent() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="trial_001",
        trial_output_dir=(
            "artifacts/canonical_multi_agent_long_horizon/pytest_histories"
        ),
        project_root=PROJECT_ROOT,
    )
    runtime.run()

    for agent_id, state in runtime.states.items():
        assert state.history
        assert {event.agent_id for event in state.history} == {agent_id}
        other_ids = set(runtime.states) - {agent_id}
        assert all(event.agent_id not in other_ids for event in state.history)


def test_office_recovery_receives_error_on_next_own_turn(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("office_shared_fact_recovery", artifact_output_dir)
    trace = _load_trace(summary)
    verifier_events = [
        event for event in trace if event["agent_id"] == "verification_agent"
    ]

    assert verifier_events[0]["tool_error_code"] == "file_not_found"
    assert verifier_events[1]["action_name"] == "read_file"
    assert verifier_events[1]["tool_status"] == "succeeded"
    assert verifier_events[1]["recovery_from_event_index"] == (
        verifier_events[0]["event_index"]
    )


def test_office_recovery_metrics_and_shared_validation_succeed(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("office_shared_fact_recovery", artifact_output_dir)
    verification = summary["agent_metrics"]["verification_agent"]  # type: ignore[index]

    assert summary["status"] == "succeeded"
    assert verification["failed_tools"] == 1
    assert verification["recovery_attempts"] == 1
    assert verification["recovery_successes"] == 1
    assert verification["generic_recovery_attempts"] == 1
    assert verification["generic_recovery_successes"] == 1
    assert verification["required_recoveries_total"] == 1
    assert verification["required_recoveries_completed"] == 1
    assert verification["required_recovery_success_rate"] == 1.0
    assert verification["input_tokens_total"] == 0
    assert verification["output_tokens_total"] == 0
    assert "constrained_fixture_command" in verification["unique_action_names"]
    assert summary["trial_metrics"]["generic_recovery_attempts"] == 1  # type: ignore[index]
    assert summary["trial_metrics"]["generic_recovery_successes"] == 1  # type: ignore[index]
    assert summary["trial_metrics"]["required_recoveries_total"] == 1  # type: ignore[index]
    assert summary["trial_metrics"]["required_recoveries_completed"] == 1  # type: ignore[index]
    assert summary["trial_metrics"]["recovery_success_rate"] == 1.0  # type: ignore[index]
    assert summary["trial_metrics"]["required_recovery_success_rate"] == 1.0  # type: ignore[index]


def test_office_recovery_requirement_contracts_and_file_resources_are_visible() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="contracts",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/contracts",
        project_root=PROJECT_ROOT,
    )
    runtime.step()
    verifier = runtime.states["verification_agent"]
    runtime._refresh_agent_context(verifier)

    progress = verifier.memory["task_progress"]
    contracts = {
        item["requirement_id"]: item for item in progress["requirement_contracts"]
    }
    recovery_contract = contracts["recovery_completed"]
    assert recovery_contract["description"].startswith(
        "After the expected missing-file error"
    )
    assert recovery_contract["evidence_type"] == "successful_recovery_action"
    assert recovery_contract["related_resource_ids"] == [
        "missing_input",
        "recovery_note",
    ]
    assert "office worker" not in json.dumps(progress)

    resources = {
        item["resource_id"]: item
        for item in verifier.memory["available_resources"]["file_resources"]
    }
    assert resources["missing_input"]["exists"] is False
    assert resources["missing_input"]["purpose"] == (
        "expected recoverable failure source"
    )
    assert resources["recovery_note"]["exists"] is True
    assert resources["recovery_note"]["readable"] is True
    assert "Recovery note" not in json.dumps(resources)


def test_successful_office_read_creates_agent_scoped_observed_evidence() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="evidence_scope",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/evidence_scope",
        project_root=PROJECT_ROOT,
    )
    runtime.step()
    document = runtime.states["document_agent"]
    verifier = runtime.states["verification_agent"]

    evidence = {
        item["source_field"]: item for item in document.memory["observed_evidence"]
    }
    assert {"owner", "version", "status"} <= set(evidence)
    assert evidence["owner"]["evidence_id"] == "ev_document_agent_0_owner"
    assert evidence["owner"]["source_tool"] == "office_fixture_read"
    assert evidence["owner"]["source_event_index"] == 0
    assert evidence["owner"]["agent_id"] == "document_agent"
    assert "owner" not in json.dumps(verifier.memory.get("observed_evidence", []))


def test_unobserved_field_has_no_evidence_until_read() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="unobserved",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/unobserved",
        project_root=PROJECT_ROOT,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy(
        (Action("office_fixture_read", {"field": "version"}),)
    )
    runtime.step()
    evidence_fields = {
        item["source_field"]
        for item in runtime.states["document_agent"].memory["observed_evidence"]
    }

    assert evidence_fields == {"version"}
    assert "owner" not in evidence_fields
    publishable = runtime.states["document_agent"].memory["available_resources"][
        "publishable_facts"
    ]
    owner = next(item for item in publishable if item["key"] == "review_owner")
    version = next(item for item in publishable if item["key"] == "review_version")
    assert owner["candidate_evidence_ids"] == []
    assert version["candidate_evidence_ids"] == ["ev_document_agent_0_version"]


def test_grounded_publish_validation_failure_modes() -> None:
    cases = [
        (
            "without_evidence",
            (
                Action("office_fixture_read", {"field": "owner"}),
                Action(
                    "shared_publish_fact",
                    {"key": "review_owner", "value": "office worker"},
                ),
            ),
            "evidence_id_required",
        ),
        (
            "unknown_evidence",
            (
                Action("office_fixture_read", {"field": "owner"}),
                Action(
                    "shared_publish_fact",
                    {
                        "key": "review_owner",
                        "value": "office worker",
                        "evidence_id": "missing_evidence",
                    },
                ),
            ),
            "evidence_not_found",
        ),
        (
            "wrong_source",
            (
                Action("office_fixture_read", {"field": "version"}),
                Action(
                    "shared_publish_fact",
                    {
                        "key": "review_owner",
                        "value": "v3.2",
                        "evidence_id": "ev_document_agent_0_version",
                    },
                ),
            ),
            "evidence_source_mismatch",
        ),
        (
            "mismatched_value",
            (
                Action("office_fixture_read", {"field": "owner"}),
                Action(
                    "shared_publish_fact",
                    {
                        "key": "review_owner",
                        "value": "john_doe",
                        "evidence_id": "ev_document_agent_0_owner",
                    },
                ),
            ),
            "published_value_mismatch",
        ),
    ]
    for trial_id, steps, expected_error in cases:
        runtime = build_long_horizon_trial_runtime(
            scenario_id="office_shared_fact_recovery",
            trial_id=trial_id,
            trial_output_dir=f"artifacts/canonical_multi_agent_long_horizon/{trial_id}",
            project_root=PROJECT_ROOT,
        )
        runtime.policies["document_agent"] = PerfectFakePolicy(steps)
        _step_until_agent_history(runtime, "document_agent", 1)
        result = _step_until_agent_history(runtime, "document_agent", 2)

        assert result.observation is not None
        assert result.observation.error_code == expected_error
        assert "review_owner" not in runtime.shared_environment.facts
        assert result.observation.metadata["grounding_valid"] is False


def test_shared_read_fact_retry_after_publish_in_canonical_round_robin() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="shared_fact_retry_after_publish",
        trial_output_dir=(
            "artifacts/canonical_multi_agent_long_horizon/"
            "shared_fact_retry_after_publish"
        ),
        project_root=PROJECT_ROOT,
        max_turns=12,
    )
    runtime.limits = RuntimeLimits(
        max_turns_total=12,
        max_turns_per_agent=8,
        max_failures_per_agent=6,
        max_identical_actions=2,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy(
        (
            Action("office_fixture_read", {"field": "version"}),
            Action("office_fixture_read", {"field": "owner"}),
            Action(
                "shared_publish_fact",
                {
                    "key": "review_owner",
                    "value": "office worker",
                    "evidence_id": "ev_document_agent_1_owner",
                },
            ),
        )
    )
    runtime.policies["verification_agent"] = PerfectFakePolicy(
        (
            Action("shared_read_fact", {"key": "review_owner"}),
            Action("shared_read_fact", {"key": "review_owner"}),
            Action("shared_read_fact", {"key": "review_owner"}),
        )
    )

    _step_until_agent_history(runtime, "verification_agent", 3)

    verifier = runtime.states["verification_agent"]
    observations = [event.observation for event in verifier.history]
    assert [item.error_code for item in observations[:2]] == [
        "shared_fact_not_found",
        "shared_fact_not_found",
    ]
    assert observations[2].success is True
    assert observations[2].error_code is None
    assert verifier.stop_reason != "repetition_guard"
    assert verifier._same_action_count == 1
    assert "review_owner_read" in verifier.memory["task_progress"][
        "completed_requirements"
    ]

    publish_index = next(
        index
        for index, event in enumerate(runtime.group_history)
        if event.agent_id == "document_agent"
        and event.action is not None
        and event.action.tool_name == "shared_publish_fact"
    )
    read_index = next(
        index
        for index, event in enumerate(
            runtime.group_history[publish_index + 1 :],
            start=publish_index + 1,
        )
        if event.agent_id == "verification_agent"
        and event.action is not None
        and event.action.tool_name == "shared_read_fact"
        and event.observation.success is True
    )
    assert read_index == publish_index + 1


def test_other_agent_evidence_is_rejected() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="other_agent_evidence",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/other_agent_evidence",
        project_root=PROJECT_ROOT,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy(
        (
            Action("office_fixture_read", {"field": "owner"}),
            Action(
                "shared_publish_fact",
                {
                    "key": "review_owner",
                    "value": "office worker",
                    "evidence_id": "ev_verification_agent_0_owner",
                },
            ),
        )
    )
    _step_until_agent_history(runtime, "document_agent", 1)
    doc = runtime.states["document_agent"]
    foreign = dict(doc.memory["observed_evidence"][0])
    foreign["agent_id"] = "verification_agent"
    foreign["evidence_id"] = "ev_verification_agent_0_owner"
    doc.memory["observed_evidence"].append(foreign)
    result = _step_until_agent_history(runtime, "document_agent", 2)

    assert result.observation is not None
    assert result.observation.error_code == "evidence_not_owned"


def test_grounded_publish_allows_trimmed_value_and_rejects_alias() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="trimmed_grounding",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/trimmed_grounding",
        project_root=PROJECT_ROOT,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy(
        (
            Action("office_fixture_read", {"field": "owner"}),
            Action(
                "shared_publish_fact",
                {
                    "key": "review_owner",
                    "value": "  office   worker\n",
                    "evidence_id": "ev_document_agent_0_owner",
                },
            ),
        )
    )
    _step_until_agent_history(runtime, "document_agent", 1)
    success = _step_until_agent_history(runtime, "document_agent", 2)

    assert success.observation is not None and success.observation.success is True
    assert runtime.shared_environment.shared_fact_metadata["review_owner"][
        "grounding_status"
    ] == "grounded"

    alias_runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="alias_grounding",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/alias_grounding",
        project_root=PROJECT_ROOT,
    )
    alias_runtime.policies["document_agent"] = PerfectFakePolicy(
        (
            Action("office_fixture_read", {"field": "owner"}),
            Action(
                "shared_publish_fact",
                {
                    "key": "review_owner",
                    "value": "john_doe",
                    "evidence_id": "ev_document_agent_0_owner",
                },
            ),
        )
    )
    _step_until_agent_history(alias_runtime, "document_agent", 1)
    failed = _step_until_agent_history(alias_runtime, "document_agent", 2)

    assert failed.observation is not None
    assert failed.observation.error_code == "published_value_mismatch"


def test_published_value_mismatch_recovery_metadata_reaches_next_model_prompt() -> None:
    class CapturingClient:
        base_url = "http://127.0.0.1:8082/v1"
        last_usage: dict[str, int] = {}
        last_diagnostics: dict[str, object] = {}
        last_usage_diagnostics: dict[str, object] = {}

        def __init__(self) -> None:
            self.states: list[dict[str, object]] = []
            self.messages: list[list[dict[str, str]]] = []
            self.actions = [
                NextAction(
                    action_name="browser_article_open",
                    parameters={"url": "https://fixture.local/articles/long-horizon"},
                ),
                NextAction(action_name="browser_article_read", parameters={}),
                NextAction(
                    action_name="browser_article_scroll",
                    parameters={"pages": 1},
                ),
                NextAction(
                    action_name="browser_article_extract",
                    parameters={"heading": "Ownership"},
                ),
                NextAction(
                    action_name="shared_publish_fact",
                    parameters={
                        "key": "review_owner",
                        "value": "office worker",
                        "evidence_id": "ev_research_agent_3_Ownership",
                    },
                ),
                NextAction(action_name="finish", parameters={}),
            ]

        def generate_next_action(self, agent_state):  # type: ignore[no-untyped-def]
            self.states.append(agent_state)
            self.messages.append(PromptBuilder().build_messages(agent_state))
            index = min(len(self.states) - 1, len(self.actions) - 1)
            return self.actions[index]

    client = CapturingClient()
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="grounding_prompt_recovery",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/grounding_prompt_recovery",
        project_root=PROJECT_ROOT,
        max_turns=16,
        policy_variant="perfect",
    )
    runtime.policies["research_agent"] = LocalOpenAIModelPolicy(  # type: ignore[arg-type]
        client=client,
        allow_model_calls=True,
        disable_thinking=True,
        response_max_tokens=256,
        temperature=0.0,
    )

    _step_until_agent_history(runtime, "research_agent", 5)
    mismatch = runtime.states["research_agent"].history[-1].observation
    assert mismatch.error_code == "published_value_mismatch"
    _step_until_agent_history(runtime, "research_agent", 6)

    next_state = client.states[-1]
    next_messages = client.messages[-1]
    prompt_text = json.dumps(next_messages, ensure_ascii=False)
    recovery = next_state["last_observation"]["metadata"]["grounding_recovery"]  # type: ignore[index]

    assert recovery == {
        "evidence_id": "ev_research_agent_3_Ownership",
        "fact_key": "review_owner",
        "source_tool": "browser_article_extract",
        "source_field": "Ownership",
        "exact_evidence_value": "The assigned owner is office worker.",
        "attempted_value": "office worker",
        "instruction": (
            "Use this exact evidence value for the selected evidence_id; "
            "do not shorten, extract, summarize, or paraphrase it."
        ),
    }
    assert "The assigned owner is office worker." in prompt_text
    assert "do not shorten, extract, summarize, or paraphrase" in prompt_text
    assert "office worker" in prompt_text
    assert "api_key" not in prompt_text.casefold()
    assert "authorization" not in prompt_text.casefold()
    assert "raw_response" not in prompt_text.casefold()


def test_grounded_fact_storage_inventory_and_finish_guard() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="grounded_storage",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/grounded_storage",
        project_root=PROJECT_ROOT,
        max_turns=12,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy(
        (
            Action("office_fixture_read", {"field": "version"}),
            Action(
                "shared_publish_fact",
                {
                    "key": "review_version",
                    "value": "v3.2",
                    "evidence_id": "ev_document_agent_0_version",
                },
            ),
            Action("finish"),
        )
    )
    _step_until_agent_history(runtime, "document_agent", 2)
    _step_until_agent_history(runtime, "document_agent", 3)

    metadata = runtime.shared_environment.shared_fact_metadata["review_version"]
    assert metadata["evidence_id"] == "ev_document_agent_0_version"
    assert metadata["evidence_source_tool"] == "office_fixture_read"
    assert metadata["evidence_source_field"] == "version"
    assert metadata["grounding_status"] == "grounded"
    document_progress = runtime.states["document_agent"].memory["task_progress"]
    assert "version_published" in document_progress["completed_requirements"]
    assert "owner_published" in document_progress["unmet_requirements"]
    finish_event = next(
        event
        for event in runtime.states["document_agent"].history
        if event.action is not None and event.action.tool_name == "finish"
    )
    assert finish_event.observation.error_code == "completion_requirements_unmet"
    unmet = finish_event.observation.metadata["unmet_requirement_contracts"]
    assert any(item["grounding_required"] is True for item in unmet)

    runtime.step()
    verifier_resources = runtime.states["verification_agent"].memory[
        "available_resources"
    ]
    version_inventory = next(
        item
        for item in verifier_resources["shared_fact_inventory"]
        if item["key"] == "review_version"
    )
    assert version_inventory["grounded"] is True


def test_article_review_owner_requires_article_derived_evidence(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("article_file_handoff", artifact_output_dir)

    assert summary["status"] == "succeeded"
    research = summary["agent_metrics"]["research_agent"]  # type: ignore[index]
    assert research["grounded_shared_facts"] == 1
    assert research["grounded_fact_requirement_completed"] == 1


def test_hallucinated_owner_status_fake_policy_fails_semantically(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial(
        "office_shared_fact_recovery",
        artifact_output_dir,
        policy_variant="publish_with_mismatched_value",
    )

    assert summary["status"] == "failed"
    document = summary["agent_metrics"]["document_agent"]  # type: ignore[index]
    assert document["value_mismatch_attempts"] == 1
    assert document["grounded_fact_requirement_completed"] == 0


def test_trace_contains_provenance_fields_for_grounded_publish(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("office_shared_fact_recovery", artifact_output_dir)
    trace = _load_trace(summary)
    publish = next(
        event
        for event in trace
        if event["action_name"] == "shared_publish_fact"
        and event["agent_id"] == "document_agent"
    )

    assert publish["selected_evidence_id"] == "ev_document_agent_0_owner"
    assert publish["evidence_source_tool"] == "office_fixture_read"
    assert publish["evidence_source_field"] == "owner"
    assert publish["grounding_required"] is True
    assert publish["grounding_valid"] is True
    assert publish["normalized_value_match"] is True


def test_failed_resource_records_error_and_discourages_unchanged_retry() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="resource_error",
        trial_output_dir="artifacts/canonical_multi_agent_long_horizon/resource_error",
        project_root=PROJECT_ROOT,
    )
    runtime.step()
    result = runtime.step()

    assert result.observation is not None
    assert result.observation.error_code == "file_not_found"
    verifier = runtime.states["verification_agent"]
    resources = {
        item["resource_id"]: item
        for item in verifier.memory["available_resources"]["file_resources"]
    }
    missing = resources["missing_input"]
    assert missing["last_error_code"] == "file_not_found"
    assert missing["unchanged_retry_discouraged"] is True
    assert verifier.memory["task_progress"]["unchanged_failed_actions"] == [
        {
            "action_name": "read_file",
            "path": (
                "artifacts/canonical_multi_agent_long_horizon/"
                "resource_error/missing_input.txt"
            ),
            "last_error_code": "file_not_found",
            "last_attempt_history_index": 0,
            "unchanged_retry_discouraged": True,
        }
    ]


def test_wait_fact_read_and_validation_do_not_satisfy_required_file_recovery() -> None:
    output_dir = "artifacts/canonical_multi_agent_long_horizon/no_file_recovery"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="no_file_recovery",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=10,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy(
        (
            Action("office_fixture_read", {"field": "owner"}),
            Action(
                "shared_publish_fact",
                {
                    "key": "review_owner",
                    "value": "office worker",
                    "evidence_id": "ev_document_agent_0_owner",
                },
            ),
            Action("finish"),
        )
    )
    runtime.policies["verification_agent"] = PerfectFakePolicy(
        (
            Action("read_file", {"path": f"{output_dir}/missing_input.txt"}),
            Action("wait_for_dependency", {"dependency_id": "review_owner"}),
            Action("shared_read_fact", {"key": "review_owner"}),
            Action(
                "constrained_fixture_command",
                {
                    "operation": "validate_shared_fact",
                    "key": "review_owner",
                    "expected": "office worker",
                },
            ),
            Action("finish"),
        )
    )

    for _ in range(10):
        if runtime.status != "running":
            break
        runtime.step()

    verifier_progress = runtime.states["verification_agent"].memory["task_progress"]
    assert "recovery_completed" not in verifier_progress["completed_requirements"]
    assert "recovery_completed" in verifier_progress["unmet_requirements"]
    finish_event = next(
        event
        for event in runtime.states["verification_agent"].history
        if event.action is not None and event.action.tool_name == "finish"
    )
    assert finish_event.action is not None
    assert finish_event.action.tool_name == "finish"
    assert finish_event.observation.error_code == "completion_requirements_unmet"
    unmet = finish_event.observation.metadata["unmet_requirement_contracts"]
    assert unmet[0]["requirement_id"] == "recovery_completed"
    assert "successful" in unmet[0]["evidence_type"]
    assert any(
        item["resource_id"] == "recovery_note"
        for item in finish_event.observation.metadata["related_available_resources"]
    )


def test_requirement_advancing_missing_file_failure_does_not_trigger_failure_limit() -> None:
    output_dir = "artifacts/canonical_multi_agent_long_horizon/progress_failure_limit"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="progress_failure_limit",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=12,
    )
    runtime.limits = RuntimeLimits(
        max_turns_total=12,
        max_turns_per_agent=8,
        max_failures_per_agent=3,
        max_identical_actions=2,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy((Action("finish"),))
    runtime.policies["verification_agent"] = PerfectFakePolicy(
        (
            Action("finish"),
            Action("office_fixture_read", {"field": "owner"}),
            Action("read_file", {"path": f"{output_dir}/missing_input.txt"}),
            Action(
                "read_file",
                {"path": "tests/fixtures/canonical_multi_agent/recovery_note.txt"},
            ),
        )
    )

    _step_until_agent_history(runtime, "verification_agent", 1)
    _step_until_agent_history(runtime, "verification_agent", 2)
    expected_failure = _step_until_agent_history(runtime, "verification_agent", 3)

    verifier = runtime.states["verification_agent"]
    assert expected_failure.observation is not None
    assert expected_failure.observation.success is False
    assert expected_failure.observation.error_code == "file_not_found"
    assert verifier.status == "ready"
    assert verifier.stop_reason is None
    assert verifier.actions_failed == 3
    assert verifier.non_progress_failure_streak == 0
    assert "recoverable_error_seen" in verifier.memory["task_progress"]["completed_requirements"]

    recovery = _step_until_agent_history(runtime, "verification_agent", 4)

    assert recovery.observation is not None
    assert recovery.observation.success is True
    assert verifier.status == "ready"
    assert verifier.actions_failed == 3
    assert verifier.recovered_failures == 1
    assert verifier.non_progress_failure_streak == 0
    assert "recovery_completed" in verifier.memory["task_progress"]["completed_requirements"]


def test_repeated_expected_missing_file_after_progress_counts_toward_failure_limit() -> None:
    output_dir = "artifacts/canonical_multi_agent_long_horizon/repeated_expected_error"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="office_shared_fact_recovery",
        trial_id="repeated_expected_error",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=12,
    )
    runtime.limits = RuntimeLimits(
        max_turns_total=12,
        max_turns_per_agent=8,
        max_failures_per_agent=2,
        max_identical_actions=4,
    )
    runtime.policies["document_agent"] = PerfectFakePolicy((Action("finish"),))
    runtime.policies["verification_agent"] = PerfectFakePolicy(
        (
            Action("read_file", {"path": f"{output_dir}/missing_input.txt"}),
            Action("read_file", {"path": f"{output_dir}/missing_input.txt"}),
            Action("read_file", {"path": f"{output_dir}/missing_input.txt"}),
        )
    )

    first = _step_until_agent_history(runtime, "verification_agent", 1)
    second = _step_until_agent_history(runtime, "verification_agent", 2)

    verifier = runtime.states["verification_agent"]
    assert first.observation is not None
    assert first.observation.error_code == "file_not_found"
    assert "recoverable_error_seen" in verifier.memory["task_progress"]["completed_requirements"]
    assert verifier.actions_failed == 2
    assert verifier.non_progress_failure_streak == 1
    assert verifier.status == "ready"

    third = _step_until_agent_history(runtime, "verification_agent", 3)

    assert second.observation is not None
    assert second.observation.error_code == "file_not_found"
    assert third.observation is not None
    assert third.observation.error_code == "file_not_found"
    assert verifier.actions_failed == 3
    assert verifier.non_progress_failure_streak == 2
    assert verifier.status == "quarantined"
    assert verifier.stop_reason == "failure_limit"


def test_recovery_note_read_satisfies_required_recovery_and_records_evidence(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("office_shared_fact_recovery", artifact_output_dir)
    trace = _load_trace(summary)
    verifier_events = [
        event for event in trace if event["agent_id"] == "verification_agent"
    ]
    recovery_event = verifier_events[1]

    assert recovery_event["action_name"] == "read_file"
    assert recovery_event["tool_status"] == "succeeded"
    assert recovery_event["requirements_advanced"] == ["recovery_completed"]
    evidence = recovery_event["required_recovery_evidence"][0]
    assert evidence["source_failure_event_index"] == 0
    assert evidence["recovery_event_index"] == 1
    assert evidence["source_error_code"] == "file_not_found"
    assert evidence["failed_resource_id"] == "missing_input"
    assert evidence["recovery_resource_id"] == "recovery_note"
    assert evidence["recovery_action_name"] == "read_file"


def test_wait_for_dependency_tracks_producer_progress_before_guard(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/dependency_wait_progress"
    note_path = f"{output_dir}/research_note.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="dependency_wait_progress",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=16,
    )
    runtime.limits = RuntimeLimits(
        max_turns_total=16,
        max_turns_per_agent=8,
        max_failures_per_agent=6,
        max_identical_actions=2,
    )
    runtime.policies["research_agent"] = PerfectFakePolicy(
        (
            Action(
                "browser_article_open",
                {"url": "https://fixture.local/articles/long-horizon"},
            ),
            Action("browser_article_read", {}),
            Action("browser_article_read", {}),
            Action(
                "browser_article_extract",
                {"heading": "Ownership"},
            ),
            Action(
                "browser_article_extract",
                {"heading": "Status"},
            ),
            Action(
                "create_file",
                {
                    "path": note_path,
                    "content": (
                        "Ownership: office worker\n"
                        "Status: Version v3.2 is approved under the "
                        "workspace policy.\n"
                    ),
                },
            ),
        )
    )
    runtime.policies["operator_agent"] = PerfectFakePolicy(
        (
            Action(
                "office_fixture_read",
                {"field": "owner"},
            ),
            Action(
                "read_file",
                {"path": note_path},
            ),
            Action(
                "wait_for_dependency",
                {"dependency_id": "research_note"},
            ),
            Action(
                "wait_for_dependency",
                {"dependency_id": "research_note"},
            ),
            Action(
                "wait_for_dependency",
                {"dependency_id": "research_note"},
            ),
            Action(
                "read_file",
                {"path": note_path},
            ),
        )
    )

    for _ in range(12):
        runtime.step()

    operator = runtime.states["operator_agent"]
    wait_events = [
        event
        for event in operator.history
        if event.action
        and event.action.tool_name == "wait_for_dependency"
    ]

    assert len(wait_events) == 3
    assert all(event.observation.success for event in wait_events)
    assert operator.stop_reason != "repetition_guard"
    assert operator._same_action_count == 1
    assert operator.history[-1].action is not None
    assert operator.history[-1].action.tool_name == "read_file"
    assert operator.history[-1].observation.success is True
    assert "research_note_read" in operator.memory["task_progress"][
        "completed_requirements"
    ]


def test_wait_for_dependency_without_progress_still_triggers_guard(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/dependency_wait_no_progress"
    note_path = f"{output_dir}/research_note.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="dependency_wait_no_progress",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=12,
    )
    runtime.limits = RuntimeLimits(
        max_turns_total=12,
        max_turns_per_agent=8,
        max_failures_per_agent=6,
        max_identical_actions=2,
    )
    runtime.policies["research_agent"] = PerfectFakePolicy(
        (
            Action(
                "browser_article_open",
                {"url": "https://fixture.local/articles/long-horizon"},
            ),
            Action("browser_article_read", {}),
            Action("browser_article_read", {}),
            Action(
                "browser_article_scroll",
                {"pages": 1},
            ),
            Action("browser_article_read", {}),
        )
    )
    runtime.policies["operator_agent"] = PerfectFakePolicy(
        (
            Action(
                "office_fixture_read",
                {"field": "owner"},
            ),
            Action(
                "read_file",
                {"path": note_path},
            ),
            Action(
                "wait_for_dependency",
                {"dependency_id": "research_note"},
            ),
            Action(
                "wait_for_dependency",
                {"dependency_id": "research_note"},
            ),
            Action(
                "wait_for_dependency",
                {"dependency_id": "research_note"},
            ),
        )
    )

    for _ in range(10):
        runtime.step()

    operator = runtime.states["operator_agent"]

    assert operator.stop_reason == "repetition_guard"
    assert operator._same_action_count == 3
    assert operator.history[-1].action is not None
    assert operator.history[-1].action.tool_name == "wait_for_dependency"
    assert operator.history[-1].observation.success is False
    assert (
        operator.history[-1].observation.error_code
        == "repeated_action_detected"
    )


def test_bounded_repetition_guard_stops_repeating_agent() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="bounded_repetition_and_role_guard",
        trial_id="trial_001",
        trial_output_dir=(
            "artifacts/canonical_multi_agent_long_horizon/pytest_repetition"
        ),
        project_root=PROJECT_ROOT,
        policy_variant="repeating",
    )
    summary = runtime.run()

    reader = summary["per_agent"]["reader_agent"]
    assert summary["status"] == "failed"
    assert reader["stop_reason"] == "repetition_guard"
    assert reader["history"][-1]["observation"]["error_code"] == (
        "repeated_action_detected"
    )


def test_role_violation_is_rejected_before_tool_dispatch() -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="bounded_repetition_and_role_guard",
        trial_id="trial_001",
        trial_output_dir=(
            "artifacts/canonical_multi_agent_long_horizon/pytest_role"
        ),
        project_root=PROJECT_ROOT,
        policy_variant="role_violating",
    )
    dispatched = False

    def forbidden_executor(action, context):  # type: ignore[no-untyped-def]
        nonlocal dispatched
        dispatched = True
        return ToolResult(success=True)

    runtime.tool_registry._executors["run_shell_command"] = forbidden_executor
    result = runtime.step()

    assert result.observation is not None
    assert result.observation.error_code == "tool_not_allowed"
    assert dispatched is False


def test_early_stop_policy_is_bounded_and_structured(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial(
        "bounded_repetition_and_role_guard",
        artifact_output_dir,
        policy_variant="early_stop",
    )
    trace = _load_trace(summary)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "trial_not_completed"
    assert len(trace) == 2
    assert all(event["action_name"] is None for event in trace)
    assert all(event["tool_status"] == "skipped" for event in trace)


def test_policy_receives_only_profile_allowed_tool_specs() -> None:
    class CapturingPolicy:
        model_execution_attempted = False

        def __init__(self) -> None:
            self.tool_names: tuple[str, ...] = ()

        def next_action(self, agent_state, observation, allowed_tools):  # type: ignore[no-untyped-def]
            self.tool_names = tuple(spec.name for spec in allowed_tools)
            return None

    policy = CapturingPolicy()
    runtime = build_long_horizon_trial_runtime(
        scenario_id="article_file_handoff",
        trial_id="trial_001",
        trial_output_dir=(
            "artifacts/canonical_multi_agent_long_horizon/pytest_tools"
        ),
        project_root=PROJECT_ROOT,
        policy_overrides={"research_agent": policy},
    )
    runtime.step()

    assert set(policy.tool_names) == set(
        runtime.states["research_agent"].profile.allowed_tools
    )
    assert "office_fixture_read" not in policy.tool_names
    assert "browser_click" not in policy.tool_names


def test_local_policy_prompt_contains_protocol_memory_shared_facts_and_error() -> None:
    class CapturingClient:
        base_url = "http://127.0.0.1:8082/v1"
        last_usage = {"prompt_tokens": 17, "completion_tokens": 5}

        def __init__(self) -> None:
            self.state: dict[str, object] = {}

        def generate_next_action(self, agent_state):  # type: ignore[no-untyped-def]
            self.state = agent_state
            return NextAction(
                action_name="finish",
                parameters={},
            )

    client = CapturingClient()
    policy = LocalOpenAIModelPolicy(  # type: ignore[arg-type]
        client=client,
        allow_model_calls=True,
        disable_thinking=True,
        response_max_tokens=256,
        temperature=0.0,
    )
    profile = AgentProfile(
        agent_id="model_agent",
        role="Fixture verifier",
        goal="Finish after examining state.",
        allowed_tools=("finish",),
    )
    state = AgentState(profile=profile)
    state.memory = {
        "private_note": "retry with corrected input",
        "shared_facts": {"review_owner": "office worker"},
    }
    previous = Observation(
        success=False,
        tool_name="read_file",
        error_code="file_not_found",
        error_message="Bounded fixture file was not found.",
    )

    action = policy.next_action(
        state,
        previous,
        (
            ToolSpec(
                name="finish",
                description="Finish.",
                family="control",
            ),
        ),
    )

    assert action.tool_name == "finish"
    assert client.state["last_observation"]["error_code"] == "file_not_found"  # type: ignore[index]
    assert client.state["memory"]["private_note"] == (  # type: ignore[index]
        "retry with corrected input"
    )
    assert client.state["shared_facts"] == {"review_owner": "office worker"}
    assert client.state["protocol"] == {
        "disable_thinking": True,
        "response_max_tokens": 256,
        "temperature": 0.0,
    }
    assert client.state["action_schema"] == {  # type: ignore[index]
        "action_name": "string",
        "parameters": "object",
    }
    assert "action_name and parameters" in client.state["instruction"]  # type: ignore[operator]
    assert "reason" not in client.state["action_schema"]  # type: ignore[operator]
    assert "expected_result" not in client.state["action_schema"]  # type: ignore[operator]
    assert "do not repeat it unchanged" in client.state["instruction"]  # type: ignore[operator]
    assert policy.last_input_tokens == 17
    assert policy.last_output_tokens == 5


def test_local_policy_requires_explicit_opt_in_without_contacting_client() -> None:
    class RefusingClient:
        base_url = "http://localhost:8082/v1"
        called = False

        def generate_next_action(self, agent_state):  # type: ignore[no-untyped-def]
            self.called = True
            raise AssertionError("client must not be called")

    client = RefusingClient()
    policy = LocalOpenAIModelPolicy(  # type: ignore[arg-type]
        client=client,
        allow_model_calls=False,
    )
    state = AgentState(
        profile=AgentProfile(
            agent_id="safe_agent",
            role="Safe",
            goal="Remain offline.",
            allowed_tools=("finish",),
        )
    )

    with pytest.raises(PolicyError) as exc_info:
        policy.next_action(state, None, ())

    assert exc_info.value.error_code == "allow_model_calls_required"
    assert client.called is False


def test_local_policy_rejects_complete_workflow_array() -> None:
    class WorkflowClient:
        base_url = "http://127.0.0.1:8082/v1"
        last_usage: dict[str, int] = {}

        def generate_next_action(self, agent_state):  # type: ignore[no-untyped-def]
            return {"actions": [{"action": "finish", "parameters": {}}]}

    policy = LocalOpenAIModelPolicy(  # type: ignore[arg-type]
        client=WorkflowClient(),
        allow_model_calls=True,
    )
    state = AgentState(
        profile=AgentProfile(
            agent_id="one_action_agent",
            role="One action",
            goal="Return one action only.",
            allowed_tools=("finish",),
        )
    )

    with pytest.raises(PolicyError) as exc_info:
        policy.next_action(state, None, ())

    assert exc_info.value.error_code == "invalid_model_action"


def test_non_local_model_endpoint_is_rejected_before_contact() -> None:
    class ExternalClient:
        base_url = "https://example.com/v1"
        called = False

        def generate_next_action(self, agent_state):  # type: ignore[no-untyped-def]
            self.called = True
            raise AssertionError("external endpoint must not be contacted")

    client = ExternalClient()
    with pytest.raises(ValueError, match="localhost"):
        LocalOpenAIModelPolicy(  # type: ignore[arg-type]
            client=client,
            allow_model_calls=True,
        )

    assert client.called is False


def test_canonical_group_trace_records_fenced_json_parse_diagnostics_and_usage(
    artifact_output_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = '```json\n{"action_name":"finish","parameters":{}}\n```'
    _install_fake_openai_response(
        monkeypatch,
        _openai_chat_payload(
            content,
            usage={"prompt_tokens": 29, "completion_tokens": 11, "total_tokens": 40},
        ),
    )

    summary = run_long_horizon_trial(
        experiment_id="pytest_canonical_parse_diagnostics",
        scenario_id="article_file_handoff",
        trial_index=1,
        model_id="first_model",
        output_dir=artifact_output_dir,
        project_root=PROJECT_ROOT,
        max_turns=1,
        allow_model_execution=True,
        model_policy_settings={"model_id": "first_model"},
    )
    trace = _load_trace(summary)
    event = trace[0]
    protocol = event["model_protocol"]
    rendered = json.dumps(trace, ensure_ascii=False)

    assert event["tool_error_code"] == "invalid_action_json"
    assert event["input_tokens"] == 29
    assert event["output_tokens"] == 11
    assert summary["trial_metrics"]["input_tokens_total"] == 29
    assert summary["trial_metrics"]["output_tokens_total"] == 11
    assert protocol["content_preview"].startswith("```json\\n")
    assert len(protocol["content_preview"]) <= 512
    assert protocol["content_first_non_whitespace_character"] == "`"
    assert protocol["content_has_markdown_fence"] is True
    assert protocol["content_has_think_tag"] is False
    assert protocol["json_error_line"] == 1
    assert protocol["json_error_column"] == 1
    assert protocol["json_error_position"] == 0
    assert protocol["usage_present"] is True
    assert protocol["usage_prompt_tokens"] == 29
    assert protocol["usage_completion_tokens"] == 11
    assert protocol["usage_total_tokens"] == 40
    assert "usage_keys" not in protocol
    assert "messages" not in rendered
    assert "available_actions" not in rendered
    assert "Return exactly one" not in rendered


def test_canonical_group_trace_records_prose_prefix_without_tolerant_extraction(
    artifact_output_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = 'Sure, here is the action:\n{"action_name":"finish","parameters":{}}'
    _install_fake_openai_response(
        monkeypatch,
        _openai_chat_payload(content, usage={"prompt_tokens": 7, "other": 3}),
    )

    summary = run_long_horizon_trial(
        experiment_id="pytest_canonical_parse_diagnostics",
        scenario_id="article_file_handoff",
        trial_index=1,
        model_id="first_model",
        output_dir=artifact_output_dir,
        project_root=PROJECT_ROOT,
        max_turns=1,
        allow_model_execution=True,
        model_policy_settings={"model_id": "first_model"},
    )
    event = _load_trace(summary)[0]
    protocol = event["model_protocol"]

    assert event["tool_error_code"] == "invalid_action_json"
    assert event["input_tokens"] == 7
    assert event["output_tokens"] is None
    assert protocol["content_preview"].startswith("Sure, here is the action:\\n")
    assert protocol["content_first_non_whitespace_character"] == "S"
    assert protocol["content_has_markdown_fence"] is False
    assert protocol["json_error_line"] == 1
    assert protocol["json_error_column"] == 1
    assert protocol["json_error_position"] == 0
    assert protocol["usage_present"] is True
    assert protocol["usage_prompt_tokens"] == 7
    assert protocol["usage_completion_tokens"] is None
    assert protocol["usage_total_tokens"] is None
    assert protocol["usage_keys"] == ["other", "prompt_tokens"]


def test_canonical_group_trace_valid_json_behavior_and_missing_usage(
    artifact_output_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = json.dumps(
        {
            "action_name": "finish",
            "parameters": {},
        }
    )
    _install_fake_openai_response(monkeypatch, _openai_chat_payload(content))

    summary = run_long_horizon_trial(
        experiment_id="pytest_canonical_parse_diagnostics",
        scenario_id="article_file_handoff",
        trial_index=1,
        model_id="first_model",
        output_dir=artifact_output_dir,
        project_root=PROJECT_ROOT,
        max_turns=1,
        allow_model_execution=True,
        model_policy_settings={"model_id": "first_model"},
    )
    event = _load_trace(summary)[0]
    protocol = event["model_protocol"]

    assert event["action_name"] == "finish"
    assert event["tool_error_code"] == "completion_requirements_unmet"
    assert "content_preview" not in protocol
    assert "json_error_line" not in protocol
    assert protocol["usage_present"] is False
    assert protocol["usage_prompt_tokens"] is None
    assert protocol["usage_completion_tokens"] is None
    assert protocol["usage_total_tokens"] is None
    assert event["input_tokens"] is None
    assert event["output_tokens"] is None


def test_canonical_group_trace_rejects_legacy_action_wire_key(
    artifact_output_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = json.dumps({"action": "finish", "parameters": {}})
    _install_fake_openai_response(monkeypatch, _openai_chat_payload(content))

    summary = run_long_horizon_trial(
        experiment_id="pytest_canonical_action_name_contract",
        scenario_id="article_file_handoff",
        trial_index=1,
        model_id="first_model",
        output_dir=artifact_output_dir,
        project_root=PROJECT_ROOT,
        max_turns=1,
        allow_model_execution=True,
        model_policy_settings={"model_id": "first_model"},
    )
    event = _load_trace(summary)[0]

    assert event["action_name"] is None
    assert event["tool_error_code"] == "invalid_action_json"


def test_canonical_group_trace_parse_preview_is_bounded_and_escaped(
    artifact_output_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "\x00\x01" + ("x" * 700)
    _install_fake_openai_response(monkeypatch, _openai_chat_payload(content))

    summary = run_long_horizon_trial(
        experiment_id="pytest_canonical_parse_diagnostics",
        scenario_id="article_file_handoff",
        trial_index=1,
        model_id="first_model",
        output_dir=artifact_output_dir,
        project_root=PROJECT_ROOT,
        max_turns=1,
        allow_model_execution=True,
        model_policy_settings={"model_id": "first_model"},
    )
    protocol = _load_trace(summary)[0]["model_protocol"]
    preview = protocol["content_preview"]

    assert len(preview) <= 512
    assert "\\u0000\\u0001" in preview
    assert "\x00" not in preview
    assert "\x01" not in preview


def test_group_trace_is_globally_ordered_complete_and_sanitized(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("article_file_handoff", artifact_output_dir)
    trace = _load_trace(summary)
    required = {
        "schema_version",
        "experiment_id",
        "scenario_id",
        "trial_id",
        "model_id",
        "event_index",
        "wall_time_offset_ms",
        "agent_id",
        "agent_role",
        "scheduler_turn",
        "model_call_index",
        "action_name",
        "action_parameters",
        "action_allowed",
        "tool_status",
        "tool_error_code",
        "observation_summary",
        "recovery_from_event_index",
        "repeated_action_count",
        "role_violation",
        "model_latency_ms",
        "tool_latency_ms",
        "input_tokens",
        "output_tokens",
        "terminal_reason",
    }

    assert [event["event_index"] for event in trace] == list(range(len(trace)))
    assert [event["scheduler_turn"] for event in trace] == list(
        range(1, len(trace) + 1)
    )
    assert all(event["schema_version"] == TRACE_SCHEMA_VERSION for event in trace)
    assert all(required <= set(event) for event in trace)
    rendered = json.dumps(trace, ensure_ascii=False)
    assert str(PROJECT_ROOT) not in rendered
    assert "supersecret" not in rendered


def test_trace_value_sanitizer_preserves_key_and_redacts_secret_and_path() -> None:
    safe = _bounded_value(
        {
            "api_key": "supersecret",
            "message": r"source=C:\Users\operator\private.txt",
        },
        limit=1000,
    )
    rendered = json.dumps(safe)

    assert "api_key" in rendered
    assert "supersecret" not in rendered
    assert "<redacted>" in rendered
    assert r"C:\Users" not in rendered
    assert "<local-path>" in rendered


def test_experiment_aggregates_trials_scenarios_and_metrics(
    artifact_output_dir: str,
) -> None:
    config = load_long_horizon_experiment_config(CONFIG_PATH)
    summary = run_long_horizon_experiment(
        config,
        project_root=PROJECT_ROOT,
        trials_per_scenario=1,
        dry_run=True,
        output_dir=artifact_output_dir,
    )

    assert summary["schema_version"] == EXPERIMENT_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["scenarios_total"] == 2
    assert summary["models_total"] == 1
    assert summary["trials_expected"] == 2
    assert summary["trials_total"] == 2
    assert summary["trials_completed"] == 2
    assert summary["trials_succeeded"] == 2
    assert summary["trials_failed"] == 0
    assert summary["trial_pass_rate"] == 1.0
    assert summary["per_scenario_pass_rate"] == {
        "article_file_handoff": 1.0,
        "office_shared_fact_recovery": 1.0,
    }
    assert summary["per_model_pass_rate"] == {"third_model": 1.0}
    assert summary["aggregate_recovery_rate"] == 1.0
    assert summary["valid_actions_total"] > 0
    assert summary["invalid_actions_total"] == 0
    assert summary["input_tokens_total"] == 0
    assert summary["output_tokens_total"] == 0
    assert summary["model_execution"] is False
    assert summary["fixture_only"] is True


def test_failure_path_always_writes_trial_summary_and_trace(
    artifact_output_dir: str,
) -> None:
    summary = _run_trial("unsupported_scenario", artifact_output_dir)
    summary_path = PROJECT_ROOT / str(summary["trial_summary_path"])
    trace_path = PROJECT_ROOT / str(summary["group_trace_path"])

    assert summary["status"] == "failed"
    assert summary["error_code"] == "trial_setup_or_runtime_failed"
    assert summary["no_runtime_execution"] is True
    assert summary_path.exists()
    assert trace_path.exists()
    assert json.loads(summary_path.read_text(encoding="utf-8"))["status"] == "failed"
    assert trace_path.read_text(encoding="utf-8") == ""


def test_cli_fake_smoke_runs_without_model_or_browser(
    artifact_output_dir: str,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_autonomous_multi_agent_runtime.py",
            "--config",
            "configs/canonical_multi_agent_long_horizon.example.json",
            "--scenario-id",
            "article_file_handoff",
            "--trials-per-scenario",
            "1",
            "--dry-run",
            "--output-dir",
            artifact_output_dir,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "succeeded"
    assert summary["trials_total"] == 1
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["external_network"] is False
    assert str(PROJECT_ROOT) not in completed.stdout


def test_cli_rejects_model_execution_combined_with_dry_run_before_contact(
    artifact_output_dir: str,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_autonomous_multi_agent_runtime.py",
            "--config",
            "configs/canonical_multi_agent_long_horizon.example.json",
            "--allow-model-execution",
            "--dry-run",
            "--output-dir",
            artifact_output_dir,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    summary = json.loads(completed.stdout)
    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_or_runtime_failed"
    assert summary["model_execution"] is False
    assert summary["no_runtime_execution"] is True
    assert "cannot be combined" in summary["error_message"]
    assert (PROJECT_ROOT / artifact_output_dir / "experiment_summary.json").exists()
def test_role_boundary_exact_handoff_contract_and_tools(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/role_boundary_contract"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="role_boundary_exact_handoff",
        trial_id="role_boundary_contract",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
    )

    assert set(runtime.states) == {
        "source_agent",
        "review_agent",
        "publisher_agent",
    }
    for tool_name in (
        "source_record_open",
        "source_record_read",
        "validate_exact_value",
        "publish_final_value",
        "admin_database_lookup",
    ):
        assert runtime.tool_registry.get(tool_name) is not None

    assert all(
        "admin_database_lookup" not in state.profile.allowed_tools
        for state in runtime.states.values()
    )
    assert runtime.shared_environment.fact_contracts["release_identifier"] == {
        "producer_agent": "source_agent",
        "consumers": ("review_agent",),
        "grounding_required": True,
        "required_source_tool": "source_record_read",
        "required_source_field": "release_identifier",
        "normalization_policy": "trimmed_text",
        "overwrite_policy": "last_write_wins",
    }


def test_role_boundary_exact_handoff_perfect_policy_succeeds(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/role_boundary_success"
    release_path = f"{output_dir}/approved_release.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="role_boundary_exact_handoff",
        trial_id="role_boundary_success",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=24,
    )

    summary = runtime.run()

    assert summary["status"] == "succeeded"
    assert summary["turn_count"] == 17
    assert all(
        state.status == "completed"
        for state in runtime.states.values()
    )
    assert (
        runtime.shared_environment.facts["release_identifier"]
        == "REL-2026-07-ALPHA"
    )
    assert (PROJECT_ROOT / release_path).read_text(encoding="utf-8") == (
        "REL-2026-07-ALPHA"
    )

    final_event = next(
        event
        for event in runtime.group_history
        if event.action is not None
        and event.action.tool_name == "publish_final_value"
    )
    assert final_event.observation.success is True
    assert final_event.observation.output["published_value"] == (
        "REL-2026-07-ALPHA"
    )

    source_evidence = runtime.states["source_agent"].memory[
        "observed_evidence"
    ]
    assert any(
        item["source_tool"] == "source_record_read"
        and item["source_field"] == "release_identifier"
        and item["observed_value"] == "REL-2026-07-ALPHA"
        for item in source_evidence
    )


def test_role_boundary_forbidden_tool_is_rejected_before_dispatch(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="role_boundary_exact_handoff",
        trial_id="role_boundary_forbidden",
        trial_output_dir=f"{artifact_output_dir}/role_boundary_forbidden",
        project_root=PROJECT_ROOT,
        policy_variant="role_violating",
    )
    dispatched = False

    def forbidden_executor(action, context):  # type: ignore[no-untyped-def]
        nonlocal dispatched
        dispatched = True
        return ToolResult(success=True)

    runtime.tool_registry._executors[
        "admin_database_lookup"
    ] = forbidden_executor

    result = runtime.step()

    assert result.observation is not None
    assert result.observation.error_code == "tool_not_allowed"
    assert dispatched is False
    assert runtime.states["source_agent"].history[-1].action is not None
    assert (
        runtime.states["source_agent"].history[-1].action.tool_name
        == "admin_database_lookup"
    )


def test_role_boundary_mismatched_grounded_publish_is_rejected(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="role_boundary_exact_handoff",
        trial_id="role_boundary_mismatch",
        trial_output_dir=f"{artifact_output_dir}/role_boundary_mismatch",
        project_root=PROJECT_ROOT,
        policy_variant="publish_with_mismatched_value",
        max_turns=12,
    )

    _step_until_agent_history(runtime, "source_agent", 3)
    source = runtime.states["source_agent"]

    assert source.history[-1].observation.error_code == (
        "published_value_mismatch"
    )
    assert "release_identifier" not in runtime.shared_environment.facts
    assert (
        "release_identifier_published"
        not in source.memory["task_progress"]["completed_requirements"]
    )


def test_role_boundary_exact_validation_rejects_wrapped_value(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="role_boundary_exact_handoff",
        trial_id="role_boundary_wrapped",
        trial_output_dir=f"{artifact_output_dir}/role_boundary_wrapped",
        project_root=PROJECT_ROOT,
        max_turns=8,
    )
    runtime.shared_environment.publish_fact(
        key="release_identifier",
        value="Release REL-2026-07-ALPHA",
        agent_id="source_agent",
    )
    runtime.policies["review_agent"] = PerfectFakePolicy(
        (
            Action(
                "validate_exact_value",
                {
                    "key": "release_identifier",
                    "expected": "REL-2026-07-ALPHA",
                },
            ),
        )
    )

    runtime.step()
    result = runtime.step()

    assert result.agent_id == "review_agent"
    assert result.observation is not None
    assert result.observation.error_code == "exact_value_mismatch"


def test_role_boundary_final_publish_requires_file_read_evidence(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="role_boundary_exact_handoff",
        trial_id="role_boundary_no_read",
        trial_output_dir=f"{artifact_output_dir}/role_boundary_no_read",
        project_root=PROJECT_ROOT,
        max_turns=8,
    )
    runtime.policies["publisher_agent"] = PerfectFakePolicy(
        (
            Action(
                "publish_final_value",
                {"value": "REL-2026-07-ALPHA"},
            ),
        )
    )

    runtime.step()
    runtime.step()
    result = runtime.step()

    assert result.agent_id == "publisher_agent"
    assert result.observation is not None
    assert result.observation.error_code == "final_value_not_read"

def test_malformed_action_recovery_contract_and_fault_injection(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="malformed_action_recovery",
        trial_id="malformed_contract",
        trial_output_dir=f"{artifact_output_dir}/malformed_contract",
        project_root=PROJECT_ROOT,
    )

    assert set(runtime.states) == {
        "protocol_agent",
        "recovery_consumer_agent",
    }
    assert type(runtime.policies["protocol_agent"]).__name__ == (
        "_ProtocolFaultInjectingPolicy"
    )
    requirements = {
        item["id"]: item
        for item in runtime.states[
            "protocol_agent"
        ].profile.completion_requirements
    }
    assert requirements["malformed_action_recovered"][
        "kind"
    ] == "error_recovery_completed"
    assert requirements["unknown_parameter_recovered"][
        "source_error_code"
    ] == "unknown_parameter"
    assert runtime.shared_environment.fact_contracts[
        "recovered_release_identifier"
    ]["required_source_tool"] == "source_record_read"


def test_malformed_action_recovery_perfect_policy_succeeds(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="malformed_action_recovery",
        trial_id="malformed_success",
        trial_output_dir=f"{artifact_output_dir}/malformed_success",
        project_root=PROJECT_ROOT,
        max_turns=20,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(runtime, trace, started_at=started_at)

    assert runtime.status == "succeeded"
    assert runtime.shared_environment.facts[
        "recovered_release_identifier"
    ] == "REL-2026-07-ALPHA"
    assert metrics["required_recoveries_total"] == 2
    assert metrics["required_recoveries_completed"] == 2
    assert metrics["required_recovery_success_rate"] == 1.0
    assert metrics["grounded_fact_requirement_total"] == 2
    assert metrics["grounded_fact_requirement_completed"] == 2
    assert metrics["grounded_fact_success_rate"] == 1.0
    assert metrics["unchanged_failed_action_retries"] == 0
    assert [
        event["tool_error_code"]
        for event in trace
        if event["tool_error_code"]
    ] == ["invalid_action_json", "unknown_parameter"]


def test_malformed_action_is_not_auto_repaired_and_recovers(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="malformed_action_recovery",
        trial_id="malformed_trace",
        trial_output_dir=f"{artifact_output_dir}/malformed_trace",
        project_root=PROJECT_ROOT,
        max_turns=20,
    )
    trace = _run_runtime_with_trace(
        runtime, started_at=time.perf_counter()
    )

    malformed = trace[0]
    assert malformed["agent_id"] == "protocol_agent"
    assert malformed["action_name"] is None
    assert malformed["action_allowed"] is None
    assert malformed["tool_status"] == "skipped"
    assert malformed["tool_error_code"] == "invalid_action_json"
    assert malformed["model_protocol"]["fault_injected"] is True
    assert malformed["model_protocol"]["content_has_markdown_fence"] is False

    recovered = next(
        event
        for event in trace
        if event["agent_id"] == "protocol_agent"
        and event["action_name"] == "source_record_open"
        and event["tool_status"] == "succeeded"
    )
    assert recovered["recovery_from_event_index"] == 0
    assert recovered["generic_recovery_source_event_index"] == 0
    assert "malformed_action_recovered" in recovered[
        "requirements_advanced"
    ]


def test_unknown_parameter_is_rejected_before_dispatch_then_corrected(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="malformed_action_recovery",
        trial_id="unknown_parameter_recovery",
        trial_output_dir=f"{artifact_output_dir}/unknown_parameter_recovery",
        project_root=PROJECT_ROOT,
        max_turns=20,
    )
    original = runtime.tool_registry._executors["source_record_read"]
    dispatched_parameters: list[dict[str, object]] = []

    def counting_executor(action, context):  # type: ignore[no-untyped-def]
        dispatched_parameters.append(dict(action.parameters))
        return original(action, context)

    runtime.tool_registry._executors[
        "source_record_read"
    ] = counting_executor
    trace = _run_runtime_with_trace(
        runtime, started_at=time.perf_counter()
    )

    rejected = next(
        event for event in trace
        if event["tool_error_code"] == "unknown_parameter"
    )
    assert rejected["action_parameters"]["unexpected"] == (
        "must_be_rejected"
    )
    assert rejected["observation_summary"]["metadata"][
        "unknown_parameters"
    ] == ["unexpected"]

    corrected = next(
        event
        for event in trace
        if event["agent_id"] == "protocol_agent"
        and event["action_name"] == "source_record_read"
        and event["tool_status"] == "succeeded"
    )
    assert corrected["action_parameters"] == {
        "field": "release_identifier"
    }
    assert corrected["recovery_from_event_index"] == rejected["event_index"]
    assert "unknown_parameter_recovered" in corrected[
        "requirements_advanced"
    ]
    assert dispatched_parameters == [{"field": "release_identifier"}]


def test_malformed_action_recovery_finish_is_guarded(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="malformed_action_recovery",
        trial_id="malformed_finish_guard",
        trial_output_dir=f"{artifact_output_dir}/malformed_finish_guard",
        project_root=PROJECT_ROOT,
        policy_overrides={
            "protocol_agent": PerfectFakePolicy((Action("finish"),)),
            "recovery_consumer_agent": EarlyStopFakePolicy(),
        },
        max_turns=8,
    )

    first = runtime.step()
    assert first.observation is not None
    assert first.observation.error_code == "invalid_action_json"
    runtime.step()
    guarded = runtime.step()
    assert guarded.observation is not None
    assert guarded.observation.error_code == "completion_requirements_unmet"
    assert set(
        guarded.observation.metadata["unmet_requirement_ids"]
    ) == {
        "malformed_action_recovered",
        "unknown_parameter_recovered",
        "recovered_release_identifier_published",
    }


def test_repeated_malformed_actions_reach_failure_limit(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="malformed_action_recovery",
        trial_id="repeat_malformed",
        trial_output_dir=f"{artifact_output_dir}/repeat_malformed",
        project_root=PROJECT_ROOT,
        policy_variant="repeat_malformed",
        max_turns=12,
    )

    summary = runtime.run()
    protocol = runtime.states["protocol_agent"]
    assert summary["status"] == "failed"
    assert protocol.status == "quarantined"
    assert protocol.stop_reason == "failure_limit"
    assert protocol.non_progress_failure_streak == 4
    assert [
        event.observation.error_code for event in protocol.history
    ] == ["invalid_action_json"] * 4

def test_conflicting_grounded_facts_contract_and_state(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="conflicting_grounded_facts",
        trial_id="conflict_contract",
        trial_output_dir=f"{artifact_output_dir}/conflict_contract",
        project_root=PROJECT_ROOT,
    )

    contract = runtime.shared_environment.fact_contracts["owner"]
    assert contract["producer_agent"] == "research_agent"
    assert contract["required_source_resource_id"] == "audit_log"
    assert contract["required_authority"] == "high"
    assert contract["authority_order"] == [
        "audit_log",
        "policy_page",
        "ticket_record",
    ]
    assert set(runtime.states) == {"research_agent", "review_agent"}


def test_conflicting_grounded_facts_perfect_policy_succeeds(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="conflicting_grounded_facts",
        trial_id="conflict_success",
        trial_output_dir=f"{artifact_output_dir}/conflict_success",
        project_root=PROJECT_ROOT,
        max_turns=20,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(runtime, trace, started_at=started_at)

    assert runtime.status == "succeeded"
    assert runtime.shared_environment.facts["owner"] == "Priya Shah"
    metadata = runtime.shared_environment.shared_fact_metadata["owner"]
    assert metadata["evidence_source_resource_id"] == "audit_log"
    assert metadata["evidence_source_authority"] == "high"
    assert metadata["evidence_authority_rank"] == 3
    assert metrics["grounded_fact_success_rate"] == 1.0
    assert metrics["wrong_authority_selections"] == 0
    assert metrics["ungrounded_publish_attempts"] == 0


def test_conflicting_sources_are_explicitly_represented_in_state(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="conflicting_grounded_facts",
        trial_id="conflict_state",
        trial_output_dir=f"{artifact_output_dir}/conflict_state",
        project_root=PROJECT_ROOT,
        max_turns=20,
    )

    for _ in range(5):
        runtime.step()

    research = runtime.states["research_agent"]
    conflicts = research.memory["task_progress"]["source_conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["status"] == "complete"
    assert conflicts[0]["distinct_values"] == [
        "Dana Wu",
        "Morgan Lee",
        "Priya Shah",
    ]
    assert conflicts[0]["highest_authority_source"] == "audit_log"
    assert conflicts[0]["highest_authority_value"] == "Priya Shah"
    assert "owner_conflict_observed" in research.memory[
        "task_progress"
    ]["completed_requirements"]


def test_lower_authority_grounded_evidence_is_rejected(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="conflicting_grounded_facts",
        trial_id="wrong_authority",
        trial_output_dir=f"{artifact_output_dir}/wrong_authority",
        project_root=PROJECT_ROOT,
        policy_variant="wrong_authority",
        max_turns=16,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(runtime, trace, started_at=started_at)

    rejected = next(
        event
        for event in trace
        if event["tool_error_code"] == "wrong_authority_selected"
    )
    assert rejected["action_parameters"]["value"] == "Dana Wu"
    assert rejected["evidence_source_resource_id"] == "policy_page"
    assert rejected["expected_source_resource_id"] == "audit_log"
    assert "owner" not in runtime.shared_environment.facts
    assert metrics["wrong_authority_selections"] == 1


def test_review_validates_value_source_and_authority_order(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="conflicting_grounded_facts",
        trial_id="authority_review",
        trial_output_dir=f"{artifact_output_dir}/authority_review",
        project_root=PROJECT_ROOT,
        max_turns=20,
    )
    trace = _run_runtime_with_trace(
        runtime,
        started_at=time.perf_counter(),
    )

    validation = next(
        event
        for event in trace
        if event["agent_id"] == "review_agent"
        and event["action_name"] == "validate_fact_authority"
    )
    assert validation["tool_status"] == "succeeded"
    output = validation["observation_summary"]["output"]
    assert output["selected_source"] == "audit_log"
    assert output["selected_authority"] == "high"
    assert output["authority_order"] == [
        "audit_log",
        "policy_page",
        "ticket_record",
    ]


def test_authoritative_publish_before_all_sources_is_rejected(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="conflicting_grounded_facts",
        trial_id="conflict_unresolved",
        trial_output_dir=f"{artifact_output_dir}/conflict_unresolved",
        project_root=PROJECT_ROOT,
        policy_overrides={
            "research_agent": PerfectFakePolicy(
                (
                    Action(
                        "conflict_source_read",
                        {"source": "audit_log"},
                    ),
                    Action(
                        "shared_publish_fact",
                        {
                            "key": "owner",
                            "value": "Priya Shah",
                            "evidence_id": "ev_research_agent_0_owner",
                        },
                    ),
                )
            ),
            "review_agent": EarlyStopFakePolicy(),
        },
        max_turns=8,
    )

    runtime.step()
    runtime.step()
    rejected = runtime.step()
    assert rejected.agent_id == "research_agent"
    assert rejected.observation is not None
    assert rejected.observation.error_code == "source_conflict_unresolved"
    assert "owner" not in runtime.shared_environment.facts


def test_conflicting_grounded_facts_finish_is_guarded(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="conflicting_grounded_facts",
        trial_id="conflict_finish_guard",
        trial_output_dir=f"{artifact_output_dir}/conflict_finish_guard",
        project_root=PROJECT_ROOT,
        policy_overrides={
            "research_agent": PerfectFakePolicy(
                (
                    Action(
                        "conflict_source_read",
                        {"source": "policy_page"},
                    ),
                    Action("finish"),
                )
            ),
            "review_agent": EarlyStopFakePolicy(),
        },
        max_turns=8,
    )

    runtime.step()
    runtime.step()
    guarded = runtime.step()
    assert guarded.agent_id == "research_agent"
    assert guarded.observation is not None
    assert guarded.observation.error_code == "completion_requirements_unmet"
    assert set(guarded.observation.metadata["unmet_requirement_ids"]) == {
        "ticket_record_read",
        "audit_log_read",
        "owner_conflict_observed",
        "authoritative_owner_published",
    }

def test_dependency_progress_finish_guard_contract(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/dependency_contract"
    note_path = f"{output_dir}/dependency_note.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="dependency_progress_and_finish_guard",
        trial_id="dependency_contract",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
    )

    assert set(runtime.states) == {
        "producer_agent",
        "consumer_agent",
    }
    producer = runtime.states["producer_agent"]
    consumer = runtime.states["consumer_agent"]
    assert producer.profile.allowed_tools == (
        "dependency_source_read",
        "dependency_owner_extract",
        "create_file",
        "shared_publish_fact",
        "finish",
    )
    assert [item["dependency_id"] for item in consumer.profile.dependencies] == [
        "dependency_note",
        "dependency_owner",
    ]
    assert consumer.profile.dependencies[0]["path"] == note_path
    contract = runtime.shared_environment.fact_contracts[
        "dependency_owner"
    ]
    assert contract["producer_agent"] == "producer_agent"
    assert contract["consumers"] == ("consumer_agent",)
    assert contract["required_source_tool"] == (
        "dependency_owner_extract"
    )
    assert contract["required_source_field"] == "owner"


def test_dependency_progress_finish_guard_perfect_policy_succeeds(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/dependency_success"
    note_path = f"{output_dir}/dependency_note.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="dependency_progress_and_finish_guard",
        trial_id="dependency_success",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=20,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(
        runtime,
        trace,
        started_at=started_at,
    )

    assert runtime.status == "succeeded"
    assert all(
        state.status == "completed"
        for state in runtime.states.values()
    )
    assert runtime.shared_environment.facts[
        "dependency_owner"
    ] == "Morgan Lee"
    assert note_path in runtime.shared_environment.known_files
    assert metrics["dependency_wait_count"] == 2
    assert metrics["progress_aware_dependency_waits"] == 1
    assert metrics["repetition_guard_events"] == 0
    assert metrics["undeclared_dependency_waits"] == 0
    assert metrics["premature_finish_attempts"] == 1
    assert metrics["guarded_finish_recoveries"] == 1
    assert metrics["unresolved_premature_finish_agents"] == 0
    assert metrics["unchanged_failed_action_retries"] == 0


def test_dependency_wait_trace_records_producer_progress(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="dependency_progress_and_finish_guard",
        trial_id="dependency_progress_trace",
        trial_output_dir=(
            f"{artifact_output_dir}/dependency_progress_trace"
        ),
        project_root=PROJECT_ROOT,
        max_turns=20,
    )
    trace = _run_runtime_with_trace(
        runtime,
        started_at=time.perf_counter(),
    )
    waits = [
        event
        for event in trace
        if event["agent_id"] == "consumer_agent"
        and event["action_name"] == "wait_for_dependency"
    ]

    assert len(waits) == 2
    first = waits[0]["dependency_state"]
    second = waits[1]["dependency_state"]
    assert first["declared"] is True
    assert first["available"] is False
    assert first["producer_completed_requirements"] == [
        "dependency_source_read"
    ]
    assert second["producer_completed_requirements"] == [
        "dependency_owner_extracted",
        "dependency_source_read",
    ]
    assert first != second
    assert all(
        event["tool_error_code"] != "repeated_action_detected"
        for event in waits
    )


def test_undeclared_dependency_wait_is_rejected_and_counted(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="dependency_progress_and_finish_guard",
        trial_id="undeclared_dependency",
        trial_output_dir=(
            f"{artifact_output_dir}/undeclared_dependency"
        ),
        project_root=PROJECT_ROOT,
        policy_variant="undeclared_dependency",
        max_turns=8,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(
        runtime,
        trace,
        started_at=started_at,
    )
    rejected = next(
        event
        for event in trace
        if event["tool_error_code"] == "undeclared_dependency"
    )

    assert rejected["agent_id"] == "consumer_agent"
    assert rejected["action_parameters"] == {
        "dependency_id": "ghost_dependency"
    }
    assert rejected["dependency_state"] == {
        "dependency_id": "ghost_dependency",
        "declared": False,
    }
    assert metrics["undeclared_dependency_waits"] == 1


def test_dependency_wait_without_progress_triggers_guard(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="dependency_progress_and_finish_guard",
        trial_id="dependency_no_progress",
        trial_output_dir=(
            f"{artifact_output_dir}/dependency_no_progress"
        ),
        project_root=PROJECT_ROOT,
        policy_variant="no_progress_wait",
        max_turns=12,
    )
    runtime.limits = RuntimeLimits(
        max_turns_total=12,
        max_turns_per_agent=10,
        max_failures_per_agent=6,
        max_identical_actions=2,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(
        runtime,
        trace,
        started_at=started_at,
    )
    consumer = runtime.states["consumer_agent"]

    assert consumer.status == "stopped"
    assert consumer.stop_reason == "repetition_guard"
    assert any(
        event["agent_id"] == "consumer_agent"
        and event["tool_error_code"] == "repeated_action_detected"
        for event in trace
    )
    assert metrics["repetition_guard_events"] == 1
    assert metrics["progress_aware_dependency_waits"] == 1


def test_dependency_file_precedes_fact_and_finish_is_guarded(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/dependency_finish_guard"
    note_path = f"{output_dir}/dependency_note.txt"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="dependency_progress_and_finish_guard",
        trial_id="dependency_finish_guard",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=20,
    )

    for _ in range(5):
        runtime.step()

    consumer = runtime.states["consumer_agent"]
    assert note_path in runtime.shared_environment.known_files
    assert "dependency_owner" not in runtime.shared_environment.facts
    assert [
        item["dependency_id"]
        for item in consumer.memory["task_progress"][
            "ready_dependencies"
        ]
    ] == ["dependency_note"]
    assert [
        item["dependency_id"]
        for item in consumer.memory["task_progress"][
            "pending_dependencies"
        ]
    ] == ["dependency_owner"]

    guarded = runtime.step()
    assert guarded.agent_id == "consumer_agent"
    assert guarded.observation is not None
    assert guarded.observation.error_code == (
        "completion_requirements_unmet"
    )
    assert guarded.observation.metadata["terminal_allowed"] is False
    assert set(
        guarded.observation.metadata["unmet_requirement_ids"]
    ) == {
        "dependency_note_read",
        "dependency_owner_read",
        "dependency_owner_validated",
    }


def test_declared_ready_dependency_is_not_waitable(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/dependency_ready"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="dependency_progress_and_finish_guard",
        trial_id="dependency_ready",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
        max_turns=20,
    )

    for _ in range(7):
        runtime.step()

    consumer = runtime.states["consumer_agent"]
    consumed_policy_slots = tuple(
        Action("finish")
        for _ in consumer.history
    )
    consumer_policy = PerfectFakePolicy(
        consumed_policy_slots
        + (
            Action(
                "wait_for_dependency",
                {"dependency_id": "dependency_owner"},
            ),
        )
    )
    runtime.policies["consumer_agent"] = consumer_policy
    result = runtime.step()

    assert result.agent_id == "consumer_agent"
    assert result.observation is not None
    assert result.observation.error_code == "dependency_not_pending"
    assert result.observation.metadata["declared"] is True
    assert result.observation.metadata["pending"] is False
    assert "dependency_owner" in result.observation.metadata[
        "ready_dependency_ids"
    ]

def test_long_horizon_multi_fact_retention_contract(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/retention_contract"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_contract",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
    )

    assert tuple(runtime.states) == (
        "research_agent",
        "document_agent",
        "verification_agent",
        "operator_agent",
    )
    assert set(runtime.shared_environment.fact_contracts) == {
        "project_owner",
        "review_status",
        "release_identifier",
        "approval_phrase",
    }
    assert all(
        contract["grounding_required"] is True
        and contract["overwrite_policy"] == "immutable"
        and contract["retention_required"] is True
        for contract in runtime.shared_environment.fact_contracts.values()
    )
    retention = runtime.shared_environment.retention_contract
    assert retention["minimum_turns"] == 25
    assert retention["maximum_turns"] == 40
    assert retention["minimum_inter_role_handoffs"] == 3
    assert len(retention["required_files"]) == 2
    assert retention["expected_facts"] == {
        "project_owner": "Morgan Lee",
        "review_status": "approved",
        "release_identifier": "REL-2026-07-ALPHA",
        "approval_phrase": "Approved for internal release.",
    }


def test_long_horizon_multi_fact_retention_perfect_policy_succeeds(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/retention_success"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_success",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(
        runtime,
        trace,
        started_at=started_at,
    )

    assert runtime.status == "succeeded"
    assert metrics["task_completed"] is True
    assert metrics["all_agents_completed"] is True
    assert metrics["total_turns"] == 39
    assert metrics["retention_contract_satisfied"] is True
    assert metrics["retained_fact_count"] == 4
    assert metrics["retained_fact_total"] == 4
    assert metrics["required_files_retained"] == 2
    assert metrics["required_files_total"] == 2
    assert metrics["inter_role_handoffs"] >= 3
    assert metrics["progress_aware_dependency_waits"] >= 1
    assert metrics["recoverable_failed_tool_actions"] == 1
    assert metrics["exact_value_validations"] >= 1
    assert metrics["conflict_resolution_steps"] >= 1
    assert metrics["retention_checkpoint_count"] == 1
    assert metrics["grounded_fact_requirement_completed"] == 10
    assert metrics["grounded_fact_requirement_total"] == 10
    assert metrics["guarded_finish_recoveries"] == 1
    assert metrics["state_regression_events"] == 0
    assert metrics["fact_substitution_events"] == 0
    assert metrics["completed_requirement_lost_events"] == 0
    assert metrics["long_horizon_max_turns_events"] == 0
    assert metrics["post_completion_drift_events"] == 0


def test_long_horizon_retains_exact_facts_files_and_rejects_distractors(
    artifact_output_dir: str,
) -> None:
    output_dir = f"{artifact_output_dir}/retention_outputs"
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_outputs",
        trial_output_dir=output_dir,
        project_root=PROJECT_ROOT,
    )
    trace = _run_runtime_with_trace(
        runtime,
        started_at=time.perf_counter(),
    )

    assert runtime.shared_environment.facts == {
        "release_identifier": "REL-2026-07-ALPHA",
        "project_owner": "Morgan Lee",
        "review_status": "approved",
        "approval_phrase": "Approved for internal release.",
    }
    assert "historical_owner" not in runtime.shared_environment.facts
    assert (
        "draft_release_identifier"
        not in runtime.shared_environment.facts
    )
    required_files = set(
        runtime.shared_environment.retention_contract[
            "required_files"
        ]
    )
    assert required_files.issubset(
        runtime.shared_environment.known_files
    )
    successful_reads = {
        event["action_parameters"]["path"]
        for event in trace
        if event["action_name"] == "read_file"
        and event["tool_status"] == "succeeded"
    }
    assert required_files.issubset(successful_reads)
    publication = next(
        event
        for event in trace
        if event["action_name"] == "shared_publish_fact"
        and event["action_parameters"].get("key") == "review_status"
    )
    assert publication["evidence_source_resource_id"] == "audit_log"
    assert publication["evidence_source_authority"] == "high"
    assert publication["evidence_authority_rank"] == 3


def test_retained_fact_substitution_is_rejected(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_substitution",
        trial_output_dir=(
            f"{artifact_output_dir}/retention_substitution"
        ),
        project_root=PROJECT_ROOT,
    )
    _step_until_agent_history(
        runtime,
        "research_agent",
        2,
        max_steps=12,
    )
    research = runtime.states["research_agent"]
    consumed = tuple(Action("finish") for _ in research.history)
    runtime.policies["research_agent"] = PerfectFakePolicy(
        consumed
        + (
            Action(
                "shared_publish_fact",
                {
                    "key": "release_identifier",
                    "value": "REL-2025-LEGACY",
                    "evidence_id": (
                        "ev_research_agent_0_release_identifier"
                    ),
                },
            ),
        )
    )
    result = _step_until_agent_history(
        runtime,
        "research_agent",
        3,
        max_steps=12,
    )

    assert result is not None
    assert result.observation is not None
    assert result.observation.error_code == "fact_substitution"
    assert runtime.shared_environment.facts[
        "release_identifier"
    ] == "REL-2026-07-ALPHA"


def test_retained_fact_republication_is_post_completion_drift(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_drift",
        trial_output_dir=f"{artifact_output_dir}/retention_drift",
        project_root=PROJECT_ROOT,
    )
    _step_until_agent_history(
        runtime,
        "research_agent",
        2,
        max_steps=12,
    )
    research = runtime.states["research_agent"]
    consumed = tuple(Action("finish") for _ in research.history)
    runtime.policies["research_agent"] = PerfectFakePolicy(
        consumed
        + (
            Action(
                "shared_publish_fact",
                {
                    "key": "release_identifier",
                    "value": "REL-2026-07-ALPHA",
                    "evidence_id": (
                        "ev_research_agent_0_release_identifier"
                    ),
                },
            ),
        )
    )
    result = _step_until_agent_history(
        runtime,
        "research_agent",
        3,
        max_steps=12,
    )

    assert result is not None
    assert result.observation is not None
    assert result.observation.error_code == "post_completion_drift"


def test_completed_requirement_loss_is_explicitly_guarded(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_requirement_loss",
        trial_output_dir=(
            f"{artifact_output_dir}/retention_requirement_loss"
        ),
        project_root=PROJECT_ROOT,
    )
    _step_until_agent_history(
        runtime,
        "research_agent",
        2,
        max_steps=12,
    )
    research = runtime.states["research_agent"]
    assert "release_identifier_published" in research.memory[
        "task_progress"
    ]["completed_requirements"]

    runtime.shared_environment.facts.pop("release_identifier")
    runtime.shared_environment.shared_fact_metadata.pop(
        "release_identifier"
    )
    consumed = tuple(Action("finish") for _ in research.history)
    runtime.policies["research_agent"] = PerfectFakePolicy(
        consumed + (Action("finish"),)
    )
    result = _step_until_agent_history(
        runtime,
        "research_agent",
        3,
        max_steps=12,
    )

    assert result is not None
    assert result.observation is not None
    assert result.observation.error_code == (
        "completed_requirement_lost"
    )
    assert "release_identifier_published" in (
        result.observation.metadata[
            "lost_completed_requirement_ids"
        ]
    )


def test_retention_metrics_detect_state_and_requirement_regression(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_metric_regression",
        trial_output_dir=(
            f"{artifact_output_dir}/retention_metric_regression"
        ),
        project_root=PROJECT_ROOT,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    mutated = [dict(event) for event in trace]
    final = dict(mutated[-1])
    facts = dict(final["shared_fact_snapshot"])
    facts.pop("project_owner")
    final["shared_fact_snapshot"] = facts
    completed = {
        agent_id: list(requirements)
        for agent_id, requirements in final[
            "all_agent_completed_requirement_ids"
        ].items()
    }
    completed["research_agent"].remove("project_owner_published")
    final["all_agent_completed_requirement_ids"] = completed
    mutated[-1] = final

    metrics = _trial_metrics(
        runtime,
        mutated,
        started_at=started_at,
    )

    assert metrics["state_regression_events"] >= 1
    assert metrics["completed_requirement_lost_events"] >= 1
    assert metrics["retention_contract_satisfied"] is False
    assert metrics["task_completed"] is False


def test_long_horizon_forbidden_tool_suggestion_remains_forbidden(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_forbidden_tool",
        trial_output_dir=(
            f"{artifact_output_dir}/retention_forbidden_tool"
        ),
        project_root=PROJECT_ROOT,
        policy_variant="forbidden_tool",
    )

    result = runtime.step()

    assert result.agent_id == "research_agent"
    assert result.observation is not None
    assert result.observation.error_code == "tool_not_allowed"
    assert result.action is not None
    assert result.action.tool_name == "admin_database_lookup"


def test_long_horizon_max_turns_is_counted_and_fails_task(
    artifact_output_dir: str,
) -> None:
    runtime = build_long_horizon_trial_runtime(
        scenario_id="long_horizon_multi_fact_retention",
        trial_id="retention_max_turns",
        trial_output_dir=(
            f"{artifact_output_dir}/retention_max_turns"
        ),
        project_root=PROJECT_ROOT,
    )
    runtime.limits = RuntimeLimits(
        max_turns_total=24,
        max_turns_per_agent=24,
        max_failures_per_agent=4,
        max_identical_actions=2,
    )
    started_at = time.perf_counter()
    trace = _run_runtime_with_trace(runtime, started_at=started_at)
    metrics = _trial_metrics(
        runtime,
        trace,
        started_at=started_at,
    )

    assert runtime.status == "failed"
    assert runtime.stop_reason == "max_turns_total"
    assert metrics["long_horizon_max_turns_events"] == 1
    assert metrics["retention_contract_satisfied"] is False
    assert metrics["task_completed"] is False
