from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.agent.autonomous_multi_agent_runtime import (
    Action,
    AgentProfile,
    AgentState,
    AutonomousMultiAgentRuntime,
    EarlyStopFakePolicy,
    LocalOpenAIModelPolicy,
    PerfectFakePolicy,
    PolicyError,
    RepeatingFakePolicy,
    RoleViolatingFakePolicy,
    RuntimeLimits,
    SharedEnvironment,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    build_default_tool_registry,
    load_runtime_from_config,
)
from src.agent.schemas import NextAction


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "canonical_multi_agent.example.json"


def test_default_registry_unifies_required_tool_families_without_click() -> None:
    registry, _ = build_default_tool_registry(project_root=PROJECT_ROOT)

    families = {spec.family for spec in registry.specs_for(registry.names())}
    names = set(registry.names())

    assert {"browser_article_read", "files", "office_documents", "simple_commands"} <= families
    assert {
        "browser_article_open",
        "browser_article_read",
        "browser_article_scroll",
        "browser_article_find",
        "browser_article_extract",
        "read_file",
        "list_directory",
        "office_extract_docx_text",
        "run_shell_command",
        "shared_publish_fact",
        "shared_read_fact",
    } <= names
    assert "browser_click" not in names
    assert "browser_open_url" not in names


def test_two_agent_fake_slice_alternates_recovers_and_retains_histories() -> None:
    runtime = load_runtime_from_config(CONFIG_PATH, project_root=PROJECT_ROOT)

    summary = runtime.run()

    assert summary["status"] == "succeeded"
    assert summary["stop_reason"] == "all_agents_terminal"
    assert summary["policy_contract"] == "one_action_per_turn"
    assert summary["turn_count"] == 8
    assert summary["scheduler_trace"] == [
        "research_reader",
        "evidence_checker",
        "research_reader",
        "evidence_checker",
        "research_reader",
        "evidence_checker",
        "research_reader",
        "evidence_checker",
    ]
    assert summary["group_metrics"]["agents_completed"] == 2
    assert summary["group_metrics"]["policy_calls_total"] == 8
    assert summary["group_metrics"]["actions_attempted"] == 8
    assert summary["group_metrics"]["actions_succeeded"] == 7
    assert summary["group_metrics"]["actions_failed"] == 1
    assert summary["group_metrics"]["recovered_failures"] == 1

    reader = summary["per_agent"]["research_reader"]
    checker = summary["per_agent"]["evidence_checker"]
    assert reader["status"] == checker["status"] == "completed"
    assert reader["turn_count"] == checker["turn_count"] == 4
    assert len(reader["history"]) == len(checker["history"]) == 4
    assert {event["agent_id"] for event in reader["history"]} == {"research_reader"}
    assert {event["agent_id"] for event in checker["history"]} == {"evidence_checker"}

    assert checker["history"][0]["observation"]["error_code"] == "file_not_found"
    assert checker["history"][1]["action"]["parameters"]["path"].endswith(
        "recovery_note.txt"
    )
    assert checker["history"][1]["observation"]["success"] is True
    assert checker["recovered_failures"] == 1

    shared = summary["shared_environment"]
    assert shared["facts"]["architecture_audit_seen"] is True
    assert shared["operations"] == [
        {
            "operation": "publish",
            "key": "architecture_audit_seen",
            "agent_id": "research_reader",
        },
        {
            "operation": "read",
            "key": "architecture_audit_seen",
            "agent_id": "evidence_checker",
            "found": True,
        },
    ]
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["external_network"] is False


