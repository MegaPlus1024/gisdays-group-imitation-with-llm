from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_plan_validation import validate_autonomous_browser_plan
from .autonomous_browser_runtime import (
    BROWSER_RUNTIME_ACTION_NAMES,
    BrowserRuntimeAction,
    BrowserRuntimePolicy,
    BrowserRuntimeSession,
    BrowserRuntimeVerifier,
    FixtureBackedBrowserRuntimeExecutor,
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


SUMMARY_SCHEMA_VERSION = "autonomous_browser_plan_fixture_execution_summary_v1"
CONFIG_SCHEMA_VERSION = "autonomous_browser_plan_fixture_execution_config_v1"
PLAN_VALIDATION_KEY = "browser_plan:validation_result"
NORMALIZED_PLAN_KEY = "browser_plan:normalized_plan"
EXECUTION_SUMMARY_KEY = "browser_plan:fixture_execution_summary"
FIXTURE_MANIFEST_RELATIVE_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
DRY_RUN_PROVIDER_NAME = "offline_browser_plan_fixture_execution_provider"


@dataclass(frozen=True)
class AutonomousBrowserPlanFixtureExecutionSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    real_browser_execution: bool
    plan_id: str | None
    validation_status: str
    execution_status: str
    actions_planned: int
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    expected_results_total: int
    expected_results_passed: int
    expected_results_failed: int
    shared_state_keys: tuple[str, ...] = ()
    stop_reason: str | None = None
    runtime_trace: tuple[dict[str, Any], ...] = ()
    runtime_trace_event_count: int = 0
    limitations: tuple[str, ...] = ()
    execution_diagnostics: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "real_browser_execution": self.real_browser_execution,
            "plan_id": self.plan_id,
            "validation_status": self.validation_status,
            "execution_status": self.execution_status,
            "actions_planned": self.actions_planned,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "expected_results_total": self.expected_results_total,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "shared_state_keys": list(self.shared_state_keys),
            "stop_reason": self.stop_reason,
            "runtime_trace": [dict(item) for item in self.runtime_trace],
            "runtime_trace_event_count": self.runtime_trace_event_count,
            "limitations": list(self.limitations),
            "execution_diagnostics": [dict(item) for item in self.execution_diagnostics],
        }


