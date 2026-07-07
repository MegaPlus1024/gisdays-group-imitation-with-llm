from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .autonomous_browser_runtime import (
    BROWSER_RUNTIME_ACTION_NAMES,
    BrowserRuntimePolicy,
    BrowserRuntimeSession,
    FixtureBackedBrowserRuntimeExecutor,
    browser_session_resource_lock,
    make_browser_runtime_action_executor,
)
from .autonomous_multi_agent_runtime import (
    AutonomousMultiAgentRuntime,
    RuntimeActionDecision,
    RuntimeActionResult,
    RuntimeAgentSpec,
    RuntimePolicy,
    RuntimeSharedState,
    RuntimeTask,
    RuntimeVirtualEnvironment,
    RuntimeWorkspace,
)
from .autonomous_browser_scenario_coverage import build_browser_scenario_coverage


SCENARIO_SCHEMA_VERSION = "autonomous_runtime_scenario_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_runtime_scenario_summary_v1"
FORBIDDEN_ACTION_PREFIXES = ("mail_", "git_", "calendar_", "email_")
FORBIDDEN_ACTION_NAMES = {"send_mail", "git_commit", "calendar_create_event"}


class AutonomousRuntimeScenarioValidationError(ValueError):
    """Raised for expected config validation failures."""


@dataclass(frozen=True)
class AutonomousRuntimeAgentConfig:
    agent_id: str
    role: str = ""
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousRuntimeAgentConfig:
        return cls(
            agent_id=_required_id(payload, "agent_id"),
            role=str(payload.get("role", "")),
            priority=_int(payload.get("priority", 0), "priority"),
            metadata=_dict(payload.get("metadata", {}), "metadata"),
        )


@dataclass(frozen=True)
class AutonomousRuntimeTaskConfig:
    task_id: str
    description: str = ""
    priority: int = 0
    assigned_agent_id: str | None = None
    depends_on: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousRuntimeTaskConfig:
        assigned = payload.get("assigned_agent_id")
        metadata = _dict(payload.get("metadata", {}), "metadata")
        depends_on = tuple(_string_list(payload.get("depends_on", []), "depends_on"))
        if depends_on:
            metadata = {**metadata, "depends_on": list(depends_on)}
        return cls(
            task_id=_required_id(payload, "task_id"),
            description=str(payload.get("description", "")),
            priority=_int(payload.get("priority", 0), "priority"),
            assigned_agent_id=str(assigned).strip() if assigned is not None else None,
            depends_on=depends_on,
            metadata=metadata,
        )


@dataclass(frozen=True)
class AutonomousRuntimeBrowserSessionConfig:
    session_id: str
    agent_id: str
    workspace_id: str
    environment_id: str
    allowed_domains: tuple[str, ...]
    start_url: str | None = None
    fixture_manifest_path: str = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousRuntimeBrowserSessionConfig:
        return cls(
            session_id=_required_id(payload, "session_id"),
            agent_id=_required_id(payload, "agent_id"),
            workspace_id=_required_id(payload, "workspace_id"),
            environment_id=_required_id(payload, "environment_id"),
            allowed_domains=tuple(_string_list(payload.get("allowed_domains"), "allowed_domains")),
            start_url=_optional_str(payload.get("start_url")),
            fixture_manifest_path=_safe_relative_path(
                str(payload.get("fixture_manifest_path", "tests/fixtures/local_intranet/office_site_v1/site_manifest.json")),
                "fixture_manifest_path",
            ),
            metadata=_dict(payload.get("metadata", {}), "metadata"),
        )