def test_role_allowlist_rejects_action_before_executor() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_file",
            description="Read a fixture.",
            family="files",
            parameter_names=("path",),
            required_parameters=("path",),
        ),
        lambda action, context: calls.append(action.tool_name)
        or ToolResult(success=True),
    )
    registry.register(
        ToolSpec(
            name="finish",
            description="Finish.",
            family="control",
        ),
        lambda action, context: ToolResult(success=True),
    )
    profiles = (
        _profile("restricted", ("finish",)),
        _profile("idle", ("finish",)),
    )
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="role_guard_test",
        profiles=profiles,
        policies={
            "restricted": RoleViolatingFakePolicy(
                Action("read_file", {"path": "docs/x.txt"})
            ),
            "idle": EarlyStopFakePolicy(),
        },
        tool_registry=registry,
        limits=RuntimeLimits(max_failures_per_agent=1),
    )

    summary = runtime.run()

    restricted = summary["per_agent"]["restricted"]
    assert summary["status"] == "failed"
    assert restricted["validation_rejections"] == 1
    assert restricted["history"][0]["observation"]["error_code"] == "tool_not_allowed"
    assert calls == []


def test_repetition_guard_stops_repeating_policy() -> None:
    registry = _simple_registry()
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="repetition_guard_test",
        profiles=(
            _profile("repeater", ("probe", "finish")),
            _profile("idle", ("finish",)),
        ),
        policies={
            "repeater": RepeatingFakePolicy(Action("probe")),
            "idle": EarlyStopFakePolicy(),
        },
        tool_registry=registry,
        limits=RuntimeLimits(
            max_turns_total=10,
            max_turns_per_agent=5,
            max_failures_per_agent=3,
            max_identical_actions=2,
        ),
    )

    summary = runtime.run()

    repeater = summary["per_agent"]["repeater"]
    assert summary["status"] == "failed"
    assert repeater["stop_reason"] == "repetition_guard"
    assert repeater["history"][-1]["observation"]["error_code"] == "repeated_action_detected"
    assert repeater["actions_succeeded"] == 2


def test_early_stop_policy_is_bounded() -> None:
    registry = _simple_registry()
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="early_stop_test",
        profiles=(
            _profile("early", ("finish",)),
            _profile("finisher", ("finish",)),
        ),
        policies={
            "early": EarlyStopFakePolicy(),
            "finisher": PerfectFakePolicy((Action("finish"),)),
        },
        tool_registry=registry,
    )

    summary = runtime.run()

    assert summary["status"] == "failed"
    assert summary["turn_count"] == 2
    assert summary["per_agent"]["early"]["stop_reason"] == "policy_stopped"
    assert summary["per_agent"]["finisher"]["status"] == "completed"


def test_fixture_article_tools_are_stepwise_and_read_only() -> None:
    registry, environment = build_default_tool_registry(project_root=PROJECT_ROOT)
    profile = AgentProfile(
        agent_id="article_reader",
        role="Article reader",
        goal="Read the safety section.",
        allowed_tools=(
            "browser_article_open",
            "browser_article_find",
            "browser_article_read",
            "finish",
        ),
    )
    state = _state_for(profile)
    context = ToolExecutionContext(
        runtime_id="article_test",
        turn_index=1,
        agent_state=state,
        shared_environment=environment,
    )

    opened = registry.execute(
        Action(
            "browser_article_open",
            {"url": "https://fixture.local/articles/runtime"},
        ),
        context,
    )
    found = registry.execute(
        Action("browser_article_find", {"query": "external network"}),
        context,
    )
    read = registry.execute(Action("browser_article_read"), context)

    assert opened.success is True
    assert found.success is True
    assert read.success is True
    assert read.output["visible_section"]["heading"] == "Safety"
    assert "browser_click" not in registry.names()


def test_local_policy_refuses_without_explicit_opt_in() -> None:
    class FakeClient:
        base_url = "http://127.0.0.1:8080/v1"

        def generate_next_action(self, agent_state):  # type: ignore[no-untyped-def]
            raise AssertionError("client must not be called")

    policy = LocalOpenAIModelPolicy(client=FakeClient())  # type: ignore[arg-type]
    profile = _profile("local_agent", ("finish",))

    with pytest.raises(PolicyError) as exc_info:
        policy.next_action(_state_for(profile), None, ())

    assert exc_info.value.error_code == "allow_model_calls_required"
    assert policy.model_execution_attempted is False


