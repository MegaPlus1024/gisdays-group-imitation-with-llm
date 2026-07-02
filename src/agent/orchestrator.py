from __future__ import annotations

from .agent import Agent, AgentStepRequest, AgentStepResult
from .state import AgentState


class Orchestrator:
    def __init__(self, agent: Agent, run_id: str) -> None:
        if not run_id.strip():
            raise ValueError("run_id must be non-empty.")
        self.agent = agent
        self.run_id = run_id

    def run_agent_step(
        self, agent_state: AgentState, step_index: int | None = None
    ) -> AgentStepResult:
        effective_step = agent_state.current_step if step_index is None else step_index
        request = AgentStepRequest(
            run_id=self.run_id,
            agent_state=agent_state,
            step_index=effective_step,
        )
        return self.agent.decide_next_action(request)

    def run_agent_steps(self, agent_states: list[AgentState]) -> list[AgentStepResult]:
        results: list[AgentStepResult] = []
        for state in agent_states:
            results.append(self.run_agent_step(state))
        return results
