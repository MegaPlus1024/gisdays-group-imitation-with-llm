from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from src.agent.autonomous_multi_agent_runtime import (
    Action,
    AgentProfile,
    AgentState,
    LocalOpenAIModelPolicy,
    Observation,
    PolicyError,
    ToolResult,
    ToolSpec,
)
from src.agent.canonical_multi_agent_experiments import (
    CONFIG_SCHEMA_VERSION,
    EXPERIMENT_SUMMARY_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
    TRIAL_SUMMARY_SCHEMA_VERSION,
    _bounded_value,
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
    assert verification["input_tokens_total"] == 0
    assert verification["output_tokens_total"] == 0
    assert "constrained_fixture_command" in verification["unique_action_names"]
    assert summary["trial_metrics"]["recovery_success_rate"] == 1.0  # type: ignore[index]


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
