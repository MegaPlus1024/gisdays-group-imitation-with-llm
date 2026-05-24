from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.endpoint = f"{self.base_url}/chat/completions"

    def _build_messages(self, agent_state: dict[str, Any]) -> list[dict[str, str]]:
        compact_state = json.dumps(agent_state, ensure_ascii=False, separators=(",", ":"))
        system_message = (
            "You are a local LLM used by an agent. Return only valid JSON "
            "matching the requested action schema."
        )
        user_message = (
            "Agent state JSON:\n"
            f"{compact_state}\n\n"
            "Return exactly one next action as JSON with this shape:\n"
            '{\n  "action": "string",\n  "parameters": {},\n  "reason": "string",\n'
            '  "expected_result": "string"\n}'
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

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
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LocalLLMJSONError(f"Invalid JSON output: {exc}") from exc

        try:
            return NextAction.model_validate(payload)
        except ValidationError as exc:
            raise LocalLLMValidationError(
                f"Output JSON failed NextAction validation: {exc}"
            ) from exc

    def generate_next_action(self, agent_state: dict[str, Any]) -> NextAction:
        payload = self._build_payload(agent_state)
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.post(self.endpoint, json=payload)
                response.raise_for_status()
                response_json = response.json()
        except httpx.HTTPError as exc:
            raise LocalLLMRequestError(f"Local runtime request failed: {exc}") from exc

        text = self.extract_assistant_content(response_json)
        return self.parse_next_action_text(text)
