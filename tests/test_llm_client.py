from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.llm_client import (
    LocalLLMClient,
    LocalLLMJSONError,
    LocalLLMRequestError,
    LocalLLMResponseError,
    LocalLLMValidationError,
)
from agent.schemas import NextAction


def test_local_llm_client_normalizes_base_url() -> None:
    client = LocalLLMClient(base_url="http://127.0.0.1:8080/v1/")
    assert client.base_url == "http://127.0.0.1:8080/v1"
    assert client.endpoint == "http://127.0.0.1:8080/v1/chat/completions"


def test_build_payload_includes_expected_fields() -> None:
    client = LocalLLMClient(model_name="first_model.gguf", temperature=0.0, max_tokens=512)
    payload = client._build_payload({"stage": "init"})
    assert payload["model"] == "first_model.gguf"
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 512
    assert isinstance(payload["messages"], list)
    assert len(payload["messages"]) == 2


def test_disable_thinking_prefix_is_applied_to_user_prompt() -> None:
    client = LocalLLMClient(disable_thinking=True, no_think_prefix="/no_think")
    messages = client._build_messages({"stage": "init"})
    assert messages[-1]["content"].startswith("/no_think\n")


def test_extract_assistant_content_valid() -> None:
    response = {"choices": [{"message": {"content": '{"action":"read_file","reason":"r","expected_result":"e","parameters":{}}'}}]}
    text = LocalLLMClient.extract_assistant_content(response)
    assert text.startswith('{"action":"read_file"')


def test_extract_assistant_content_rejects_missing_choices() -> None:
    with pytest.raises(LocalLLMResponseError):
        LocalLLMClient.extract_assistant_content({})


def test_extract_assistant_content_rejects_empty() -> None:
    with pytest.raises(LocalLLMResponseError):
        LocalLLMClient.extract_assistant_content({"choices": [{"message": {"content": "   "}}]})


def test_empty_content_with_reasoning_has_structured_diagnostics() -> None:
    client = LocalLLMClient(disable_thinking=True, no_think_prefix="/no_think")
    with pytest.raises(LocalLLMResponseError) as raised:
        client._extract_assistant_content_with_diagnostics(
            {"id": "response-1", "choices": [{"finish_reason": "stop", "message": {"content": "", "reasoning_content": "internal"}}]}
        )
    assert raised.value.error_code == "empty_content_with_reasoning"
    assert client.last_diagnostics["reasoning_content_length"] == 8
    assert client.last_diagnostics["content_length"] == 0


def test_parse_next_action_text_accepts_valid_json() -> None:
    text = '{"action":"read_file","parameters":{},"reason":"need file","expected_result":"file content"}'
    action = LocalLLMClient.parse_next_action_text(text)
    assert isinstance(action, NextAction)
    assert action.action == "read_file"


def test_parse_next_action_text_rejects_invalid_json() -> None:
    with pytest.raises(LocalLLMJSONError):
        LocalLLMClient.parse_next_action_text("{not-json}")


def test_parse_next_action_text_rejects_schema_invalid_json() -> None:
    with pytest.raises(LocalLLMValidationError):
        LocalLLMClient.parse_next_action_text('{"action":"","parameters":{},"reason":"x","expected_result":"y"}')


def test_generate_next_action_returns_next_action_with_mocked_http(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class MockResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"action":"read_file","parameters":{},"reason":"inspect state","expected_result":"read complete"}'
                        }
                    }
                ]
            }

    class MockClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self) -> MockClient:
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def post(self, endpoint: str, json: dict[str, Any]) -> MockResponse:
            captured["endpoint"] = endpoint
            captured["json"] = json
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", MockClient)

    client = LocalLLMClient()
    result = client.generate_next_action({"phase": "initial"})
    assert isinstance(result, NextAction)
    assert result.action == "read_file"
    assert captured["trust_env"] is False
    assert captured["endpoint"] == "http://127.0.0.1:8080/v1/chat/completions"


def test_generate_next_action_maps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self) -> ErrorClient:
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def post(self, endpoint: str, json: dict[str, Any]) -> Any:
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "Client", ErrorClient)
    client = LocalLLMClient()
    with pytest.raises(LocalLLMRequestError):
        client.generate_next_action({"phase": "initial"})
