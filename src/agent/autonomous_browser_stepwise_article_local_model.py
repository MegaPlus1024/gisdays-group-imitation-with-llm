from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from .autonomous_browser_stepwise_article_benchmark import (
    DEFAULT_STEPWISE_ARTICLE_ACTIONS,
    StepwiseArticleAction,
    StepwiseArticleObservation,
)


STEPWISE_ARTICLE_LOCAL_MODEL_SCHEMA_VERSION = "autonomous_browser_stepwise_article_local_model_v1"
DEFAULT_STEPWISE_ARTICLE_MODEL_TEMPERATURE = 0.0
DEFAULT_STEPWISE_ARTICLE_RESPONSE_MAX_TOKENS = 512
DEFAULT_STEPWISE_ARTICLE_MODEL_TIMEOUT_SECONDS = 600.0
DEFAULT_STEPWISE_ARTICLE_NO_THINK_PREFIX = "/no_think"
ALLOWED_LOCAL_MODEL_HOSTS = {"127.0.0.1", "localhost"}
ALLOWED_STEPWISE_ARTICLE_ACTION_NAMES = frozenset(DEFAULT_STEPWISE_ARTICLE_ACTIONS)


@dataclass(frozen=True)
class StepwiseArticleChatCompletionRequest:
    endpoint_url: str
    model_alias: str
    messages: tuple[dict[str, str], ...]
    temperature: float
    max_tokens: int
    timeout_seconds: float


@dataclass(frozen=True)
class StepwiseArticleChatCompletionResponse:
    content: str
    finish_reason: str | None = None
    reasoning_content_length: int = 0
    raw_response: dict[str, Any] | None = None


class StepwiseArticleLocalModelError(ValueError):
    def __init__(self, message: str, error_code: str, diagnostics: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.diagnostics = dict(diagnostics or {})


class StepwiseArticleHttpResponse(Protocol):
    status_code: int
    text: str

    def json(self) -> Any:
        ...


class StepwiseArticleHttpTransport(Protocol):
    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> StepwiseArticleHttpResponse:
        ...


class HttpxStepwiseArticleTransport:
    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> StepwiseArticleHttpResponse:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            return client.post(url, json=json)


@dataclass(frozen=True)
class StepwiseArticleLocalModelConfig:
    model_alias: str
    base_url: str
    allow_model_execution: bool = False
    temperature: float = DEFAULT_STEPWISE_ARTICLE_MODEL_TEMPERATURE
    response_max_tokens: int = DEFAULT_STEPWISE_ARTICLE_RESPONSE_MAX_TOKENS
    disable_thinking: bool = False
    no_think_prefix: str = DEFAULT_STEPWISE_ARTICLE_NO_THINK_PREFIX
    request_timeout_seconds: float = DEFAULT_STEPWISE_ARTICLE_MODEL_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        normalized_base_url = _normalize_base_url(self.base_url)
        if normalized_base_url is None:
            raise StepwiseArticleLocalModelError(
                "base_url must be a local OpenAI-style endpoint base URL.",
                "base_url_invalid",
                {"base_url_present": bool(str(self.base_url).strip())},
            )
        if not _safe_identifier(self.model_alias):
            raise StepwiseArticleLocalModelError(
                "model_alias must be a safe identifier.",
                "model_alias_invalid",
            )
        if self.response_max_tokens <= 0:
            raise StepwiseArticleLocalModelError(
                "response_max_tokens must be positive.",
                "response_max_tokens_invalid",
            )
        if self.request_timeout_seconds <= 0:
            raise StepwiseArticleLocalModelError(
                "request_timeout_seconds must be positive.",
                "request_timeout_invalid",
            )
        if self.temperature < 0:
            raise StepwiseArticleLocalModelError(
                "temperature must be non-negative.",
                "temperature_invalid",
            )
        if not isinstance(self.disable_thinking, bool):
            raise StepwiseArticleLocalModelError(
                "disable_thinking must be a boolean.",
                "disable_thinking_invalid",
            )
        if not isinstance(self.no_think_prefix, str) or not self.no_think_prefix.strip():
            raise StepwiseArticleLocalModelError(
                "no_think_prefix must be a non-empty string.",
                "no_think_prefix_invalid",
            )
        object.__setattr__(self, "base_url", normalized_base_url)
        object.__setattr__(self, "no_think_prefix", self.no_think_prefix.strip())

    @property
    def endpoint_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STEPWISE_ARTICLE_LOCAL_MODEL_SCHEMA_VERSION,
            "model_alias": self.model_alias,
            "base_url": self.base_url,
            "endpoint_url": self.endpoint_url,
            "allow_model_execution": self.allow_model_execution,
            "temperature": self.temperature,
            "response_max_tokens": self.response_max_tokens,
            "disable_thinking": self.disable_thinking,
            "no_think_prefix": self.no_think_prefix,
            "request_timeout_seconds": self.request_timeout_seconds,
        }


