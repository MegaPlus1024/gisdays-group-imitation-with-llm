from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_scenario_suite import (
    AutonomousBrowserScenarioSuite,
    AutonomousBrowserScenarioSuiteValidationError,
    load_autonomous_browser_scenario_suite,
    run_autonomous_browser_scenario_suite,
)
from .autonomous_multi_agent_runtime import (
    AutonomousMultiAgentRuntime,
    RuntimeAgentSpec,
    RuntimePolicy,
    RuntimeSharedState,
    RuntimeStopReason,
    RuntimeTask,
    RuntimeVirtualEnvironment,
    RuntimeWorkspace,
)


INTEGRATION_SCHEMA_VERSION = "autonomous_runtime_browser_suite_integration_summary_v1"
DETERMINISTIC_PROVIDER_NAME = "deterministic_scripted_browser_suite_provider"


@dataclass(frozen=True)
class AutonomousRuntimeBrowserSuiteIntegrationSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    runtime_task_count: int
    browser_suite_status: str
    scenarios_attempted: int
    scenarios_succeeded: int
    scenarios_failed: int
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    expected_results_total: int
    expected_results_passed: int
    expected_results_failed: int
    required_actions_covered: tuple[str, ...] = ()
    required_actions_missing: tuple[str, ...] = ()
    shared_state_updates: tuple[dict[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()
    suite_id: str = ""
    suite_config_path: str | None = None
    runtime_summary: dict[str, Any] = field(default_factory=dict)
    browser_suite_summary: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "no_runtime_execution": self.no_runtime_execution,
            "runtime_task_count": self.runtime_task_count,
            "browser_suite_status": self.browser_suite_status,
            "scenarios_attempted": self.scenarios_attempted,
            "scenarios_succeeded": self.scenarios_succeeded,
            "scenarios_failed": self.scenarios_failed,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "expected_results_total": self.expected_results_total,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "required_actions_covered": list(self.required_actions_covered),
            "required_actions_missing": list(self.required_actions_missing),
            "shared_state_updates": [dict(item) for item in self.shared_state_updates],
            "limitations": list(self.limitations),
            "suite_id": self.suite_id,
            "suite_config_path": self.suite_config_path,
            "runtime_summary": dict(self.runtime_summary),
            "browser_suite_summary": dict(self.browser_suite_summary),
        }


def run_autonomous_browser_suite_task(
    suite_config: str | Path | AutonomousBrowserScenarioSuite | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    runtime_id: str = "autonomous_browser_suite_bridge_runtime",
    agent_id: str = "browser_suite_runner",
    task_id: str = "browser_suite_task",
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    suite, suite_source_path, load_error = _load_suite_config(suite_config, repo_root=repo)
    if load_error is not None:
        return AutonomousRuntimeBrowserSuiteIntegrationSummary(
            schema_version=INTEGRATION_SCHEMA_VERSION,
            status="failed",
            error_code="invalid_suite_config",
            error_message=load_error,
            no_runtime_execution=True,
            runtime_task_count=0,
            browser_suite_status="failed",
            scenarios_attempted=0,
            scenarios_succeeded=0,
            scenarios_failed=0,
            actions_attempted=0,
            actions_succeeded=0,
            actions_failed=0,
            expected_results_total=0,
            expected_results_passed=0,
            expected_results_failed=0,
            limitations=_limitations(),
            suite_config_path=suite_source_path,
        ).to_dict()

    runtime = _build_runtime(runtime_id, agent_id, task_id, suite, suite_source_path)
    shared_state = runtime.shared_state
    shared_updates: list[dict[str, Any]] = []

    shared_state.assign_task(agent_id, task_id)
    shared_updates.append(
        {
            "update_type": "task_submitted",
            "provider": DETERMINISTIC_PROVIDER_NAME,
            "agent_id": agent_id,
            "task_id": task_id,
            "suite_id": suite.suite_id,
            "suite_config_path": suite_source_path,
        }
    )
    shared_state.record_event(
        "browser_suite_task_submitted",
        "Browser suite task submitted to deterministic offline bridge.",
        agent_id=agent_id,
        task_id=task_id,
        metadata={
            "provider": DETERMINISTIC_PROVIDER_NAME,
            "suite_id": suite.suite_id,
            "suite_config_path": suite_source_path,
        },
    )

    suite_summary = run_autonomous_browser_scenario_suite(suite, repo_root=repo).to_summary()
    aggregate = _aggregate_suite_metrics(suite_summary)
    browser_suite_status, error_code, error_message = _evaluate_suite_summary(suite_summary, aggregate)
    if error_code is None:
        shared_state.add_fact("browser_suite:last_summary", suite_summary, agent_id)
        shared_state.complete_task(task_id)
        shared_state.record_event(
            "browser_suite_task_completed",
            "Browser suite task completed successfully.",
            agent_id=agent_id,
            task_id=task_id,
            metadata={"suite_id": suite.suite_id, "browser_suite_status": browser_suite_status},
        )
        shared_updates.append(
            {
                "update_type": "task_completed",
                "task_id": task_id,
                "suite_id": suite.suite_id,
                "browser_suite_status": browser_suite_status,
            }
        )
    else:
        shared_state.fail_task(task_id, error_message or error_code)
        shared_state.record_event(
            "browser_suite_task_failed",
            error_message or "Browser suite task failed.",
            agent_id=agent_id,
            task_id=task_id,
            severity="error",
            metadata={"suite_id": suite.suite_id, "browser_suite_status": browser_suite_status, "error_code": error_code},
        )
        shared_updates.append(
            {
                "update_type": "task_failed",
                "task_id": task_id,
                "suite_id": suite.suite_id,
                "browser_suite_status": browser_suite_status,
                "error_code": error_code,
            }
        )

    runtime.tick_count = 1
    runtime.action_count = 1
    if error_code is not None:
        runtime.failure_count = 1
    runtime.stop_reason = RuntimeStopReason.ALL_TASKS_TERMINAL
    runtime_summary = runtime.to_summary()

    return AutonomousRuntimeBrowserSuiteIntegrationSummary(
        schema_version=INTEGRATION_SCHEMA_VERSION,
        status="succeeded" if error_code is None else "failed",
        error_code=error_code,
        error_message=error_message,
        no_runtime_execution=True,
        runtime_task_count=len(runtime.shared_state.tasks),
        browser_suite_status=browser_suite_status,
        scenarios_attempted=aggregate["scenarios_attempted"],
        scenarios_succeeded=aggregate["scenarios_succeeded"],
        scenarios_failed=aggregate["scenarios_failed"],
        actions_attempted=aggregate["actions_attempted"],
        actions_succeeded=aggregate["actions_succeeded"],
        actions_failed=aggregate["actions_failed"],
        expected_results_total=aggregate["expected_results_total"],
        expected_results_passed=aggregate["expected_results_passed"],
        expected_results_failed=aggregate["expected_results_failed"],
        required_actions_covered=tuple(str(value) for value in suite_summary.get("required_actions_covered", [])),
        required_actions_missing=tuple(str(value) for value in suite_summary.get("required_actions_missing", [])),
        shared_state_updates=tuple(shared_updates),
        limitations=_limitations(),
        suite_id=suite.suite_id,
        suite_config_path=suite_source_path,
        runtime_summary=runtime_summary,
        browser_suite_summary=suite_summary,
    ).to_dict()


def _build_runtime(
    runtime_id: str,
    agent_id: str,
    task_id: str,
    suite: AutonomousBrowserScenarioSuite,
    suite_source_path: str | None,
) -> AutonomousMultiAgentRuntime:
    shared_state = RuntimeSharedState.from_specs(
        [RuntimeAgentSpec(agent_id, role="browser suite runner", metadata={"provider": DETERMINISTIC_PROVIDER_NAME})],
        [
            RuntimeTask(
                task_id,
                description=f"Run browser suite {suite.suite_id}.",
                metadata={
                    "suite_id": suite.suite_id,
                    "suite_config_path": suite_source_path,
                    "bridge": DETERMINISTIC_PROVIDER_NAME,
                },
            )
        ],
    )
    return AutonomousMultiAgentRuntime(
        runtime_id=runtime_id,
        shared_state=shared_state,
        policy=RuntimePolicy(max_ticks=1, max_actions_total=1, max_actions_per_agent=1, idle_tick_limit=1),
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id=f"{runtime_id}_environment",
            workspace=RuntimeWorkspace(workspace_root="artifacts/runtime_workspace"),
            allowed_resource_namespaces=("browser",),
            metadata={"bridge": DETERMINISTIC_PROVIDER_NAME},
        ),
    )


def _load_suite_config(
    suite_config: str | Path | AutonomousBrowserScenarioSuite | Mapping[str, Any],
    *,
    repo_root: Path,
) -> tuple[AutonomousBrowserScenarioSuite | None, str | None, str | None]:
    if isinstance(suite_config, AutonomousBrowserScenarioSuite):
        return suite_config, None, None
    if isinstance(suite_config, Mapping):
        try:
            return AutonomousBrowserScenarioSuite.from_dict(suite_config), None, None
        except AutonomousBrowserScenarioSuiteValidationError as exc:
            return None, None, str(exc)
    path = Path(suite_config)
    try:
        suite = load_autonomous_browser_scenario_suite(path)
    except (AutonomousBrowserScenarioSuiteValidationError, OSError) as exc:
        return None, _safe_display_path(path, repo_root), str(exc)
    return suite, _safe_display_path(path, repo_root), None


def _evaluate_suite_summary(
    summary: Mapping[str, Any],
    aggregate: Mapping[str, int],
) -> tuple[str, str | None, str | None]:
    if int(aggregate.get("scenarios_failed", 0)) > 0:
        return "failed", "suite_run_failed", "Browser suite scenarios failed."
    if int(aggregate.get("expected_results_failed", 0)) > 0:
        return "failed", "expected_results_failed", "Browser suite expected results failed."
    missing_actions = [str(value) for value in summary.get("required_actions_missing", [])]
    if missing_actions:
        return "failed", "required_actions_missing", "Browser suite required actions are missing."
    if not bool(summary.get("expected_min_passed_scenarios_met", True)):
        return "failed", "suite_run_failed", "Browser suite minimum scenario threshold was not met."
    return "passed", None, None


def _aggregate_suite_metrics(summary: Mapping[str, Any]) -> dict[str, int]:
    scenario_summaries = summary.get("scenario_summaries", [])
    if not isinstance(scenario_summaries, list):
        scenario_summaries = []
    scenarios_attempted = len(scenario_summaries)
    scenarios_succeeded = 0
    scenarios_failed = 0
    actions_attempted = 0
    actions_succeeded = 0
    actions_failed = 0
    expected_results_total = 0
    expected_results_passed = 0
    expected_results_failed = 0
    for item in scenario_summaries:
        if not isinstance(item, Mapping):
            continue
        coverage = item.get("browser_coverage")
        if isinstance(coverage, Mapping):
            succeeded = _int(coverage.get("actions_succeeded", 0))
            failed = _int(coverage.get("actions_failed", 0))
            actions_succeeded += succeeded
            actions_failed += failed
            actions_attempted += succeeded + failed
            passed = _int(coverage.get("expected_results_passed", 0))
            failed_expected = _int(coverage.get("expected_results_failed", 0))
            expected_results_passed += passed
            expected_results_failed += failed_expected
            expected_results_total += passed + failed_expected
        if str(item.get("status")) == "passed":
            scenarios_succeeded += 1
        else:
            scenarios_failed += 1
    return {
        "scenarios_attempted": scenarios_attempted,
        "scenarios_succeeded": scenarios_succeeded,
        "scenarios_failed": scenarios_failed,
        "actions_attempted": actions_attempted,
        "actions_succeeded": actions_succeeded,
        "actions_failed": actions_failed,
        "expected_results_total": expected_results_total,
        "expected_results_passed": expected_results_passed,
        "expected_results_failed": expected_results_failed,
    }


def _safe_display_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve(strict=False)
    repo = repo_root.resolve(strict=False)
    try:
        return resolved.relative_to(repo).as_posix()
    except ValueError:
        return path.name


def _limitations() -> tuple[str, ...]:
    return (
        "offline deterministic bridge only",
        "local loopback fixture suite only",
        "no real browser or Playwright launch",
        "no LLM planning",
        "not production browser automation",
        "no mail/git/calendar actions",
        "not production hardening",
    )


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0