@dataclass(frozen=True)
class AutonomousRuntimeScriptedStep:
    step_id: str
    agent_id: str
    task_id: str
    browser_session_id: str
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_text: str | None = None
    expected_url: str | None = None
    required_artifact_ref: str | None = None
    resource_locks: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousRuntimeScriptedStep:
        session_id = _required_id(payload, "browser_session_id")
        raw_locks = tuple(_string_list(payload.get("resource_locks", []), "resource_locks"))
        locks = raw_locks or (browser_session_resource_lock(session_id),)
        return cls(
            step_id=_required_id(payload, "step_id"),
            agent_id=_required_id(payload, "agent_id"),
            task_id=_required_id(payload, "task_id"),
            browser_session_id=session_id,
            action_name=_required_id(payload, "action_name"),
            parameters=_dict(payload.get("parameters", {}), "parameters"),
            expected_text=_optional_str(payload.get("expected_text")),
            expected_url=_optional_str(payload.get("expected_url")),
            required_artifact_ref=_optional_str(payload.get("required_artifact_ref")),
            resource_locks=locks,
            metadata=_dict(payload.get("metadata", {}), "metadata"),
        )


@dataclass(frozen=True)
class AutonomousRuntimeScenario:
    schema_version: str
    scenario_id: str
    description: str
    agents: tuple[AutonomousRuntimeAgentConfig, ...]
    tasks: tuple[AutonomousRuntimeTaskConfig, ...]
    virtual_environment: dict[str, Any]
    browser_sessions: tuple[AutonomousRuntimeBrowserSessionConfig, ...]
    scripted_steps: tuple[AutonomousRuntimeScriptedStep, ...]
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    expected_results: tuple[dict[str, Any], ...] = ()
    validation_warnings: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousRuntimeScenario:
        scenario = cls(
            schema_version=str(payload.get("schema_version", "")),
            scenario_id=_required_id(payload, "scenario_id"),
            description=str(payload.get("description", "")),
            agents=tuple(AutonomousRuntimeAgentConfig.from_dict(item) for item in _dict_list(payload.get("agents"), "agents")),
            tasks=tuple(AutonomousRuntimeTaskConfig.from_dict(item) for item in _dict_list(payload.get("tasks"), "tasks")),
            virtual_environment=_dict(payload.get("virtual_environment", {}), "virtual_environment"),
            browser_sessions=tuple(
                AutonomousRuntimeBrowserSessionConfig.from_dict(item)
                for item in _dict_list(payload.get("browser_sessions"), "browser_sessions")
            ),
            scripted_steps=tuple(
                AutonomousRuntimeScriptedStep.from_dict(item)
                for item in _dict_list(payload.get("scripted_steps"), "scripted_steps")
            ),
            runtime_policy=_dict(payload.get("runtime_policy", {}), "runtime_policy"),
            expected_results=tuple(_dict(item, "expected_results item") for item in payload.get("expected_results", [])),
            validation_warnings=tuple(_string_list(payload.get("validation_warnings", []), "validation_warnings")),
        )
        return scenario.validate()

    def validate(self) -> AutonomousRuntimeScenario:
        if self.schema_version != SCENARIO_SCHEMA_VERSION:
            raise AutonomousRuntimeScenarioValidationError("schema_version does not match autonomous_runtime_scenario_v1.")
        if not self.agents:
            raise AutonomousRuntimeScenarioValidationError("agents must be non-empty.")
        if not self.tasks:
            raise AutonomousRuntimeScenarioValidationError("tasks must be non-empty.")
        if not self.browser_sessions:
            raise AutonomousRuntimeScenarioValidationError("browser_sessions must be non-empty.")
        if not self.scripted_steps:
            raise AutonomousRuntimeScenarioValidationError("scripted_steps must be non-empty.")

        agent_ids = [agent.agent_id for agent in self.agents]
        task_ids = [task.task_id for task in self.tasks]
        session_ids = [session.session_id for session in self.browser_sessions]
        _reject_duplicates(agent_ids, "agent_id")
        _reject_duplicates(task_ids, "task_id")
        _reject_duplicates(session_ids, "browser session_id")

        agent_set = set(agent_ids)
        task_set = set(task_ids)
        session_map = {session.session_id: session for session in self.browser_sessions}
        for task in self.tasks:
            if task.assigned_agent_id is not None and task.assigned_agent_id not in agent_set:
                raise AutonomousRuntimeScenarioValidationError(f"Task '{task.task_id}' references unknown agent.")
            for dependency in task.depends_on:
                if dependency not in task_set:
                    raise AutonomousRuntimeScenarioValidationError(f"Task '{task.task_id}' references unknown dependency.")
                if dependency == task.task_id:
                    raise AutonomousRuntimeScenarioValidationError(f"Task '{task.task_id}' cannot depend on itself.")

        namespaces = tuple(_string_list(self.virtual_environment.get("allowed_resource_namespaces", []), "allowed_resource_namespaces"))
        if "browser" not in namespaces:
            raise AutonomousRuntimeScenarioValidationError("virtual_environment must include the browser namespace.")
        workspace = _dict(self.virtual_environment.get("workspace", {}), "virtual_environment.workspace")
        _safe_relative_path(str(workspace.get("workspace_root", "runtime/workspace")), "workspace_root")
        per_agent = _dict(workspace.get("per_agent_workspaces", {}), "per_agent_workspaces")
        for value in per_agent.values():
            _safe_relative_path(str(value), "per_agent_workspace")

        for session in self.browser_sessions:
            if session.agent_id not in agent_set:
                raise AutonomousRuntimeScenarioValidationError(f"Browser session '{session.session_id}' references unknown agent.")
            if not session.allowed_domains:
                raise AutonomousRuntimeScenarioValidationError("browser sessions require explicit allowed_domains.")
            if session.start_url:
                _validate_url_allowed(session.start_url, session.allowed_domains)

        for step in self.scripted_steps:
            if step.agent_id not in agent_set:
                raise AutonomousRuntimeScenarioValidationError(f"Step '{step.step_id}' references unknown agent.")
            if step.task_id not in task_set:
                raise AutonomousRuntimeScenarioValidationError(f"Step '{step.step_id}' references unknown task.")
            if step.browser_session_id not in session_map:
                raise AutonomousRuntimeScenarioValidationError(f"Step '{step.step_id}' references unknown browser session.")
            if _is_forbidden_action(step.action_name):
                raise AutonomousRuntimeScenarioValidationError(f"Forbidden external action is not allowed: {step.action_name}")
            if step.action_name not in BROWSER_RUNTIME_ACTION_NAMES:
                raise AutonomousRuntimeScenarioValidationError(f"Browser action is not allowlisted: {step.action_name}")
            _validate_step_urls(step, session_map[step.browser_session_id])

        policy = _runtime_policy_from_dict(self.runtime_policy)
        if policy.max_ticks <= 0 or policy.max_ticks > 1_000:
            raise AutonomousRuntimeScenarioValidationError("runtime_policy.max_ticks must be between 1 and 1000.")
        if policy.max_actions_total <= 0 or policy.max_actions_total > 1_000:
            raise AutonomousRuntimeScenarioValidationError("runtime_policy.max_actions_total must be between 1 and 1000.")
        return self


