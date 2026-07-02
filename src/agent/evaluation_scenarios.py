from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EvaluationMetricName = Literal[
    "json_validity_rate",
    "next_action_parse_success_rate",
    "registry_acceptance_rate",
    "role_compliance_rate",
    "typical_action_rate",
    "atypical_action_count",
    "forbidden_for_normality_count",
    "diversity_score",
    "repetition_score",
    "sequence_coherence_score",
    "history_usage_score",
    "normal_activity_score",
    "average_selection_latency_seconds",
    "average_total_step_latency_seconds",
    "cpu_percent_avg",
    "cpu_percent_max",
    "ram_delta_mb_avg",
    "tokens_per_second",
    "failure_count",
    "recovery_count",
]

EvaluationScenarioMode = Literal["single_agent", "multi_agent"]


class EvaluationScenarioAgentSpec(BaseModel):
    agent_id: str
    role_id: str
    role_template_path: str
    activity_profile_path: str
    initial_state_path: str | None = None
    available_actions: list[str]
    expected_action_families: list[str] = Field(default_factory=list)
    expected_behavior_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id", "role_id", "role_template_path", "activity_profile_path")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent_id/role_id/role_template_path/activity_profile_path must be non-empty.")
        return value

    @field_validator("available_actions")
    @classmethod
    def validate_actions(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("available_actions must not be empty.")
        if len(value) != len(set(value)):
            raise ValueError("available_actions must not contain duplicates.")
        return value

    @model_validator(mode="after")
    def validate_families(self) -> EvaluationScenarioAgentSpec:
        if len(self.expected_action_families) != len(set(self.expected_action_families)):
            raise ValueError("expected_action_families must not contain duplicates.")
        return self


class EvaluationScenarioStopPolicy(BaseModel):
    max_steps: int = 5
    stop_on_validation_failure: bool = True
    stop_on_unsafe_action: bool = True
    stop_on_repeated_action: bool = True
    stop_on_forbidden_for_normality: bool = True
    stop_on_excessive_atypical_actions: bool = True
    stop_on_no_progress: bool = False
    stop_criteria_config_path: str | None = "configs/autonomous_stop_criteria.example.json"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("max_steps")
    @classmethod
    def validate_max_steps(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_steps must be >= 1.")
        return value


class EvaluationScenarioExpectedBehavior(BaseModel):
    min_normal_activity_score: float = 0.6
    min_diversity_score: float = 0.4
    max_repeated_same_parameters: int = 2
    max_forbidden_for_normality_count: int = 0
    max_atypical_action_count: int = 2
    required_sequence_patterns: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_normal_activity_score", "min_diversity_score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("score fields must be between 0 and 1.")
        return value

    @field_validator(
        "max_repeated_same_parameters",
        "max_forbidden_for_normality_count",
        "max_atypical_action_count",
    )
    @classmethod
    def validate_counts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("count fields must be >= 0.")
        return value

    @model_validator(mode="after")
    def validate_lists(self) -> EvaluationScenarioExpectedBehavior:
        if len(self.required_sequence_patterns) != len(set(self.required_sequence_patterns)):
            raise ValueError("required_sequence_patterns must not contain duplicates.")
        if len(self.forbidden_actions) != len(set(self.forbidden_actions)):
            raise ValueError("forbidden_actions must not contain duplicates.")
        return self


class EvaluationScenarioResourcePlan(BaseModel):
    cpu_only: bool = True
    collect_latency: bool = True
    collect_cpu: bool = True
    collect_ram: bool = True
    collect_tokens_per_second: bool = True
    estimate_multi_agent_capacity: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationScenario(BaseModel):
    scenario_id: str
    schema_version: str = "evaluation_scenario_v1"
    name: str
    description: str
    mode: EvaluationScenarioMode
    agents: list[EvaluationScenarioAgentSpec]
    stop_policy: EvaluationScenarioStopPolicy = Field(default_factory=EvaluationScenarioStopPolicy)
    metrics: list[EvaluationMetricName]
    expected_behavior: EvaluationScenarioExpectedBehavior = Field(default_factory=EvaluationScenarioExpectedBehavior)
    resource_plan: EvaluationScenarioResourcePlan = Field(default_factory=EvaluationScenarioResourcePlan)
    behavioral_fixture_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scenario_id", "schema_version", "name", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scenario_id/schema_version/name/description must be non-empty.")
        return value

    @field_validator("agents")
    @classmethod
    def validate_agents_non_empty(cls, value: list[EvaluationScenarioAgentSpec]) -> list[EvaluationScenarioAgentSpec]:
        if not value:
            raise ValueError("agents must not be empty.")
        return value

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: list[EvaluationMetricName]) -> list[EvaluationMetricName]:
        if not value:
            raise ValueError("metrics must not be empty.")
        if len(value) != len(set(value)):
            raise ValueError("metrics must not contain duplicates.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> EvaluationScenario:
        if self.mode == "single_agent" and len(self.agents) != 1:
            raise ValueError("single_agent mode must have exactly one agent.")
        if self.mode == "multi_agent" and len(self.agents) < 2:
            raise ValueError("multi_agent mode must have at least two agents.")
        if len(self.behavioral_fixture_refs) != len(set(self.behavioral_fixture_refs)):
            raise ValueError("behavioral_fixture_refs must not contain duplicates.")
        agent_ids = [a.agent_id for a in self.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("agent_id values must be unique.")
        return self

    def agent_count(self) -> int:
        return len(self.agents)

    def role_ids(self) -> list[str]:
        return [a.role_id for a in self.agents]

    def metric_names(self) -> list[str]:
        return list(self.metrics)

    def is_multi_agent(self) -> bool:
        return self.mode == "multi_agent"


def load_evaluation_scenario(path: str | Path) -> EvaluationScenario:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvaluationScenario.model_validate(payload)


def load_evaluation_scenarios_from_dir(path: str | Path) -> list[EvaluationScenario]:
    scenarios: list[EvaluationScenario] = []
    for p in sorted(Path(path).glob("*.json"), key=lambda x: x.name):
        scenarios.append(load_evaluation_scenario(p))
    return sorted(scenarios, key=lambda s: s.scenario_id)


def verify_evaluation_scenario_references(scenario: EvaluationScenario) -> list[str]:
    missing: list[str] = []

    def check(path_value: str | None) -> None:
        if path_value is None:
            return
        if not Path(path_value).exists():
            missing.append(path_value)

    for agent in scenario.agents:
        check(agent.role_template_path)
        check(agent.activity_profile_path)
        check(agent.initial_state_path)
    check(scenario.stop_policy.stop_criteria_config_path)
    for ref in scenario.behavioral_fixture_refs:
        check(ref)
    return missing


def evaluation_scenario_summary(scenario: EvaluationScenario) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "mode": scenario.mode,
        "agent_count": scenario.agent_count(),
        "role_ids": scenario.role_ids(),
        "max_steps": scenario.stop_policy.max_steps,
        "metrics": scenario.metric_names(),
        "min_normal_activity_score": scenario.expected_behavior.min_normal_activity_score,
        "cpu_only": scenario.resource_plan.cpu_only,
    }
