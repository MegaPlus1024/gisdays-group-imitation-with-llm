from __future__ import annotations

import importlib
import json
from pathlib import Path

from src.agent.autonomous_browser_runtime import (
    BROWSER_RUNTIME_ACTION_NAMES,
    BrowserRuntimeAction,
    BrowserRuntimePolicy,
    BrowserRuntimeSession,
    BrowserRuntimeVerifier,
    FixtureBackedBrowserRuntimeExecutor,
    PlaywrightBrowserRuntimeExecutor,
    browser_session_resource_lock,
    make_browser_runtime_action_executor,
)
from src.agent.autonomous_multi_agent_runtime import (
    AutonomousMultiAgentRuntime,
    RuntimeActionDecision,
    RuntimeAgentSpec,
    RuntimePolicy,
    RuntimeSharedState,
    RuntimeTask,
    RuntimeVirtualEnvironment,
    RuntimeWorkspace,
)
from src.agent.scripts.browser_playwright_activity import PlaywrightBrowserActivityConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"


def _session(**overrides: object) -> BrowserRuntimeSession:
    values = {
        "session_id": "browser_session",
        "agent_id": "agent_a",
        "workspace_id": "workspace_a",
        "environment_id": "env_a",
        "allowed_domains": ("localhost", "127.0.0.1", "local-intranet.test"),
    }
    values.update(overrides)
    return BrowserRuntimeSession(**values)  # type: ignore[arg-type]


def _executor(policy: BrowserRuntimePolicy | None = None) -> FixtureBackedBrowserRuntimeExecutor:
    return FixtureBackedBrowserRuntimeExecutor(
        fixture_manifest_path=MANIFEST_PATH,
        project_root=PROJECT_ROOT,
        policy=policy,
    )


def _action(name: str, **parameters: object) -> BrowserRuntimeAction:
    return BrowserRuntimeAction(
        agent_id="agent_a",
        action_type="browser",
        action_name=name,
        parameters=dict(parameters),
        session_id="browser_session",
    )


def test_browser_session_initializes_with_safe_metadata() -> None:
    session = _session(start_url="http://local-intranet.test/")

    summary = session.to_summary()

    assert summary["schema_version"] == "autonomous_browser_runtime_summary_v1"
    assert summary["session_id"] == "browser_session"
    assert summary["current_url"] == "http://local-intranet.test/"
    assert summary["visited_url_count"] == 1
    assert json.loads(json.dumps(summary))["environment_id"] == "env_a"


def test_browser_action_rejects_when_namespace_disabled() -> None:
    state = RuntimeSharedState.from_specs([RuntimeAgentSpec("agent_a")], [RuntimeTask("task")])
    action_executor = make_browser_runtime_action_executor(
        _executor(),
        {},
        allowed_resource_namespaces=("files",),
    )

    result = action_executor(
        RuntimeActionDecision(
            agent_id="agent_a",
            action_type="browser",
            action_name="browser_open_url",
            parameters={"url": "http://local-intranet.test/"},
            task_id="task",
        ),
        state,
    )

    assert result.success is False
    assert result.error_type == "browser_namespace_disabled"
    assert state.group_event_log[-1].event_type == "browser_policy_denied"


def test_browser_action_accepts_when_namespace_enabled() -> None:
    sessions: dict[str, BrowserRuntimeSession] = {}
    state = RuntimeSharedState.from_specs([RuntimeAgentSpec("agent_a")], [RuntimeTask("task")])
    action_executor = make_browser_runtime_action_executor(
        _executor(),
        sessions,
        allowed_resource_namespaces=("browser",),
    )

    result = action_executor(
        RuntimeActionDecision(
            agent_id="agent_a",
            action_type="browser",
            action_name="browser_open_url",
            parameters={"url": "http://local-intranet.test/"},
            task_id="task",
        ),
        state,
    )

    assert result.success is True
    assert sessions["agent_a_browser"].current_url == "http://local-intranet.test/"
    assert state.group_event_log[-1].event_type == "browser_action_observed"


def test_disallowed_url_scheme_rejected() -> None:
    session = _session()

    result = _executor().execute(
        _action("browser_open_url", url="file:///tmp/page.html"),
        session,
    )

    assert result.success is False
    assert result.error_type == "browser_url_denied"
    assert session.policy_denials == 1