def run_autonomous_browser_plan_fixture_execution(
    plan_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    runtime_id: str = "autonomous_browser_plan_fixture_execution_runtime",
    agent_id: str = "browser_plan_executor",
    task_id: str = "browser_plan_fixture_task",
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    fixture_repo = _resolve_fixture_repo_root(repo)
    validation_result = validate_autonomous_browser_plan(plan_artifact)
    plan_id = validation_result.get("plan_id")
    validation_status = str(validation_result.get("status", "rejected"))
    actions_planned = _int(validation_result.get("actions_total", 0))
    runtime_trace: list[dict[str, Any]] = [
        {"event": "plan_loaded", "plan_id": plan_id, "source_type": _source_type(plan_artifact)},
        {
            "event": "plan_validated",
            "plan_id": plan_id,
            "validation_status": validation_status,
            "error_code": validation_result.get("error_code"),
        },
        {"event": "task_submitted", "task_id": task_id, "status": "pending"},
        {"event": "task_scheduled", "task_id": task_id, "status": "running"},
    ]

    shared_state = RuntimeSharedState.from_specs(
        [RuntimeAgentSpec(agent_id, role="browser plan executor", metadata={"provider": DRY_RUN_PROVIDER_NAME})],
        [RuntimeTask(task_id, description=f"Fixture execution for browser plan {plan_id or 'unknown'}")],
    )
    runtime = AutonomousMultiAgentRuntime(
        runtime_id=runtime_id,
        shared_state=shared_state,
        policy=RuntimePolicy(max_ticks=1, max_actions_total=max(1, actions_planned), max_actions_per_agent=max(1, actions_planned)),
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id=f"{runtime_id}_environment",
            workspace=RuntimeWorkspace(workspace_root="artifacts/runtime_workspace"),
            allowed_resource_namespaces=("browser",),
            metadata={"bridge": DRY_RUN_PROVIDER_NAME},
        ),
    )
    shared_state.assign_task(agent_id, task_id)
    shared_state.add_fact(PLAN_VALIDATION_KEY, validation_result, agent_id)
    shared_state_keys = {PLAN_VALIDATION_KEY}

    if validation_status != "accepted":
        shared_state.fail_task(task_id, str(validation_result.get("error_code") or "browser_plan_validation_failed"))
        shared_state.add_fact(EXECUTION_SUMMARY_KEY, {}, agent_id)
        shared_state_keys.add(EXECUTION_SUMMARY_KEY)
        runtime_trace.insert(4, {"event": "execution_skipped_by_design", "task_id": task_id, "execution_status": "validation_rejected"})
        runtime_trace.append({"event": "shared_state_updated", "shared_state_keys": sorted(shared_state_keys)})
        runtime_trace.append({"event": "runtime_stopped", "stop_reason": "validation_rejected"})
        runtime_summary = runtime.to_summary()
        summary = AutonomousBrowserPlanFixtureExecutionSummary(
            schema_version=SUMMARY_SCHEMA_VERSION,
            status="rejected",
            error_code=str(validation_result.get("error_code") or "browser_plan_validation_failed"),
            no_runtime_execution=True,
            real_browser_execution=False,
            plan_id=plan_id,
            validation_status=validation_status,
            execution_status="validation_rejected",
            actions_planned=actions_planned,
            actions_attempted=0,
            actions_succeeded=0,
            actions_failed=0,
            expected_results_total=_expected_results_total(validation_result),
            expected_results_passed=0,
            expected_results_failed=_expected_results_total(validation_result),
            shared_state_keys=tuple(sorted(shared_state_keys)),
            stop_reason="validation_rejected",
            runtime_trace=tuple(runtime_trace),
            runtime_trace_event_count=len(runtime_trace),
            limitations=_limitations(),
            execution_diagnostics=(),
        )
        payload = summary.to_dict()
        shared_state.shared_facts[EXECUTION_SUMMARY_KEY]["value"] = payload
        return payload

    normalized_plan = validation_result.get("normalized_plan")
    if not isinstance(normalized_plan, Mapping):
        return _structured_failure(
            runtime,
            shared_state,
            shared_state_keys,
            runtime_trace,
            plan_id,
            validation_result,
            actions_planned,
            "normalized_plan_missing",
            "Validated plan is missing normalized actions.",
            execution_status="execution_failed",
            stop_reason="execution_failed",
        )

    shared_state.add_fact(NORMALIZED_PLAN_KEY, normalized_plan, agent_id)
    shared_state_keys.add(NORMALIZED_PLAN_KEY)
    runtime_trace.append({"event": "fixture_execution_started", "plan_id": plan_id, "action_count": len(normalized_plan.get("actions", []))})

    executor = FixtureBackedBrowserRuntimeExecutor(
        fixture_manifest_path=FIXTURE_MANIFEST_RELATIVE_PATH,
        project_root=fixture_repo,
        policy=BrowserRuntimePolicy(
            allowed_action_names=tuple(sorted(BROWSER_RUNTIME_ACTION_NAMES)),
            fixture_mode=True,
            playwright_enabled=False,
        ),
    )
    verifier = BrowserRuntimeVerifier()
    session = BrowserRuntimeSession(
        session_id=f"{runtime_id}_session",
        agent_id=agent_id,
        workspace_id="browser_plan_workspace",
        environment_id=f"{runtime_id}_environment",
        allowed_domains=("local.intranet", "local-intranet.test", "docs.local", "portal.local"),
        policy_flags=executor.policy.to_flags(),
    )

    execution_diagnostics: list[dict[str, Any]] = []
    expected_results_total = 0
    expected_results_passed = 0
    expected_results_failed = 0
    actions_attempted = 0
    actions_succeeded = 0
    actions_failed = 0
    stop_reason = RuntimeStopReason.ALL_TASKS_TERMINAL.value
    error_code: str | None = None
    status = "succeeded"
    execution_status = "fixture_executed"

    for action in normalized_plan.get("actions", []):
        if not isinstance(action, Mapping):
            return _structured_failure(
                runtime,
                shared_state,
                shared_state_keys,
                runtime_trace,
                plan_id,
                validation_result,
                actions_planned,
                "invalid_normalized_action",
                "Validated plan contains an invalid action shape.",
                execution_status="execution_failed",
                stop_reason="execution_failed",
                execution_diagnostics=tuple(execution_diagnostics),
            )
        step_id = _safe_text(action.get("step_id"))
        action_name = _safe_text(action.get("action_name"))
        if action_name not in BROWSER_RUNTIME_ACTION_NAMES:
            return _structured_failure(
                runtime,
                shared_state,
                shared_state_keys,
                runtime_trace,
                plan_id,
                validation_result,
                actions_planned,
                "unknown_normalized_action",
                "Validated plan contains an unsupported browser action.",
                execution_status="execution_failed",
                stop_reason="execution_failed",
                execution_diagnostics=tuple(execution_diagnostics),
            )
        expected_text = action.get("expected_text")
        if not isinstance(expected_text, str) or not expected_text.strip():
            return _structured_failure(
                runtime,
                shared_state,
                shared_state_keys,
                runtime_trace,
                plan_id,
                validation_result,
                actions_planned,
                "missing_expected_text",
                "Fixture-backed execution requires expected_text for every action.",
                execution_status="execution_failed",
                stop_reason="execution_failed",
                execution_diagnostics=tuple(execution_diagnostics),
            )

        expected_results_total += 1
        runtime_trace.append(
            {
                "event": "action_executed",
                "step_id": step_id,
                "action_name": action_name,
                "status": "running",
            }
        )

        result = executor.execute(
            BrowserRuntimeAction(
                agent_id=agent_id,
                action_type="browser",
                action_name=action_name,
                parameters=dict(action.get("parameters") or {}),
                session_id=session.session_id,
                task_id=task_id,
            ),
            session,
        )
        actions_attempted += 1
        if result.success:
            actions_succeeded += 1
        else:
            actions_failed += 1
            status = "failed"
            error_code = result.error_type or "browser_action_failed"
            stop_reason = "execution_failed"

        verification = verifier.verify(result, expected_text=expected_text)
        runtime_trace.append(
            {
                "event": "expected_result_checked",
                "step_id": step_id,
                "action_name": action_name,
                "status": "passed" if verification.passed else "failed",
                "verification_reason": verification.reason,
            }
        )
        if verification.passed:
            expected_results_passed += 1
        else:
            expected_results_failed += 1
            if status == "succeeded":
                status = "failed"
                error_code = verification.reason
                stop_reason = "execution_failed"
            execution_diagnostics.append(
                {
                    "step_id": step_id,
                    "action_name": action_name,
                    "error_code": verification.reason,
                }
            )
            break

        if not result.success:
            execution_diagnostics.append(
                {
                    "step_id": step_id,
                    "action_name": action_name,
                    "error_code": result.error_type,
                }
            )
            break

        execution_diagnostics.append(
            {
                "step_id": step_id,
                "action_name": action_name,
                "status": "succeeded",
            }
        )

    if status == "succeeded" and actions_failed == 0 and expected_results_failed == 0:
        shared_state.complete_task(task_id)
    else:
        shared_state.fail_task(task_id, error_code or stop_reason)

    runtime.stop_reason = RuntimeStopReason.ALL_TASKS_TERMINAL
    runtime.tick_count = 1
    runtime.action_count = actions_attempted
    runtime_summary = runtime.to_summary()

    shared_state.add_fact(EXECUTION_SUMMARY_KEY, {}, agent_id)
    shared_state_keys.add(EXECUTION_SUMMARY_KEY)
    runtime_trace.append({"event": "shared_state_updated", "shared_state_keys": sorted(shared_state_keys)})
    runtime_trace.append({"event": "runtime_stopped", "stop_reason": stop_reason})

    expected_results_failed = max(expected_results_failed, expected_results_total - expected_results_passed)
    summary = AutonomousBrowserPlanFixtureExecutionSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        plan_id=plan_id,
        validation_status=validation_status,
        execution_status=execution_status if status == "succeeded" else "execution_failed",
        actions_planned=actions_planned,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_succeeded,
        actions_failed=actions_failed,
        expected_results_total=expected_results_total,
        expected_results_passed=expected_results_passed,
        expected_results_failed=expected_results_failed,
        shared_state_keys=tuple(sorted(shared_state_keys)),
        stop_reason=stop_reason,
        runtime_trace=tuple(runtime_trace),
        runtime_trace_event_count=len(runtime_trace),
        limitations=_limitations(),
        execution_diagnostics=tuple(execution_diagnostics),
    )
    payload = summary.to_dict()
    shared_state.shared_facts[EXECUTION_SUMMARY_KEY]["value"] = payload
    return payload


