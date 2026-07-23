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


class LocalLLMRequestError(LocalLLMClientError):
    """Request/transport failure while calling local runtime."""


class LocalLLMResponseError(LocalLLMClientError):
    """Malformed or missing model response content."""


class LocalLLMJSONError(LocalLLMClientError):
    """Model output was not valid JSON."""


class LocalLLMValidationError(LocalLLMClientError):
    """Model JSON failed schema validation."""


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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.endpoint = f"{self.base_url}/chat/completions"
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.last_usage: dict[str, int] = {}

    def _build_messages(self, agent_state: dict[str, Any]) -> list[dict[str, str]]:
        return self.prompt_builder.build_messages(agent_state)

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
                "Missing assistant message content in response JSON."
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise LocalLLMResponseError("Assistant message content is empty.")
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
        text = self.extract_assistant_content(response_json)
        return self.parse_next_action_text(text)