@dataclass
class StepwiseArticleLocalModelClient:
    config: StepwiseArticleLocalModelConfig
    transport: StepwiseArticleHttpTransport | None = None
    model_name: str = field(init=False)
    model_execution_attempted: bool = field(default=False, init=False)
    model_execution_completed: bool = field(default=False, init=False)
    last_finish_reason: str | None = field(default=None, init=False)
    last_response_id: str | None = field(default=None, init=False)
    last_raw_model_response: str | None = field(default=None, init=False)
    last_action_prompt_preview: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.model_name = self.config.model_alias
        if self.transport is None:
            self.transport = HttpxStepwiseArticleTransport()

    def next_action(
        self,
        task: str,
        observation: StepwiseArticleObservation,
        memory: dict[str, Any],
    ) -> StepwiseArticleAction:
        if not self.config.allow_model_execution:
            raise StepwiseArticleLocalModelError(
                "Real model execution requires explicit opt-in.",
                "allow_model_execution_required",
                {"model_execution": False},
            )
        prompt_messages = build_stepwise_article_prompt(
            task,
            observation,
            disable_thinking=self.config.disable_thinking,
            no_think_prefix=self.config.no_think_prefix,
        )
        self.last_action_prompt_preview = _preview_for_diagnostics(
            prompt_messages[-1]["content"],
            limit=400,
        )
        request = StepwiseArticleChatCompletionRequest(
            endpoint_url=self.config.endpoint_url,
            model_alias=self.config.model_alias,
            messages=prompt_messages,
            temperature=self.config.temperature,
            max_tokens=self.config.response_max_tokens,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        response = self._complete(request)
        self.last_finish_reason = response.finish_reason
        self.last_response_id = _response_id(response.raw_response)
        self.last_raw_model_response = response.content
        try:
            return parse_stepwise_article_action_response(response.content)
        except StepwiseArticleLocalModelError as exc:
            diagnostics = {
                "scenario_id": observation.scenario_id,
                "model_alias": self.config.model_alias,
                "trial_index": _memory_int(memory, "trial_index", default=1),
                "step_index": len(memory.get("step_results", [])) + 1,
                "parse_error_code": exc.error_code,
                "parse_error_message": str(exc),
                "raw_model_response_preview": _preview_for_diagnostics(response.content, limit=1000),
                "raw_model_response_length": len(response.content),
                "content_length": len(response.content),
                "reasoning_content_length": response.reasoning_content_length,
                "finish_reason": response.finish_reason,
                "response_id": self.last_response_id,
                "action_prompt_preview": self.last_action_prompt_preview,
                "allowed_actions": list(DEFAULT_STEPWISE_ARTICLE_ACTIONS),
                "response_max_tokens": self.config.response_max_tokens,
                "temperature": self.config.temperature,
                "disable_thinking": self.config.disable_thinking,
                "no_think_prefix_used": self.config.no_think_prefix if self.config.disable_thinking else None,
                "model_execution": True,
            }
            raise StepwiseArticleLocalModelError(
                "Model response could not be parsed into a single allowed action.",
                "model_output_parse_failed",
                diagnostics,
            ) from exc

    def _complete(
        self,
        request: StepwiseArticleChatCompletionRequest,
    ) -> StepwiseArticleChatCompletionResponse:
        payload = {
            "model": request.model_alias,
            "messages": [dict(message) for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        self.model_execution_attempted = True
        try:
            response = self.transport.post(
                request.endpoint_url,
                json=payload,
                timeout=request.timeout_seconds,
            )
        except Exception as exc:
            raise StepwiseArticleLocalModelError(
                "Local article-model request failed.",
                "model_http_request_failed",
                {
                    "exception_type": exc.__class__.__name__,
                    "endpoint_host": _endpoint_host(request.endpoint_url),
                    "endpoint_path": _endpoint_path(request.endpoint_url),
                },
            ) from exc
        if int(getattr(response, "status_code", 0)) >= 400:
            raise StepwiseArticleLocalModelError(
                "Local article-model endpoint returned an HTTP error.",
                "model_http_status_error",
                {
                    "http_status": int(getattr(response, "status_code", 0)),
                    "endpoint_host": _endpoint_host(request.endpoint_url),
                    "endpoint_path": _endpoint_path(request.endpoint_url),
                    "response_text_preview": _safe_preview(getattr(response, "text", "")),
                },
            )
        try:
            response_json = response.json()
        except Exception as exc:
            raise StepwiseArticleLocalModelError(
                "Local article-model response was not valid JSON.",
                "model_response_json_invalid",
                {
                    "exception_type": exc.__class__.__name__,
                    "endpoint_host": _endpoint_host(request.endpoint_url),
                },
            ) from exc
        content = _assistant_content(response_json)
        self.model_execution_completed = True
        return StepwiseArticleChatCompletionResponse(
            content=content,
            finish_reason=_finish_reason(response_json),
            reasoning_content_length=_reasoning_content_length(response_json),
            raw_response=response_json if isinstance(response_json, dict) else None,
        )


def build_stepwise_article_prompt(
    task: str,
    observation: StepwiseArticleObservation,
    *,
    allowed_actions: Sequence[str] = DEFAULT_STEPWISE_ARTICLE_ACTIONS,
    disable_thinking: bool = False,
    no_think_prefix: str = DEFAULT_STEPWISE_ARTICLE_NO_THINK_PREFIX,
) -> tuple[dict[str, str], ...]:
    allowed_actions_text = ", ".join(allowed_actions)
    system = (
        "Return exactly one JSON object only.\n"
        "You are choosing the next single step for a fixture-only stepwise article benchmark.\n"
        f"Allowed action names exactly: {allowed_actions_text}.\n"
        "Do not return a workflow, plan, steps array, or actions array.\n"
        "Do not use browser_click; it is not allowed in this benchmark.\n"
        "If you choose final_answer, return parameters with answer_text, citations, and confidence.\n"
        'Confidence must be one of: "low", "medium", "high".'
    )
    user_body = (
        f"Task: {task}\n"
        f"Scenario ID: {observation.scenario_id}\n"
        f"Page opened: {json.dumps(observation.page_opened)}\n"
        f"Current URL: {observation.current_url or 'null'}\n"
        f"Article title: {observation.article_title or 'null'}\n"
        f"Visible section id: {observation.visible_section_id or 'null'}\n"
        f"Visible section title: {observation.visible_section_title or 'null'}\n"
        f"Sections total: {observation.sections_total}\n"
        f"Sections read count: {observation.sections_read_count}\n"
        f"Sections read ids: {', '.join(observation.sections_read_ids) if observation.sections_read_ids else 'none'}\n"
        f"Last action name: {observation.last_action_name or 'null'}\n"
        f"Last find result: {json.dumps(observation.last_find_result or {}, ensure_ascii=False, sort_keys=True)}\n"
        f"Visible text:\n{observation.visible_text or '[no page content visible yet]'}\n\n"
        "Reply with exactly one JSON object using this schema:\n"
        '{\n'
        '  "action_name": "...",\n'
        '  "parameters": {...},\n'
        '  "reason": "short optional reason"\n'
        '}\n'
        "For final_answer use:\n"
        '{\n'
        '  "action_name": "final_answer",\n'
        '  "parameters": {\n'
        '    "answer_text": "...",\n'
        '    "citations": ["section_or_anchor_id"],\n'
        '    "confidence": "low|medium|high"\n'
        "  }\n"
        "}\n"
        "Return no prose before or after the JSON."
    )
    user = user_body
    if disable_thinking:
        user = f"{no_think_prefix.strip()}\n{user_body}"
    return (
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    )


def parse_stepwise_article_action_response(raw_text: str) -> StepwiseArticleAction:
    payload = _extract_single_json_payload(raw_text)
    if isinstance(payload, list):
        raise StepwiseArticleLocalModelError(
            "Model response must contain exactly one action object, not a list.",
            "multiple_actions_rejected",
        )
    if not isinstance(payload, dict):
        raise StepwiseArticleLocalModelError(
            "Model response root must be a JSON object.",
            "action_object_required",
        )
    if _looks_like_workflow_json(payload):
        raise StepwiseArticleLocalModelError(
            "Full workflow JSON is not allowed; return exactly one action.",
            "full_workflow_json_rejected",
            {"disallowed_keys": sorted(key for key in payload.keys() if key in {"actions", "steps", "final_answer", "facts", "evidence_items"})},
        )

    action_name = payload.get("action_name")
    if not isinstance(action_name, str) or not action_name.strip():
        raise StepwiseArticleLocalModelError(
            "action_name must be a non-empty string.",
            "action_name_missing",
        )
    normalized_action_name = action_name.strip()
    if normalized_action_name == "browser_click":
        raise StepwiseArticleLocalModelError(
            "browser_click is not allowed in the default article benchmark.",
            "disallowed_action_browser_click",
            {"action_name": normalized_action_name},
        )
    if normalized_action_name not in ALLOWED_STEPWISE_ARTICLE_ACTION_NAMES:
        raise StepwiseArticleLocalModelError(
            "Unknown action_name returned by the model.",
            "unknown_action",
            {"action_name": normalized_action_name},
        )
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise StepwiseArticleLocalModelError(
            "parameters must be a JSON object.",
            "parameters_invalid",
            {"action_name": normalized_action_name},
        )
    normalized_parameters = dict(parameters)
    if normalized_action_name == "final_answer":
        normalized_parameters = _normalize_final_answer_parameters(normalized_parameters)
    return StepwiseArticleAction(
        action_name=normalized_action_name,
        parameters=normalized_parameters,
    )


def _normalize_final_answer_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    answer_text = parameters.get("answer_text")
    if not isinstance(answer_text, str) or not answer_text.strip():
        raise StepwiseArticleLocalModelError(
            "final_answer.answer_text must be a non-empty string.",
            "final_answer_text_invalid",
        )
    citations_payload = parameters.get("citations", parameters.get("citation_ids", []))
    if isinstance(citations_payload, str):
        citations = [citations_payload.strip()] if citations_payload.strip() else []
    elif isinstance(citations_payload, list):
        citations = [str(item).strip() for item in citations_payload if str(item).strip()]
    else:
        raise StepwiseArticleLocalModelError(
            "final_answer.citations must be a list of section identifiers.",
            "final_answer_citations_invalid",
        )
    confidence = parameters.get("confidence", "medium")
    if not isinstance(confidence, str) or confidence.strip() not in {"low", "medium", "high"}:
        raise StepwiseArticleLocalModelError(
            "final_answer.confidence must be one of low|medium|high.",
            "final_answer_confidence_invalid",
        )
    return {
        "answer_text": answer_text.strip(),
        "citation_ids": citations,
        "confidence": confidence.strip(),
    }


def _assistant_content(response_json: Any) -> str:
    if not isinstance(response_json, Mapping):
        raise StepwiseArticleLocalModelError(
            "Model response JSON root must be an object.",
            "model_response_shape_invalid",
        )
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise StepwiseArticleLocalModelError(
            "Model response is missing choices.",
            "model_response_choices_missing",
        )
    first = choices[0]
    if not isinstance(first, Mapping):
        raise StepwiseArticleLocalModelError(
            "Model response choice must be an object.",
            "model_response_choice_invalid",
        )
    message = first.get("message")
    if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
        raise StepwiseArticleLocalModelError(
            "Model response message content is missing.",
            "model_response_content_missing",
        )
    return str(message["content"])


def _finish_reason(response_json: Any) -> str | None:
    if not isinstance(response_json, Mapping):
        return None
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    finish_reason = first.get("finish_reason")
    return finish_reason if isinstance(finish_reason, str) else None


def _reasoning_content_length(response_json: Any) -> int:
    if not isinstance(response_json, Mapping):
        return 0
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return 0
    first = choices[0]
    if not isinstance(first, Mapping):
        return 0
    message = first.get("message")
    if not isinstance(message, Mapping):
        return 0
    return _content_like_length(message.get("reasoning_content"))


def _content_like_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(json.dumps(list(value), ensure_ascii=False))
    if isinstance(value, Mapping):
        return len(json.dumps(dict(value), ensure_ascii=False, sort_keys=True))
    return 0


def _extract_single_json_payload(raw_text: str) -> Any | None:
    text = raw_text.strip()
    if not text:
        raise StepwiseArticleLocalModelError(
            "Model response did not contain a JSON object.",
            "no_json_object_found",
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if text.startswith("{") or text.startswith("["):
            raise StepwiseArticleLocalModelError(
                "Model response looked like JSON but could not be parsed.",
                "invalid_json",
            )

    fenced_candidates = [
        block.strip()
        for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if block.strip()
    ]
    parsed_candidates: list[Any] = []
    for candidate in fenced_candidates:
        try:
            parsed_candidates.append(json.loads(candidate))
            continue
        except json.JSONDecodeError:
            if candidate.startswith("{") or candidate.startswith("["):
                raise StepwiseArticleLocalModelError(
                    "Fenced JSON candidate could not be parsed.",
                    "invalid_json",
                )
            balanced = _extract_balanced_json_object(candidate)
            if balanced is not None:
                try:
                    parsed_candidates.append(json.loads(balanced))
                except json.JSONDecodeError:
                    raise StepwiseArticleLocalModelError(
                        "Balanced JSON object could not be parsed.",
                        "invalid_json",
                    ) from None
    if len(parsed_candidates) > 1:
        raise StepwiseArticleLocalModelError(
            "Multiple JSON objects were found in the model response.",
            "multiple_actions_rejected",
        )
    if len(parsed_candidates) == 1:
        return parsed_candidates[0]

    balanced_objects = _extract_balanced_json_objects(text)
    if len(balanced_objects) > 1:
        raise StepwiseArticleLocalModelError(
            "Multiple JSON objects were found in the model response.",
            "multiple_actions_rejected",
        )
    if len(balanced_objects) == 1:
        try:
            return json.loads(balanced_objects[0])
        except json.JSONDecodeError:
            raise StepwiseArticleLocalModelError(
                "Balanced JSON object could not be parsed.",
                "invalid_json",
            ) from None
    raise StepwiseArticleLocalModelError(
        "Model response did not contain a JSON object.",
        "no_json_object_found",
    )


def _extract_balanced_json_object(text: str) -> str | None:
    objects = _extract_balanced_json_objects(text)
    return objects[0] if len(objects) == 1 else None


def _extract_balanced_json_objects(text: str) -> list[str]:
    results: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    start_index: int | None = None
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue
        if char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start_index is not None:
                results.append(text[start_index : index + 1])
                start_index = None
    return results


def _looks_like_workflow_json(payload: Mapping[str, Any]) -> bool:
    if "actions" in payload or "steps" in payload:
        return True
    if "final_answer" in payload and "action_name" not in payload:
        return True
    if "facts" in payload or "evidence_items" in payload:
        return True
    return False


def _normalize_base_url(value: str) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme != "http" or not parsed.netloc:
        return None
    if parsed.hostname not in ALLOWED_LOCAL_MODEL_HOSTS:
        return None
    if parsed.path.rstrip("/") not in {"", "/v1"}:
        return None
    return f"http://{parsed.netloc}/v1"


def _endpoint_host(url: str) -> str | None:
    return urlparse(url).hostname


def _endpoint_path(url: str) -> str:
    return urlparse(url).path or "/"


def _safe_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", value.strip()))


def _safe_preview(value: str, *, limit: int = 200) -> str:
    text = " ".join(value.split())
    return text[:limit]


def _response_id(response_json: Any) -> str | None:
    if not isinstance(response_json, Mapping):
        return None
    value = response_json.get("id")
    return value if isinstance(value, str) else None


def _memory_int(memory: Mapping[str, Any], key: str, *, default: int) -> int:
    value = memory.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _preview_for_diagnostics(value: str, *, limit: int) -> str:
    compact = " ".join(str(value).split())
    sanitized = re.sub(
        r"authorization\s*:\s*bearer\s+\S+",
        "[redacted authorization header]",
        compact,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"\bBearer\s+[A-Za-z0-9._-]{8,}\b",
        "Bearer [redacted]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"\b(api[_-]?key|token|secret)\b\s*[:=]\s*([^\s,;]+)",
        r"\1=[redacted]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized[:limit]