@dataclass
class BuiltAutonomousRuntimeScenario:
    scenario: AutonomousRuntimeScenario
    runtime: AutonomousMultiAgentRuntime
    shared_state: RuntimeSharedState
    browser_sessions: dict[str, BrowserRuntimeSession]
    decision_provider: ScriptedRuntimeDecisionProvider
    validation_warnings: list[str] = field(default_factory=list)

    def run(self) -> dict[str, Any]:
        self.runtime.run()
        return build_autonomous_runtime_scenario_summary(self)


class ScriptedRuntimeDecisionProvider:
    def __init__(self, steps: tuple[AutonomousRuntimeScriptedStep, ...]) -> None:
        self.steps = steps
        self._consumed: set[str] = set()
        self.exhausted_events: list[dict[str, Any]] = []
        self.dependency_block_events: list[dict[str, Any]] = []

    def __call__(self, agent: RuntimeAgentSpec, state: RuntimeSharedState) -> RuntimeActionDecision | None:
        task_id = state.task_assignments.get(agent.agent_id)
        if task_id is not None:
            unmet = _unmet_task_dependencies(task_id, state)
            if unmet:
                event = {"agent_id": agent.agent_id, "task_id": task_id, "reason": "task_dependencies_unmet", "unmet_dependencies": unmet}
                self.dependency_block_events.append(event)
                state.record_event(
                    "task_dependency_blocked",
                    "Scheduled task is waiting for declared dependencies.",
                    agent_id=agent.agent_id,
                    task_id=task_id,
                    severity="warning",
                    metadata={"unmet_dependencies": unmet},
                )
                return None
        for step in self.steps:
            if step.step_id in self._consumed:
                continue
            if step.agent_id != agent.agent_id:
                continue
            if task_id is not None and step.task_id != task_id:
                continue
            if task_id is None and step.task_id not in state.tasks:
                continue
            self._consumed.add(step.step_id)
            parameters = dict(step.parameters)
            parameters["session_id"] = step.browser_session_id
            return RuntimeActionDecision(
                agent_id=step.agent_id,
                action_type="browser",
                action_name=step.action_name,
                parameters=parameters,
                task_id=step.task_id,
                resource_locks=step.resource_locks,
                metadata={
                    "scripted_step_id": step.step_id,
                    "browser_session_id": step.browser_session_id,
                    "expected_text": step.expected_text,
                    "expected_url": step.expected_url,
                    "required_artifact_ref": step.required_artifact_ref,
                    **step.metadata,
                },
            )

        self.exhausted_events.append({"agent_id": agent.agent_id, "task_id": task_id, "reason": "scripted_steps_exhausted"})
        state.record_event(
            "scripted_steps_exhausted",
            "Scripted decision provider has no step for the scheduled agent/task.",
            agent_id=agent.agent_id,
            task_id=task_id,
            severity="warning",
        )
        return None


