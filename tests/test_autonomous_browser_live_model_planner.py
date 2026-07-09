from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.agent.autonomous_browser_live_model_planner import (
    ChatCompletionResponse,
    LocalModelLivePlanner,
    LocalModelLivePlannerError,
    LocalModelPlannerConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = {
    "observation_id": "observation_0001",
    "current_url": "https://local.intranet/",
    "title": "Office Intranet",
    "text_preview": "Review ticket updates",
    "metadata": {"fixture_source": True},
}
ALLOWED_ALIASES = ("first_model", "second_model", "third_model")


class FakeChatCompletionClient:
    def __init__(self, responses: list[ChatCompletionResponse]) -> None:
        self.responses = list(responses)
        self.requests = []

    def complete(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected model request")
        return self.responses.pop(0)


def _planner(
    *,
    model_alias: str = "third_model",
    allow_model_calls: bool = True,
    model_endpoint: str = "http://127.0.0.1:8082/v1",
    no_think: bool | None = None,
    client: FakeChatCompletionClient | None = None,
) -> LocalModelLivePlanner:
    config = LocalModelPlannerConfig(
        kind="local_model",
        model_alias=model_alias,
        model_endpoint=model_endpoint,
        allow_model_calls=allow_model_calls,
        planner_id="browser_live_loop_local_model_planner_test",
        allowed_model_aliases=ALLOWED_ALIASES,
        no_think=no_think,
    )
    return LocalModelLivePlanner(config=config, client=client, repo_root=PROJECT_ROOT)


def test_third_model_prompt_includes_no_think_by_default() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=False)

    messages = planner.build_messages(OBSERVATION)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[0]["content"].startswith("/no_think")
    assert "Return exactly one JSON object only." in messages[0]["content"]


def test_second_model_prompt_omits_no_think() -> None:
    planner = _planner(model_alias="second_model", allow_model_calls=False)

    messages = planner.build_messages(OBSERVATION)

    assert messages[0]["role"] == "system"
    assert "/no_think" not in messages[0]["content"]


def test_valid_next_action_returns_step() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert step.step_id == "open_home"
    assert step.action_name == "browser_open_url"
    assert step.parameters["url"] == "https://local.intranet/"
    assert step.expected_text == "Office Intranet"
    assert step.done is False
    assert planner.model_execution_attempted is True
    assert planner.model_execution_completed is True
    assert client.requests[0].model == "third_model"
    assert client.requests[0].stream is False
    assert client.requests[0].max_tokens >= 1200
    assert client.requests[0].messages[0]["content"].startswith("/no_think")
    assert planner.to_summary()["request_payload_metadata"]["stream"] is False
    assert planner.to_summary()["request_payload_metadata"]["max_tokens"] >= 1200


def test_done_action_returns_done_step() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"done","action_name":"done","parameters":{},"expected_text":"","done":true}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert step.done is True
    assert step.action_name == "done"


def test_json_array_is_rejected() -> None:
    client = FakeChatCompletionClient([ChatCompletionResponse(content="[]", finish_reason="stop")])
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_output_no_json_object"


