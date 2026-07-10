from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
import urllib.parse

from .autonomous_browser_live_planner import (
    CAPTURED_PLAN_PLANNER_KIND,
    SCRIPTED_PLANNER_KIND,
    AutonomousBrowserLivePlannerStep,
    CapturedPlanStepPlanner,
    ScriptedLivePlanner,
    load_live_planner_backend,
)
from .autonomous_browser_live_model_planner import (
    DEFAULT_LOCAL_MODEL_ALIAS,
    DEFAULT_LOCAL_MODEL_ENDPOINT,
    DEFAULT_LOCAL_MODEL_MAX_REPAIR_ATTEMPTS,
    DEFAULT_LOCAL_MODEL_REPAIR_ENABLED,
    ALLOWED_LOCAL_EXPECTED_URL_HOSTS,
    ALLOWED_LOCAL_MODEL_ACTION_NAMES,
    ChatCompletionClient,
    LocalModelLivePlanner,
    LocalModelLivePlannerError,
    LocalModelPlannerConfig,
    REPAIRABLE_MODEL_OUTPUT_ERROR_CODES,
)
from .autonomous_browser_plan_validation import validate_autonomous_browser_plan
from .autonomous_browser_runtime import (
    BrowserRuntimeAction,
    BrowserRuntimeObservation,
    BrowserRuntimePolicy,
    BrowserRuntimeSession,
    BrowserRuntimeVerifier,
    FixtureBackedBrowserRuntimeExecutor,
    _extract_links,
)
from .browser_fixture_resolver import resolve_browser_fixture_url