class AutonomousRuntimeScenarioBuilder:
    def __init__(self, scenario: AutonomousRuntimeScenario, *, fixture_root: Path | None = None) -> None:
        self.scenario = scenario
        self.fixture_root = fixture_root

    def build(self) -> BuiltAutonomousRuntimeScenario:
        shared_state = RuntimeSharedState.from_specs(
            [
                RuntimeAgentSpec(
                    agent.agent_id,
                    role=agent.role,
                    priority=agent.priority,
                    metadata=dict(agent.metadata),
                )
                for agent in self.scenario.agents
            ],
            [
                RuntimeTask(
                    task.task_id,
                    description=task.description,
                    priority=task.priority,
                    assigned_agent_id=task.assigned_agent_id,
                    metadata=dict(task.metadata),
                )
                for task in self.scenario.tasks
            ],
        )
        virtual_environment = _virtual_environment_from_dict(self.scenario.virtual_environment)
        browser_sessions = {
            session.session_id: BrowserRuntimeSession(
                session_id=session.session_id,
                agent_id=session.agent_id,
                workspace_id=session.workspace_id,
                environment_id=session.environment_id,
                allowed_domains=session.allowed_domains,
                start_url=session.start_url,
                policy_flags=BrowserRuntimePolicy().to_flags(),
            )
            for session in self.scenario.browser_sessions
        }
        fixture_manifest_path = _common_fixture_manifest_path(self.scenario.browser_sessions)
        project_root = self.fixture_root or Path(".")
        browser_executor = FixtureBackedBrowserRuntimeExecutor(
            fixture_manifest_path=fixture_manifest_path,
            project_root=project_root,
            policy=BrowserRuntimePolicy(),
        )
        decision_provider = ScriptedRuntimeDecisionProvider(self.scenario.scripted_steps)
        runtime = AutonomousMultiAgentRuntime(
            runtime_id=self.scenario.scenario_id,
            shared_state=shared_state,
            policy=_runtime_policy_from_dict(self.scenario.runtime_policy),
            virtual_environment=virtual_environment,
            decision_provider=decision_provider,
            action_executor=make_browser_runtime_action_executor(
                browser_executor,
                browser_sessions,
                allowed_resource_namespaces=virtual_environment.allowed_resource_namespaces,
                default_workspace_id=virtual_environment.workspace.workspace_root,
                default_environment_id=virtual_environment.environment_id,
            ),
            verifier=_scenario_step_verifier,
        )
        return BuiltAutonomousRuntimeScenario(
            scenario=self.scenario,
            runtime=runtime,
            shared_state=shared_state,
            browser_sessions=browser_sessions,
            decision_provider=decision_provider,
            validation_warnings=list(self.scenario.validation_warnings),
        )


