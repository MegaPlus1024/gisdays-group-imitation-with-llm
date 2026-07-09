from __future__ import annotations

from pathlib import Path

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
    assert client.requests[0].messages[0]["content"].startswith("/no_think")


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

    assert excinfo.value.error_code == "planner_response_array_not_allowed"


def test_multiple_json_objects_are_rejected() -> None:
    client = FakeChatCompletionClient(
        [ChatCompletionResponse(content='{"step_id":"one"} {"step_id":"two"}', finish_reason="stop")]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "planner_response_parse_failed"


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

    assert excinfo.value.error_code == "planner_response_plan_shape_not_allowed"


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

    assert excinfo.value.error_code in {"secret_like_parameter_value", "secret_like_parameter_key"}


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

    assert excinfo.value.error_code == "planner_response_truncated"


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

    assert excinfo.value.error_code == "endpoint_host_not_allowed"
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
