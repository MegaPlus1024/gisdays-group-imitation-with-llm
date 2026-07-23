from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from src.agent.autonomous_multi_agent_runtime import (
    Action,
    AgentProfile,
    AgentState,
    HistoryEvent,
    LocalOpenAIModelPolicy,
    Observation,
    PolicyError,
    PerfectFakePolicy,
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
                action="finish",
                parameters={},
                reason="complete",
                expected_result="finished",
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
