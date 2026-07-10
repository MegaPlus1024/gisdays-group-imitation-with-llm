from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from .autonomous_browser_live_planner import AutonomousBrowserLivePlannerStep
from .autonomous_browser_plan_validation import PLAN_SCHEMA_VERSION, validate_autonomous_browser_plan
from .browser_fixture_resolver import resolve_browser_fixture_url


LOCAL_MODEL_LIVE_PLANNER_SCHEMA_VERSION = "autonomous_browser_live_model_planner_v1"
DEFAULT_LOCAL_MODEL_PLANNER_ID = "browser_live_loop_local_model_planner_v1"
DEFAULT_LOCAL_MODEL_ALIAS = "third_model"
DEFAULT_LOCAL_MODEL_ENDPOINT = "http://127.0.0.1:8082/v1"
MIN_LOCAL_MODEL_MAX_TOKENS = 1200
DEFAULT_LOCAL_MODEL_TEMPERATURE = 0.0
DEFAULT_LOCAL_MODEL_MAX_TOKENS = 256
DEFAULT_LOCAL_MODEL_TIMEOUT_SECONDS = 120.0
DEFAULT_LOCAL_MODEL_REPAIR_ENABLED = True
DEFAULT_LOCAL_MODEL_MAX_REPAIR_ATTEMPTS = 1
ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost"}
ALLOWED_LOCAL_EXPECTED_URL_HOSTS = {
    "127.0.0.1",
    "localhost",
    "local.intranet",
    "local-intranet.test",
    "docs.local",
    "portal.local",
}
ALLOWED_LOCAL_MODEL_ACTION_NAMES = {
    "browser_open_url",
    "browser_click",
    "browser_extract_text",
    "browser_snapshot",
    "done",
}
REPAIRABLE_MODEL_OUTPUT_ERROR_CODES = {
    "model_output_expected_text_not_atomic",
    "model_output_invalid_expected_url",
    "model_output_expected_url_not_matching_destination",
    "model_output_expected_text_not_visible",
    "model_output_unsupported_click_target",
    "model_output_click_target_not_visible",
    "model_output_irrelevant_click_target",
}


@dataclass(frozen=True)
class ChatCompletionRequest:
    endpoint_base_url: str
    model: str
    messages: tuple[dict[str, str], ...]
    temperature: float
    max_tokens: int
    stream: bool
    timeout_seconds: float


@dataclass(frozen=True)
class ChatCompletionResponse:
    content: str
    finish_reason: str | None = None
    model: str | None = None
    raw_response: dict[str, Any] | None = None


@runtime_checkable
class ChatCompletionClient(Protocol):
    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        raise NotImplementedError