def load_autonomous_runtime_scenario(path: str | Path) -> AutonomousRuntimeScenario:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AutonomousRuntimeScenarioValidationError("Scenario JSON is malformed.") from exc
    except OSError as exc:
        raise AutonomousRuntimeScenarioValidationError("Scenario file could not be read.") from exc
    if not isinstance(payload, dict):
        raise AutonomousRuntimeScenarioValidationError("Scenario root must be a JSON object.")
    try:
        return AutonomousRuntimeScenario.from_dict(payload)
    except AutonomousRuntimeScenarioValidationError:
        raise
    except Exception as exc:
        raise AutonomousRuntimeScenarioValidationError(str(exc)) from exc


def build_autonomous_runtime_from_scenario(
    scenario: AutonomousRuntimeScenario,
    fixture_root: Path | None = None,
) -> BuiltAutonomousRuntimeScenario:
    return AutonomousRuntimeScenarioBuilder(scenario, fixture_root=fixture_root).build()


def run_autonomous_runtime_scenario(
    scenario: AutonomousRuntimeScenario,
    *,
    fixture_root: Path | None = None,
) -> dict[str, Any]:
    built = build_autonomous_runtime_from_scenario(scenario, fixture_root=fixture_root)
    return built.run()


def write_autonomous_runtime_scenario_summary(summary: Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    _validate_safe_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    return path


def build_autonomous_runtime_scenario_summary(built: BuiltAutonomousRuntimeScenario) -> dict[str, Any]:
    runtime_summary = built.runtime.to_summary()
    expected = _evaluate_expected_results(built)
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "scenario_id": built.scenario.scenario_id,
        "status": runtime_summary["status"],
        "stop_reason": runtime_summary["stop_reason"],
        "tick_count": runtime_summary["tick_count"],
        "action_count": runtime_summary["action_count"],
        "task_counts": runtime_summary["task_counts"],
        "agent_counts": runtime_summary["agent_counts"],
        "browser_session_summaries": {
            session_id: session.to_summary()
            for session_id, session in sorted(built.browser_sessions.items())
        },
        "runtime_summary": runtime_summary,
        "expected_results": expected,
        "expected_results_passed": all(item["passed"] for item in expected),
        "task_dependency_status": _task_dependency_status(built.shared_state),
        "validation_warnings": list(built.validation_warnings),
        "scripted_provider": {
            "consumed_step_count": len(built.decision_provider._consumed),
            "exhausted_events": list(built.decision_provider.exhausted_events),
            "dependency_block_events": list(built.decision_provider.dependency_block_events),
        },
        "no_runtime_execution": True,
    }
    summary["browser_coverage"] = build_browser_scenario_coverage(built.scenario, summary)
    return summary


def _scenario_step_verifier(
    decision: RuntimeActionDecision,
    result: RuntimeActionResult,
    state: RuntimeSharedState,
) -> bool:
    del state
    if not result.success:
        return False
    browser_result = result.metadata.get("browser_result") if isinstance(result.metadata, dict) else None
    observation = browser_result.get("observation") if isinstance(browser_result, dict) else None
    text = str(observation.get("text_preview", "")) if isinstance(observation, dict) else ""
    current_url = observation.get("current_url") if isinstance(observation, dict) else None
    expected_text = decision.metadata.get("expected_text")
    expected_url = decision.metadata.get("expected_url")
    required_artifact = decision.metadata.get("required_artifact_ref")
    if isinstance(expected_text, str) and expected_text not in text:
        return False
    if isinstance(expected_url, str) and current_url != expected_url:
        return False
    if isinstance(required_artifact, str) and required_artifact not in result.artifact_refs:
        return False
    return True