def _structured_failure(
    runtime: AutonomousMultiAgentRuntime,
    shared_state: RuntimeSharedState,
    shared_state_keys: set[str],
    runtime_trace: list[dict[str, Any]],
    plan_id: str | None,
    validation_result: Mapping[str, Any],
    actions_planned: int,
    error_code: str,
    error_message: str,
    *,
    execution_status: str,
    stop_reason: str,
    execution_diagnostics: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    task_id = next(iter(shared_state.tasks))
    shared_state.fail_task(task_id, error_code)
    runtime.stop_reason = RuntimeStopReason.ALL_TASKS_TERMINAL
    runtime.tick_count = 1
    runtime.action_count = 0
    runtime_summary = runtime.to_summary()
    shared_state.add_fact(EXECUTION_SUMMARY_KEY, {}, "browser_plan_executor")
    shared_state_keys.add(EXECUTION_SUMMARY_KEY)
    runtime_trace.append({"event": "shared_state_updated", "shared_state_keys": sorted(shared_state_keys)})
    runtime_trace.append({"event": "runtime_stopped", "stop_reason": stop_reason})
    summary = AutonomousBrowserPlanFixtureExecutionSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        plan_id=plan_id,
        validation_status=str(validation_result.get("status", "rejected")),
        execution_status=execution_status,
        actions_planned=actions_planned,
        actions_attempted=0,
        actions_succeeded=0,
        actions_failed=0,
        expected_results_total=_expected_results_total(validation_result),
        expected_results_passed=0,
        expected_results_failed=_expected_results_total(validation_result),
        shared_state_keys=tuple(sorted(shared_state_keys)),
        stop_reason=stop_reason,
        runtime_trace=tuple(runtime_trace),
        runtime_trace_event_count=len(runtime_trace),
        limitations=_limitations(),
        execution_diagnostics=tuple(execution_diagnostics)
        + (
            {
                "error_code": error_code,
                "message": error_message,
            },
        ),
    )
    payload = summary.to_dict()
    shared_state.shared_facts[EXECUTION_SUMMARY_KEY]["value"] = payload
    return payload


def _expected_results_total(validation_result: Mapping[str, Any]) -> int:
    normalized_plan = validation_result.get("normalized_plan")
    if isinstance(normalized_plan, Mapping):
        actions = normalized_plan.get("actions")
        if isinstance(actions, list):
            return len(actions)
    return 0


def _source_type(plan_artifact: str | Path | Mapping[str, Any]) -> str:
    return "mapping" if isinstance(plan_artifact, Mapping) else "path"


def _limitations() -> tuple[str, ...]:
    return (
        "offline fixture-backed execution only",
        "validated browser plans only",
        "no LLM calls",
        "no Playwright import",
        "no real browser execution",
        "no local HTTP server",
        "not production browser automation",
    )


def _safe_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _resolve_fixture_repo_root(repo_root: Path) -> Path:
    if (repo_root / FIXTURE_MANIFEST_RELATIVE_PATH).exists():
        return repo_root
    fallback_root = Path(__file__).resolve().parents[2]
    if (fallback_root / FIXTURE_MANIFEST_RELATIVE_PATH).exists():
        return fallback_root
    return repo_root
