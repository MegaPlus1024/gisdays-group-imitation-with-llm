from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .execution_history import ExecutionHistoryLogger
from .state import AgentState

MultiAgentAgentStatus = Literal["succeeded", "failed", "skipped"]
MultiAgentRunStatus = Literal[
    "completed",
    "completed_with_failures",
    "stopped_on_agent_failure",
    "failed",
]


class MultiAgentOrchestratorSmokeConfig(BaseModel):
    orchestrator_id: str = "multi_agent_orchestrator_smoke_v1"
    max_agents: int = 3
    max_steps_per_agent: int = 1
    execution_mode: Literal["sequential"] = "sequential"
    isolate_agent_failures: bool = True
    stop_on_first_agent_failure: bool = False
    write_history_logs: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("orchestrator_id")
    @classmethod
    def validate_orchestrator_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("orchestrator_id must be non-empty.")
        return value

    @field_validator("max_agents", "max_steps_per_agent")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_agents and max_steps_per_agent must be >= 1.")
        return value


class MultiAgentRunSpec(BaseModel):
    agent_id: str
    agent_state: AgentState
    role_template_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_agent_compat(self) -> MultiAgentRunSpec:
        if self.agent_state.agent_id and self.agent_id != self.agent_state.agent_id:
            raise ValueError("agent_id must match agent_state.agent_id for v1 smoke mode.")
        return self