def test_local_policy_adapts_one_next_action_not_workflow_json() -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        base_url = "http://localhost:8080/v1"

        def generate_next_action(self, agent_state):  # type: ignore[no-untyped-def]
            calls.append(agent_state)
            return NextAction(
                action_name="finish",
                parameters={},
            )

    policy = LocalOpenAIModelPolicy(  # type: ignore[arg-type]
        client=FakeClient(),
        allow_model_calls=True,
    )
    profile = _profile("local_agent", ("finish",))

    action = policy.next_action(_state_for(profile), None, ())

    assert action == Action(
        tool_name="finish",
        parameters={},
    )
    assert len(calls) == 1
    assert "Return exactly one action object" in calls[0]["instruction"]
    assert "do not repeat it unchanged" in calls[0]["instruction"]
    assert calls[0]["available_actions"] == []
    assert calls[0]["shared_facts"] == {}
    assert calls[0]["protocol"]["disable_thinking"] is True
    assert "actions" not in action.to_dict()


def test_action_and_profile_reject_browser_click() -> None:
    with pytest.raises(ValueError, match="browser_click"):
        Action("browser_click")

    with pytest.raises(ValueError, match="browser_click"):
        AgentProfile(
            agent_id="clicker",
            role="Invalid",
            goal="Click",
            allowed_tools=("browser_click",),
        )


def test_summary_does_not_expose_local_absolute_paths() -> None:
    runtime = load_runtime_from_config(CONFIG_PATH, project_root=PROJECT_ROOT)

    rendered = json.dumps(runtime.run(), ensure_ascii=False)

    assert str(PROJECT_ROOT) not in rendered
    assert "resolved_path" not in rendered


def test_summary_preserves_secret_key_but_redacts_value() -> None:
    registry = _simple_registry()
    registry.register(
        ToolSpec(
            name="shared_publish_fact",
            description="Publish a shared fact.",
            family="coordination",
            required_parameters=("key", "value"),
            parameter_names=("key", "value"),
        ),
        lambda action, context: (
            context.shared_environment.publish_fact(
                key=str(action.parameters["key"]),
                value=action.parameters["value"],
                agent_id=context.agent_state.agent_id,
            )
            or ToolResult(success=True)
        ),
    )
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="summary_redaction_test",
        profiles=(
            _profile("publisher", ("shared_publish_fact", "finish")),
            _profile("finisher", ("finish",)),
        ),
        policies={
            "publisher": PerfectFakePolicy(
                (
                    Action(
                        "shared_publish_fact",
                        {"key": "api_key", "value": "supersecret"},
                    ),
                    Action("finish"),
                )
            ),
            "finisher": PerfectFakePolicy((Action("finish"),)),
        },
        tool_registry=registry,
    )

    rendered = json.dumps(runtime.run(), ensure_ascii=False)

    assert "api_key" in rendered
    assert "supersecret" not in rendered
    assert "<redacted>" in rendered


def test_cli_fake_smoke_succeeds_without_model_or_browser() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_autonomous_multi_agent_runtime.py",
            "--config",
            "configs/canonical_multi_agent.example.json",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "succeeded"
    assert summary["turn_count"] == 8
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert "\n" not in completed.stdout.strip()
    assert str(PROJECT_ROOT) not in completed.stdout


def _profile(agent_id: str, allowed_tools: tuple[str, ...]) -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        role=f"{agent_id} role",
        goal=f"{agent_id} goal",
        allowed_tools=allowed_tools,
    )


def _simple_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="probe",
            description="Return a deterministic probe result.",
            family="test",
        ),
        lambda action, context: ToolResult(success=True, output="ok"),
    )
    registry.register(
        ToolSpec(
            name="finish",
            description="Finish.",
            family="control",
        ),
        lambda action, context: ToolResult(success=True),
    )
    return registry


def _state_for(profile: AgentProfile) -> AgentState:
    return AgentState(profile=profile)