def _evaluate_expected_results(built: BuiltAutonomousRuntimeScenario) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for raw in built.scenario.expected_results:
        result_id = str(raw.get("result_id", raw.get("kind", "expected_result")))
        kind = str(raw.get("kind", ""))
        passed = False
        details: dict[str, Any] = {}
        if kind == "task_completed":
            task_id = str(raw.get("task_id", ""))
            task = built.shared_state.tasks.get(task_id)
            passed = task is not None and task.status == "completed"
            details = {"task_id": task_id, "status": task.status if task else None}
        elif kind == "browser_session_text":
            session_id = str(raw.get("session_id", ""))
            expected_text = str(raw.get("expected_text", ""))
            session = built.browser_sessions.get(session_id)
            text = session.last_observation.text_preview if session and session.last_observation else ""
            passed = bool(expected_text and expected_text in text)
            details = {"session_id": session_id, "expected_text": expected_text}
        elif kind == "browser_session_current_url":
            session_id = str(raw.get("session_id", ""))
            expected_url = str(raw.get("expected_url", ""))
            session = built.browser_sessions.get(session_id)
            passed = session is not None and session.current_url == expected_url
            details = {"session_id": session_id, "expected_url": expected_url, "current_url": session.current_url if session else None}
        elif kind == "snapshot_count_at_least":
            session_id = str(raw.get("session_id", ""))
            count = _int(raw.get("count", 1), "count")
            session = built.browser_sessions.get(session_id)
            actual = len(session.snapshots) if session else 0
            passed = actual >= count
            details = {"session_id": session_id, "expected_count": count, "actual_count": actual}
        elif kind in {"task_expected_result", "task_browser_expected_result"}:
            passed, details = _evaluate_task_expected_result(raw, built)
        else:
            details = {"unsupported_kind": kind}
        results.append({"result_id": result_id, "kind": kind, "passed": passed, "details": details})
    return results


def _evaluate_task_expected_result(raw: Mapping[str, Any], built: BuiltAutonomousRuntimeScenario) -> tuple[bool, dict[str, Any]]:
    task_id = str(raw.get("task_id", ""))
    task = built.shared_state.tasks.get(task_id)
    task_events = _task_browser_events(built, task_id)
    latest_observation = _latest_observation_from_events(task_events)
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {
        "task_id": task_id,
        "task_status": task.status if task else None,
        "event_count": len(task_events),
    }
    checks["task_completed"] = task is not None and task.status == "completed"

    expected_text = raw.get("expected_text")
    if isinstance(expected_text, str) and expected_text:
        text = str(latest_observation.get("text_preview", "")) if latest_observation else ""
        checks["expected_text"] = expected_text in text
        details["expected_text"] = expected_text

    expected_url = raw.get("expected_current_url")
    if isinstance(expected_url, str) and expected_url:
        current_url = latest_observation.get("current_url") if latest_observation else None
        checks["expected_current_url"] = current_url == expected_url
        details["expected_current_url"] = expected_url
        details["current_url"] = current_url

    if "expected_snapshot_count_min" in raw:
        expected_count = _int(raw.get("expected_snapshot_count_min", 1), "expected_snapshot_count_min")
        actual_count = _task_snapshot_count(task_events)
        checks["expected_snapshot_count_min"] = actual_count >= expected_count
        details["expected_snapshot_count_min"] = expected_count
        details["snapshot_count"] = actual_count

    artifact_kinds = _string_list(raw.get("expected_artifact_kinds", []), "expected_artifact_kinds")
    if artifact_kinds:
        artifact_refs = list(task.artifact_refs) if task else []
        kind_checks = {kind: _artifact_kind_present(kind, artifact_refs) for kind in artifact_kinds}
        checks["expected_artifact_kinds"] = all(kind_checks.values())
        details["expected_artifact_kinds"] = kind_checks
        details["artifact_refs"] = artifact_refs

    details["checks"] = checks
    return all(checks.values()), details