def test_disallowed_domain_rejected() -> None:
    session = _session(allowed_domains=("local-intranet.test",))

    result = _executor().execute(
        _action("browser_open_url", url="https://example.com/report"),
        session,
    )

    assert result.success is False
    assert result.error_type == "browser_domain_denied"
    assert session.actions_failed == 1


def test_fixture_open_url_succeeds() -> None:
    session = _session()

    result = _executor().execute(
        _action("browser_open_url", url="http://local-intranet.test/tickets/1"),
        session,
    )

    assert result.success is True
    assert result.observation is not None
    assert result.observation.title == "Ticket 1 - Quarterly Access Review"
    assert "Quarterly Access Review" in result.observation.text_preview
    assert result.metadata["network_used"] is False
    assert session.current_url == "http://local-intranet.test/tickets/1"


def test_fixture_extract_text_returns_bounded_text() -> None:
    session = _session(current_url="http://local-intranet.test/tickets/1")

    result = _executor(BrowserRuntimePolicy(max_text_chars=40)).execute(
        _action("browser_extract_text"),
        session,
    )

    assert result.success is True
    assert isinstance(result.output, str)
    assert len(result.output) <= 40
    assert "Ticket 1" in result.output


def test_fixture_click_moves_to_target_fixture() -> None:
    session = _session(current_url="http://local-intranet.test/tickets/1")

    result = _executor().execute(
        _action("browser_click", target_text="Workspace policy"),
        session,
    )

    assert result.success is True
    assert session.current_url == "http://local-intranet.test/docs/policy"
    assert result.observation is not None
    assert result.observation.title == "Workspace Policy"


def test_fixture_search_returns_deterministic_results() -> None:
    session = _session()

    result = _executor().execute(
        _action("browser_search", query="workspace policy"),
        session,
    )

    assert result.success is True
    assert result.output["results"][0]["fixture_route"] == "/docs/policy"  # type: ignore[index]
    assert result.metadata["result_count"] >= 1


def test_fixture_fill_and_submit_update_synthetic_form_state() -> None:
    session = _session(current_url="http://local-intranet.test/tickets/1")
    executor = _executor()

    fill = executor.execute(
        _action("browser_fill", fields={"status": "ready", "owner": "office"}),
        session,
    )
    submit = executor.execute(_action("browser_submit"), session)

    assert fill.success is True
    assert submit.success is True
    assert session.form_state["http://local-intranet.test/tickets/1"]["status"] == "ready"
    assert session.form_state["http://local-intranet.test/tickets/1"]["_submitted"] == "true"


def test_snapshot_emits_json_serializable_observation() -> None:
    session = _session(current_url="http://local-intranet.test/tickets/1")

    result = _executor().execute(_action("browser_snapshot"), session)

    assert result.success is True
    assert result.observation is not None
    assert result.observation.snapshot_id == "browser_session-snapshot-1"
    assert result.artifact_refs == ("browser/browser_session/browser_session-snapshot-1.json",)
    assert session.to_summary()["snapshot_count"] == 1
    assert json.loads(json.dumps(result.to_dict()))["success"] is True


def test_browser_verifier_passes_on_expected_text() -> None:
    session = _session()
    result = _executor().execute(
        _action("browser_open_url", url="http://local-intranet.test/tickets/1"),
        session,
    )

    verification = BrowserRuntimeVerifier().verify(result, expected_text="Quarterly Access Review")

    assert verification.passed is True


def test_browser_verifier_fails_on_missing_expected_text() -> None:
    session = _session()
    result = _executor().execute(
        _action("browser_open_url", url="http://local-intranet.test/tickets/1"),
        session,
    )

    verification = BrowserRuntimeVerifier().verify(result, expected_text="does not exist")

    assert verification.passed is False
    assert verification.reason == "expected_text_missing"


def test_runtime_integration_executes_browser_action_through_injected_executor() -> None:
    sessions: dict[str, BrowserRuntimeSession] = {}
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="browser_runtime",
        agents=[RuntimeAgentSpec("agent_a")],
        tasks=[RuntimeTask("task")],
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id="env",
            workspace=RuntimeWorkspace("runtime/workspace"),
            allowed_resource_namespaces=("files", "browser"),
        ),
        decision_provider=lambda agent, state: RuntimeActionDecision(
            agent_id=agent.agent_id,
            action_type="browser",
            action_name="browser_open_url",
            parameters={"url": "http://local-intranet.test/tickets/1"},
            task_id="task",
        ),
        action_executor=make_browser_runtime_action_executor(_executor(), sessions),
    )

    result = runtime.step()

    assert result.status == "success"
    assert runtime.shared_state.tasks["task"].status == "completed"
    assert "browser:agent_a_browser:last_observation" in runtime.shared_state.shared_facts
    assert sessions["agent_a_browser"].current_url == "http://local-intranet.test/tickets/1"