CONFIG_SCHEMA_VERSION = "autonomous_browser_live_loop_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_live_loop_summary_v1"
TRACE_SCHEMA_VERSION = "autonomous_browser_live_loop_trace_v1"
DEFAULT_LOOP_BACKEND = "offline_fixture"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/browser_live_loop_offline"
DEFAULT_FIXTURE_MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
DEFAULT_MAX_STEPS = 16
DEFAULT_MAX_REPEATED_ACTION_COUNT = 2
LOCAL_MODEL_PLANNER_KIND = "local_model"
DEFAULT_ALLOWED_DOMAINS = (
    "local.intranet",
    "local-intranet.test",
    "docs.local",
    "portal.local",
)


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopBrowserSessionConfig:
    session_id: str
    agent_id: str
    workspace_id: str
    environment_id: str
    allowed_domains: tuple[str, ...]
    start_url: str | None = None
    fixture_manifest_path: str = DEFAULT_FIXTURE_MANIFEST_PATH
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousBrowserLiveLoopBrowserSessionConfig:
        return cls(
            session_id=_required_identifier(payload.get("session_id"), "session_id"),
            agent_id=_required_identifier(payload.get("agent_id"), "agent_id"),
            workspace_id=_required_identifier(payload.get("workspace_id"), "workspace_id"),
            environment_id=_required_identifier(payload.get("environment_id"), "environment_id"),
            allowed_domains=tuple(_string_list(payload.get("allowed_domains"), "allowed_domains") or DEFAULT_ALLOWED_DOMAINS),
            start_url=_optional_text(payload.get("start_url")),
            fixture_manifest_path=_safe_relative_path(
                payload.get("fixture_manifest_path", DEFAULT_FIXTURE_MANIFEST_PATH),
                "fixture_manifest_path",
            )
            or DEFAULT_FIXTURE_MANIFEST_PATH,
            metadata=_dict(payload.get("metadata", {}), "metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "environment_id": self.environment_id,
            "allowed_domains": list(self.allowed_domains),
            "start_url": self.start_url,
            "fixture_manifest_path": self.fixture_manifest_path,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopPlannerConfig:
    kind: str
    scripted_steps: tuple[AutonomousBrowserLivePlannerStep, ...] = ()
    captured_plan_path: str | None = None
    model_alias: str | None = None
    model_endpoint: str | None = None
    allow_model_calls: bool = False
    repair_enabled: bool = DEFAULT_LOCAL_MODEL_REPAIR_ENABLED
    max_repair_attempts: int = DEFAULT_LOCAL_MODEL_MAX_REPAIR_ATTEMPTS
    planner_id: str = "browser_live_loop_planner"
    allowed_model_aliases: tuple[str, ...] = ()
    no_think: bool | None = None
    temperature: float = 0.0
    max_tokens: int = 256
    timeout_seconds: float = 120.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousBrowserLiveLoopPlannerConfig:
        kind = str(payload.get("kind", "")).strip().lower()
        planner_id = str(payload.get("planner_id", "browser_live_loop_planner")).strip() or "browser_live_loop_planner"
        metadata = _dict(payload.get("metadata", {}), "planner_backend.metadata")
        if kind == SCRIPTED_PLANNER_KIND:
            scripted_steps_value = payload.get("scripted_steps", [])
            if not isinstance(scripted_steps_value, list):
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.scripted_steps must be a list.")
            scripted_steps = tuple(_planner_step_from_dict(item, index) for index, item in enumerate(scripted_steps_value))
            return cls(kind=kind, scripted_steps=scripted_steps, planner_id=planner_id, metadata=metadata)
        if kind == CAPTURED_PLAN_PLANNER_KIND:
            captured_plan_path = _safe_relative_path(payload.get("captured_plan_path"), "planner_backend.captured_plan_path")
            if captured_plan_path is None:
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.captured_plan_path must be a safe relative path.")
            return cls(
                kind=kind,
                captured_plan_path=captured_plan_path,
                planner_id=planner_id,
                metadata=metadata,
            )
        if kind == LOCAL_MODEL_PLANNER_KIND:
            model_alias = _safe_identifier(payload.get("model_alias", DEFAULT_LOCAL_MODEL_ALIAS), "planner_backend.model_alias")
            model_endpoint = _safe_endpoint_base_url(payload.get("model_endpoint", DEFAULT_LOCAL_MODEL_ENDPOINT))
            if model_alias is None:
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.model_alias must be a safe identifier.")
            if model_endpoint is None:
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.model_endpoint must be a safe endpoint URL.")
            allow_model_calls = payload.get("allow_model_calls", False)
            if not isinstance(allow_model_calls, bool):
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.allow_model_calls must be a boolean.")
            repair_enabled = payload.get("repair_enabled", DEFAULT_LOCAL_MODEL_REPAIR_ENABLED)
            if not isinstance(repair_enabled, bool):
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.repair_enabled must be a boolean.")
            max_repair_attempts = _int(payload.get("max_repair_attempts", DEFAULT_LOCAL_MODEL_MAX_REPAIR_ATTEMPTS), "planner_backend.max_repair_attempts")
            if max_repair_attempts < 0:
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.max_repair_attempts must be a non-negative integer.")
            allowed_model_aliases = tuple(
                str(item).strip()
                for item in payload.get("allowed_model_aliases", [])
                if isinstance(item, str) and item.strip()
            )
            no_think = payload.get("no_think")
            if no_think is not None and not isinstance(no_think, bool):
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.no_think must be a boolean if provided.")
            temperature = _float(payload.get("temperature", 0.0), "planner_backend.temperature")
            max_tokens = _int(payload.get("max_tokens", 256), "planner_backend.max_tokens")
            timeout_seconds = _float(payload.get("timeout_seconds", 120.0), "planner_backend.timeout_seconds")
            if temperature is None or max_tokens is None or timeout_seconds is None:
                raise AutonomousBrowserLiveLoopConfigError("planner_backend numeric fields are invalid.")
            return cls(
                kind=kind,
                model_alias=model_alias,
                model_endpoint=model_endpoint,
                allow_model_calls=allow_model_calls,
                repair_enabled=repair_enabled,
                max_repair_attempts=max_repair_attempts,
                planner_id=planner_id,
                allowed_model_aliases=allowed_model_aliases,
                no_think=no_think,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                metadata=metadata,
            )
        raise AutonomousBrowserLiveLoopConfigError("planner_backend.kind must be scripted, captured_plan, or local_model.")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "planner_id": self.planner_id,
            "metadata": dict(self.metadata),
        }
        if self.scripted_steps:
            payload["scripted_steps"] = [step.to_dict() for step in self.scripted_steps]
        if self.captured_plan_path is not None:
            payload["captured_plan_path"] = self.captured_plan_path
        if self.model_alias is not None:
            payload["model_alias"] = self.model_alias
        if self.model_endpoint is not None:
            payload["model_endpoint"] = self.model_endpoint
        if self.allowed_model_aliases:
            payload["allowed_model_aliases"] = list(self.allowed_model_aliases)
        if self.kind == LOCAL_MODEL_PLANNER_KIND or self.allow_model_calls:
            payload["allow_model_calls"] = self.allow_model_calls
        if self.kind == LOCAL_MODEL_PLANNER_KIND or self.repair_enabled:
            payload["repair_enabled"] = self.repair_enabled
        if self.kind == LOCAL_MODEL_PLANNER_KIND or self.max_repair_attempts != DEFAULT_LOCAL_MODEL_MAX_REPAIR_ATTEMPTS:
            payload["max_repair_attempts"] = self.max_repair_attempts
        if self.no_think is not None:
            payload["no_think"] = self.no_think
        if self.kind == LOCAL_MODEL_PLANNER_KIND:
            payload["temperature"] = self.temperature
            payload["max_tokens"] = self.max_tokens
            payload["timeout_seconds"] = self.timeout_seconds
        return payload


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopCompletionCriteria:
    url: str | None = None
    any_text: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> AutonomousBrowserLiveLoopCompletionCriteria:
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise AutonomousBrowserLiveLoopConfigError("completion_policy scenario criteria must be objects.")
        any_text = tuple(_string_list(payload.get("any_text", []), "completion_policy.scenario_criteria.any_text"))
        return cls(
            url=_optional_text(payload.get("url")),
            any_text=any_text,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "any_text": list(self.any_text),
        }
        if self.url is not None:
            payload["url"] = self.url
        return payload


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopCompletionPolicyConfig:
    enabled: bool = False
    policy_id: str = "fixture_goal_completion_v1"
    scenario_criteria: dict[str, AutonomousBrowserLiveLoopCompletionCriteria] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any] | None,
    ) -> AutonomousBrowserLiveLoopCompletionPolicyConfig:
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise AutonomousBrowserLiveLoopConfigError("completion_policy must be an object.")
        enabled = payload.get("enabled", False)
        if not isinstance(enabled, bool):
            raise AutonomousBrowserLiveLoopConfigError("completion_policy.enabled must be a boolean.")
        policy_id = str(payload.get("policy_id", "fixture_goal_completion_v1")).strip() or "fixture_goal_completion_v1"
        if any(ch in policy_id for ch in ("\\", "/", ":", "\0")):
            raise AutonomousBrowserLiveLoopConfigError("completion_policy.policy_id must be a safe identifier.")
        scenario_criteria_payload = payload.get("scenario_criteria", {})
        if not isinstance(scenario_criteria_payload, Mapping):
            raise AutonomousBrowserLiveLoopConfigError("completion_policy.scenario_criteria must be an object.")
        scenario_criteria: dict[str, AutonomousBrowserLiveLoopCompletionCriteria] = {}
        for scenario_id, criteria_payload in scenario_criteria_payload.items():
            scenario_key = _required_identifier(scenario_id, "completion_policy.scenario_criteria key")
            scenario_criteria[scenario_key] = AutonomousBrowserLiveLoopCompletionCriteria.from_dict(criteria_payload)
        metadata = _dict(payload.get("metadata", {}), "completion_policy.metadata")
        return cls(
            enabled=enabled,
            policy_id=policy_id,
            scenario_criteria=scenario_criteria,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "policy_id": self.policy_id,
            "scenario_criteria": {key: value.to_dict() for key, value in self.scenario_criteria.items()},
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopConfig:
    schema_version: str
    scenario_id: str
    loop_backend: str
    output_dir: str
    no_runtime_execution: bool
    max_steps: int
    max_repeated_action_count: int
    browser_session: AutonomousBrowserLiveLoopBrowserSessionConfig
    planner_backend: AutonomousBrowserLiveLoopPlannerConfig
    completion_policy: AutonomousBrowserLiveLoopCompletionPolicyConfig = field(default_factory=AutonomousBrowserLiveLoopCompletionPolicyConfig)
    limitations: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousBrowserLiveLoopConfig:
        schema_version = str(payload.get("schema_version", "")).strip()
        scenario_id = _required_identifier(payload.get("scenario_id"), "scenario_id")
        loop_backend = str(payload.get("loop_backend", DEFAULT_LOOP_BACKEND)).strip().lower() or DEFAULT_LOOP_BACKEND
        output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
        if output_dir is None:
            raise AutonomousBrowserLiveLoopConfigError("output_dir must be a safe relative path.")
        no_runtime_execution = payload.get("no_runtime_execution")
        max_steps = _int(payload.get("max_steps", DEFAULT_MAX_STEPS), "max_steps")
        max_repeated_action_count = _int(payload.get("max_repeated_action_count", DEFAULT_MAX_REPEATED_ACTION_COUNT), "max_repeated_action_count")
        browser_session_payload = payload.get("browser_session")
        planner_backend_payload = payload.get("planner_backend")
        if not isinstance(browser_session_payload, Mapping):
            raise AutonomousBrowserLiveLoopConfigError("browser_session must be an object.")
        if not isinstance(planner_backend_payload, Mapping):
            raise AutonomousBrowserLiveLoopConfigError("planner_backend must be an object.")
        limitations = tuple(
            str(item).strip()
            for item in payload.get("limitations", [])
            if isinstance(item, str) and item.strip()
        )
        config = cls(
            schema_version=schema_version,
            scenario_id=scenario_id,
            loop_backend=loop_backend,
            output_dir=output_dir,
            no_runtime_execution=bool(no_runtime_execution),
            max_steps=max_steps,
            max_repeated_action_count=max_repeated_action_count,
            browser_session=AutonomousBrowserLiveLoopBrowserSessionConfig.from_dict(browser_session_payload),
            planner_backend=AutonomousBrowserLiveLoopPlannerConfig.from_dict(planner_backend_payload),
            completion_policy=AutonomousBrowserLiveLoopCompletionPolicyConfig.from_dict(payload.get("completion_policy")),
            limitations=limitations,
        )
        return config.validate()

    def validate(self) -> AutonomousBrowserLiveLoopConfig:
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise AutonomousBrowserLiveLoopConfigError("schema_version must match autonomous_browser_live_loop_config_v1.")
        if self.loop_backend != DEFAULT_LOOP_BACKEND:
            raise AutonomousBrowserLiveLoopConfigError("loop_backend must be offline_fixture.")
        if not self.no_runtime_execution:
            raise AutonomousBrowserLiveLoopConfigError("no_runtime_execution must be true.")
        if self.max_steps <= 0:
            raise AutonomousBrowserLiveLoopConfigError("max_steps must be positive.")
        if self.max_repeated_action_count <= 0:
            raise AutonomousBrowserLiveLoopConfigError("max_repeated_action_count must be positive.")
        if not self.browser_session.allowed_domains:
            raise AutonomousBrowserLiveLoopConfigError("browser_session.allowed_domains must be non-empty.")
        if self.planner_backend.kind == SCRIPTED_PLANNER_KIND and not self.planner_backend.scripted_steps:
            raise AutonomousBrowserLiveLoopConfigError("planner_backend.scripted_steps must be non-empty.")
        if self.planner_backend.kind == CAPTURED_PLAN_PLANNER_KIND and self.planner_backend.captured_plan_path is None:
            raise AutonomousBrowserLiveLoopConfigError("planner_backend.captured_plan_path must be provided.")
        if self.planner_backend.kind == LOCAL_MODEL_PLANNER_KIND:
            if self.planner_backend.model_alias is None:
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.model_alias must be provided.")
            if self.planner_backend.model_endpoint is None:
                raise AutonomousBrowserLiveLoopConfigError("planner_backend.model_endpoint must be provided.")
        if self.completion_policy.enabled:
            if not self.completion_policy.scenario_criteria:
                raise AutonomousBrowserLiveLoopConfigError("completion_policy.scenario_criteria must be non-empty when enabled.")
            for scenario_id, criteria in self.completion_policy.scenario_criteria.items():
                if not criteria.url:
                    raise AutonomousBrowserLiveLoopConfigError(
                        f"completion_policy.scenario_criteria[{scenario_id}].url must be provided when enabled."
                    )
                if not criteria.any_text:
                    raise AutonomousBrowserLiveLoopConfigError(
                        f"completion_policy.scenario_criteria[{scenario_id}].any_text must be non-empty when enabled."
                    )
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "loop_backend": self.loop_backend,
            "output_dir": self.output_dir,
            "no_runtime_execution": self.no_runtime_execution,
            "max_steps": self.max_steps,
            "max_repeated_action_count": self.max_repeated_action_count,
            "browser_session": self.browser_session.to_dict(),
            "planner_backend": self.planner_backend.to_dict(),
            "completion_policy": self.completion_policy.to_dict(),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopSummary:
    schema_version: str
    status: str
    scenario_id: str
    loop_backend: str
    planner_backend: dict[str, Any]
    max_steps: int
    steps_attempted: int
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    expected_results_passed: int
    expected_results_failed: int
    observations_total: int
    stop_reason: str | None
    error_code: str | None
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    no_runtime_execution: bool
    output_dir: str
    trace_path: str
    limitations: tuple[str, ...] = ()
    runtime_trace: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "scenario_id": self.scenario_id,
            "loop_backend": self.loop_backend,
            "planner_backend": dict(self.planner_backend),
            "max_steps": self.max_steps,
            "steps_attempted": self.steps_attempted,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "observations_total": self.observations_total,
            "stop_reason": self.stop_reason,
            "error_code": self.error_code,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "no_runtime_execution": self.no_runtime_execution,
            "output_dir": self.output_dir,
            "trace_path": self.trace_path,
            "limitations": list(self.limitations),
            "runtime_trace": [dict(item) for item in self.runtime_trace],
        }