def _task_browser_events(built: BuiltAutonomousRuntimeScenario, task_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in built.shared_state.group_event_log:
        if event.task_id != task_id or event.event_type != "browser_action_observed":
            continue
        events.append(event.to_dict())
    return events


def _latest_observation_from_events(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        metadata = event.get("metadata")
        browser_result = metadata.get("browser_result") if isinstance(metadata, dict) else None
        observation = browser_result.get("observation") if isinstance(browser_result, dict) else None
        if isinstance(observation, dict):
            return observation
    return None


def _task_snapshot_count(events: list[dict[str, Any]]) -> int:
    count = 0
    for event in events:
        metadata = event.get("metadata")
        browser_result = metadata.get("browser_result") if isinstance(metadata, dict) else None
        artifact_refs = browser_result.get("artifact_refs") if isinstance(browser_result, dict) else []
        if isinstance(artifact_refs, list):
            count += sum(1 for ref in artifact_refs if _is_browser_snapshot_ref(str(ref)))
    return count


def _artifact_kind_present(kind: str, artifact_refs: list[str]) -> bool:
    if kind == "browser_snapshot":
        return any(_is_browser_snapshot_ref(ref) for ref in artifact_refs)
    return False


def _is_browser_snapshot_ref(ref: str) -> bool:
    return ref.startswith("browser/") and "-snapshot-" in ref and ref.endswith(".json")


def _unmet_task_dependencies(task_id: str, state: RuntimeSharedState) -> list[str]:
    task = state.tasks.get(task_id)
    if task is None:
        return []
    dependencies = _string_list(task.metadata.get("depends_on", []), "depends_on")
    unmet: list[str] = []
    for dependency in dependencies:
        dependency_task = state.tasks.get(dependency)
        if dependency_task is None or dependency_task.status != "completed":
            unmet.append(dependency)
    return unmet


def _task_dependency_status(state: RuntimeSharedState) -> list[dict[str, Any]]:
    status: list[dict[str, Any]] = []
    for task_id, task in sorted(state.tasks.items()):
        dependencies = _string_list(task.metadata.get("depends_on", []), "depends_on")
        unmet = _unmet_task_dependencies(task_id, state)
        status.append(
            {
                "task_id": task_id,
                "depends_on": dependencies,
                "unmet_dependencies": unmet,
                "dependencies_satisfied": not unmet,
            }
        )
    return status


def _runtime_policy_from_dict(payload: Mapping[str, Any]) -> RuntimePolicy:
    return RuntimePolicy(
        scheduler=str(payload.get("scheduler", "round_robin")),  # type: ignore[arg-type]
        max_ticks=_int(payload.get("max_ticks", 100), "max_ticks"),
        max_actions_total=_int(payload.get("max_actions_total", 100), "max_actions_total"),
        max_actions_per_agent=_int(payload.get("max_actions_per_agent", 20), "max_actions_per_agent"),
        idle_tick_limit=_int(payload.get("idle_tick_limit", 5), "idle_tick_limit"),
        max_failures_total=_int(payload.get("max_failures_total", 10), "max_failures_total"),
        max_retries_per_task=_int(payload.get("max_retries_per_task", 0), "max_retries_per_task"),
        max_agent_failures=_int(payload.get("max_agent_failures", 3), "max_agent_failures"),
        stop_when_all_tasks_terminal=bool(payload.get("stop_when_all_tasks_terminal", True)),
        stop_when_no_runnable_agents=bool(payload.get("stop_when_no_runnable_agents", True)),
    )


def _virtual_environment_from_dict(payload: Mapping[str, Any]) -> RuntimeVirtualEnvironment:
    workspace_payload = _dict(payload.get("workspace", {}), "workspace")
    per_agent = _dict(workspace_payload.get("per_agent_workspaces", {}), "per_agent_workspaces")
    return RuntimeVirtualEnvironment(
        environment_id=str(payload.get("environment_id", "autonomous_browser_environment")),
        workspace=RuntimeWorkspace(
            workspace_root=str(workspace_payload.get("workspace_root", "artifacts/autonomous_runtime_workspace")),
            per_agent_workspaces={str(key): str(value) for key, value in per_agent.items()},
            reset_policy=str(workspace_payload.get("reset_policy", "never")),  # type: ignore[arg-type]
        ),
        allowed_resource_namespaces=tuple(_string_list(payload.get("allowed_resource_namespaces", ["browser"]), "allowed_resource_namespaces")),
        metadata=_dict(payload.get("metadata", {}), "virtual_environment.metadata"),
    )


def _common_fixture_manifest_path(sessions: tuple[AutonomousRuntimeBrowserSessionConfig, ...]) -> str:
    paths = {session.fixture_manifest_path for session in sessions}
    if len(paths) != 1:
        raise AutonomousRuntimeScenarioValidationError("Phase 9.3 supports one fixture_manifest_path per scenario.")
    return next(iter(paths))


def _validate_step_urls(step: AutonomousRuntimeScriptedStep, session: AutonomousRuntimeBrowserSessionConfig) -> None:
    for key in ("url", "target_url", "href", "success_url"):
        value = step.parameters.get(key)
        if isinstance(value, str) and value.strip():
            url = value.strip()
            if key in {"href"} and url.startswith("/"):
                continue
            _validate_url_allowed(url, session.allowed_domains)


def _validate_url_allowed(url: str, allowed_domains: tuple[str, ...]) -> None:
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise AutonomousRuntimeScenarioValidationError("URL could not be parsed.") from exc
    if parsed.scheme not in {"http", "https"}:
        raise AutonomousRuntimeScenarioValidationError("Browser scenario URLs must use http/https logical fixture URLs.")
    if parsed.username or parsed.password:
        raise AutonomousRuntimeScenarioValidationError("Credential URLs are not allowed.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise AutonomousRuntimeScenarioValidationError("Browser scenario URL must include a host.")
    if host not in {domain.lower() for domain in allowed_domains}:
        raise AutonomousRuntimeScenarioValidationError("Browser scenario URL host is outside allowed_domains.")


def _is_forbidden_action(action_name: str) -> bool:
    lowered = action_name.lower()
    return lowered in FORBIDDEN_ACTION_NAMES or lowered.startswith(FORBIDDEN_ACTION_PREFIXES)


def _validate_safe_output_path(path: Path) -> None:
    raw = str(path).replace("\\", "/")
    if "://" in raw or Path(raw).is_absolute() or PurePosixPath(raw).is_absolute():
        raise AutonomousRuntimeScenarioValidationError("output path must be a safe relative path.")
    if any(part == ".." for part in PurePosixPath(raw).parts):
        raise AutonomousRuntimeScenarioValidationError("output path must not contain traversal.")


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise AutonomousRuntimeScenarioValidationError(f"{label} must be non-empty.")
    if "://" in normalized or Path(value).is_absolute() or PurePosixPath(normalized).is_absolute():
        raise AutonomousRuntimeScenarioValidationError(f"{label} must be a safe relative path.")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise AutonomousRuntimeScenarioValidationError(f"{label} must not contain traversal.")
    return PurePosixPath(normalized).as_posix()


def _required_id(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AutonomousRuntimeScenarioValidationError(f"{key} must be a non-empty string.")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AutonomousRuntimeScenarioValidationError("optional string values must be non-empty when provided.")
    return value.strip()


def _dict(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AutonomousRuntimeScenarioValidationError(f"{label} must be an object.")
    return dict(value)


def _dict_list(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise AutonomousRuntimeScenarioValidationError(f"{label} must be a list.")
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise AutonomousRuntimeScenarioValidationError(f"{label} entries must be objects.")
        rows.append(dict(item))
    return rows


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise AutonomousRuntimeScenarioValidationError(f"{label} must be a list.")
    rows: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise AutonomousRuntimeScenarioValidationError(f"{label} entries must be non-empty strings.")
        rows.append(item.strip())
    return rows


def _int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AutonomousRuntimeScenarioValidationError(f"{label} must be an integer.")
    if value < 0:
        raise AutonomousRuntimeScenarioValidationError(f"{label} must be >= 0.")
    return value


def _reject_duplicates(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise AutonomousRuntimeScenarioValidationError(f"{label} values must be unique.")