class MultiAgentAgentResult(BaseModel):
    orchestrator_id: str
    run_id: str
    agent_id: str
    status: MultiAgentAgentStatus
    success: bool
    step_count: int = 0
    selected_actions: list[str] = Field(default_factory=list)
    trajectory_result: Any | None = None
    recovery_result: Any | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("orchestrator_id", "run_id", "agent_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("orchestrator_id, run_id, and agent_id must be non-empty.")
        return value

    @field_validator("step_count")
    @classmethod
    def validate_step_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("step_count must be >= 0.")
        return value

    @model_validator(mode="after")
    def validate_error_shape(self) -> MultiAgentAgentResult:
        if not self.success:
            if not self.error_type or not self.error_message:
                raise ValueError(
                    "Failed agent result requires non-empty error_type and error_message."
                )
        return self


class MultiAgentOrchestratorSmokeResult(BaseModel):
    orchestrator_id: str
    run_id: str
    status: MultiAgentRunStatus
    success: bool
    agent_results: list[MultiAgentAgentResult]
    stopped_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("orchestrator_id", "run_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("orchestrator_id and run_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> MultiAgentOrchestratorSmokeResult:
        if not self.agent_results:
            raise ValueError("agent_results must not be empty.")
        if not self.success and (self.stopped_reason is None or not self.stopped_reason.strip()):
            raise ValueError("stopped_reason should be non-empty when success=False.")
        return self

    def total_agents(self) -> int:
        return len(self.agent_results)

    def successful_agents_count(self) -> int:
        return sum(1 for item in self.agent_results if item.success)

    def failed_agents_count(self) -> int:
        return sum(1 for item in self.agent_results if not item.success)

    def selected_actions_by_agent(self) -> dict[str, list[str]]:
        return {item.agent_id: list(item.selected_actions) for item in self.agent_results}


class MultiAgentOrchestratorSmoke:
    def __init__(
        self,
        config: MultiAgentOrchestratorSmokeConfig | None = None,
        runner_factory: Any | None = None,
        history_logger: ExecutionHistoryLogger | None = None,
    ) -> None:
        self.config = config or MultiAgentOrchestratorSmokeConfig()
        self.runner_factory = runner_factory
        self.history_logger = history_logger

    def run_smoke(
        self,
        specs: list[MultiAgentRunSpec],
        run_id: str = "multi_agent_smoke_demo",
    ) -> MultiAgentOrchestratorSmokeResult:
        if not run_id.strip():
            raise ValueError("run_id must be non-empty.")
        if not specs:
            raise ValueError("specs must not be empty.")
        if len(specs) > self.config.max_agents:
            raise ValueError("specs count exceeds max_agents.")
        if self.runner_factory is None:
            raise ValueError("runner_factory is required for smoke orchestrator v1")

        agent_results: list[MultiAgentAgentResult] = []
        stopped_reason: str | None = None
        stopped = False

        for spec in specs:
            try:
                runner = self.runner_factory(spec)
                trajectory_result = runner.run_trajectory(spec.agent_state, run_id=run_id)
                selected_actions = _extract_actions(trajectory_result)
                step_count = _extract_step_count(trajectory_result, selected_actions)
                ok = bool(getattr(trajectory_result, "success", False))
                if ok:
                    agent_results.append(
                        MultiAgentAgentResult(
                            orchestrator_id=self.config.orchestrator_id,
                            run_id=run_id,
                            agent_id=spec.agent_id,
                            status="succeeded",
                            success=True,
                            step_count=step_count,
                            selected_actions=selected_actions,
                            trajectory_result=trajectory_result,
                        )
                    )
                else:
                    error_message = (
                        getattr(trajectory_result, "stopped_reason", None)
                        or "Agent trajectory returned success=False."
                    )
                    agent_results.append(
                        MultiAgentAgentResult(
                            orchestrator_id=self.config.orchestrator_id,
                            run_id=run_id,
                            agent_id=spec.agent_id,
                            status="failed",
                            success=False,
                            step_count=step_count,
                            selected_actions=selected_actions,
                            trajectory_result=trajectory_result,
                            error_type="trajectory_failed",
                            error_message=error_message,
                        )
                    )
                    if self.config.stop_on_first_agent_failure:
                        stopped = True
                        stopped_reason = f"Stopped on agent failure: {spec.agent_id}"
                        break
            except Exception as exc:
                agent_results.append(
                    MultiAgentAgentResult(
                        orchestrator_id=self.config.orchestrator_id,
                        run_id=run_id,
                        agent_id=spec.agent_id,
                        status="failed",
                        success=False,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc) if str(exc).strip() else exc.__class__.__name__,
                    )
                )
                if self.config.stop_on_first_agent_failure:
                    stopped = True
                    stopped_reason = f"Stopped on agent failure: {spec.agent_id}"
                    break

        if not agent_results:
            return MultiAgentOrchestratorSmokeResult(
                orchestrator_id=self.config.orchestrator_id,
                run_id=run_id,
                status="failed",
                success=False,
                agent_results=[
                    MultiAgentAgentResult(
                        orchestrator_id=self.config.orchestrator_id,
                        run_id=run_id,
                        agent_id="unknown",
                        status="failed",
                        success=False,
                        error_type="no_agent_results",
                        error_message="No agent results were produced.",
                    )
                ],
                stopped_reason="No agent results were produced.",
            )

        failed_count = sum(1 for result in agent_results if not result.success)
        if stopped and self.config.stop_on_first_agent_failure:
            return MultiAgentOrchestratorSmokeResult(
                orchestrator_id=self.config.orchestrator_id,
                run_id=run_id,
                status="stopped_on_agent_failure",
                success=False,
                agent_results=agent_results,
                stopped_reason=stopped_reason or "Stopped on first agent failure.",
            )
        if failed_count == 0:
            return MultiAgentOrchestratorSmokeResult(
                orchestrator_id=self.config.orchestrator_id,
                run_id=run_id,
                status="completed",
                success=True,
                agent_results=agent_results,
            )
        return MultiAgentOrchestratorSmokeResult(
            orchestrator_id=self.config.orchestrator_id,
            run_id=run_id,
            status="completed_with_failures",
            success=False,
            agent_results=agent_results,
            stopped_reason="One or more agents failed during smoke run.",
        )


def load_multi_agent_orchestrator_smoke_config(
    path: str | Path,
) -> MultiAgentOrchestratorSmokeConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return MultiAgentOrchestratorSmokeConfig.model_validate(payload)


def _extract_actions(trajectory_result: Any) -> list[str]:
    method = getattr(trajectory_result, "selected_actions", None)
    if callable(method):
        actions = method()
        if isinstance(actions, list):
            return [str(a) for a in actions]
    return []


def _extract_step_count(trajectory_result: Any, selected_actions: list[str]) -> int:
    steps = getattr(trajectory_result, "steps", None)
    if isinstance(steps, list):
        return len(steps)
    return len(selected_actions)