def test_invalid_json_is_rejected() -> None:
    client = FakeChatCompletionClient(
        [ChatCompletionResponse(content='{"step_id":"one"} {"step_id":"two"}', finish_reason="stop")]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_response_invalid_json"


def test_full_plan_object_is_rejected() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"schema_version":"autonomous_browser_plan_v1","plan_id":"plan","goal":"goal","scenario_id":"browser_live_loop_local_model","max_actions":1,"actions":[{"step_id":"one","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}]}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_output_invalid_action"


def test_external_url_is_rejected() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_external","action_name":"browser_open_url","parameters":{"url":"https://example.com/"},"expected_text":"Example"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "external_url_not_allowed"


def test_secret_like_request_is_rejected() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"secret","action_name":"browser_extract_text","parameters":{"query":"api_key = supersecret"},"expected_text":"secret"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    diagnostics = excinfo.value.diagnostics
    diagnostics_text = json.dumps(diagnostics, ensure_ascii=False)

    assert excinfo.value.error_code == "secret_like_parameter_value"
    assert diagnostics["validation_result"]["diagnostics"][0]["finding_type"] == "secret_like_parameter_value"
    assert diagnostics["validation_result"]["diagnostics"][0]["path"] == "actions[0].parameters.query"
    assert diagnostics["validation_result"]["diagnostics"][0]["parameter_key"] == "api_key"
    assert "supersecret" not in diagnostics_text
    assert "Traceback" not in diagnostics_text


def test_finish_reason_length_is_rejected() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="length",
            )
        ]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_finish_reason_length"


def test_allow_model_calls_required_refusal() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(allow_model_calls=False, client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "allow_model_calls_required"
    assert client.requests == []


def test_non_local_endpoint_is_rejected_without_calling_client() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(model_endpoint="http://example.com:8082/v1", client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "non_local_model_endpoint"
    assert client.requests == []


def test_localhost_endpoint_is_allowed_with_fake_client() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(model_endpoint="http://localhost:8082/v1", client=client)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert step.action_name == "browser_open_url"
    assert client.requests[0].endpoint_base_url == "http://localhost:8082/v1"


def test_http_transport_failure_reports_request_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self) -> ErrorClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def post(self, url: str, json: dict[str, object]) -> httpx.Response:
            del json
            raise httpx.ConnectError("connection refused: PROMPT_DO_NOT_COPY token=SECRET_TOKEN")

    monkeypatch.setattr(httpx, "Client", ErrorClient)
    planner = _planner(allow_model_calls=True)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    exc = excinfo.value
    diagnostics = exc.diagnostics
    diagnostics_text = str(diagnostics)

    assert exc.error_code == "model_http_request_failed"
    assert diagnostics["exception_type"] == "ConnectError"
    assert diagnostics["endpoint_path"] == "/v1/chat/completions"
    assert diagnostics["model_alias"] == "third_model"
    assert diagnostics["request_payload_metadata"]["message_count"] == 2
    assert diagnostics["request_payload_metadata"]["stream"] is False
    assert "connection refused" in diagnostics["response_text_preview_sanitized"]
    assert "SECRET_TOKEN" not in diagnostics_text
    assert "Traceback" not in diagnostics_text


def test_http_500_reports_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadStatusClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self) -> BadStatusClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def post(self, url: str, json: dict[str, object]) -> httpx.Response:
            del json
            return httpx.Response(
                500,
                text='{"error":"bad model","raw_prompt":"PROMPT_DO_NOT_COPY","token":"SECRET_TOKEN"}',
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "Client", BadStatusClient)
    planner = _planner(allow_model_calls=True)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    exc = excinfo.value
    diagnostics = exc.diagnostics
    diagnostics_text = str(diagnostics)

    assert exc.error_code == "model_http_status_error"
    assert diagnostics["http_status"] == 500
    assert diagnostics["endpoint_path"] == "/v1/chat/completions"
    assert diagnostics["request_payload_metadata"]["max_tokens"] >= 1200
    assert diagnostics["request_payload_metadata"]["stream"] is False
    assert "bad model" in diagnostics["response_text_preview_sanitized"]
    assert "PROMPT_DO_NOT_COPY" not in diagnostics_text
    assert "SECRET_TOKEN" not in diagnostics_text


def test_missing_choices_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingChoicesClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self) -> MissingChoicesClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def post(self, url: str, json: dict[str, object]) -> httpx.Response:
            del json
            return httpx.Response(200, json={"model": "third_model"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "Client", MissingChoicesClient)
    planner = _planner(allow_model_calls=True)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_response_missing_choices"


def test_missing_content_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingContentClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self) -> MissingContentClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def post(self, url: str, json: dict[str, object]) -> httpx.Response:
            del json
            return httpx.Response(
                200,
                json={"choices": [{"finish_reason": "stop", "message": {}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "Client", MissingContentClient)
    planner = _planner(allow_model_calls=True)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_response_missing_content"


def test_no_json_object_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class ArrayContentClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self) -> ArrayContentClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def post(self, url: str, json: dict[str, object]) -> httpx.Response:
            del json
            return httpx.Response(
                200,
                json={"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "Client", ArrayContentClient)
    planner = _planner(allow_model_calls=True)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    diagnostics_text = json.dumps(excinfo.value.diagnostics, ensure_ascii=False)

    assert excinfo.value.error_code == "model_output_no_json_object"
    assert "supersecret" not in diagnostics_text
    assert "Traceback" not in diagnostics_text