def load_autonomous_browser_live_loop_config(config_artifact: str | Path | Mapping[str, Any]) -> AutonomousBrowserLiveLoopConfig:
    try:
        payload = _load_json_payload(config_artifact)
    except OSError as exc:
        raise AutonomousBrowserLiveLoopConfigError("live loop config could not be read.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomousBrowserLiveLoopConfigError("live loop config JSON is malformed.") from exc
    if not isinstance(payload, dict):
        raise AutonomousBrowserLiveLoopConfigError("live loop config root must be a JSON object.")
    return AutonomousBrowserLiveLoopConfig.from_dict(payload)


def run_autonomous_browser_live_loop(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    model_client: ChatCompletionClient | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    try:
        config = load_autonomous_browser_live_loop_config(config_artifact)
    except AutonomousBrowserLiveLoopConfigError as exc:
        return _failure_summary(
            status="failed",
            error_code="config_validation_failed",
            scenario_id=None,
            loop_backend=DEFAULT_LOOP_BACKEND,
            planner_backend={"kind": None},
            max_steps=0,
            output_dir=None,
            trace_path=None,
            limitations=tuple(),
            diagnostics={"config_error": str(exc)},
        )

    try:
        planner_backend = _load_planner_backend(config.planner_backend, repo_root=repo)
    except (AutonomousBrowserLiveLoopConfigError, LocalModelLivePlannerError, ValueError) as exc:
        return _failure_summary(
            status="refused" if isinstance(exc, LocalModelLivePlannerError) else "failed",
            error_code=getattr(exc, "error_code", None) or "planner_backend_validation_failed",
            scenario_id=config.scenario_id,
            loop_backend=config.loop_backend,
            planner_backend=config.planner_backend.to_dict(),
            max_steps=config.max_steps,
            output_dir=config.output_dir,
            trace_path=f"{config.output_dir}/autonomous_browser_live_loop_trace.json",
            limitations=_limitations(config),
            diagnostics={"planner_backend_error": str(exc)},
        )

    if isinstance(planner_backend, LocalModelLivePlanner):
        if model_client is not None:
            planner_backend.client = model_client
        try:
            planner_backend.validate_runtime_guard()
        except LocalModelLivePlannerError as exc:
            return _failure_summary(
                status="refused",
                error_code=exc.error_code,
                scenario_id=config.scenario_id,
                loop_backend=config.loop_backend,
                planner_backend=planner_backend.to_summary(),
                max_steps=config.max_steps,
                output_dir=config.output_dir,
                trace_path=f"{config.output_dir}/autonomous_browser_live_loop_trace.json",
                limitations=_limitations(config),
                diagnostics={"planner_backend_error": str(exc), **exc.diagnostics},
            )

    output_dir = repo / config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_rel_path = f"{config.output_dir}/autonomous_browser_live_loop_trace.json"
    trace_path = repo / trace_rel_path

    session = BrowserRuntimeSession(
        session_id=config.browser_session.session_id,
        agent_id=config.browser_session.agent_id,
        workspace_id=config.browser_session.workspace_id,
        environment_id=config.browser_session.environment_id,
        allowed_domains=config.browser_session.allowed_domains,
        start_url=config.browser_session.start_url,
        policy_flags=BrowserRuntimePolicy().to_flags(),
    )
    executor = FixtureBackedBrowserRuntimeExecutor(
        fixture_manifest_path=config.browser_session.fixture_manifest_path,
        project_root=repo,
        policy=BrowserRuntimePolicy(),
    )
    verifier = BrowserRuntimeVerifier()

    current_observation = _initial_observation(
        session,
        config.scenario_id,
        config.browser_session.fixture_manifest_path,
        repo,
    )
    observation_count = 1
    trace_entries: list[dict[str, Any]] = []
    actions_attempted = 0
    actions_succeeded = 0
    actions_failed = 0
    expected_results_passed = 0
    expected_results_failed = 0
    steps_attempted = 0
    stop_reason: str | None = None
    error_code: str | None = None
    status = "succeeded"
    model_execution = False
    repeated_signature: tuple[str, str, str, str, bool] | None = None
    repeated_count = 0
    planner_original_error_code: str | None = None
    repair_applied_any = False

    while steps_attempted < config.max_steps:
        planner_input = _planner_observation_dict(current_observation, observation_count)
        if isinstance(planner_backend, LocalModelLivePlanner):
            model_execution = True
        current_url = current_observation.get("current_url")
        if isinstance(current_url, str) and current_url.strip():
            session.current_url = current_url.strip()
        try:
            planned_step = planner_backend.next_step(planner_input)
        except LocalModelLivePlannerError as exc:
            error_code = exc.error_code
            status = "refused" if exc.error_code in {"allow_model_calls_required", "non_local_model_endpoint", "unsupported_model_alias"} else "rejected"
            stop_reason = "planner_backend_refused" if status == "refused" else "planner_action_rejected"
            runtime_trace: tuple[dict[str, Any], ...] = ()
            if status == "rejected" and (exc.error_code or "").startswith(("model_output_", "model_response_", "model_finish_reason_")):
                runtime_trace = (
                    {
                        "step_index": steps_attempted + 1,
                        "observation_id": current_observation["observation_id"],
                        "planner_action": None,
                        "validation_status": "skipped",
                        "fixture_execution_status": "skipped",
                        "action_result": None,
                        "expected_result": None,
                        "next_observation_id": current_observation["observation_id"],
                        "error_code": error_code,
                    },
                )
            if runtime_trace:
                trace_entries = list(runtime_trace)
            break
        if planned_step is None:
            stop_reason = "planner_exhausted"
            break

        planner_action = planned_step.to_dict()
        repair_attempts_for_step = 0
        repair_original_error_code: str | None = None
        repair_applied = False

        if planned_step.done:
            steps_attempted += 1
            trace_entries.append(
                {
                    "step_index": steps_attempted,
                    "observation_id": current_observation["observation_id"],
                    "planner_action": planner_action,
                    "validation_status": "skipped",
                    "fixture_execution_status": "skipped",
                    "action_result": None,
                    "expected_result": None,
                    "next_observation_id": current_observation["observation_id"],
                    "error_code": None,
                }
            )
            stop_reason = "planner_signaled_done"
            break

        if isinstance(planner_backend, LocalModelLivePlanner) and planned_step.action_name not in ALLOWED_LOCAL_MODEL_ACTION_NAMES:
            steps_attempted += 1
            error_code = "model_output_unsupported_action"
            status = "rejected"
            stop_reason = "planner_action_rejected"
            trace_entries.append(
                {
                    "step_index": steps_attempted,
                    "observation_id": current_observation["observation_id"],
                    "planner_action": planner_action,
                    "validation_status": "rejected",
                    "fixture_execution_status": "skipped",
                    "action_result": None,
                    "expected_result": None,
                    "next_observation_id": current_observation["observation_id"],
                    "error_code": error_code,
                }
            )
            break

        if isinstance(planner_backend, LocalModelLivePlanner) and not _observation_has_open_page(current_observation) and planned_step.action_name in {
            "browser_click",
            "browser_extract_text",
            "browser_snapshot",
        }:
            error_code = "live_action_requires_open_page"
            status = "rejected"
            stop_reason = "planner_action_rejected"
            trace_entries.append(
                {
                    "step_index": steps_attempted + 1,
                    "observation_id": current_observation["observation_id"],
                    "planner_action": planner_action,
                    "validation_status": "rejected",
                    "fixture_execution_status": "skipped",
                    "action_result": None,
                    "expected_result": None,
                    "next_observation_id": current_observation["observation_id"],
                    "error_code": error_code,
                }
            )
            break

        expected_text_issue = _planner_expected_text_not_atomic(planned_step.expected_text)
        if expected_text_issue is not None:
            steps_attempted += 1
            error_code = expected_text_issue["error_code"]
            status = "rejected"
            stop_reason = "planner_action_rejected"
            trace_entries.append(
                {
                    "step_index": steps_attempted,
                    "observation_id": current_observation["observation_id"],
                    "planner_action": planner_action,
                    "validation_status": "rejected",
                    "fixture_execution_status": "skipped",
                    "action_result": None,
                    "expected_result": {
                        "passed": False,
                        "reason": error_code,
                        "metadata": expected_text_issue["metadata"],
                    },
                    "next_observation_id": current_observation["observation_id"],
                    "error_code": error_code,
                }
            )
            break

        if not planned_step.expected_text.strip():
            steps_attempted += 1
            error_code = "missing_expected_text"
            status = "rejected"
            stop_reason = "planner_action_rejected"
            trace_entries.append(
                {
                    "step_index": steps_attempted,
                    "observation_id": current_observation["observation_id"],
                    "planner_action": planner_action,
                    "validation_status": "rejected",
                    "fixture_execution_status": "skipped",
                    "action_result": None,
                    "expected_result": None,
                    "next_observation_id": current_observation["observation_id"],
                    "error_code": error_code,
                }
            )
            break

        signature = _action_signature(planned_step)
        if signature == repeated_signature:
            repeated_count += 1
        else:
            repeated_signature = signature
            repeated_count = 1
        if repeated_count > config.max_repeated_action_count:
            steps_attempted += 1
            error_code = "repeated_planner_action_limit_reached"
            status = "rejected"
            stop_reason = "repeated_action_guard_triggered"
            trace_entries.append(
                {
                    "step_index": steps_attempted,
                    "observation_id": current_observation["observation_id"],
                    "planner_action": planner_action,
                    "validation_status": "rejected",
                    "fixture_execution_status": "skipped",
                    "action_result": None,
                    "expected_result": None,
                    "next_observation_id": current_observation["observation_id"],
                    "error_code": error_code,
                }
            )
            break

        validation_result = validate_autonomous_browser_plan(
            {
                "schema_version": "autonomous_browser_plan_v1",
                "plan_id": f"{config.scenario_id}_{planned_step.step_id}_{steps_attempted + 1}",
                "goal": f"Live loop step {planned_step.step_id}",
                "scenario_id": config.scenario_id,
                "max_actions": 1,
                "actions": [
                    {
                        "step_id": planned_step.step_id,
                        "action_name": planned_step.action_name,
                        "parameters": dict(planned_step.parameters),
                        "expected_text": planned_step.expected_text,
                        **({"expected_url": planned_step.expected_url} if planned_step.expected_url is not None else {}),
                    }
                ],
            }
        )
        validation_status = str(validation_result.get("status", "rejected"))
        if validation_status != "accepted":
            error_code = str(validation_result.get("error_code") or "browser_plan_validation_failed")
            status = "rejected"
            stop_reason = "planner_action_rejected"
            trace_entries.append(
                {
                    "step_index": steps_attempted,
                    "observation_id": current_observation["observation_id"],
                    "planner_action": planner_action,
                    "validation_status": validation_status,
                    "fixture_execution_status": "skipped",
                    "action_result": None,
                    "expected_result": None,
                    "next_observation_id": current_observation["observation_id"],
                    "error_code": error_code,
                }
            )
            break

        if planned_step.action_name == "browser_open_url":
            expected_text_issue = _browser_open_url_expected_text_not_visible(
                planned_step.expected_text,
                planned_step.parameters,
                session=session,
                fixture_manifest_path=config.browser_session.fixture_manifest_path,
                repo_root=repo,
            )
            if expected_text_issue is not None:
                if isinstance(planner_backend, LocalModelLivePlanner):
                    repair_original_error_code = repair_original_error_code or expected_text_issue["error_code"]
                    planner_original_error_code = planner_original_error_code or repair_original_error_code
                    try:
                        repaired_step = _attempt_local_model_action_repair(
                            planner_backend,
                            observation=current_observation,
                            invalid_action=planned_step,
                            error_code=expected_text_issue["error_code"],
                            error_message="Model response expected_text must match the destination page for browser_open_url.",
                            error_diagnostics=expected_text_issue,
                        )
                    except LocalModelLivePlannerError as repair_exc:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_text_issue["error_code"]
                        steps_attempted += 1
                        error_code = repair_exc.error_code
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_text_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": True,
                                    "original_error_code": repair_original_error_code or expected_text_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                    if repaired_step is not None:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_text_issue["error_code"]
                        planner_original_error_code = planner_original_error_code or repair_original_error_code
                        planned_step = repaired_step
                        planner_action = planned_step.to_dict()
                        repair_applied = True
                        expected_text_issue = _browser_open_url_expected_text_not_visible(
                            planned_step.expected_text,
                            planned_step.parameters,
                            session=session,
                            fixture_manifest_path=config.browser_session.fixture_manifest_path,
                            repo_root=repo,
                        )
                        if expected_text_issue is not None:
                            steps_attempted += 1
                            error_code = expected_text_issue["error_code"]
                            status = "rejected"
                            stop_reason = "planner_action_rejected"
                            trace_entries.append(
                                {
                                    "step_index": steps_attempted,
                                    "observation_id": current_observation["observation_id"],
                                    "planner_action": planner_action,
                                    "validation_status": "accepted",
                                    "fixture_execution_status": "skipped",
                                    "action_result": None,
                                    "expected_result": {
                                        "passed": False,
                                        "reason": error_code,
                                        "metadata": expected_text_issue["metadata"],
                                    },
                                    "next_observation_id": current_observation["observation_id"],
                                    "error_code": error_code,
                                }
                            )
                            break
                    else:
                        steps_attempted += 1
                        error_code = expected_text_issue["error_code"]
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_text_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": repair_applied,
                                    "original_error_code": repair_original_error_code or expected_text_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                else:
                    steps_attempted += 1
                    error_code = expected_text_issue["error_code"]
                    status = "rejected"
                    stop_reason = "planner_action_rejected"
                    trace_entries.append(
                        {
                            "step_index": steps_attempted,
                            "observation_id": current_observation["observation_id"],
                            "planner_action": planner_action,
                            "validation_status": "accepted",
                            "fixture_execution_status": "skipped",
                            "action_result": None,
                            "expected_result": {
                                "passed": False,
                                "reason": error_code,
                                "metadata": expected_text_issue["metadata"],
                            },
                            "next_observation_id": current_observation["observation_id"],
                            "error_code": error_code,
                        }
                    )
                    break

        click_destination_resolution = None
        if planned_step.action_name == "browser_click":
            click_destination_resolution = _resolve_browser_click_destination(
                planned_step.parameters,
                session=session,
                fixture_manifest_path=config.browser_session.fixture_manifest_path,
                repo_root=repo,
            )
            click_target_issue = _browser_click_target_not_visible(
                planned_step.parameters,
                current_observation=current_observation,
                session=session,
                fixture_manifest_path=config.browser_session.fixture_manifest_path,
                repo_root=repo,
            )
            if click_target_issue is not None:
                if isinstance(planner_backend, LocalModelLivePlanner):
                    repair_original_error_code = repair_original_error_code or click_target_issue["error_code"]
                    planner_original_error_code = planner_original_error_code or repair_original_error_code
                    try:
                        repaired_step = _attempt_local_model_action_repair(
                            planner_backend,
                            observation=current_observation,
                            invalid_action=planned_step,
                            error_code=click_target_issue["error_code"],
                            error_message="Model response click target is not visible on the current page.",
                            error_diagnostics=click_target_issue,
                        )
                    except LocalModelLivePlannerError as repair_exc:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or click_target_issue["error_code"]
                        steps_attempted += 1
                        error_code = repair_exc.error_code
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": click_target_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": True,
                                    "original_error_code": repair_original_error_code or click_target_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                    if repaired_step is not None:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or click_target_issue["error_code"]
                        planner_original_error_code = planner_original_error_code or repair_original_error_code
                        planned_step = repaired_step
                        planner_action = planned_step.to_dict()
                        repair_applied = True
                        click_target_issue = _browser_click_target_not_visible(
                            planned_step.parameters,
                            current_observation=current_observation,
                            session=session,
                            fixture_manifest_path=config.browser_session.fixture_manifest_path,
                            repo_root=repo,
                        )
                        if click_target_issue is not None:
                            steps_attempted += 1
                            error_code = click_target_issue["error_code"]
                            status = "rejected"
                            stop_reason = "planner_action_rejected"
                            _count_repair_as_failed(planner_backend, repair_applied)
                            trace_entries.append(
                                {
                                    "step_index": steps_attempted,
                                    "observation_id": current_observation["observation_id"],
                                    "planner_action": planner_action,
                                    "validation_status": "rejected",
                                    "fixture_execution_status": "skipped",
                                    "action_result": None,
                                    "expected_result": {
                                        "passed": False,
                                        "reason": error_code,
                                        "metadata": click_target_issue["metadata"],
                                    },
                                    "next_observation_id": current_observation["observation_id"],
                                    "error_code": error_code,
                                    "metadata": {
                                        "repair_applied": repair_applied,
                                        "original_error_code": repair_original_error_code or click_target_issue["error_code"],
                                        "repair_error_code": error_code,
                                    },
                                }
                            )
                            break
                    else:
                        steps_attempted += 1
                        error_code = click_target_issue["error_code"]
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": click_target_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": repair_applied,
                                    "original_error_code": repair_original_error_code or click_target_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                else:
                    steps_attempted += 1
                    error_code = click_target_issue["error_code"]
                    status = "rejected"
                    stop_reason = "planner_action_rejected"
                    trace_entries.append(
                        {
                            "step_index": steps_attempted,
                            "observation_id": current_observation["observation_id"],
                            "planner_action": planner_action,
                            "validation_status": "rejected",
                            "fixture_execution_status": "skipped",
                            "action_result": None,
                            "expected_result": {
                                "passed": False,
                                "reason": error_code,
                                "metadata": click_target_issue["metadata"],
                            },
                            "next_observation_id": current_observation["observation_id"],
                            "error_code": error_code,
                        }
                    )
                    break
            unsupported_click_issue = _browser_click_target_not_supported(
                planned_step.parameters,
                session=session,
                fixture_manifest_path=config.browser_session.fixture_manifest_path,
                repo_root=repo,
            )
            if unsupported_click_issue is not None:
                if isinstance(planner_backend, LocalModelLivePlanner):
                    repair_original_error_code = repair_original_error_code or unsupported_click_issue["error_code"]
                    planner_original_error_code = planner_original_error_code or repair_original_error_code
                    try:
                        repaired_step = _attempt_local_model_action_repair(
                            planner_backend,
                            observation=current_observation,
                            invalid_action=planned_step,
                            error_code=unsupported_click_issue["error_code"],
                            error_message="Model response click target does not match a visible local link/button.",
                            error_diagnostics=unsupported_click_issue,
                        )
                    except LocalModelLivePlannerError as repair_exc:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or unsupported_click_issue["error_code"]
                        steps_attempted += 1
                        error_code = repair_exc.error_code
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": unsupported_click_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": True,
                                    "original_error_code": repair_original_error_code or unsupported_click_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                    if repaired_step is not None:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or unsupported_click_issue["error_code"]
                        planner_original_error_code = planner_original_error_code or repair_original_error_code
                        planned_step = repaired_step
                        planner_action = planned_step.to_dict()
                        repair_applied = True
                        unsupported_click_issue = _browser_click_target_not_supported(
                            planned_step.parameters,
                            session=session,
                            fixture_manifest_path=config.browser_session.fixture_manifest_path,
                            repo_root=repo,
                        )
                        if unsupported_click_issue is not None:
                            steps_attempted += 1
                            error_code = unsupported_click_issue["error_code"]
                            status = "rejected"
                            stop_reason = "planner_action_rejected"
                            _count_repair_as_failed(planner_backend, repair_applied)
                            trace_entries.append(
                                {
                                    "step_index": steps_attempted,
                                    "observation_id": current_observation["observation_id"],
                                    "planner_action": planner_action,
                                    "validation_status": "accepted",
                                    "fixture_execution_status": "skipped",
                                    "action_result": None,
                                    "expected_result": {
                                        "passed": False,
                                        "reason": error_code,
                                        "metadata": unsupported_click_issue["metadata"],
                                    },
                                    "next_observation_id": current_observation["observation_id"],
                                    "error_code": error_code,
                                }
                            )
                            break
                    else:
                        steps_attempted += 1
                        error_code = unsupported_click_issue["error_code"]
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": unsupported_click_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": repair_applied,
                                    "original_error_code": repair_original_error_code or unsupported_click_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
            expected_url_issue = _browser_click_expected_url_not_valid(
                planned_step.expected_url,
                expected_text=planned_step.expected_text,
                parameters=planned_step.parameters,
                session=session,
                fixture_manifest_path=config.browser_session.fixture_manifest_path,
                repo_root=repo,
            )
            if expected_url_issue is not None:
                if isinstance(planner_backend, LocalModelLivePlanner):
                    repair_original_error_code = repair_original_error_code or expected_url_issue["error_code"]
                    planner_original_error_code = planner_original_error_code or repair_original_error_code
                    try:
                        repaired_step = _attempt_local_model_action_repair(
                            planner_backend,
                            observation=current_observation,
                            invalid_action=planned_step,
                            error_code=expected_url_issue["error_code"],
                            error_message="Model response expected_url is not valid for the current click target.",
                            error_diagnostics=expected_url_issue,
                        )
                    except LocalModelLivePlannerError as repair_exc:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_url_issue["error_code"]
                        steps_attempted += 1
                        error_code = repair_exc.error_code
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_url_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": True,
                                    "original_error_code": repair_original_error_code or expected_url_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                    if repaired_step is not None:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_url_issue["error_code"]
                        planner_original_error_code = planner_original_error_code or repair_original_error_code
                        planned_step = repaired_step
                        planner_action = planned_step.to_dict()
                        repair_applied = True
                        expected_url_issue = _browser_click_expected_url_not_valid(
                            planned_step.expected_url,
                            expected_text=planned_step.expected_text,
                            parameters=planned_step.parameters,
                            session=session,
                            fixture_manifest_path=config.browser_session.fixture_manifest_path,
                            repo_root=repo,
                        )
                        if expected_url_issue is not None:
                            steps_attempted += 1
                            error_code = expected_url_issue["error_code"]
                            status = "rejected"
                            stop_reason = "planner_action_rejected"
                            _count_repair_as_failed(planner_backend, repair_applied)
                            trace_entries.append(
                                {
                                    "step_index": steps_attempted,
                                    "observation_id": current_observation["observation_id"],
                                    "planner_action": planner_action,
                                    "validation_status": "accepted",
                                    "fixture_execution_status": "skipped",
                                    "action_result": None,
                                    "expected_result": {
                                        "passed": False,
                                        "reason": error_code,
                                        "metadata": expected_url_issue["metadata"],
                                    },
                                    "next_observation_id": current_observation["observation_id"],
                                    "error_code": error_code,
                                }
                            )
                            break
                    else:
                        steps_attempted += 1
                        error_code = expected_url_issue["error_code"]
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_url_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": repair_applied,
                                    "original_error_code": repair_original_error_code or expected_url_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                else:
                    steps_attempted += 1
                    error_code = expected_url_issue["error_code"]
                    status = "rejected"
                    stop_reason = "planner_action_rejected"
                    trace_entries.append(
                        {
                            "step_index": steps_attempted,
                            "observation_id": current_observation["observation_id"],
                            "planner_action": planner_action,
                            "validation_status": "accepted",
                            "fixture_execution_status": "skipped",
                            "action_result": None,
                            "expected_result": {
                                "passed": False,
                                "reason": error_code,
                                "metadata": expected_url_issue["metadata"],
                            },
                            "next_observation_id": current_observation["observation_id"],
                            "error_code": error_code,
                        }
                    )
                    break

            expected_url_issue = _browser_click_expected_url_not_matching_destination(
                planned_step.expected_url,
                planned_step.parameters,
                session=session,
                fixture_manifest_path=config.browser_session.fixture_manifest_path,
                repo_root=repo,
            )
            if expected_url_issue is not None:
                if isinstance(planner_backend, LocalModelLivePlanner):
                    repair_original_error_code = repair_original_error_code or expected_url_issue["error_code"]
                    planner_original_error_code = planner_original_error_code or repair_original_error_code
                    try:
                        repaired_step = _attempt_local_model_action_repair(
                            planner_backend,
                            observation=current_observation,
                            invalid_action=planned_step,
                            error_code=expected_url_issue["error_code"],
                            error_message="Model response expected_url must match the click destination exactly.",
                            error_diagnostics=expected_url_issue,
                        )
                    except LocalModelLivePlannerError as repair_exc:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_url_issue["error_code"]
                        steps_attempted += 1
                        error_code = repair_exc.error_code
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_url_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": True,
                                    "original_error_code": repair_original_error_code or expected_url_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                    if repaired_step is not None:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_url_issue["error_code"]
                        planner_original_error_code = planner_original_error_code or repair_original_error_code
                        planned_step = repaired_step
                        planner_action = planned_step.to_dict()
                        repair_applied = True
                        expected_url_issue = _browser_click_expected_url_not_matching_destination(
                            planned_step.expected_url,
                            planned_step.parameters,
                            session=session,
                            fixture_manifest_path=config.browser_session.fixture_manifest_path,
                            repo_root=repo,
                        )
                        if expected_url_issue is not None:
                            steps_attempted += 1
                            error_code = expected_url_issue["error_code"]
                            status = "rejected"
                            stop_reason = "planner_action_rejected"
                            trace_entries.append(
                                {
                                    "step_index": steps_attempted,
                                    "observation_id": current_observation["observation_id"],
                                    "planner_action": planner_action,
                                    "validation_status": "accepted",
                                    "fixture_execution_status": "skipped",
                                    "action_result": None,
                                    "expected_result": {
                                        "passed": False,
                                        "reason": error_code,
                                        "metadata": expected_url_issue["metadata"],
                                    },
                                    "next_observation_id": current_observation["observation_id"],
                                    "error_code": error_code,
                                }
                            )
                            break
                    else:
                        steps_attempted += 1
                        error_code = expected_url_issue["error_code"]
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_url_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": repair_applied,
                                    "original_error_code": repair_original_error_code or expected_url_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                else:
                    steps_attempted += 1
                    error_code = expected_url_issue["error_code"]
                    status = "rejected"
                    stop_reason = "planner_action_rejected"
                    trace_entries.append(
                        {
                            "step_index": steps_attempted,
                            "observation_id": current_observation["observation_id"],
                            "planner_action": planner_action,
                            "validation_status": "accepted",
                            "fixture_execution_status": "skipped",
                            "action_result": None,
                            "expected_result": {
                                "passed": False,
                                "reason": error_code,
                                "metadata": expected_url_issue["metadata"],
                            },
                            "next_observation_id": current_observation["observation_id"],
                            "error_code": error_code,
                        }
                    )
                    break

            expected_text_issue = _browser_click_expected_text_not_visible(
                planned_step.expected_text,
                planned_step.parameters,
                session=session,
                fixture_manifest_path=config.browser_session.fixture_manifest_path,
                repo_root=repo,
            )
            if expected_text_issue is not None:
                if isinstance(planner_backend, LocalModelLivePlanner):
                    repair_original_error_code = repair_original_error_code or expected_text_issue["error_code"]
                    planner_original_error_code = planner_original_error_code or repair_original_error_code
                    try:
                        repaired_step = _attempt_local_model_action_repair(
                            planner_backend,
                            observation=current_observation,
                            invalid_action=planned_step,
                            error_code=expected_text_issue["error_code"],
                            error_message="Model response expected_text must describe the destination page, not the current page.",
                            error_diagnostics=expected_text_issue,
                        )
                    except LocalModelLivePlannerError as repair_exc:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_text_issue["error_code"]
                        steps_attempted += 1
                        error_code = repair_exc.error_code
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_text_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": True,
                                    "original_error_code": repair_original_error_code or expected_text_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                    if repaired_step is not None:
                        repair_attempts_for_step += 1
                        repair_original_error_code = repair_original_error_code or expected_text_issue["error_code"]
                        planner_original_error_code = planner_original_error_code or repair_original_error_code
                        planned_step = repaired_step
                        planner_action = planned_step.to_dict()
                        repair_applied = True
                        expected_text_issue = _browser_click_expected_text_not_visible(
                            planned_step.expected_text,
                            planned_step.parameters,
                            session=session,
                            fixture_manifest_path=config.browser_session.fixture_manifest_path,
                            repo_root=repo,
                        )
                        if expected_text_issue is not None:
                            steps_attempted += 1
                            error_code = expected_text_issue["error_code"]
                            status = "rejected"
                            stop_reason = "planner_action_rejected"
                            _count_repair_as_failed(planner_backend, repair_applied)
                            trace_entries.append(
                                {
                                    "step_index": steps_attempted,
                                    "observation_id": current_observation["observation_id"],
                                    "planner_action": planner_action,
                                    "validation_status": "accepted",
                                    "fixture_execution_status": "skipped",
                                    "action_result": None,
                                    "expected_result": {
                                        "passed": False,
                                        "reason": error_code,
                                        "metadata": expected_text_issue["metadata"],
                                    },
                                    "next_observation_id": current_observation["observation_id"],
                                    "error_code": error_code,
                                }
                            )
                            break
                    else:
                        steps_attempted += 1
                        error_code = expected_text_issue["error_code"]
                        status = "rejected"
                        stop_reason = "planner_action_rejected"
                        trace_entries.append(
                            {
                                "step_index": steps_attempted,
                                "observation_id": current_observation["observation_id"],
                                "planner_action": planner_action,
                                "validation_status": "rejected",
                                "fixture_execution_status": "skipped",
                                "action_result": None,
                                "expected_result": {
                                    "passed": False,
                                    "reason": error_code,
                                    "metadata": expected_text_issue["metadata"],
                                },
                                "next_observation_id": current_observation["observation_id"],
                                "error_code": error_code,
                                "metadata": {
                                    "repair_applied": repair_applied,
                                    "original_error_code": repair_original_error_code or expected_text_issue["error_code"],
                                    "repair_error_code": error_code,
                                },
                            }
                        )
                        break
                else:
                    steps_attempted += 1
                    error_code = expected_text_issue["error_code"]
                    status = "rejected"
                    stop_reason = "planner_action_rejected"
                    trace_entries.append(
                        {
                            "step_index": steps_attempted,
                            "observation_id": current_observation["observation_id"],
                            "planner_action": planner_action,
                            "validation_status": "accepted",
                            "fixture_execution_status": "skipped",
                            "action_result": None,
                            "expected_result": {
                                "passed": False,
                                "reason": error_code,
                                "metadata": expected_text_issue["metadata"],
                            },
                            "next_observation_id": current_observation["observation_id"],
                            "error_code": error_code,
                        }
                    )
                    break

        if repair_applied:
            validation_result = validate_autonomous_browser_plan(
                {
                    "schema_version": "autonomous_browser_plan_v1",
                    "plan_id": f"{config.scenario_id}_{planned_step.step_id}_{steps_attempted + 1}",
                    "goal": f"Live loop step {planned_step.step_id}",
                    "scenario_id": config.scenario_id,
                    "max_actions": 1,
                    "actions": [
                        {
                            "step_id": planned_step.step_id,
                            "action_name": planned_step.action_name,
                            "parameters": dict(planned_step.parameters),
                            "expected_text": planned_step.expected_text,
                            **({"expected_url": planned_step.expected_url} if planned_step.expected_url is not None else {}),
                        }
                    ],
                }
            )
            validation_status = str(validation_result.get("status", "rejected"))
            if validation_status != "accepted":
                error_code = str(validation_result.get("error_code") or "browser_plan_validation_failed")
                status = "rejected"
                stop_reason = "planner_action_rejected"
                steps_attempted += 1
                trace_entries.append(
                    {
                        "step_index": steps_attempted,
                        "observation_id": current_observation["observation_id"],
                        "planner_action": planner_action,
                        "validation_status": validation_status,
                        "fixture_execution_status": "skipped",
                        "action_result": None,
                        "expected_result": None,
                        "next_observation_id": current_observation["observation_id"],
                        "error_code": error_code,
                    }
                )
                break

        steps_attempted += 1
        normalized_plan = validation_result.get("normalized_plan")
        assert isinstance(normalized_plan, Mapping)
        normalized_action = normalized_plan["actions"][0]
        action = BrowserRuntimeAction(
            agent_id=config.browser_session.agent_id,
            action_type="browser",
            action_name=str(normalized_action["action_name"]),
            parameters=dict(normalized_action["parameters"]),
            session_id=config.browser_session.session_id,
            task_id=config.scenario_id,
        )
        result = executor.execute(action, session)
        actions_attempted += 1
        if result.success:
            actions_succeeded += 1
        else:
            actions_failed += 1

        verification = verifier.verify(
            result,
            expected_text=planned_step.expected_text,
            expected_url=planned_step.expected_url,
        )
        expected_result = verification.to_dict()
        if verification.passed:
            expected_results_passed += 1
        else:
            expected_results_failed += 1
        if (
            planned_step.action_name == "browser_click"
            and planned_step.expected_url is None
            and click_destination_resolution is not None
            and isinstance(expected_result.get("metadata"), dict)
        ):
            expected_result["metadata"]["resolved_destination_url"] = click_destination_resolution.url

        next_observation = result.observation if result.observation is not None else session.last_observation
        if next_observation is None:
            next_observation = current_observation.get("observation")
        if next_observation is not None:
            observation_count += 1
        next_observation_dict = _observation_dict(next_observation, observation_count)
        metadata = next_observation_dict.get("metadata")
        if isinstance(metadata, dict):
            metadata["page_opened"] = True
            metadata["fixture_manifest_path"] = config.browser_session.fixture_manifest_path
        trace_entries.append(
            {
                "step_index": steps_attempted,
                "observation_id": current_observation["observation_id"],
                "planner_action": planner_action,
                "validation_status": validation_status,
                "fixture_execution_status": "succeeded" if result.success and verification.passed else "failed",
                "action_result": result.to_dict(),
                "expected_result": expected_result,
                "next_observation_id": next_observation_dict["observation_id"],
                "error_code": None
                if result.success and verification.passed
                else result.error_type or verification.reason or "browser_action_failed",
                **(
                    {
                        "metadata": {
                            "repair_applied": True,
                            "original_error_code": repair_original_error_code,
                            "repair_attempts": repair_attempts_for_step,
                        }
                    }
                    if repair_applied
                    else {}
                ),
            }
        )
        if repair_applied:
            repair_applied_any = True

        if not result.success:
            _count_repair_as_failed(planner_backend, repair_applied)
            error_code = result.error_type or "browser_action_failed"
            status = "failed"
            stop_reason = "browser_action_failed"
            break
        if not verification.passed:
            _count_repair_as_failed(planner_backend, repair_applied)
            error_code = verification.reason or "expected_result_failed"
            status = "failed"
            stop_reason = "expected_result_failed"
            break

        current_observation = next_observation_dict
        completion_match = _completion_policy_goal_satisfied(config, current_observation)
        if completion_match is not None:
            matched_criteria = completion_match.get("matched_completion_criteria")
            matched_scenario_id = (
                matched_criteria.get("scenario_id")
                if isinstance(matched_criteria, Mapping)
                else None
            )
            if matched_scenario_id != config.scenario_id:
                stop_reason = "completion_policy_scenario_mismatch"
                status = "failed"
                error_code = "completion_policy_scenario_mismatch"
                if trace_entries:
                    last_trace = trace_entries[-1]
                    metadata = dict(last_trace.get("metadata", {})) if isinstance(last_trace.get("metadata"), Mapping) else {}
                    metadata.update(
                        {
                            "completion_policy_id": completion_match.get("completion_policy_id"),
                            "matched_completion_criteria": matched_criteria,
                            "completion_policy_scenario_mismatch": True,
                        }
                    )
                    last_trace["metadata"] = metadata
                break
            stop_reason = "goal_satisfied"
            status = "succeeded"
            error_code = None
            if trace_entries:
                last_trace = trace_entries[-1]
                metadata = dict(last_trace.get("metadata", {})) if isinstance(last_trace.get("metadata"), Mapping) else {}
                metadata.update(completion_match)
                last_trace["metadata"] = metadata
            break
        if steps_attempted >= config.max_steps:
            stop_reason = "max_steps_reached"
            status = "failed"
            error_code = "max_steps_reached"
            break

    if stop_reason is None:
        stop_reason = "planner_exhausted"
        if status == "succeeded":
            status = "failed"
            error_code = error_code or "planner_exhausted"

    if planner_original_error_code is not None and isinstance(planner_backend, LocalModelLivePlanner):
        planner_backend.original_error_code = planner_original_error_code
    if (
        isinstance(planner_backend, LocalModelLivePlanner)
        and trace_entries
    ):
        repair_succeeded = any(
            isinstance(entry.get("metadata"), Mapping)
            and entry["metadata"].get("repair_applied")
            and entry.get("fixture_execution_status") == "succeeded"
            for entry in trace_entries
        )
        if repair_succeeded and planner_backend.repair_attempts_succeeded == 0 and planner_backend.repair_attempts_failed > 0:
            planner_backend.repair_attempts_succeeded += 1
            planner_backend.repair_attempts_failed -= 1

    summary = AutonomousBrowserLiveLoopSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        scenario_id=config.scenario_id,
        loop_backend=config.loop_backend,
        planner_backend=planner_backend.to_summary(),
        max_steps=config.max_steps,
        steps_attempted=steps_attempted,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_succeeded,
        actions_failed=actions_failed,
        expected_results_passed=expected_results_passed,
        expected_results_failed=expected_results_failed,
        observations_total=observation_count,
        stop_reason=stop_reason,
        error_code=error_code,
        model_execution=model_execution,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        no_runtime_execution=True,
        output_dir=config.output_dir,
        trace_path=trace_rel_path,
        limitations=_limitations(config),
        runtime_trace=tuple(trace_entries),
    )
    payload = summary.to_dict()
    _write_json(trace_path, {
        "schema_version": TRACE_SCHEMA_VERSION,
        "scenario_id": config.scenario_id,
        "trace": trace_entries,
        "observations_total": observation_count,
    })
    _write_json(output_dir / "autonomous_browser_live_loop_summary.json", payload)
    return payload


def write_autonomous_browser_live_loop_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "autonomous_browser_live_loop_summary.json"
    _write_json(path, summary)
    return path


def write_autonomous_browser_live_loop_trace(trace: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "autonomous_browser_live_loop_trace.json"
    _write_json(path, trace)
    return path


def _load_planner_backend(
    planner_backend_config: AutonomousBrowserLiveLoopPlannerConfig,
    *,
    repo_root: Path,
) -> ScriptedLivePlanner | CapturedPlanStepPlanner | LocalModelLivePlanner:
    if planner_backend_config.kind == LOCAL_MODEL_PLANNER_KIND:
        return LocalModelLivePlanner(
            config=LocalModelPlannerConfig.from_dict(planner_backend_config.to_dict()),
            client=None,
            repo_root=repo_root,
        )
    return load_live_planner_backend(planner_backend_config.to_dict(), repo_root=repo_root)


def _initial_observation(
    session: BrowserRuntimeSession,
    scenario_id: str,
    fixture_manifest_path: str,
    repo_root: Path,
) -> dict[str, Any]:
    metadata = {
        "fixture_source": False,
        "browser_opened": False,
        "network_used": False,
        "page_opened": False,
        "fixture_manifest_path": fixture_manifest_path,
        "scenario_id": scenario_id,
    }
    if not session.start_url:
        observation = BrowserRuntimeObservation(
            action_name="planner_observe",
            current_url=None,
            title=None,
            text_preview="",
            metadata=metadata,
        )
        return _observation_dict(observation, 1)

    resolution = resolve_browser_fixture_url(
        session.start_url,
        fixture_manifest_path,
        project_root=repo_root,
        allowed_url_prefixes=_prefixes_for_domains(session.allowed_domains),
        preview_chars=2_000,
    )
    anchors = _start_page_visible_anchors(session.start_url, resolution.title, resolution.extracted_text_preview)
    observation = BrowserRuntimeObservation(
        action_name="planner_observe",
        current_url=None,
        title=resolution.title,
        text_preview=resolution.extracted_text_preview,
        metadata={
            **metadata,
            "start_url": session.start_url,
            "scenario_start_url": session.start_url,
            "start_page_title": resolution.title,
            "start_page_text_preview": resolution.extracted_text_preview,
            "start_page_visible_anchors": list(anchors),
        },
    )
    return _observation_dict(observation, 1)


def _observation_dict(observation: BrowserRuntimeObservation | Mapping[str, Any] | None, index: int) -> dict[str, Any]:
    if observation is None:
        return {
            "observation_id": f"observation_{index:04d}",
            "current_url": None,
            "title": None,
            "text_preview": "",
            "metadata": {},
        }
    if isinstance(observation, Mapping):
        return {
            "observation_id": f"observation_{index:04d}",
            "current_url": observation.get("current_url"),
            "title": observation.get("title"),
            "text_preview": observation.get("text_preview", ""),
            "metadata": dict(observation.get("metadata", {})) if isinstance(observation.get("metadata"), Mapping) else {},
        }
    return {
        "observation_id": f"observation_{index:04d}",
        "current_url": observation.current_url,
        "title": observation.title,
        "text_preview": observation.text_preview,
        "metadata": dict(observation.metadata),
    }


def _planner_observation_dict(observation: Mapping[str, Any], index: int) -> dict[str, Any]:
    payload = dict(observation)
    payload["observation_id"] = payload.get("observation_id", f"observation_{index:04d}")
    return payload


def _action_signature(step: AutonomousBrowserLivePlannerStep) -> tuple[str, str, str, str, bool]:
    return (
        step.action_name,
        json.dumps(step.parameters, ensure_ascii=True, sort_keys=True),
        step.expected_text,
        step.expected_url or "",
        step.done,
    )


def _limitations(config: AutonomousBrowserLiveLoopConfig) -> tuple[str, ...]:
    base = [
        "offline fixture-only live loop",
        "planner backend is scripted, captured-plan, or guarded local-model only",
        "no model calls",
        "no real browser execution",
        "no Playwright import",
        "not production browser automation",
    ]
    if config.planner_backend.kind == LOCAL_MODEL_PLANNER_KIND:
        base[2] = "no model calls unless allow_model_calls is explicitly enabled"
    for item in config.limitations:
        if item and item not in base:
            base.append(item)
    return tuple(base)


def _failure_summary(
    *,
    status: str,
    error_code: str | None,
    scenario_id: str | None,
    loop_backend: str,
    planner_backend: Mapping[str, Any],
    max_steps: int,
    output_dir: str | None,
    trace_path: str | None,
    limitations: tuple[str, ...],
    diagnostics: Mapping[str, Any] | None = None,
    runtime_trace: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    if error_code == "config_validation_failed":
        stop_reason = "config_validation_failed"
    elif status == "refused":
        stop_reason = "planner_backend_refused"
    else:
        stop_reason = "failed"
    summary = AutonomousBrowserLiveLoopSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        scenario_id=scenario_id or "unknown_scenario",
        loop_backend=loop_backend,
        planner_backend=dict(planner_backend),
        max_steps=max_steps,
        steps_attempted=0,
        actions_attempted=0,
        actions_succeeded=0,
        actions_failed=0,
        expected_results_passed=0,
        expected_results_failed=0,
        observations_total=0,
        stop_reason=stop_reason,
        error_code=error_code,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        no_runtime_execution=True,
        output_dir=output_dir or DEFAULT_OUTPUT_DIR,
        trace_path=trace_path or f"{DEFAULT_OUTPUT_DIR}/autonomous_browser_live_loop_trace.json",
        limitations=limitations,
        runtime_trace=runtime_trace,
    )
    payload = summary.to_dict()
    if diagnostics:
        payload["diagnostics"] = _jsonable(diagnostics)
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_json_payload(config_artifact: str | Path | Mapping[str, Any]) -> Any:
    if isinstance(config_artifact, Mapping):
        return dict(config_artifact)
    return json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))


