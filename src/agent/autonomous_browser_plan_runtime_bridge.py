from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_plan_validation import validate_autonomous_browser_plan
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


DRY_RUN_SCHEMA_VERSION = "autonomous_browser_plan_runtime_dry_run_summary_v1"
DRY_RUN_PROVIDER_NAME = "offline_browser_plan_dry_run_provider"
VALIDATION_RESULT_KEY = "browser_plan:validation_result"
NORMALIZED_PLAN_KEY = "browser_plan:normalized_plan"
DRY_RUN_SUMMARY_KEY = "browser_plan:dry_run_summary"


@dataclass(frozen=True)
class AutonomousBrowserPlanDryRunSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    plan_id: str | None
    validation_status: str
    actions_total: int
    normalized_actions_total: int
    runtime_task_count: int
    execution_status: str
    stop_reason: str | None
    runtime_trace_event_count: int
    runtime_trace: tuple[dict[str, Any], ...] = ()
    shared_state_keys: tuple[str, ...] = ()
    task_statuses: dict[str, str] = field(default_factory=dict)
    validation_result: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    output_files: tuple[str, ...] = ()
    runtime_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "plan_id": self.plan_id,
            "validation_status": self.validation_status,
            "actions_total": self.actions_total,
            "normalized_actions_total": self.normalized_actions_total,
            "runtime_task_count": self.runtime_task_count,
            "execution_status": self.execution_status,
            "stop_reason": self.stop_reason,
            "runtime_trace_event_count": self.runtime_trace_event_count,
            "runtime_trace": [dict(item) for item in self.runtime_trace],
            "shared_state_keys": list(self.shared_state_keys),
            "task_statuses": dict(self.task_statuses),
            "validation_result": dict(self.validation_result),
            "limitations": list(self.limitations),
            "output_files": list(self.output_files),
            "runtime_summary": dict(self.runtime_summary),
        }


def run_autonomous_browser_plan_dry_run(
    plan_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    runtime_id: str = "autonomous_browser_plan_dry_run_runtime",
    agent_id: str = "browser_plan_planner",
    task_id: str = "browser_plan_task",
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    validation_result = validate_autonomous_browser_plan(plan_artifact)
    plan_id = validation_result.get("plan_id")
    validation_status = str(validation_result.get("status", "rejected"))
    actions_total = _int(validation_result.get("actions_total", 0))
    normalized_actions_total = _normalized_actions_total(validation_result)
    runtime_trace: list[dict[str, Any]] = [
        {
            "event": "plan_loaded",
            "plan_id": plan_id,
            "source_type": _source_type(plan_artifact),
        },
        {
            "event": "plan_validated",
            "plan_id": plan_id,
            "validation_status": validation_status,
            "error_code": validation_result.get("error_code"),
            "actions_total": actions_total,
        },
    ]

    shared_state = RuntimeSharedState.from_specs(
        [RuntimeAgentSpec(agent_id, role="browser plan planner", metadata={"provider": DRY_RUN_PROVIDER_NAME})],
        [RuntimeTask(task_id, description=f"Dry-run browser plan {plan_id or 'unknown'}.")],
    )
    runtime = AutonomousMultiAgentRuntime(
        runtime_id=runtime_id,
        shared_state=shared_state,
        policy=RuntimePolicy(max_ticks=1, max_actions_total=1, max_actions_per_agent=1, idle_tick_limit=1),
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id=f"{runtime_id}_environment",
            workspace=RuntimeWorkspace(workspace_root="artifacts/runtime_workspace"),
            allowed_resource_namespaces=("browser",),
            metadata={"bridge": DRY_RUN_PROVIDER_NAME},
        ),
    )

    shared_state.assign_task(agent_id, task_id)
    runtime_trace.append({"event": "task_submitted", "task_id": task_id, "status": "pending"})
    runtime_trace.append({"event": "task_scheduled", "task_id": task_id, "status": "running"})

    shared_state.add_fact(VALIDATION_RESULT_KEY, validation_result, agent_id)
    shared_state_keys = {VALIDATION_RESULT_KEY}

    runtime_task_count = 1
    task_status = "completed"
    status = "accepted"
    error_code = None
    stop_reason = RuntimeStopReason.ALL_TASKS_TERMINAL.value
    execution_status = "skipped_by_design"
    normalized_plan = validation_result.get("normalized_plan")

    if validation_status != "accepted":
        task_status = "failed"
        status = "rejected"
        error_code = str(validation_result.get("error_code") or "browser_plan_validation_failed")
        stop_reason = "validation_rejected"
        runtime_trace.append(
            {
                "event": "plan_rejected",
                "plan_id": plan_id,
                "error_code": error_code,
            }
        )
        runtime_trace.append(
            {
                "event": "execution_skipped_by_design",
                "task_id": task_id,
                "execution_status": execution_status,
            }
        )
    else:
        if isinstance(normalized_plan, Mapping):
            shared_state.add_fact(NORMALIZED_PLAN_KEY, normalized_plan, agent_id)
            shared_state_keys.add(NORMALIZED_PLAN_KEY)
        shared_state.complete_task(task_id)
        shared_state.record_event(
            "browser_plan_dry_run_task_completed",
            "Browser plan dry-run task completed without execution.",
            agent_id=agent_id,
            task_id=task_id,
            metadata={"plan_id": plan_id, "execution_status": execution_status},
        )
        runtime_trace.append(
            {
                "event": "execution_skipped_by_design",
                "task_id": task_id,
                "execution_status": execution_status,
            }
        )

    runtime.stop_reason = RuntimeStopReason.ALL_TASKS_TERMINAL
    runtime.tick_count = 1
    runtime.action_count = 0
    runtime_summary = runtime.to_summary()

    if validation_status != "accepted":
        shared_state.fail_task(task_id, str(validation_result.get("error_code") or "browser_plan_validation_failed"))
    else:
        status = "accepted"

    shared_state.add_fact(DRY_RUN_SUMMARY_KEY, {}, agent_id)
    shared_state_keys.add(DRY_RUN_SUMMARY_KEY)
    runtime_trace.append({"event": "shared_state_updated", "shared_state_keys": sorted(shared_state_keys)})
    runtime_trace.append({"event": "runtime_stopped", "stop_reason": stop_reason})

    dry_run_summary = AutonomousBrowserPlanDryRunSummary(
        schema_version=DRY_RUN_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        plan_id=plan_id,
        validation_status=validation_status,
        actions_total=actions_total,
        normalized_actions_total=normalized_actions_total,
        runtime_task_count=runtime_task_count,
        execution_status=execution_status,
        stop_reason=stop_reason,
        runtime_trace_event_count=len(runtime_trace),
        runtime_trace=tuple(runtime_trace),
        shared_state_keys=tuple(sorted(shared_state_keys)),
        task_statuses={task_id: task_status},
        validation_result=validation_result,
        limitations=_limitations(),
        runtime_summary=runtime_summary,
    )
    dry_run_payload = dry_run_summary.to_dict()
    shared_state.shared_facts[DRY_RUN_SUMMARY_KEY]["value"] = dry_run_payload
    return dry_run_payload


def _normalized_actions_total(validation_result: Mapping[str, Any]) -> int:
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
        "offline dry-run only",
        "validated-plan planning bridge only",
        "no LLM calls",
        "no browser execution",
        "no Playwright import",
        "no model runtime",
        "not production browser automation",
    )


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0
