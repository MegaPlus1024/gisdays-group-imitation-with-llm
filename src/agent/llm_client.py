from __future__ import annotations
from typing import Any

import httpx

from .action_contract import (
    NextActionJSONError,
    NextActionValidationError,
    parse_next_action_text as parse_next_action_contract_text,
)
from .prompt_contract import PromptBuilder
from .schemas import NextAction


class LocalLLMClientError(Exception):
    """Base error for local LLM adapter failures."""

    error_code = "local_model_error"


class LocalLLMRequestError(LocalLLMClientError):
    """Request/transport failure while calling local runtime."""


class LocalLLMResponseError(LocalLLMClientError):
    """Malformed or missing model response content."""

    def __init__(self, message: str, error_code: str = "empty_content") -> None:
        super().__init__(message)
        self.error_code = error_code


class LocalLLMJSONError(LocalLLMClientError):
    """Model output was not valid JSON."""

    error_code = "invalid_action_json"


class LocalLLMValidationError(LocalLLMClientError):
    """Model JSON failed schema validation."""

    error_code = "invalid_action_json"


class LocalLLMClient:
    """Reusable adapter for a local OpenAI-compatible llama-server endpoint."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080/v1",
        model_name: str = "first_model.gguf",
        timeout_seconds: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int = 512,
        prompt_builder: PromptBuilder | None = None,
        disable_thinking: bool = False,
        no_think_prefix: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.endpoint = f"{self.base_url}/chat/completions"
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.disable_thinking = disable_thinking
        self.no_think_prefix = no_think_prefix.strip()
        self.last_usage: dict[str, int] = {}
        self.last_diagnostics: dict[str, Any] = {}

    def _build_messages(self, agent_state: dict[str, Any]) -> list[dict[str, str]]:
        messages = self.prompt_builder.build_messages(agent_state)
        if self.disable_thinking and self.no_think_prefix and messages:
            messages = [dict(message) for message in messages]
            messages[-1]["content"] = (
                f"{self.no_think_prefix}\n{messages[-1]['content']}"
            )
        return messages

    def _build_payload(self, agent_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "messages": self._build_messages(agent_state),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    @staticmethod
    def extract_assistant_content(response_json: dict[str, Any]) -> str:
        try:
            content = response_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalLLMResponseError(
                "Missing assistant message content in response JSON.", "empty_content"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise LocalLLMResponseError("Assistant message content is empty.")
        return content

    def _extract_assistant_content_with_diagnostics(
        self, response_json: dict[str, Any]
    ) -> str:
        try:
            choice = response_json["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalLLMResponseError(
                "Missing assistant message content in response JSON.",
                "empty_content",
            ) from exc

        content = message.get("content")
        reasoning_content = message.get("reasoning_content")
        finish_reason = choice.get("finish_reason")
        self.last_diagnostics = {
            "response_id": response_json.get("id"),
            "finish_reason": finish_reason,
            "content_length": len(content) if isinstance(content, str) else 0,
            "reasoning_content_length": (
                len(reasoning_content) if isinstance(reasoning_content, str) else 0
            ),
            "no_think_prefix_used": bool(
                self.disable_thinking and self.no_think_prefix
            ),
        }

        if not isinstance(content, str) or not content.strip():
            if self.last_diagnostics["reasoning_content_length"]:
                code = "empty_content_with_reasoning"
            elif finish_reason == "length":
                code = "finish_reason_length"
            else:
                code = "empty_content"
            raise LocalLLMResponseError("Assistant message content is empty.", code)
        return content

    @staticmethod
    def parse_next_action_text(text: str) -> NextAction:
        try:
            return parse_next_action_contract_text(text)
        except NextActionJSONError as exc:
            raise LocalLLMJSONError(str(exc)) from exc
        except NextActionValidationError as exc:
            raise LocalLLMValidationError(
                f"Output JSON failed NextAction validation: {exc}"
            ) from exc

    def generate_next_action(self, agent_state: dict[str, Any]) -> NextAction:
        self.last_usage = {}
        self.last_diagnostics = {}
        payload = self._build_payload(agent_state)
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.post(self.endpoint, json=payload)
                response.raise_for_status()
                response_json = response.json()
        except httpx.HTTPError as exc:
            raise LocalLLMRequestError(f"Local runtime request failed: {exc}") from exc

        usage = response_json.get("usage")
        if isinstance(usage, dict):
            self.last_usage = {
                key: int(value)
                for key, value in usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and isinstance(value, int)
                and value >= 0
            }
        text = self._extract_assistant_content_with_diagnostics(response_json)
        return self.parse_next_action_text(text)