def _safe_relative_path(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        raise AutonomousBrowserLiveLoopConfigError(f"{label} must be a safe relative path.")
    return path.as_posix()


def _safe_endpoint_base_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return None
    if parsed.params or parsed.query or parsed.fragment:
        return None
    return normalized


def _required_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutonomousBrowserLiveLoopConfigError(f"{label} must be a non-empty string.")
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        raise AutonomousBrowserLiveLoopConfigError(f"{label} must be a safe identifier.")
    return stripped


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AutonomousBrowserLiveLoopConfigError(f"{label} must be a list.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise AutonomousBrowserLiveLoopConfigError(f"{label} must contain non-empty strings.")
        out.append(item.strip())
    return out


def _dict(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AutonomousBrowserLiveLoopConfigError(f"{label} must be an object.")
    return dict(value)


def _float(value: Any, label: str) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AutonomousBrowserLiveLoopConfigError(f"{label} must be an integer.")
    return value


def _planner_step_from_dict(value: Any, index: int) -> AutonomousBrowserLivePlannerStep:
    if not isinstance(value, Mapping):
        raise AutonomousBrowserLiveLoopConfigError(f"planner_backend.scripted_steps[{index}] must be an object.")
    step_id = _required_identifier(value.get("step_id"), f"planner_backend.scripted_steps[{index}].step_id")
    action_name = _required_identifier(value.get("action_name"), f"planner_backend.scripted_steps[{index}].action_name")
    parameters = _dict(value.get("parameters", {}), f"planner_backend.scripted_steps[{index}].parameters")
    expected_text = _optional_text(value.get("expected_text"))
    expected_url = _optional_text(value.get("expected_url"))
    done = bool(value.get("done", False))
    metadata = _dict(value.get("metadata", {}), f"planner_backend.scripted_steps[{index}].metadata")
    return AutonomousBrowserLivePlannerStep(
        step_id=step_id,
        action_name=action_name,
        parameters=parameters,
        expected_text=expected_text or "",
        expected_url=expected_url,
        done=done,
        metadata=metadata,
    )


def _prefixes_for_domains(domains: tuple[str, ...]) -> list[str]:
    prefixes: list[str] = []
    for domain in domains:
        prefixes.append(f"http://{domain}")
        prefixes.append(f"https://{domain}")
    return prefixes


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _observation_has_open_page(observation: Mapping[str, Any]) -> bool:
    metadata = observation.get("metadata")
    if not isinstance(metadata, Mapping):
        return False
    for key in ("page_opened", "browser_opened", "fixture_document_opened", "document_opened"):
        if bool(metadata.get(key)):
            return True
    return False


def _browser_click_target_not_visible(
    parameters: Mapping[str, Any],
    *,
    current_observation: Mapping[str, Any],
    session: BrowserRuntimeSession,
    fixture_manifest_path: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    target_text = str(parameters.get("target_text") or parameters.get("text") or "").strip()
    current_url = session.current_url if isinstance(session.current_url, str) else None
    if not target_text or not current_url:
        return None
    try:
        current_resolution = resolve_browser_fixture_url(
            current_url,
            fixture_manifest_path,
            project_root=repo_root,
            allowed_url_prefixes=_prefixes_for_domains(session.allowed_domains),
            preview_chars=2_000,
        )
    except Exception:
        return None
    links = _extract_links(current_resolution.fixture_path.read_text(encoding="utf-8"))
    visible_click_targets = [
        str(link.get("text")).strip()
        for link in links[:8]
        if isinstance(link, Mapping) and isinstance(link.get("text"), str) and str(link.get("text")).strip()
    ]
    destination_resolution = _resolve_browser_click_destination(
        parameters,
        session=session,
        fixture_manifest_path=fixture_manifest_path,
        repo_root=repo_root,
    )
    if destination_resolution is not None:
        return None
    return {
        "error_code": "model_output_click_target_not_visible",
        "metadata": {
            "target_text": target_text,
            "current_url": current_resolution.url,
            "visible_click_targets": visible_click_targets,
            "page_title": current_observation.get("title"),
        },
    }


def _completion_policy_goal_satisfied(
    config: AutonomousBrowserLiveLoopConfig,
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    policy = config.completion_policy
    if not policy.enabled:
        return None
    criteria_key = config.scenario_id
    criteria = policy.scenario_criteria.get(criteria_key)
    if criteria is None:
        return None
    current_url = _optional_text(observation.get("current_url"))
    if criteria.url is not None and current_url != criteria.url:
        return None
    page_title = _optional_text(observation.get("title")) or ""
    page_text = _optional_text(observation.get("text_preview")) or ""
    page_text_blob = " ".join(item for item in (page_title, page_text) if item).strip()
    matched_text_anchors = tuple(anchor for anchor in criteria.any_text if anchor and anchor in page_text_blob)
    if not matched_text_anchors:
        return None
    matched_completion_criteria = {
        "scenario_id": criteria_key,
        "url": criteria.url,
        "any_text": list(criteria.any_text),
        "matched_url": current_url,
        "matched_text_anchors": list(matched_text_anchors),
        "page_title": page_title or None,
    }
    return {
        "goal_satisfied": True,
        "completion_policy_id": policy.policy_id,
        "matched_completion_criteria": matched_completion_criteria,
        "matched_url": current_url,
        "matched_text_anchors": list(matched_text_anchors),
    }


def _count_repair_as_failed(planner_backend: ScriptedLivePlanner | CapturedPlanStepPlanner | LocalModelLivePlanner, repair_applied: bool) -> None:
    if not repair_applied or not isinstance(planner_backend, LocalModelLivePlanner):
        return
    if planner_backend.repair_attempts_succeeded <= 0:
        return
    planner_backend.repair_attempts_succeeded -= 1
    planner_backend.repair_attempts_failed += 1


def _start_page_visible_anchors(start_url: str, title: str | None, text_preview: str) -> tuple[str, ...]:
    hints: list[str] = []
    known_hints = {
        "https://local.intranet/": (
            "Office Intranet Home",
            "Workspace policy",
            "Search marker: fixture-backed result for local policy review.",
        ),
        "https://docs.local/docs/policy-disambiguation": (
            "Policy Disambiguation",
            "Current policy",
            "Search marker: current policy source is the fixture-backed answer.",
        ),
    }
    for hint in known_hints.get(start_url, ()):
        if hint and hint in text_preview or hint == title:
            if hint not in hints:
                hints.append(hint)
    if title and title not in hints:
        hints.insert(0, title)
    return tuple(hints)


def _browser_open_url_expected_text_not_visible(
    expected_text: str,
    parameters: Mapping[str, Any],
    *,
    session: BrowserRuntimeSession,
    fixture_manifest_path: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    url = parameters.get("url")
    if not isinstance(url, str) or not expected_text.strip():
        return None
    try:
        resolution = resolve_browser_fixture_url(
            url,
            fixture_manifest_path,
            project_root=repo_root,
            allowed_url_prefixes=_prefixes_for_domains(session.allowed_domains),
            preview_chars=2_000,
        )
    except Exception:
        return None
    visible_text = f"{resolution.title or ''} {resolution.extracted_text_preview}".strip()
    if expected_text in visible_text:
        return None
    return {
        "error_code": "model_output_expected_text_not_visible",
        "metadata": {
            "expected_text": expected_text,
            "target_url": resolution.url,
            "visible_anchors": _start_page_visible_anchors(resolution.url, resolution.title, resolution.extracted_text_preview),
        },
    }


def _browser_click_expected_url_not_matching_destination(
    expected_url: str,
    parameters: Mapping[str, Any],
    *,
    session: BrowserRuntimeSession,
    fixture_manifest_path: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    destination_resolution = _resolve_browser_click_destination(
        parameters,
        session=session,
        fixture_manifest_path=fixture_manifest_path,
        repo_root=repo_root,
    )
    if destination_resolution is None or not isinstance(expected_url, str) or not expected_url.strip():
        return None
    expected_url_value = expected_url.strip()
    if expected_url_value == destination_resolution.url:
        return None
    return {
        "error_code": "model_output_expected_url_not_matching_destination",
        "metadata": {
            "expected_url": expected_url_value,
            "resolved_destination_url": destination_resolution.url,
            "target_text": str(parameters.get("target_text") or parameters.get("text") or ""),
            "destination_anchors": _start_page_visible_anchors(
                destination_resolution.url,
                destination_resolution.title,
                destination_resolution.extracted_text_preview,
            ),
        },
    }


def _browser_click_expected_url_not_valid(
    expected_url: str | None,
    *,
    expected_text: str,
    parameters: Mapping[str, Any] | None = None,
    session: BrowserRuntimeSession | None = None,
    fixture_manifest_path: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    if not isinstance(expected_url, str) or not expected_url.strip():
        return None
    expected_url_value = expected_url.strip()
    parsed = urllib.parse.urlparse(expected_url_value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or hostname not in ALLOWED_LOCAL_EXPECTED_URL_HOSTS:
        target_text = str((parameters or {}).get("target_text") or (parameters or {}).get("text") or "").strip() if parameters else ""
        resolved_destination_url = None
        if session is not None and fixture_manifest_path and repo_root is not None and target_text:
            destination_resolution = _resolve_browser_click_destination(
                parameters or {},
                session=session,
                fixture_manifest_path=fixture_manifest_path,
                repo_root=repo_root,
            )
            if destination_resolution is not None:
                resolved_destination_url = destination_resolution.url
        return {
            "error_code": "model_output_invalid_expected_url",
            "metadata": {
                "expected_url_raw_sanitized": _sanitize_prompt_text(expected_url_value),
                "expected_text": expected_text,
                **({"target_text": target_text} if target_text else {}),
                **({"resolved_destination_url": resolved_destination_url} if resolved_destination_url else {}),
            },
        }
    return None


def _planner_expected_text_not_atomic(expected_text: str) -> dict[str, Any] | None:
    expected_text_value = expected_text.strip() if isinstance(expected_text, str) else ""
    if not expected_text_value:
        return None
    if _expected_text_is_composite(expected_text_value):
        return {
            "error_code": "model_output_expected_text_not_atomic",
            "metadata": {
                "expected_text": expected_text_value,
            },
        }
    return None


def _expected_text_is_composite(value: str) -> bool:
    if "\n" in value or ";" in value or "|" in value or " / " in value:
        return True
    return bool(re.search(r"(^|\n)\s*[-*•]\s+", value))


def _resolve_browser_click_destination(
    parameters: Mapping[str, Any],
    *,
    session: BrowserRuntimeSession,
    fixture_manifest_path: str,
    repo_root: Path,
) -> Any | None:
    target_text = parameters.get("target_text") or parameters.get("text")
    current_url = session.current_url
    if not isinstance(target_text, str) or not target_text.strip():
        return None
    if not isinstance(current_url, str) or not current_url.strip():
        return None
    try:
        current_resolution = resolve_browser_fixture_url(
            current_url,
            fixture_manifest_path,
            project_root=repo_root,
            allowed_url_prefixes=_prefixes_for_domains(session.allowed_domains),
            preview_chars=2_000,
        )
    except Exception:
        return None
    links = _extract_links(current_resolution.fixture_path.read_text(encoding="utf-8"))
    target_url = None
    for link in links:
        if target_text.strip().lower() in link["text"].lower():
            target_url = urllib.parse.urljoin(current_url, link["href"])
            break
    if target_url is None:
        return None
    try:
        return resolve_browser_fixture_url(
            target_url,
            fixture_manifest_path,
            project_root=repo_root,
            allowed_url_prefixes=_prefixes_for_domains(session.allowed_domains),
            preview_chars=2_000,
        )
    except Exception:
        return None


def _browser_click_expected_text_not_visible(
    expected_text: str,
    parameters: Mapping[str, Any],
    *,
    session: BrowserRuntimeSession,
    fixture_manifest_path: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    destination_resolution = _resolve_browser_click_destination(
        parameters,
        session=session,
        fixture_manifest_path=fixture_manifest_path,
        repo_root=repo_root,
    )
    if destination_resolution is None:
        return None
    expected_text_value = expected_text.strip()
    visible_text = f"{destination_resolution.title or ''} {destination_resolution.extracted_text_preview}".strip()
    if expected_text_value in visible_text:
        return None
    return {
        "error_code": "model_output_expected_text_not_visible",
        "metadata": {
            "expected_text": expected_text_value,
            "target_text": str(parameters.get("target_text") or parameters.get("text") or ""),
            "target_url": destination_resolution.url,
            "visible_anchors": _start_page_visible_anchors(
                destination_resolution.url,
                destination_resolution.title,
                destination_resolution.extracted_text_preview,
            ),
        },
    }


def _browser_click_target_not_supported(
    parameters: Mapping[str, Any],
    *,
    session: BrowserRuntimeSession,
    fixture_manifest_path: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    destination_resolution = _resolve_browser_click_destination(
        parameters,
        session=session,
        fixture_manifest_path=fixture_manifest_path,
        repo_root=repo_root,
    )
    if destination_resolution is not None:
        return None
    target_text = str(parameters.get("target_text") or parameters.get("text") or "").strip()
    if not target_text:
        return None
    current_url = session.current_url
    if not isinstance(current_url, str) or not current_url.strip():
        return None
    try:
        current_resolution = resolve_browser_fixture_url(
            current_url,
            fixture_manifest_path,
            project_root=repo_root,
            allowed_url_prefixes=_prefixes_for_domains(session.allowed_domains),
            preview_chars=2_000,
        )
    except Exception:
        return None
    links = _extract_links(current_resolution.fixture_path.read_text(encoding="utf-8"))
    return {
        "error_code": "model_output_unsupported_click_target",
        "metadata": {
            "target_text": target_text,
            "current_url": current_resolution.url,
            "visible_links": [str(link.get("text")) for link in links[:8] if isinstance(link, Mapping)],
        },
    }


def _attempt_local_model_action_repair(
    planner_backend: LocalModelLivePlanner,
    *,
    observation: Mapping[str, Any] | None,
    invalid_action: Mapping[str, Any] | AutonomousBrowserLivePlannerStep,
    error_code: str,
    error_message: str,
    error_diagnostics: Mapping[str, Any] | None,
) -> AutonomousBrowserLivePlannerStep | None:
    if not planner_backend.config.repair_enabled or planner_backend.config.max_repair_attempts <= 0:
        return None
    if error_code not in REPAIRABLE_MODEL_OUTPUT_ERROR_CODES:
        return None
    return planner_backend.repair_step(
        observation=observation,
        invalid_action=invalid_action,
        error_code=error_code,
        error_message=error_message,
        error_diagnostics=error_diagnostics,
    )


class AutonomousBrowserLiveLoopConfigError(ValueError):
    pass
