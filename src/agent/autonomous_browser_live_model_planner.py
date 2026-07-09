from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from .autonomous_browser_live_planner import AutonomousBrowserLivePlannerStep
from .autonomous_browser_plan_validation import PLAN_SCHEMA_VERSION, validate_autonomous_browser_plan


LOCAL_MODEL_LIVE_PLANNER_SCHEMA_VERSION = "autonomous_browser_live_model_planner_v1"
DEFAULT_LOCAL_MODEL_PLANNER_ID = "browser_live_loop_local_model_planner_v1"
DEFAULT_LOCAL_MODEL_ALIAS = "third_model"
DEFAULT_LOCAL_MODEL_ENDPOINT = "http://127.0.0.1:8082/v1"
DEFAULT_LOCAL_MODEL_TEMPERATURE = 0.0
DEFAULT_LOCAL_MODEL_MAX_TOKENS = 256
DEFAULT_LOCAL_MODEL_TIMEOUT_SECONDS = 120.0
ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


@dataclass(frozen=True)
class ChatCompletionRequest:
    endpoint_base_url: str
    model: str
    messages: tuple[dict[str, str], ...]
    temperature: float
    max_tokens: int
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
        url = f"{request.endpoint_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": request.model,
            "messages": [dict(message) for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        with httpx.Client(timeout=request.timeout_seconds, trust_env=False) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            response_json = response.json()
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
    planner_id: str = DEFAULT_LOCAL_MODEL_PLANNER_ID
    allowed_model_aliases: tuple[str, ...] = ()
    no_think: bool | None = None
    temperature: float = DEFAULT_LOCAL_MODEL_TEMPERATURE
    max_tokens: int = DEFAULT_LOCAL_MODEL_MAX_TOKENS
    timeout_seconds: float = DEFAULT_LOCAL_MODEL_TIMEOUT_SECONDS
    metadata: dict[str, Any] = field(default_factory=dict)

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
    last_finish_reason: str | None = field(default=None, init=False)
    last_request: ChatCompletionRequest | None = field(default=None, init=False)
    last_response: ChatCompletionResponse | None = field(default=None, init=False)

    def build_messages(self, observation: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
        payload = _observation_payload(observation)
        system_parts = [
            "You are a guarded local browser planner for a fixture-backed loop.",
            "Return exactly one JSON object only.",
            "Do not use markdown, code fences, arrays, or multiple JSON objects.",
            "The JSON object must represent one next browser action or a done signal.",
            "Allowed action names: browser_open_url, browser_click, browser_extract_text, browser_fill, browser_submit, browser_wait, browser_search, browser_snapshot, done.",
            "Never request secrets, credentials, tokens, passwords, file URLs, external URLs, or real browser access.",
        ]
        if self._effective_no_think():
            system_parts.insert(0, "/no_think")
        user_parts = [
            "Observation JSON:",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "Return one JSON object with keys step_id, action_name, parameters, expected_text, optional expected_url, optional done, optional metadata.",
            "If you are done, set action_name to done and done to true.",
            "If you are not done, keep expected_text short and grounded in the local fixture observation.",
        ]
        return [
            {"role": "system", "content": "\n".join(system_parts)},
            {"role": "user", "content": "\n".join(user_parts)},
        ]

    def validate_runtime_guard(self) -> None:
        if not self.config.allow_model_calls:
            self.last_error_code = "allow_model_calls_required"
            raise LocalModelLivePlannerError(
                "Model calls are disabled for this planner backend.",
                "allow_model_calls_required",
            )

        parsed = urllib.parse.urlparse(self.config.model_endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            self.last_error_code = "endpoint_host_not_allowed"
            raise LocalModelLivePlannerError(
                "Model endpoint must be a local loopback HTTP(S) URL.",
                "endpoint_host_not_allowed",
            )
        hostname = (parsed.hostname or "").lower()
        if hostname not in ALLOWED_LOCAL_HOSTS:
            self.last_error_code = "endpoint_host_not_allowed"
            raise LocalModelLivePlannerError(
                "Model endpoint host is not allowed.",
                "endpoint_host_not_allowed",
            )

        allowed_aliases = self.allowed_model_aliases()
        if self.config.model_alias not in allowed_aliases:
            self.last_error_code = "model_alias_not_allowed"
            raise LocalModelLivePlannerError(
                "Model alias is not listed in the allowed planner config.",
                "model_alias_not_allowed",
            )

    def allowed_model_aliases(self) -> tuple[str, ...]:
        if self.config.allowed_model_aliases:
            return self.config.allowed_model_aliases
        return _load_model_aliases(self.repo_root)

    def next_step(self, observation: Mapping[str, Any] | None = None) -> AutonomousBrowserLivePlannerStep | None:
        self.validate_runtime_guard()
        self.step_index += 1
        request = ChatCompletionRequest(
            endpoint_base_url=self.config.model_endpoint,
            model=self.config.model_alias,
            messages=tuple(self.build_messages(observation)),
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout_seconds=self.config.timeout_seconds,
        )
        self.last_request = request
        self.model_execution_attempted = True
        client = self.client or HttpxChatCompletionClient()
        try:
            response = client.complete(request)
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            self.last_error_code = "planner_request_failed"
            raise LocalModelLivePlannerError(
                "Model request failed.",
                "planner_request_failed",
            ) from exc
        self.last_response = response
        self.model_execution_completed = True
        self.last_finish_reason = response.finish_reason
        if (response.finish_reason or "").strip().lower() == "length":
            self.last_error_code = "planner_response_truncated"
            raise LocalModelLivePlannerError(
                "Model response finished due to length limit.",
                "planner_response_truncated",
            )

        content = response.content.strip()
        if not content:
            self.last_error_code = "planner_response_parse_failed"
            raise LocalModelLivePlannerError(
                "Model response content was empty.",
                "planner_response_parse_failed",
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            self.last_error_code = "planner_response_parse_failed"
            raise LocalModelLivePlannerError(
                "Model response was not valid JSON.",
                "planner_response_parse_failed",
            ) from exc

        if not isinstance(parsed, Mapping):
            if isinstance(parsed, list):
                self.last_error_code = "planner_response_array_not_allowed"
                raise LocalModelLivePlannerError(
                    "Model response JSON array is not allowed.",
                    "planner_response_array_not_allowed",
                )
            self.last_error_code = "planner_response_must_be_object"
            raise LocalModelLivePlannerError(
                "Model response must be a JSON object.",
                "planner_response_must_be_object",
            )

        if "actions" in parsed:
            self.last_error_code = "planner_response_plan_shape_not_allowed"
            raise LocalModelLivePlannerError(
                "Full plan objects are not allowed.",
                "planner_response_plan_shape_not_allowed",
            )

        step = self._step_from_payload(parsed)
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
            "last_finish_reason": self.last_finish_reason,
            "allowed_model_aliases": list(self.allowed_model_aliases()),
        }

    def _step_from_payload(self, payload: Mapping[str, Any]) -> AutonomousBrowserLivePlannerStep:
        if "actions" in payload:
            self.last_error_code = "planner_response_plan_shape_not_allowed"
            raise LocalModelLivePlannerError(
                "Full plan objects are not allowed.",
                "planner_response_plan_shape_not_allowed",
            )

        action_name = _safe_text(payload.get("action_name"), "action_name")
        if action_name is None:
            self.last_error_code = "missing_action_name"
            raise LocalModelLivePlannerError(
                "Model response is missing action_name.",
                "missing_action_name",
            )

        step_id = _safe_text(payload.get("step_id"), "step_id")
        if step_id is None:
            step_id = "done" if action_name == "done" or bool(payload.get("done")) else f"{self.config.planner_id}_step_{self.step_index:04d}"

        done = bool(payload.get("done", False)) or action_name == "done"
        parameters = payload.get("parameters", {})
        expected_text = _safe_text(payload.get("expected_text"), "expected_text") or ""
        expected_url = _safe_text(payload.get("expected_url"), "expected_url")
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

        if not expected_text:
            self.last_error_code = "missing_expected_text"
            raise LocalModelLivePlannerError(
                "Model response is missing expected_text.",
                "missing_expected_text",
            )

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
            self.last_error_code = error_code
            raise LocalModelLivePlannerError(
                "Model response action failed validation.",
                error_code,
                {"validation_result": validation_result},
            )
        normalized_plan = validation_result.get("normalized_plan")
        if not isinstance(normalized_plan, Mapping):
            self.last_error_code = "planner_action_validation_failed"
            raise LocalModelLivePlannerError(
                "Model response validation did not produce a normalized plan.",
                "planner_action_validation_failed",
            )
        normalized_action = normalized_plan["actions"][0]
        self.last_error_code = None
        return AutonomousBrowserLivePlannerStep(
            step_id=str(normalized_action["step_id"]),
            action_name=str(normalized_action["action_name"]),
            parameters=dict(normalized_action["parameters"]),
            expected_text=str(normalized_action.get("expected_text", "")),
            expected_url=str(normalized_action["expected_url"]) if isinstance(normalized_action.get("expected_url"), str) else None,
            done=False,
            metadata=metadata,
        )

    def _effective_no_think(self) -> bool:
        if self.config.no_think is not None:
            return self.config.no_think
        return self.config.model_alias == DEFAULT_LOCAL_MODEL_ALIAS


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
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalModelLivePlannerError(
            "Chat completion response is missing assistant content.",
            "planner_response_parse_failed",
        ) from exc
    if not isinstance(content, str):
        raise LocalModelLivePlannerError(
            "Chat completion assistant content must be text.",
            "planner_response_parse_failed",
        )
    return content


def _finish_reason(response_json: Mapping[str, Any]) -> str | None:
    try:
        finish_reason = response_json["choices"][0]["finish_reason"]
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