def test_browser_resource_lock_prevents_conflicting_session_use() -> None:
    state = RuntimeSharedState.from_specs([RuntimeAgentSpec("agent_a"), RuntimeAgentSpec("agent_b")], [RuntimeTask("task")])
    assert state.acquire_lock(browser_session_resource_lock("browser_session"), "agent_b") is True
    executor_called = False

    def executor(decision: RuntimeActionDecision, shared: RuntimeSharedState) -> object:
        nonlocal executor_called
        executor_called = True
        return make_browser_runtime_action_executor(_executor(), {})(decision, shared)

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="browser_lock",
        shared_state=state,
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id="env",
            workspace=RuntimeWorkspace("runtime/workspace"),
            allowed_resource_namespaces=("browser",),
        ),
        policy=RuntimePolicy(idle_tick_limit=5),
        decision_provider=lambda agent, shared: RuntimeActionDecision(
            agent_id=agent.agent_id,
            action_type="browser",
            action_name="browser_open_url",
            parameters={"url": "http://local-intranet.test/"},
            task_id="task",
            resource_locks=(browser_session_resource_lock("browser_session"),),
        ),
        action_executor=executor,  # type: ignore[arg-type]
    )

    result = runtime.step()

    assert result.status == "blocked"
    assert executor_called is False
    assert state.resource_locks[browser_session_resource_lock("browser_session")] == "agent_b"


def test_policy_denial_is_recorded_as_structured_event() -> None:
    sessions: dict[str, BrowserRuntimeSession] = {}
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="browser_policy_denial",
        agents=[RuntimeAgentSpec("agent_a")],
        tasks=[RuntimeTask("task")],
        policy=RuntimePolicy(max_retries_per_task=0),
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id="env",
            workspace=RuntimeWorkspace("runtime/workspace"),
            allowed_resource_namespaces=("browser",),
        ),
        decision_provider=lambda agent, state: RuntimeActionDecision(
            agent_id=agent.agent_id,
            action_type="browser",
            action_name="browser_open_url",
            parameters={"url": "https://example.com/report"},
            task_id="task",
        ),
        action_executor=make_browser_runtime_action_executor(_executor(), sessions),
    )

    result = runtime.step()

    assert result.status == "failed"
    assert result.action_result is not None
    assert result.action_result.error_type == "browser_domain_denied"
    assert any(event.event_type == "browser_policy_denied" for event in runtime.shared_state.group_event_log)


def test_playwright_adapter_is_import_safe_and_does_not_launch_browser() -> None:
    importlib.import_module("src.agent.autonomous_browser_runtime")

    def fail_loader() -> object:
        raise AssertionError("disabled Playwright adapter must not load Playwright")

    result = PlaywrightBrowserRuntimeExecutor(
        config=PlaywrightBrowserActivityConfig(enabled=False),
        dependency_loader=fail_loader,
    ).execute(
        _action("browser_open_url", url="http://127.0.0.1:8088/tickets/1"),
        _session(allowed_domains=("127.0.0.1",)),
    )

    assert result.success is False
    assert result.error_type == "real_browser_automation_disabled"
    assert result.metadata["browser_launched"] is False
    assert result.metadata["real_browser_automation"] is False


def test_no_mail_git_calendar_actions_are_added() -> None:
    names = set(BROWSER_RUNTIME_ACTION_NAMES)

    assert "mail_send" not in names
    assert "git_commit" not in names
    assert "calendar_create_event" not in names
    assert all(name.startswith("browser_") for name in names)


def test_fixture_executor_makes_no_real_http_browser_api_or_model_calls() -> None:
    session = _session()

    result = _executor().execute(
        _action("browser_open_url", url="http://local-intranet.test/tickets/1"),
        session,
    )

    assert result.success is True
    assert result.metadata["network_used"] is False
    assert result.metadata["browser_opened"] is False
    assert result.observation is not None
    assert result.observation.metadata["real_network_traffic"] is False