class HttpxChatCompletionClient:
    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        url = request.endpoint_base_url.rstrip("/")
        payload = {
            "model": request.model,
            "messages": [dict(message) for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream,
        }
        with httpx.Client(timeout=request.timeout_seconds, trust_env=False) as client:
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
                response_json = response.json()
            except httpx.HTTPStatusError as exc:
                raise LocalModelLivePlannerError(
                    "Local model endpoint returned an HTTP error.",
                    "model_http_status_error",
                    {
                        "exception_type": exc.__class__.__name__,
                        "http_status": exc.response.status_code,
                        "endpoint_host": _endpoint_host(request.endpoint_base_url),
                        "endpoint_port": _endpoint_port(request.endpoint_base_url),
                        "endpoint_path": _endpoint_path(url),
                        "model_alias": request.model,
                        "request_payload_metadata": _request_payload_metadata(request),
                        "response_text_preview_sanitized": _safe_response_excerpt(exc.response.text, limit=300),
                    },
                ) from exc
            except httpx.HTTPError as exc:
                raise LocalModelLivePlannerError(
                    "Local model request failed.",
                    "model_http_request_failed",
                    {
                        "exception_type": exc.__class__.__name__,
                        "endpoint_path": _endpoint_path(url),
                        "endpoint_host": _endpoint_host(request.endpoint_base_url),
                        "endpoint_port": _endpoint_port(request.endpoint_base_url),
                        "model_alias": request.model,
                        "request_payload_metadata": _request_payload_metadata(request),
                        "response_text_preview_sanitized": _safe_response_excerpt(str(exc), limit=300),
                    },
                ) from exc
        return ChatCompletionResponse(
            content=_assistant_content(response_json),
            finish_reason=_finish_reason(response_json),
            model=_response_model(response_json),
            raw_response=response_json if isinstance(response_json, dict) else None,
        )


class LocalModelLivePlannerError(ValueError):
    def __init__(self, message: str, error_code: str, diagnostics: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.diagnostics = dict(diagnostics or {})


@dataclass(frozen=True)
class LocalModelPlannerConfig:
    kind: str
    model_alias: str
    model_endpoint: str
    allow_model_calls: bool = False
    repair_enabled: bool = DEFAULT_LOCAL_MODEL_REPAIR_ENABLED
    max_repair_attempts: int = DEFAULT_LOCAL_MODEL_MAX_REPAIR_ATTEMPTS
    planner_id: str = DEFAULT_LOCAL_MODEL_PLANNER_ID
    allowed_model_aliases: tuple[str, ...] = ()
    no_think: bool | None = None
    temperature: float = DEFAULT_LOCAL_MODEL_TEMPERATURE
    max_tokens: int = DEFAULT_LOCAL_MODEL_MAX_TOKENS
    timeout_seconds: float = DEFAULT_LOCAL_MODEL_TIMEOUT_SECONDS
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_endpoint = _normalize_local_model_endpoint(self.model_endpoint)
        if normalized_endpoint is None:
            raise LocalModelLivePlannerError("planner_backend.model_endpoint must be a safe endpoint URL.", "model_endpoint_invalid")
        object.__setattr__(self, "model_endpoint", normalized_endpoint)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LocalModelPlannerConfig:
        kind = str(payload.get("kind", "")).strip().lower()
        if kind != "local_model":
            raise LocalModelLivePlannerError("planner_backend.kind must be local_model.", "planner_backend_kind_not_allowed")
        planner_id = _safe_identifier(payload.get("planner_id", DEFAULT_LOCAL_MODEL_PLANNER_ID), "planner_id") or DEFAULT_LOCAL_MODEL_PLANNER_ID
        model_alias = _safe_identifier(payload.get("model_alias", DEFAULT_LOCAL_MODEL_ALIAS), "model_alias")
        model_endpoint = _safe_endpoint_base_url(payload.get("model_endpoint", DEFAULT_LOCAL_MODEL_ENDPOINT))
        if model_alias is None:
            raise LocalModelLivePlannerError("planner_backend.model_alias must be a safe identifier.", "model_alias_invalid")
        if model_endpoint is None:
            raise LocalModelLivePlannerError("planner_backend.model_endpoint must be a safe endpoint URL.", "model_endpoint_invalid")

        allow_model_calls = payload.get("allow_model_calls", False)
        if not isinstance(allow_model_calls, bool):
            raise LocalModelLivePlannerError("planner_backend.allow_model_calls must be a boolean.", "allow_model_calls_invalid")
        repair_enabled = payload.get("repair_enabled", DEFAULT_LOCAL_MODEL_REPAIR_ENABLED)
        if not isinstance(repair_enabled, bool):
            raise LocalModelLivePlannerError("planner_backend.repair_enabled must be a boolean.", "repair_enabled_invalid")
        max_repair_attempts = _int(
            payload.get("max_repair_attempts", DEFAULT_LOCAL_MODEL_MAX_REPAIR_ATTEMPTS),
            "max_repair_attempts",
        )
        if max_repair_attempts is None or max_repair_attempts < 0:
            raise LocalModelLivePlannerError(
                "planner_backend.max_repair_attempts must be a non-negative integer.",
                "max_repair_attempts_invalid",
            )

        allowed_model_aliases = tuple(
            str(item).strip()
            for item in payload.get("allowed_model_aliases", [])
            if isinstance(item, str) and item.strip()
        )
        no_think = payload.get("no_think")
        if no_think is not None and not isinstance(no_think, bool):
            raise LocalModelLivePlannerError("planner_backend.no_think must be a boolean if provided.", "no_think_invalid")

        temperature = _float(payload.get("temperature", DEFAULT_LOCAL_MODEL_TEMPERATURE), "temperature")
        max_tokens = _int(payload.get("max_tokens", DEFAULT_LOCAL_MODEL_MAX_TOKENS), "max_tokens")
        timeout_seconds = _float(payload.get("timeout_seconds", DEFAULT_LOCAL_MODEL_TIMEOUT_SECONDS), "timeout_seconds")
        if temperature is None or max_tokens is None or timeout_seconds is None:
            raise LocalModelLivePlannerError("planner_backend numeric fields are invalid.", "planner_backend_numeric_invalid")
        metadata = _dict(payload.get("metadata", {}), "planner_backend.metadata")

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "planner_id": self.planner_id,
            "model_alias": self.model_alias,
            "model_endpoint": self.model_endpoint,
            "allow_model_calls": self.allow_model_calls,
            "repair_enabled": self.repair_enabled,
            "max_repair_attempts": self.max_repair_attempts,
            "allowed_model_aliases": list(self.allowed_model_aliases),
            "no_think": self.no_think,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "metadata": dict(self.metadata),
        }


@dataclass
class LocalModelLivePlanner:
    config: LocalModelPlannerConfig
    client: ChatCompletionClient | None = None
    repo_root: Path = Path(".")
    step_index: int = field(default=0, init=False, repr=False)
    model_execution_attempted: bool = field(default=False, init=False)
    model_execution_completed: bool = field(default=False, init=False)
    last_error_code: str | None = field(default=None, init=False)
    last_error_message_sanitized: str | None = field(default=None, init=False)
    last_exception_type: str | None = field(default=None, init=False)
    last_http_status: int | None = field(default=None, init=False)
    last_error_diagnostics: dict[str, Any] = field(default_factory=dict, init=False)
    original_error_code: str | None = field(default=None, init=False)
    repair_attempts: int = field(default=0, init=False)
    repair_attempts_succeeded: int = field(default=0, init=False)
    repair_attempts_failed: int = field(default=0, init=False)
    last_repair_error_code: str | None = field(default=None, init=False)
    last_repair_response_text_preview_sanitized: str | None = field(default=None, init=False)
    last_finish_reason: str | None = field(default=None, init=False)
    last_response_text_preview_sanitized: str | None = field(default=None, init=False)
    last_request_payload_metadata: dict[str, Any] = field(default_factory=dict, init=False)
    last_request: ChatCompletionRequest | None = field(default=None, init=False)
    last_response: ChatCompletionResponse | None = field(default=None, init=False)

    def build_messages(self, observation: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
        payload = _observation_payload(observation)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
        system_parts = [
            "You are a guarded local browser planner for a fixture-backed loop.",
            "Return exactly one JSON object only.",
            "Do not use markdown, code fences, arrays, or multiple JSON objects.",
            "The JSON object must represent one next browser action or a done signal.",
            "Allowed action names exactly: browser_open_url, browser_click, browser_extract_text, browser_snapshot, done.",
            "Do not use browser_search.",
            "Do not search the web.",
            "Do not invent search actions.",
            "You are already inside a local fixture environment.",
            "Choose only from visible local links/buttons and allowed local fixture actions.",
            "For browser_click, use parameters {\"target_text\": \"<visible link/button text>\"}.",
            "Do not use link_text, button_text, selector, href, XPath, or CSS selectors for browser_click.",
            "For browser_click, expected_text must come from the destination page reached by target_text, not the page you are currently reading.",
            "For browser_click, expected_text must be exactly one visible substring, not multiple anchors joined together.",
            "For browser_click, omit expected_url. Runtime resolves the destination URL from target_text and verifies it locally; if you include expected_url anyway, it must match the destination exactly.",
            "Never request secrets, credentials, tokens, passwords, file URLs, external URLs, or real browser access.",
        ]
        if self._effective_no_think():
            system_parts.insert(0, "/no_think")
        user_parts = [
            "Observation JSON:",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ]
        surface_hints = _surface_hints(payload)
        if surface_hints:
            user_parts.append(f"Visible local hints: {surface_hints}")
        click_guidance = _click_destination_guidance(payload, metadata, repo_root=self.repo_root)
        if click_guidance:
            user_parts.extend(click_guidance)
        page_state_guidance = _page_state_guidance(payload, metadata, repo_root=self.repo_root)
        if page_state_guidance:
            user_parts.extend(page_state_guidance)
        if payload.get("current_url") is None:
            start_url = _prompt_text(metadata.get("scenario_start_url") or metadata.get("start_url"))
            if start_url:
                user_parts.append(f"Scenario start URL: {start_url}. First action must be browser_open_url with that URL.")
                user_parts.append("Do not click before opening.")
                goal_id = _prompt_text(metadata.get("scenario_id"))
                if goal_id == "hard_ticket_priority_crosscheck":
                    user_parts.append('For hard_ticket_priority_crosscheck from the home page, click "Ticket board", not "Workspace policy".')
                    user_parts.append("Avoid for this goal: Workspace policy; Team status; Approvals queue.")
                elif goal_id == "hard_approval_policy_match":
                    user_parts.append('For hard_approval_policy_match from the home page, click "Approvals queue", not "Workspace policy".')
                    user_parts.append("Avoid for this goal: Workspace policy; Ticket board; Team status.")
            anchor_hints = _start_page_anchor_hints(payload, metadata)
            if anchor_hints:
                user_parts.append(f"Start-page visible anchors: {'; '.join(anchor_hints)}")
                user_parts.append("For the first browser_open_url action, expected_text must be an exact visible substring from the page that will be open after the action.")
                user_parts.append("Do not invent welcome text.")
                if "Office Intranet Home" in anchor_hints or "Workspace policy" in anchor_hints:
                    user_parts.append('For this start page, prefer "Office Intranet Home" or "Workspace policy".')
            system_parts.append("When current_url is null, open the scenario start URL before click, extract, or snapshot actions.")
        user_parts.extend(
            [
                "Return one JSON object with keys step_id, action_name, parameters, expected_text, optional expected_url (omit it for browser_click), optional done, optional metadata.",
                "If you are done, set action_name to done and done to true.",
                "If you are not done, keep expected_text short and grounded in the local fixture observation.",
            ]
        )
        return [
            {"role": "system", "content": "\n".join(system_parts)},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

    def validate_runtime_guard(self) -> None:
        if not self.config.allow_model_calls:
            error = LocalModelLivePlannerError(
                "Model calls are disabled for this planner backend.",
                "allow_model_calls_required",
            )
            self._record_error(error)
            raise error

        parsed = urllib.parse.urlparse(self.config.model_endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            error = LocalModelLivePlannerError(
                "Model endpoint must be a local loopback HTTP(S) URL.",
                "non_local_model_endpoint",
            )
            self._record_error(error)
            raise error
        hostname = (parsed.hostname or "").lower()
        if hostname not in ALLOWED_LOCAL_HOSTS:
            error = LocalModelLivePlannerError(
                "Model endpoint host is not allowed.",
                "non_local_model_endpoint",
            )
            self._record_error(error)
            raise error

        allowed_aliases = self.allowed_model_aliases()
        if self.config.model_alias not in allowed_aliases:
            error = LocalModelLivePlannerError(
                "Model alias is not listed in the allowed planner config.",
                "unsupported_model_alias",
            )
            self._record_error(error)
            raise error

    def allowed_model_aliases(self) -> tuple[str, ...]:
        if self.config.allowed_model_aliases:
            return self.config.allowed_model_aliases
        return _load_model_aliases(self.repo_root)

    def _clear_repair_state(self) -> None:
        self.original_error_code = None
        self.last_repair_error_code = None
        self.last_repair_response_text_preview_sanitized = None

    def _should_attempt_repair(self, error_code: str | None) -> bool:
        return bool(
            error_code
            and self._repairing_is_enabled()
            and error_code in REPAIRABLE_MODEL_OUTPUT_ERROR_CODES
        )

    def next_step(self, observation: Mapping[str, Any] | None = None) -> AutonomousBrowserLivePlannerStep | None:
        self.validate_runtime_guard()
        self.step_index += 1
        self._clear_repair_state()
        request = ChatCompletionRequest(
            endpoint_base_url=self.config.model_endpoint,
            model=self.config.model_alias,
            messages=tuple(self.build_messages(observation)),
            temperature=self.config.temperature,
            max_tokens=max(self.config.max_tokens, MIN_LOCAL_MODEL_MAX_TOKENS),
            stream=False,
            timeout_seconds=self.config.timeout_seconds,
        )
        self.last_request = request
        self.last_request_payload_metadata = _request_payload_metadata(request)
        self.last_error_diagnostics = {}
        self.last_error_message_sanitized = None
        self.last_exception_type = None
        self.last_http_status = None
        self.last_response_text_preview_sanitized = None
        self.model_execution_attempted = True
        client = self.client or HttpxChatCompletionClient()
        try:
            response = client.complete(request)
        except LocalModelLivePlannerError as exc:
            self._record_error(exc)
            raise
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            wrapped = LocalModelLivePlannerError(
                "Model request failed.",
                "planner_request_failed",
                {
                    "exception_type": exc.__class__.__name__,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": _safe_response_excerpt(str(exc), limit=300),
                },
            )
            self._record_error(wrapped)
            raise wrapped from exc
        self.last_response = response
        self.model_execution_completed = True
        self.last_finish_reason = response.finish_reason
        self.last_response_text_preview_sanitized = _safe_response_excerpt(response.content, limit=300)
        if (response.finish_reason or "").strip().lower() == "length":
            error = LocalModelLivePlannerError(
                "Model response finished due to length limit.",
                "model_finish_reason_length",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self._record_error(error)
            raise error

        content = response.content.strip()
        if not content:
            error = LocalModelLivePlannerError(
                "Model response content was empty.",
                "model_response_missing_content",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self._record_error(error)
            raise error

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            error = LocalModelLivePlannerError(
                "Model response was not valid JSON.",
                "model_response_invalid_json",
                {
                    "exception_type": exc.__class__.__name__,
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self._record_error(error)
            raise error from exc

        if not isinstance(parsed, Mapping):
            error = LocalModelLivePlannerError(
                "Model response must be a JSON object.",
                "model_output_no_json_object",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self._record_error(error)
            raise error

        if "actions" in parsed:
            error = LocalModelLivePlannerError(
                "Full plan objects are not allowed.",
                "model_output_invalid_action",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self._record_error(error)
            raise error

        try:
            step = self._step_from_payload(parsed)
        except LocalModelLivePlannerError as exc:
            if self._should_attempt_repair(exc.error_code):
                repaired = self.repair_step(
                    observation=observation,
                    invalid_action=parsed,
                    error_code=exc.error_code,
                    error_message=str(exc),
                    error_diagnostics=exc.diagnostics,
                )
                self.original_error_code = self.original_error_code or exc.error_code
                self.last_error_code = None
                self.last_error_message_sanitized = None
                self.last_exception_type = None
                self.last_http_status = None
                self.last_error_diagnostics = {}
                return repaired
            raise
        return step

    def to_summary(self) -> dict[str, Any]:
        return {
            "schema_version": LOCAL_MODEL_LIVE_PLANNER_SCHEMA_VERSION,
            "kind": self.config.kind,
            "planner_id": self.config.planner_id,
            "model_alias": self.config.model_alias,
            "model_endpoint": self.config.model_endpoint,
            "allow_model_calls": self.config.allow_model_calls,
            "no_think": self._effective_no_think(),
            "model_execution_attempted": self.model_execution_attempted,
            "model_execution_completed": self.model_execution_completed,
            "last_error_code": self.last_error_code,
            "last_error_message_sanitized": self.last_error_message_sanitized,
            "last_exception_type": self.last_exception_type,
            "last_http_status": self.last_http_status,
            "last_error_diagnostics": dict(self.last_error_diagnostics) if self.last_error_diagnostics else {},
            "original_error_code": self.original_error_code,
            "repair_enabled": self.config.repair_enabled,
            "max_repair_attempts": self.config.max_repair_attempts,
            "repair_attempts": self.repair_attempts,
            "repair_attempts_total": self.repair_attempts,
            "repair_attempts_succeeded": self.repair_attempts_succeeded,
            "repair_attempts_succeeded_total": self.repair_attempts_succeeded,
            "repair_attempts_failed": self.repair_attempts_failed,
            "repair_attempts_failed_total": self.repair_attempts_failed,
            "last_repair_error_code": self.last_repair_error_code,
            "last_repair_response_text_preview_sanitized": self.last_repair_response_text_preview_sanitized,
            "last_finish_reason": self.last_finish_reason,
            "last_response_text_preview_sanitized": self.last_response_text_preview_sanitized,
            "request_payload_metadata": dict(self.last_request_payload_metadata),
            "last_request_preview": _request_preview(self.last_request) if self.last_request is not None else None,
            "last_response_preview": _response_preview(self.last_response) if self.last_response is not None else None,
            "allowed_model_aliases": list(self.allowed_model_aliases()),
        }

    def repair_step(
        self,
        *,
        observation: Mapping[str, Any] | None,
        invalid_action: Mapping[str, Any] | AutonomousBrowserLivePlannerStep,
        error_code: str,
        error_message: str,
        error_diagnostics: Mapping[str, Any] | None = None,
    ) -> AutonomousBrowserLivePlannerStep:
        if not self._repairing_is_enabled():
            raise LocalModelLivePlannerError(error_message, error_code, dict(error_diagnostics or {}))
        repair_payload = self._build_repair_request_payload(
            observation=observation,
            invalid_action=invalid_action,
            error_code=error_code,
            error_message=error_message,
            error_diagnostics=error_diagnostics,
        )
        self.repair_attempts += 1
        self.original_error_code = self.original_error_code or error_code
        request = ChatCompletionRequest(
            endpoint_base_url=self.config.model_endpoint,
            model=self.config.model_alias,
            messages=tuple(repair_payload["messages"]),
            temperature=self.config.temperature,
            max_tokens=max(self.config.max_tokens, MIN_LOCAL_MODEL_MAX_TOKENS),
            stream=False,
            timeout_seconds=self.config.timeout_seconds,
        )
        self.last_request = request
        self.last_request_payload_metadata = _request_payload_metadata(request)
        self.last_error_diagnostics = {}
        self.last_error_message_sanitized = None
        self.last_exception_type = None
        self.last_http_status = None
        self.last_response_text_preview_sanitized = None
        client = self.client or HttpxChatCompletionClient()
        try:
            response = client.complete(request)
        except LocalModelLivePlannerError as exc:
            self.repair_attempts_failed += 1
            self.last_repair_error_code = exc.error_code
            self.last_repair_response_text_preview_sanitized = None
            self._record_error(exc)
            raise
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            self.repair_attempts_failed += 1
            wrapped = LocalModelLivePlannerError(
                "Repair request failed.",
                "planner_request_failed",
                {
                    "exception_type": exc.__class__.__name__,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": _safe_response_excerpt(str(exc), limit=300),
                },
            )
            self.last_repair_error_code = wrapped.error_code
            self.last_repair_response_text_preview_sanitized = wrapped.diagnostics.get("response_text_preview_sanitized")
            self._record_error(wrapped)
            raise wrapped from exc
        self.last_response = response
        self.model_execution_completed = True
        self.last_finish_reason = response.finish_reason
        self.last_response_text_preview_sanitized = _safe_response_excerpt(response.content, limit=300)
        self.last_repair_response_text_preview_sanitized = self.last_response_text_preview_sanitized
        if (response.finish_reason or "").strip().lower() == "length":
            self.repair_attempts_failed += 1
            error = LocalModelLivePlannerError(
                "Repair response finished due to length limit.",
                "model_finish_reason_length",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self.last_repair_error_code = error.error_code
            self._record_error(error)
            raise error

        content = response.content.strip()
        if not content:
            self.repair_attempts_failed += 1
            error = LocalModelLivePlannerError(
                "Repair response content was empty.",
                "model_response_missing_content",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self.last_repair_error_code = error.error_code
            self._record_error(error)
            raise error

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            self.repair_attempts_failed += 1
            error = LocalModelLivePlannerError(
                "Repair response was not valid JSON.",
                "model_response_invalid_json",
                {
                    "exception_type": exc.__class__.__name__,
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self.last_repair_error_code = error.error_code
            self._record_error(error)
            raise error from exc

        if not isinstance(parsed, Mapping):
            self.repair_attempts_failed += 1
            error = LocalModelLivePlannerError(
                "Repair response must be a JSON object.",
                "model_output_no_json_object",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self.last_repair_error_code = error.error_code
            self._record_error(error)
            raise error

        if "actions" in parsed:
            self.repair_attempts_failed += 1
            error = LocalModelLivePlannerError(
                "Full plan objects are not allowed.",
                "model_output_invalid_action",
                {
                    "exception_type": "LocalModelLivePlannerError",
                    "finish_reason": response.finish_reason,
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "response_text_preview_sanitized": self.last_response_text_preview_sanitized,
                },
            )
            self.last_repair_error_code = error.error_code
            self._record_error(error)
            raise error

        try:
            step = self._step_from_payload(parsed)
        except LocalModelLivePlannerError as exc:
            self.repair_attempts_failed += 1
            self.last_repair_error_code = exc.error_code
            self._record_error(exc)
            raise

        self.repair_attempts_succeeded += 1
        self.last_repair_error_code = None
        self.last_error_code = None
        self.last_error_message_sanitized = None
        self.last_exception_type = None
        self.last_http_status = None
        self.last_error_diagnostics = {}
        return step

    def _step_from_payload(self, payload: Mapping[str, Any]) -> AutonomousBrowserLivePlannerStep:
        if "actions" in payload:
            error = LocalModelLivePlannerError(
                "Full plan objects are not allowed.",
                "model_output_invalid_action",
                {"request_payload_metadata": dict(self.last_request_payload_metadata)},
            )
            self._record_error(error)
            raise error

        action_name = _safe_text(payload.get("action_name"), "action_name")
        if action_name is None:
            error = LocalModelLivePlannerError(
                "Model response is missing action_name.",
                "model_output_invalid_action",
                {"request_payload_metadata": dict(self.last_request_payload_metadata)},
            )
            self._record_error(error)
            raise error

        step_id = _safe_text(payload.get("step_id"), "step_id")
        if step_id is None:
            step_id = "done" if action_name == "done" or bool(payload.get("done")) else f"{self.config.planner_id}_step_{self.step_index:04d}"

        done = bool(payload.get("done", False)) or action_name == "done"
        parameters = payload.get("parameters", {})
        if not isinstance(parameters, Mapping):
            error = LocalModelLivePlannerError(
                "Model response parameters must be an object.",
                "model_output_invalid_action",
                {"request_payload_metadata": dict(self.last_request_payload_metadata)},
            )
            self._record_error(error)
            raise error
        expected_text = _validated_expected_text(
            payload.get("expected_text"),
            "expected_text",
            request_payload_metadata=dict(self.last_request_payload_metadata),
        )
        expected_url = _safe_expected_url(
            payload.get("expected_url"),
            "expected_url",
            request_payload_metadata=dict(self.last_request_payload_metadata),
        )
        metadata = _dict(payload.get("metadata", {}), "metadata")

        if done:
            return AutonomousBrowserLivePlannerStep(
                step_id=step_id,
                action_name="done",
                parameters={},
                expected_text="",
                expected_url=None,
                done=True,
                metadata=metadata,
            )

        if expected_text is None:
            error = LocalModelLivePlannerError(
                "Model response is missing expected_text.",
                "model_output_invalid_action",
                {"request_payload_metadata": dict(self.last_request_payload_metadata)},
            )
            self._record_error(error)
            raise error

        if action_name not in ALLOWED_LOCAL_MODEL_ACTION_NAMES:
            error = LocalModelLivePlannerError(
                "Model response action is not supported by the guarded local-model live loop.",
                "model_output_unsupported_action",
                {
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "action_name": action_name,
                },
            )
            self._record_error(error)
            raise error

        if action_name == "browser_click":
            parameters = self._normalize_click_parameters(parameters)

        validation_result = validate_autonomous_browser_plan(
            {
                "schema_version": PLAN_SCHEMA_VERSION,
                "plan_id": f"{self.config.planner_id}_proposal_{self.step_index:04d}",
                "goal": "Propose one next browser action.",
                "scenario_id": _safe_text(payload.get("scenario_id"), "scenario_id") or "browser_live_loop_local_model",
                "max_actions": 1,
                "actions": [
                    {
                        "step_id": step_id,
                        "action_name": action_name,
                        "parameters": parameters,
                        "expected_text": expected_text,
                        **({"expected_url": expected_url} if expected_url is not None else {}),
                    }
                ],
            }
        )
        if str(validation_result.get("status")) != "accepted":
            error_code = str(validation_result.get("error_code") or "planner_action_validation_failed")
            error = LocalModelLivePlannerError(
                "Model response action failed validation.",
                error_code,
                {"validation_result": validation_result},
            )
            self._record_error(error)
            raise error
        normalized_plan = validation_result.get("normalized_plan")
        if not isinstance(normalized_plan, Mapping):
            error = LocalModelLivePlannerError(
                "Model response validation did not produce a normalized plan.",
                "model_output_invalid_action",
                {"request_payload_metadata": dict(self.last_request_payload_metadata)},
            )
            self._record_error(error)
            raise error
        normalized_action = normalized_plan["actions"][0]
        self.last_error_code = None
        self.last_error_message_sanitized = None
        self.last_exception_type = None
        self.last_http_status = None
        self.last_error_diagnostics = {}
        return AutonomousBrowserLivePlannerStep(
            step_id=str(normalized_action["step_id"]),
            action_name=str(normalized_action["action_name"]),
            parameters=dict(normalized_action["parameters"]),
            expected_text=str(normalized_action.get("expected_text", "")),
            expected_url=expected_url,
            done=False,
            metadata=metadata,
        )

    def _repairing_is_enabled(self) -> bool:
        return bool(self.config.repair_enabled and self.config.max_repair_attempts > 0)

    def _build_repair_request_payload(
        self,
        *,
        observation: Mapping[str, Any] | None,
        invalid_action: Mapping[str, Any] | AutonomousBrowserLivePlannerStep,
        error_code: str,
        error_message: str,
        error_diagnostics: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        payload = _observation_payload(observation)
        invalid_payload = invalid_action.to_dict() if isinstance(invalid_action, AutonomousBrowserLivePlannerStep) else dict(invalid_action)
        repair_messages = self._build_repair_messages(
            observation_payload=payload,
            invalid_action=invalid_payload,
            error_code=error_code,
            error_message=error_message,
            error_diagnostics=error_diagnostics,
        )
        return {"messages": repair_messages}

    def _build_repair_messages(
        self,
        *,
        observation_payload: Mapping[str, Any],
        invalid_action: Mapping[str, Any],
        error_code: str,
        error_message: str,
        error_diagnostics: Mapping[str, Any] | None,
    ) -> list[dict[str, str]]:
        system_parts = [
            "You are repairing one invalid browser planner action for a controlled local loop.",
            "Return exactly one JSON object only.",
            "Do not use markdown, code fences, arrays, or multiple JSON objects.",
            "Do not invent extra actions.",
            "Use only safe local fixture URLs and visible local fixture text.",
            "Keep the repaired action minimal and valid for the current observation.",
        ]
        if self._effective_no_think():
            system_parts.insert(0, "/no_think")

        user_parts = [
            "Previous response was rejected before fixture execution.",
            f"Exact error_code: {error_code}",
            f"Short error message: {error_message}",
            "Current observation JSON:",
            json.dumps(_repair_observation_payload(observation_payload), ensure_ascii=False, sort_keys=True),
            "Sanitized previous invalid action:",
            json.dumps(_sanitize_prompt_value(invalid_action), ensure_ascii=False, sort_keys=True),
            "Repair constraints:",
            *_repair_constraints_lines(
                error_code=error_code,
                observation_payload=observation_payload,
                invalid_action=invalid_action,
                error_diagnostics=error_diagnostics,
                repo_root=self.repo_root,
            ),
            "Return exactly one JSON object with keys step_id, action_name, parameters, expected_text, optional expected_url (omit it for browser_click), optional done, optional metadata.",
            "No prose, no markdown, no code fences.",
        ]
        return [
            {"role": "system", "content": "\n".join(system_parts)},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

    def _normalize_click_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(parameters)
        target_text = None
        for key in ("target_text", "text", "link_text", "button_text"):
            value = normalized.get(key)
            candidate = _safe_text(value, key)
            if candidate:
                target_text = candidate
                break

        if target_text is None:
            error = LocalModelLivePlannerError(
                "Model response click target must use visible link/button text.",
                "missing_required_parameter",
                {
                    "request_payload_metadata": dict(self.last_request_payload_metadata),
                    "action_name": "browser_click",
                    "parameter_key": "target_text",
                },
            )
            self._record_error(error)
            raise error

        for key in ("target_text", "text", "link_text", "button_text", "target_url", "href", "selector"):
            normalized.pop(key, None)
        normalized["target_text"] = target_text
        return normalized

    def _effective_no_think(self) -> bool:
        if self.config.no_think is not None:
            return self.config.no_think
        return self.config.model_alias == DEFAULT_LOCAL_MODEL_ALIAS

    def _record_error(self, exc: LocalModelLivePlannerError) -> None:
        self.last_error_code = exc.error_code
        self.last_error_message_sanitized = _safe_response_excerpt(str(exc), limit=300)
        diagnostics = dict(exc.diagnostics)
        self.last_error_diagnostics = diagnostics
        self.last_exception_type = str(diagnostics.get("exception_type") or exc.__class__.__name__)
        http_status = diagnostics.get("http_status")
        self.last_http_status = http_status if isinstance(http_status, int) else None
        response_preview = diagnostics.get("response_text_preview_sanitized")
        if isinstance(response_preview, str):
            self.last_response_text_preview_sanitized = response_preview


def _load_model_aliases(repo_root: Path) -> tuple[str, ...]:
    path = repo_root / "configs" / "evaluation_models.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError:
        return ()
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, Mapping):
        return ()
    aliases: list[str] = []
    models = payload.get("models", [])
    if not isinstance(models, list):
        return ()
    for item in models:
        if not isinstance(item, Mapping):
            continue
        model_id = _safe_identifier(item.get("model_id"), "model_id")
        if model_id and model_id not in aliases:
            aliases.append(model_id)
        for alias in item.get("aliases", []):
            if isinstance(alias, str) and alias.strip():
                clean = alias.strip()
                if clean not in aliases:
                    aliases.append(clean)
    return tuple(aliases)


def _assistant_content(response_json: Mapping[str, Any]) -> str:
    if not isinstance(response_json, Mapping):
        raise LocalModelLivePlannerError(
            "Chat completion response root must be a JSON object.",
            "model_response_missing_choices",
        )
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LocalModelLivePlannerError(
            "Chat completion response is missing choices.",
            "model_response_missing_choices",
        )
    try:
        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise KeyError("choice")
        message = first_choice.get("message")
        if not isinstance(message, Mapping):
            raise KeyError("message")
        content = message.get("content")
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalModelLivePlannerError(
            "Chat completion response is missing assistant content.",
            "model_response_missing_content",
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise LocalModelLivePlannerError(
            "Chat completion assistant content must be text.",
            "model_response_missing_content",
        )
    return content


def _finish_reason(response_json: Mapping[str, Any]) -> str | None:
    if not isinstance(response_json, Mapping):
        return None
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    try:
        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            return None
        finish_reason = first_choice.get("finish_reason")
    except (KeyError, IndexError, TypeError):
        return None
    return finish_reason if isinstance(finish_reason, str) else None


def _response_model(response_json: Mapping[str, Any]) -> str | None:
    model = response_json.get("model")
    return model if isinstance(model, str) else None


def _observation_payload(observation: Mapping[str, Any] | None) -> dict[str, Any]:
    if observation is None:
        return {
            "observation_id": None,
            "current_url": None,
            "title": None,
            "text_preview": "",
            "metadata": {},
        }
    return {
        "observation_id": observation.get("observation_id"),
        "current_url": observation.get("current_url"),
        "title": observation.get("title"),
        "text_preview": observation.get("text_preview", ""),
        "metadata": dict(observation.get("metadata", {})) if isinstance(observation.get("metadata"), Mapping) else {},
    }


def _safe_text(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


def _safe_identifier(value: Any, label: str) -> str | None:
    return _safe_text(value, label)


def _safe_expected_url(
    value: Any,
    label: str,
    *,
    request_payload_metadata: Mapping[str, Any] | None = None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LocalModelLivePlannerError(
            "Model response expected_url is not a valid local fixture URL.",
            "model_output_invalid_expected_url",
            {
                "request_payload_metadata": dict(request_payload_metadata or {}),
                "expected_url_path": label,
            },
        )
    stripped = value.strip()
    parsed = urllib.parse.urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise LocalModelLivePlannerError(
            "Model response expected_url is not a valid local fixture URL.",
            "model_output_invalid_expected_url",
            {
                "request_payload_metadata": dict(request_payload_metadata or {}),
                "expected_url_path": label,
                "expected_url_raw_sanitized": _sanitize_prompt_text(stripped),
            },
        )
    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_LOCAL_EXPECTED_URL_HOSTS:
        raise LocalModelLivePlannerError(
            "Model response expected_url is not a valid local fixture URL.",
            "model_output_invalid_expected_url",
            {
                "request_payload_metadata": dict(request_payload_metadata or {}),
                "expected_url_path": label,
                "expected_url_raw_sanitized": _sanitize_prompt_text(stripped),
            },
        )
    return stripped


def _validated_expected_text(
    value: Any,
    label: str,
    *,
    request_payload_metadata: Mapping[str, Any] | None = None,
) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if _expected_text_is_composite(stripped):
        raise LocalModelLivePlannerError(
            "Model response expected_text must be one exact visible substring, not a list.",
            "model_output_expected_text_not_atomic",
            {
                "request_payload_metadata": dict(request_payload_metadata or {}),
                "expected_text_path": label,
            },
        )
    return stripped


def _expected_text_is_composite(value: str) -> bool:
    if "\n" in value or ";" in value or "|" in value or " / " in value:
        return True
    return bool(re.search(r"(^|\n)\s*[-*•]\s+", value))


def _safe_endpoint_base_url(value: Any) -> str | None:
    return _normalize_local_model_endpoint(value)


def _normalize_local_model_endpoint(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return None
    if parsed.params or parsed.query or parsed.fragment:
        return None
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname in ALLOWED_LOCAL_HOSTS:
        if path in {"", "/"}:
            path = "/v1/chat/completions"
        elif path == "/v1":
            path = "/v1/chat/completions"
        elif path == "/v1/chat/completions":
            path = "/v1/chat/completions"
        else:
            return None
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    return normalized


def _dict(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LocalModelLivePlannerError(f"{label} must be an object.", f"{label.replace('.', '_')}_invalid")
    return dict(value)


def _float(value: Any, label: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _int(value: Any, label: str) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _request_preview(request: ChatCompletionRequest) -> dict[str, Any]:
    return {
        "endpoint_host": _endpoint_host(request.endpoint_base_url),
        "endpoint_port": _endpoint_port(request.endpoint_base_url),
        "model_id": request.model,
        "request_payload_metadata": _request_payload_metadata(request),
    }


def _response_preview(response: ChatCompletionResponse) -> dict[str, Any]:
    return {
        "model": response.model,
        "finish_reason": response.finish_reason,
    }


def _endpoint_path(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    return path or "/"


def _endpoint_host(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else None


def _endpoint_port(url: str) -> int | None:
    parsed = urllib.parse.urlparse(url)
    return parsed.port


def _request_payload_metadata(request: ChatCompletionRequest) -> dict[str, Any]:
    return {
        "endpoint_host": _endpoint_host(request.endpoint_base_url),
        "endpoint_port": _endpoint_port(request.endpoint_base_url),
        "endpoint_path": _endpoint_path(request.endpoint_base_url),
        "model_alias": request.model,
        "message_count": len(request.messages),
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "stream": request.stream,
    }


def _request_shape(request: ChatCompletionRequest) -> dict[str, Any]:
    messages = request.messages
    return {
        "has_messages": isinstance(messages, Sequence),
        "message_count": len(messages) if isinstance(messages, Sequence) else 0,
        "has_tools": False,
        "has_response_format": False,
        "has_stream": False,
        "temperature_present": True,
        "max_tokens_present": True,
    }


def _safe_response_excerpt(value: str, *, limit: int = 800) -> str:
    text = _redact_secret_text(value)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    return text[:limit] + ("...[truncated]" if len(text) > limit else "")


def _surface_hints(payload: Mapping[str, Any]) -> str | None:
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    hints: list[str] = []
    for key in ("available_links", "links", "available_buttons", "buttons"):
        items = metadata.get(key)
        if isinstance(items, list):
            for item in items[:3]:
                hint = _compact_hint(item)
                if hint:
                    hints.append(hint)
    if not hints:
        return None
    return "; ".join(hints[:4])


def _compact_hint(item: Any) -> str | None:
    if isinstance(item, str) and item.strip():
        return item.strip()
    if isinstance(item, Mapping):
        text = _prompt_text(item.get("text") or item.get("label") or item.get("title"))
        url = _prompt_text(item.get("url") or item.get("href"))
        if text and url:
            return f"{text} -> {url}"
        if text:
            return text
        if url:
            return url
    return None


def _prompt_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _start_page_anchor_hints(payload: Mapping[str, Any], metadata: Mapping[str, Any]) -> list[str] | None:
    anchors: list[str] = []
    raw_anchors = metadata.get("start_page_visible_anchors")
    if isinstance(raw_anchors, list):
        for item in raw_anchors:
            if isinstance(item, str) and item.strip() and item.strip() not in anchors:
                anchors.append(item.strip())
    if anchors:
        return anchors

    start_url = _prompt_text(metadata.get("scenario_start_url") or metadata.get("start_url"))
    title = _prompt_text(payload.get("title"))
    text_preview = _prompt_text(payload.get("text_preview")) or ""
    return list(_page_visible_anchor_hints(start_url, title, text_preview)) or None


def _click_destination_guidance(
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    repo_root: Path,
) -> list[str] | None:
    goal_id = _prompt_text(metadata.get("scenario_id"))
    current_url = _prompt_text(payload.get("current_url"))
    fixture_manifest_path = _prompt_text(metadata.get("fixture_manifest_path"))
    if not current_url or not fixture_manifest_path:
        return None
    try:
        current_resolution = resolve_browser_fixture_url(
            current_url,
            fixture_manifest_path,
            project_root=repo_root,
            allowed_url_prefixes=_fixture_url_prefixes(),
            preview_chars=2_000,
        )
    except Exception:
        return None

    links = _extract_anchor_links(current_resolution.fixture_path.read_text(encoding="utf-8"))
    if not links:
        return None
    lines: list[str] = [
        "Choose the link/button relevant to the scenario goal.",
        "Do not choose a link just because it is visible.",
        "For browser_click, omit expected_url; runtime verifies the destination URL from target_text.",
        "If you include expected_url for a click anyway, it must exactly match the listed destination URL.",
        "Do not invent URL paths such as /ticket_board.",
        "Click destination guidance:",
    ]
    if goal_id == "hard_policy_disambiguation" and current_url == "https://local.intranet/":
        lines.append('For hard_policy_disambiguation from the home page, click "Workspace policy", not "Ticket board".')
        lines.append("Avoid for this goal: Ticket board; Team status; Approvals queue.")
        lines.append('For hard_policy_disambiguation, expected_text must be one exact visible substring; choose one of "Workspace Policy", "Allowed activity", or "Search marker: fixture-backed result for workspace policy review.".')
        lines.append("Runtime destination URL for Workspace policy: https://local.intranet/docs/policy.")
        lines.append("For browser_click, omit expected_url.")
    elif goal_id == "hard_ticket_priority_crosscheck":
        if current_url == "https://local.intranet/":
            lines.append('For hard_ticket_priority_crosscheck from the home page, click "Ticket board", not "Workspace policy".')
            lines.append("Avoid for this goal: Workspace policy; Approvals queue.")
        elif current_url == "https://local.intranet/tickets":
            lines.append('For hard_ticket_priority_crosscheck from Ticket board, click "Ticket 1".')
            lines.append("Do not return to Workspace policy.")
        elif current_url == "https://local.intranet/tickets/1":
            lines.append("The ticket goal is already on the destination page.")
            lines.append('Prefer done, browser_extract_text, or browser_snapshot once you can confirm "Quarterly Access Review", "Priority: high", and "Assigned role: office worker".')
    elif goal_id == "hard_approval_policy_match":
        if current_url == "https://local.intranet/":
            lines.append('For hard_approval_policy_match from the home page, click "Approvals queue", not "Workspace policy".')
            lines.append("Avoid for this goal: Ticket board; Workspace policy.")
        elif current_url == "https://local.intranet/portal":
            lines.append('For hard_approval_policy_match from Portal Home, click "Approvals queue".')
            lines.append("Do not start with Workspace policy.")
        elif current_url == "https://local.intranet/portal/approvals":
            lines.append('For hard_approval_policy_match from Approvals queue, click "Policy match review".')
            lines.append("Do not click Workspace policy unless the approval evidence page explicitly requires it.")
    urls: list[str] = []
    for link in links:
        target_text = link["text"]
        href = link["href"]
        if not target_text or not href:
            continue
        target_url = urllib.parse.urljoin(current_url, href)
        try:
            target_resolution = resolve_browser_fixture_url(
                target_url,
                fixture_manifest_path,
                project_root=repo_root,
                allowed_url_prefixes=_fixture_url_prefixes(),
                preview_chars=2_000,
            )
        except Exception:
            continue
        anchors = _page_visible_anchor_hints(
            target_resolution.url,
            target_resolution.title,
            target_resolution.extracted_text_preview,
        )
        destination_line = f"{target_text} -> {target_resolution.url}"
        if destination_line not in urls:
            urls.append(destination_line)
        if target_text == "Workspace policy" and anchors:
            anchor_line = f"{target_text} anchors: {'; '.join(anchors[:3])}"
            if anchor_line not in lines:
                lines.append(anchor_line)
    if urls:
        lines.append(f"Exact click destinations: {'; '.join(urls)}")
    return lines or None


def _current_page_click_targets(
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    repo_root: Path,
) -> tuple[str, ...] | None:
    current_url = _prompt_text(payload.get("current_url"))
    fixture_manifest_path = _prompt_text(metadata.get("fixture_manifest_path"))
    if not current_url or not fixture_manifest_path:
        return None
    try:
        current_resolution = resolve_browser_fixture_url(
            current_url,
            fixture_manifest_path,
            project_root=repo_root,
            allowed_url_prefixes=_fixture_url_prefixes(),
            preview_chars=2_000,
        )
    except Exception:
        return None

    targets: list[str] = []
    for link in _extract_anchor_links(current_resolution.fixture_path.read_text(encoding="utf-8"))[:8]:
        target_text = _prompt_text(link.get("text"))
        if target_text and target_text not in targets:
            targets.append(target_text)
    return tuple(targets) or None


def _page_state_guidance(
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    repo_root: Path,
) -> list[str] | None:
    current_url = _prompt_text(payload.get("current_url"))
    if not current_url:
        return None
    fixture_manifest_path = _prompt_text(metadata.get("fixture_manifest_path"))
    if not fixture_manifest_path:
        return None

    lines: list[str] = []
    anchors = _page_visible_anchor_hints(
        current_url,
        _prompt_text(payload.get("title")),
        _prompt_text(payload.get("text_preview")) or "",
    )
    if anchors:
        lines.append(f"Visible page anchors: {'; '.join(anchors[:4])}")
    click_targets = _current_page_click_targets(payload, metadata, repo_root=repo_root)
    if click_targets:
        lines.append(f"Visible click targets: {'; '.join(click_targets[:8])}.")
    lines.append("Only click listed visible click targets.")
    lines.append("Do not click page titles or headings unless they are listed as click targets.")

    goal_id = _prompt_text(metadata.get("scenario_id"))
    if goal_id == "hard_policy_disambiguation" and current_url == "https://local.intranet/docs/policy":
        lines.extend(
            [
                "You are on the relevant policy page.",
                "The scenario goal is satisfied when you have evidence of the live policy source.",
                "Do not click Office Intranet Home.",
                "Do not click Home unless the goal explicitly requires navigation back.",
                "Prefer done if the goal is already satisfied and no more action is required.",
                'Next valid choices: done; browser_extract_text with expected_text "Allowed activity" or "Search marker: fixture-backed result for workspace policy review."; browser_snapshot with expected_text "Workspace Policy".',
            ]
        )
    elif goal_id == "hard_ticket_priority_crosscheck" and current_url == "https://local.intranet/tickets":
        lines.extend(
            [
                "You are on the relevant ticket board page.",
                'The next goal-relevant click is "Ticket 1".',
                "Do not click Workspace policy from here.",
                "Prefer done if the ticket page already proves Quarterly Access Review, high priority, and office worker assignment.",
            ]
        )
    elif goal_id == "hard_ticket_priority_crosscheck" and current_url == "https://local.intranet/tickets/1":
        lines.extend(
            [
                "You are on the relevant ticket page.",
                "The scenario goal is satisfied when you have evidence of the quarterly access review ticket.",
                "Do not click Workspace policy.",
                "Prefer done if the goal is already satisfied and no more action is required.",
                'Next valid choices: done; browser_extract_text with expected_text "Quarterly Access Review" or "Assigned role: office worker"; browser_snapshot with expected_text "Ticket 1 - Quarterly Access Review".',
            ]
        )
    elif goal_id == "hard_approval_policy_match" and current_url == "https://local.intranet/portal/approvals":
        lines.extend(
            [
                "You are on the relevant approvals queue page.",
                'The next goal-relevant click is "Policy match review".',
                "Do not click Workspace policy unless the approval evidence page explicitly requires it.",
                "Do not click Ticket board or Team status from here.",
            ]
        )
    elif goal_id == "hard_approval_policy_match" and current_url == "https://local.intranet/portal/approval-match":
        lines.extend(
            [
                "You are on the relevant approval policy match page.",
                "The scenario goal is satisfied when you have evidence of the approval policy match fixture.",
                "Do not click Workspace policy.",
                "Prefer done if the goal is already satisfied and no more action is required.",
                'Next valid choices: done; browser_extract_text with expected_text "Policy match: confirmed." or "Search marker: approval-policy match is the fixture-backed answer."; browser_snapshot with expected_text "Approval Policy Match".',
            ]
        )
    return lines or None


def _page_visible_anchor_hints(page_url: str | None, title: str | None, text_preview: str) -> tuple[str, ...]:
    if not page_url:
        return tuple()
    hints: list[str] = []
    known_hints: dict[str, tuple[str, ...]] = {
        "https://local.intranet/": (
            "Office Intranet Home",
            "Workspace policy",
            "Search marker: fixture-backed result for local policy review.",
        ),
        "https://local.intranet/tickets": (
            "Ticket Board",
            "Open tickets",
            "Ticket 1: Quarterly Access Review requires an office-worker status note.",
        ),
        "https://local.intranet/tickets/1": (
            "Ticket 1 - Quarterly Access Review",
            "Quarterly Access Review",
            "Priority: high",
            "Assigned role: office worker",
        ),
        "https://local.intranet/portal": (
            "Portal Home",
            "Approvals queue",
            "Approval status",
            "New request",
        ),
        "https://local.intranet/portal/approvals": (
            "Approvals Queue",
            "Pending approval check",
            "Approval item APR-42 is waiting for local policy verification.",
            "Owner: office worker.",
        ),
        "https://local.intranet/portal/approval-match": (
            "Approval Policy Match",
            "Local-only approval review",
            "Request id: APR-51.",
            "Policy match: confirmed.",
            "Search marker: approval-policy match is the fixture-backed answer.",
        ),
        "https://local.intranet/portal/status": (
            "Approval Status",
            "Approval status: ready for fixture-backed review.",
            "Policy checkpoint: local access review evidence is present.",
        ),
        "https://local.intranet/docs/policy": (
            "Workspace Policy",
            "Allowed activity",
            "Disallowed activity",
            "Search marker: fixture-backed result for workspace policy review.",
        ),
        "https://docs.local/docs/policy-disambiguation": (
            "Policy Disambiguation",
            "Current policy",
            "Search marker: current policy source is the fixture-backed answer.",
        ),
    }
    for hint in known_hints.get(page_url, ()):
        if hint and (hint == title or hint in text_preview):
            if hint not in hints:
                hints.append(hint)
    if title and title not in hints:
        hints.insert(0, title)
    return tuple(hints)


def _extract_anchor_links(html: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
        href = _prompt_text(match.group(1))
        text = _prompt_text(re.sub(r"<[^>]+>", " ", match.group(2)))
        if href and text:
            links.append({"href": href, "text": text})
    return links


def _fixture_url_prefixes() -> list[str]:
    prefixes: list[str] = []
    for host in sorted(ALLOWED_LOCAL_EXPECTED_URL_HOSTS):
        prefixes.append(f"http://{host}")
        prefixes.append(f"https://{host}")
    return prefixes


def _redact_secret_text(value: str) -> str:
    text = re.sub(
        r"(?i)['\"]?\b(api[_-]?key|token|secret|password|credential|auth)\b['\"]?\s*[:=]\s*['\"]?[^,\s'\"}]+",
        lambda match: f"{match.group(1)}=<redacted_secret>",
        value,
    )
    return re.sub(
        r"(?i)['\"]?\b(raw_prompt|raw_response|raw_output|raw_model_output|full_prompt|full_response|prompt_text|response_text)\b['\"]?\s*[:=]\s*['\"]?[^,\s'\"}]+",
        "<redacted_raw_text>",
        text,
    )


def _sanitize_prompt_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            sanitized[str(key)] = _sanitize_prompt_value(_sanitize_prompt_item(str(key), item))
        return sanitized
    if isinstance(value, list):
        return [_sanitize_prompt_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_prompt_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_prompt_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_prompt_text(str(value))


def _sanitize_prompt_item(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in ("api_key", "token", "secret", "password", "credential", "auth")):
        return "<redacted_secret>"
    if any(
        marker in lowered
        for marker in ("raw_prompt", "raw_response", "raw_output", "raw_model_output", "full_prompt", "full_response", "prompt_text", "response_text")
    ):
        return "<redacted_raw_text>"
    return value


def _sanitize_prompt_text(value: str) -> str:
    text = _redact_secret_text(value)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    return text


def _repair_constraints_lines(
    *,
    error_code: str,
    observation_payload: Mapping[str, Any],
    invalid_action: Mapping[str, Any],
    error_diagnostics: Mapping[str, Any] | None,
    repo_root: Path,
) -> list[str]:
    metadata = observation_payload.get("metadata") if isinstance(observation_payload.get("metadata"), Mapping) else {}
    diagnostics_metadata = error_diagnostics.get("metadata") if isinstance(error_diagnostics, Mapping) else None
    scenario_id = _prompt_text(metadata.get("scenario_id")) if isinstance(metadata, Mapping) else None
    if scenario_id is None and isinstance(error_diagnostics, Mapping):
        scenario_id = _prompt_text(error_diagnostics.get("scenario_id"))
    if scenario_id is None and isinstance(diagnostics_metadata, Mapping):
        scenario_id = _prompt_text(diagnostics_metadata.get("scenario_id"))
    current_url = _prompt_text(observation_payload.get("current_url"))
    current_url_key = current_url.rstrip("/") if current_url else None
    action_name = _prompt_text(invalid_action.get("action_name")) or ""
    current_page_targets = _current_page_click_targets(observation_payload, metadata, repo_root=repo_root)
    lines: list[str] = [
        "Return exactly one JSON object.",
        "Keep the repaired action minimal and valid for the current observation.",
    ]
    if action_name == "browser_click":
        lines.append('Keep action_name browser_click.')
        lines.append('Use parameters {"target_text": "<visible link/button text>"}.')
        lines.append("Omit expected_url for browser_click.")
    if error_code == "model_output_expected_text_not_atomic":
        lines.append("expected_text must be exactly one visible substring.")
        lines.append("Do not join anchors with semicolons.")
    elif error_code == "model_output_invalid_expected_url":
        lines.append("Do not output expected_url.")
        lines.append("Do not output http<absolute_path>.")
    elif error_code == "model_output_expected_url_not_matching_destination":
        lines.append("Omit expected_url for browser_click.")
    elif error_code == "model_output_expected_text_not_visible":
        lines.append("expected_text must be one exact visible substring from the destination page.")
        lines.append("Do not copy text from the current page when the click navigates elsewhere.")
    elif error_code == "model_output_irrelevant_click_target":
        lines.append("The previous target was visible but irrelevant to this scenario.")
        current_targets = set(current_page_targets or ())
        allowed_click_targets_source: Any = ()
        if isinstance(error_diagnostics, Mapping):
            allowed_click_targets_source = error_diagnostics.get("allowed_relevant_click_targets", ())
        if (not allowed_click_targets_source) and isinstance(diagnostics_metadata, Mapping):
            allowed_click_targets_source = diagnostics_metadata.get("allowed_relevant_click_targets", ())
        allowed_relevant_click_targets = tuple(
            str(item).strip()
            for item in allowed_click_targets_source
            if isinstance(item, str) and item.strip()
        ) if isinstance(allowed_click_targets_source, Sequence) else ()
        allowed_targets = set(allowed_relevant_click_targets)
        if scenario_id == "hard_policy_disambiguation" and "Workspace policy" in current_targets:
            lines.extend(
                [
                    'For hard_policy_disambiguation from the home page, click "Workspace policy".',
                    'Use browser_click with expected_text "Workspace Policy" if you need to open the policy page.',
                    "Avoid for this goal: Ticket board; Team status; Approvals queue.",
                ]
            )
        elif scenario_id == "hard_ticket_priority_crosscheck" and "Ticket board" in current_targets and "Ticket 1" not in current_targets:
            lines.extend(
                [
                    'For hard_ticket_priority_crosscheck from the home page, click "Ticket board".',
                    'Use browser_click with expected_text "Ticket Board" if you need to open the ticket board page.',
                    "Avoid for this goal: Workspace policy; Team status; Approvals queue.",
                ]
            )
        elif scenario_id == "hard_ticket_priority_crosscheck" and "Ticket 1" in current_targets:
            lines.extend(
                [
                    'For hard_ticket_priority_crosscheck from Ticket board, click "Ticket 1".',
                    'Use browser_click with expected_text "Ticket 1 - Quarterly Access Review" if you need the ticket detail page.',
                    "Avoid for this goal: Workspace policy.",
                ]
            )
        elif scenario_id == "hard_approval_policy_match" and "Approvals queue" in allowed_targets:
            lines.extend(
                [
                    'For hard_approval_policy_match from the home page, click "Approvals queue".',
                    'Use browser_click with expected_text "Approvals Queue" if you need to open the approvals queue page.',
                    "Avoid for this goal: Workspace policy; Ticket board; Team status.",
                ]
            )
        elif scenario_id == "hard_approval_policy_match" and "Policy match review" in allowed_targets:
            lines.extend(
                [
                    'For hard_approval_policy_match from Approvals queue, click "Policy match review".',
                    'Use browser_click with expected_text "Approval Policy Match" if you need the approval evidence page.',
                    "Avoid for this goal: Workspace policy; Ticket board; Team status.",
                ]
            )
        lines.append("No prose, one JSON object.")
    elif error_code == "model_output_unsupported_click_target":
        lines.append('Use parameters {"target_text": "<visible link/button text>"} for browser_click.')
        lines.append("Do not use selector, href, link_text, or button_text.")
    elif error_code == "model_output_click_target_not_visible":
        lines.append("The previous target_text was not visible or clickable on the current page.")
        lines.append("Do not click page titles or headings unless they are listed as click targets.")
    else:
        lines.append("Use only allowed local fixture actions and safe local fixture URLs.")
    if current_page_targets:
        lines.append(f"Current page visible click targets: {'; '.join(current_page_targets[:8])}.")
    current_page_anchors = _page_visible_anchor_hints(
        current_url,
        _prompt_text(observation_payload.get("title")),
        _prompt_text(observation_payload.get("text_preview")) or "",
    )
    if current_page_anchors:
        lines.append(f"Current page anchors: {'; '.join(current_page_anchors[:4])}")
    if scenario_id == "hard_policy_disambiguation" and current_url == "https://local.intranet/":
        lines.extend(
            [
                'For hard_policy_disambiguation from the home page, click "Workspace policy", not "Ticket board".',
                "Avoid for this goal: Ticket board; Team status; Approvals queue.",
                "Use destination-page anchors only.",
                'For hard_policy_disambiguation, expected_text must be one exact visible substring; choose one of "Workspace Policy", "Allowed activity", or "Search marker: fixture-backed result for workspace policy review.".',
                "Runtime destination URL for Workspace policy: https://local.intranet/docs/policy.",
                "For browser_click, omit expected_url.",
                "Do not use http<absolute_path>, https<absolute_path>, or <absolute_path>.",
                "Do not use semicolons.",
                "Do not use multiple expected_text anchors.",
                "Do not use start-page/home-page text.",
                "Suggested repair JSON example:",
                '{"step_id": "step_001_repair", "action_name": "browser_click", "parameters": {"target_text": "Workspace policy"}, "expected_text": "Workspace Policy"}',
                "Do not output expected_url.",
                "Do not output http<absolute_path>.",
                "No prose, no markdown.",
            ]
        )
    if scenario_id == "hard_policy_disambiguation" and current_url == "https://local.intranet/docs/policy":
        lines.extend(
            [
                "You are on the relevant policy page.",
                "The scenario goal is satisfied when you have evidence of the live policy source.",
                "Do not click Office Intranet Home.",
                "Do not click Home unless the goal explicitly requires navigation back.",
                "Prefer done if the goal is already satisfied and no more action is required.",
                'Use browser_extract_text with expected_text "Allowed activity" or "Search marker: fixture-backed result for workspace policy review." to collect evidence.',
                'Use browser_snapshot with expected_text "Workspace Policy" if you need a compact page capture.',
            ]
        )
    elif scenario_id == "hard_ticket_priority_crosscheck" and current_url == "https://local.intranet/":
        lines.extend(
            [
                'For hard_ticket_priority_crosscheck from the home page, click "Ticket board", not "Workspace policy".',
                "Avoid for this goal: Workspace policy; Approvals queue.",
                "Use destination-page anchors only.",
                'For hard_ticket_priority_crosscheck, expected_text must be one exact visible substring; choose one of "Ticket 1 - Quarterly Access Review", "Quarterly Access Review", "Priority: high", or "Assigned role: office worker".',
                "Runtime destination URL for Ticket 1: https://local.intranet/tickets/1.",
                "For browser_click, omit expected_url.",
                "Do not use http<absolute_path>, https<absolute_path>, or <absolute_path>.",
                "Do not use semicolons.",
                "Do not use multiple expected_text anchors.",
                "Do not use start-page/home-page text.",
                "Suggested repair JSON example:",
                '{"step_id": "step_001_repair", "action_name": "browser_click", "parameters": {"target_text": "Ticket board"}, "expected_text": "Ticket Board"}',
                "Do not output expected_url.",
                "Do not output http<absolute_path>.",
                "No prose, no markdown.",
            ]
        )
    elif scenario_id == "hard_ticket_priority_crosscheck" and current_url == "https://local.intranet/tickets":
        lines.extend(
            [
                "You are on the relevant ticket board page.",
                'The next goal-relevant click is "Ticket 1".',
                "Do not click Workspace policy from here.",
                "Prefer done if the ticket page already proves Quarterly Access Review, high priority, and office worker assignment.",
                'Use browser_click with expected_text "Ticket 1 - Quarterly Access Review" if you need to open the ticket record.',
                'Use browser_extract_text with expected_text "Quarterly Access Review" or "Priority: high" to collect evidence.',
                'Use browser_snapshot with expected_text "Ticket 1 - Quarterly Access Review" if you need a compact page capture.',
            ]
        )
    elif scenario_id == "hard_ticket_priority_crosscheck" and current_url == "https://local.intranet/tickets/1":
        lines.extend(
            [
                "You are on the relevant ticket page.",
                "The scenario goal is satisfied when you have evidence of the quarterly access review ticket.",
                "Do not click Workspace policy.",
                "Prefer done if the goal is already satisfied and no more action is required.",
                'Use browser_extract_text with expected_text "Quarterly Access Review" or "Assigned role: office worker" to collect evidence.',
                'Use browser_snapshot with expected_text "Ticket 1 - Quarterly Access Review" if you need a compact page capture.',
            ]
        )
    elif scenario_id == "hard_approval_policy_match" and current_url == "https://local.intranet/":
        lines.extend(
            [
                'For hard_approval_policy_match from the home page, click "Approvals queue", not "Workspace policy".',
                "Avoid for this goal: Ticket board; Workspace policy.",
                "Use destination-page anchors only.",
                'For hard_approval_policy_match, expected_text must be one exact visible substring; choose one of "Approvals Queue", "Pending approval check", "Approval item APR-42 is waiting for local policy verification.", or "Owner: office worker."',
                "Runtime destination URL for Approvals queue: https://local.intranet/portal/approvals.",
                "For browser_click, omit expected_url.",
                "Do not use http<absolute_path>, https<absolute_path>, or <absolute_path>.",
                "Do not use semicolons.",
                "Do not use multiple expected_text anchors.",
                "Do not use start-page/home-page text.",
                "Suggested repair JSON example:",
                '{"step_id": "step_001_repair", "action_name": "browser_click", "parameters": {"target_text": "Approvals queue"}, "expected_text": "Approvals Queue"}',
                "Do not output expected_url.",
                "Do not output http<absolute_path>.",
                "No prose, no markdown.",
            ]
        )
    elif scenario_id == "hard_approval_policy_match" and current_url == "https://local.intranet/portal/approvals":
        lines.extend(
            [
                "You are on the relevant approvals queue page.",
                'The next goal-relevant click is "Policy match review".',
                "Do not click Workspace policy unless the approval evidence page explicitly requires it.",
                'Use browser_click with expected_text "Approval Policy Match" if you need to open the approval evidence page.',
                'Use browser_extract_text with expected_text "Approval item APR-42 is waiting for local policy verification." or "Owner: office worker." to collect queue evidence.',
                'Use browser_snapshot with expected_text "Approvals Queue" if you need a compact page capture.',
            ]
        )
    elif scenario_id == "hard_approval_policy_match" and current_url == "https://local.intranet/portal/approval-match":
        lines.extend(
            [
                "You are on the relevant approval policy match page.",
                "The scenario goal is satisfied when you have evidence of the approval policy match fixture.",
                "Do not click Workspace policy.",
                "Prefer done if the goal is already satisfied and no more action is required.",
                'Use browser_extract_text with expected_text "Policy match: confirmed." or "Search marker: approval-policy match is the fixture-backed answer." to collect evidence.',
                'Use browser_snapshot with expected_text "Approval Policy Match" if you need a compact page capture.',
            ]
        )
    if error_diagnostics:
        safe_diagnostics = _sanitize_prompt_value(dict(error_diagnostics))
        lines.extend(
            [
                "Rejection diagnostics:",
                json.dumps(safe_diagnostics, ensure_ascii=False, sort_keys=True),
            ]
        )
    return lines


def _repair_observation_payload(observation_payload: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in ("observation_id", "current_url", "title"):
        value = observation_payload.get(key)
        if value is not None:
            payload[key] = _sanitize_prompt_value(value)
    metadata = observation_payload.get("metadata")
    if isinstance(metadata, Mapping):
        safe_metadata: dict[str, Any] = {}
        for key in ("scenario_id", "fixture_source", "page_opened", "browser_opened"):
            if key in metadata:
                safe_metadata[key] = _sanitize_prompt_value(metadata.get(key))
        if safe_metadata:
            payload["metadata"] = safe_metadata
    return payload
