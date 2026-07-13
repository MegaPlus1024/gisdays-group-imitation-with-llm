from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_stepwise_article_benchmark import (
    StepwiseArticleObservation,
)
from src.agent.autonomous_browser_stepwise_article_local_model import (
    StepwiseArticleLocalModelClient,
    StepwiseArticleLocalModelConfig,
    StepwiseArticleLocalModelError,
    build_stepwise_article_prompt,
    parse_stepwise_article_action_response,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_stepwise_article_benchmark_local_model.py"


OBSERVATION = StepwiseArticleObservation(
    scenario_id="article_short_single_fact",
    task="What time does the harbor office open?",
    page_opened=True,
    current_url="https://articles.local/harbor-bulletin",
    article_title="Harbor Bulletin",
    visible_section_id="harbor_hours",
    visible_section_title="Harbor Office Hours",
    visible_text="Harbor Office Hours\nThe harbor office opens at 06:30 each weekday for visitor processing.",
    available_actions=(
        "browser_open_url",
        "browser_read_visible_text",
        "browser_scroll_down",
        "browser_find_text",
        "browser_extract_section",
        "final_answer",
    ),
    sections_total=1,
    sections_read_count=1,
    sections_read_ids=("harbor_hours",),
)


class FakeTransportResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> Any:
        return self._payload


class FakeTransport:
    def __init__(self, responses: list[FakeTransportResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> FakeTransportResponse:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        return self.responses.pop(0)


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("stepwise_article_local_cli", CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt_contains_task_observation_allowed_actions_and_one_action_instruction() -> None:
    messages = build_stepwise_article_prompt(OBSERVATION.task, OBSERVATION)

    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "Return exactly one JSON object only." in system
    assert "Allowed action names exactly: browser_open_url, browser_read_visible_text, browser_scroll_down, browser_find_text, browser_extract_section, final_answer." in system
    assert "Do not use browser_click" in system
    assert "Task: What time does the harbor office open?" in user
    assert "Current URL: https://articles.local/harbor-bulletin" in user
    assert "Visible text:" in user
    assert "The harbor office opens at 06:30" in user


def test_disable_thinking_prepends_prefix_without_changing_prompt_body() -> None:
    regular_messages = build_stepwise_article_prompt(OBSERVATION.task, OBSERVATION)
    prefixed_messages = build_stepwise_article_prompt(
        OBSERVATION.task,
        OBSERVATION,
        disable_thinking=True,
        no_think_prefix="/no_think",
    )

    regular_user = regular_messages[1]["content"]
    prefixed_user = prefixed_messages[1]["content"]

    assert prefixed_user.startswith("/no_think\n")
    assert prefixed_user[len("/no_think\n") :] == regular_user


def test_parser_accepts_plain_json_action() -> None:
    action = parse_stepwise_article_action_response(
        '{"action_name":"browser_find_text","parameters":{"query":"06:30"},"reason":"find the hour"}'
    )

    assert action.action_name == "browser_find_text"
    assert action.parameters == {"query": "06:30"}


def test_parser_accepts_fenced_json_action() -> None:
    action = parse_stepwise_article_action_response(
        '```json\n{"action_name":"final_answer","parameters":{"answer_text":"The harbor office opens at 06:30.","citations":["harbor_hours"],"confidence":"high"}}\n```'
    )

    assert action.action_name == "final_answer"
    assert action.parameters["answer_text"] == "The harbor office opens at 06:30."
    assert action.parameters["citation_ids"] == ["harbor_hours"]
    assert action.parameters["confidence"] == "high"


def test_parser_rejects_browser_click() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response(
            '{"action_name":"browser_click","parameters":{"target_text":"Open"}}'
        )

    assert exc.value.error_code == "disallowed_action_browser_click"


def test_parser_rejects_unknown_action() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response(
            '{"action_name":"browser_search","parameters":{"query":"anything"}}'
        )

    assert exc.value.error_code == "unknown_action"


def test_parser_rejects_full_workflow_json_with_actions_array() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response(
            '{"schema_version":"x","actions":[{"action_name":"browser_open_url","parameters":{"url":"https://articles.local/harbor-bulletin"}}]}'
        )

    assert exc.value.error_code == "full_workflow_json_rejected"


def test_parser_rejects_multiple_actions() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response(
            '[{"action_name":"browser_open_url","parameters":{"url":"https://articles.local/harbor-bulletin"}},{"action_name":"browser_read_visible_text","parameters":{}}]'
        )

    assert exc.value.error_code == "multiple_actions_rejected"


def test_parser_rejects_missing_json_with_specific_code() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response("No JSON here, just prose.")

    assert exc.value.error_code == "no_json_object_found"


def test_parser_rejects_invalid_json_with_specific_code() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response('{"action_name":"browser_read_visible_text"')

    assert exc.value.error_code == "invalid_json"


def test_local_client_uses_injected_fake_transport_and_does_not_perform_real_http() -> None:
    transport = FakeTransport(
        [
            FakeTransportResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"action_name":"browser_read_visible_text","parameters":{},"reason":"read visible text"}'
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }
            )
        ]
    )
    client = StepwiseArticleLocalModelClient(
        config=StepwiseArticleLocalModelConfig(
            model_alias="third_model",
            base_url="http://127.0.0.1:8082/v1",
            allow_model_execution=True,
            response_max_tokens=512,
            temperature=0.25,
        ),
        transport=transport,
    )

    action = client.next_action(OBSERVATION.task, OBSERVATION, memory={})

    assert action.action_name == "browser_read_visible_text"
    assert transport.calls[0]["url"] == "http://127.0.0.1:8082/v1/chat/completions"
    assert transport.calls[0]["json"]["model"] == "third_model"
    assert transport.calls[0]["json"]["max_tokens"] == 512
    assert transport.calls[0]["json"]["temperature"] == 0.25
    assert client.model_execution_attempted is True
    assert client.model_execution_completed is True


def test_config_defaults_include_nonzero_response_max_tokens() -> None:
    config = StepwiseArticleLocalModelConfig(
        model_alias="third_model",
        base_url="http://127.0.0.1:8082/v1",
        allow_model_execution=True,
    )

    assert config.response_max_tokens > 0
    assert config.temperature == 0.0
    assert config.disable_thinking is False
    assert config.no_think_prefix == "/no_think"


def test_disable_thinking_prefix_is_sent_in_user_prompt() -> None:
    transport = FakeTransport(
        [
            FakeTransportResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"action_name":"browser_read_visible_text","parameters":{},"reason":"read visible text"}'
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }
            )
        ]
    )
    client = StepwiseArticleLocalModelClient(
        config=StepwiseArticleLocalModelConfig(
            model_alias="third_model",
            base_url="http://127.0.0.1:8082/v1",
            allow_model_execution=True,
            disable_thinking=True,
            no_think_prefix="/no_think",
        ),
        transport=transport,
    )

    client.next_action(OBSERVATION.task, OBSERVATION, memory={})

    user_message = transport.calls[0]["json"]["messages"][1]["content"]
    assert user_message.startswith("/no_think\n")
    assert "Task: What time does the harbor office open?" in user_message


def test_guarded_cli_refuses_to_run_without_allow_model_execution(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_cli_module()

    exit_code = module.main(
        ["--base-url", "http://127.0.0.1:8082/v1", "--model-alias", "third_model"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["error_code"] == "allow_model_execution_required"
    assert payload["model_execution"] is False
    assert payload["real_browser_execution"] is False
    assert payload["playwright_execution"] is False
    assert payload["browser_opened"] is False
    assert payload["fixture_only"] is True
    assert "--allow-model-execution is required" in payload["error_message"]


def test_guarded_cli_writes_output_json_on_refusal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_cli_module()
    output_path = tmp_path / "refusal.json"

    exit_code = module.main(
        [
            "--base-url",
            "http://127.0.0.1:8082/v1",
            "--model-alias",
            "third_model",
            "--disable-thinking",
            "--response-max-tokens",
            "512",
            "--output-json",
            str(output_path),
        ]
    )

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert output_path.exists()
    assert stdout_payload == file_payload
    assert file_payload["error_code"] == "allow_model_execution_required"
    assert file_payload["model_execution"] is False
    assert file_payload["no_runtime_execution"] is True
    assert file_payload["disable_thinking"] is True
    assert file_payload["response_max_tokens"] == 512
    assert file_payload["no_think_prefix_used"] == "/no_think"


def test_parse_failure_after_fake_transport_sets_truthful_runtime_flags_and_diagnostics() -> None:
    transport = FakeTransport(
        [
            FakeTransportResponse(
                {
                    "id": "resp_stepwise_001",
                    "choices": [
                        {
                            "message": {
                                "content": "Authorization: Bearer supersecret-token browser_click Ticket board"
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }
            )
        ]
    )
    client = StepwiseArticleLocalModelClient(
        config=StepwiseArticleLocalModelConfig(
            model_alias="third_model",
            base_url="http://127.0.0.1:8082/v1",
            allow_model_execution=True,
        ),
        transport=transport,
    )

    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        client.next_action(
            OBSERVATION.task,
            OBSERVATION,
            memory={"trial_index": 2, "step_results": [{"step_index": 1}]},
        )

    diagnostics = exc.value.diagnostics
    assert exc.value.error_code == "model_output_parse_failed"
    assert client.model_execution_attempted is True
    assert client.model_execution_completed is True
    assert diagnostics["scenario_id"] == OBSERVATION.scenario_id
    assert diagnostics["model_alias"] == "third_model"
    assert diagnostics["trial_index"] == 2
    assert diagnostics["step_index"] == 2
    assert diagnostics["parse_error_code"] == "no_json_object_found"
    assert diagnostics["finish_reason"] == "stop"
    assert diagnostics["response_id"] == "resp_stepwise_001"
    assert diagnostics["raw_model_response_length"] > 0
    assert diagnostics["content_length"] == diagnostics["raw_model_response_length"]
    assert diagnostics["reasoning_content_length"] == 0
    assert diagnostics["response_max_tokens"] == 512
    assert diagnostics["temperature"] == 0.0
    assert diagnostics["disable_thinking"] is False
    assert diagnostics["no_think_prefix_used"] is None
    assert "browser_open_url" in diagnostics["allowed_actions"]
    assert "[redacted authorization header]" in diagnostics["raw_model_response_preview"]
    assert "supersecret-token" not in diagnostics["raw_model_response_preview"]


def test_parser_uses_message_content_not_reasoning_content() -> None:
    transport = FakeTransport(
        [
            FakeTransportResponse(
                {
                    "id": "resp_stepwise_003",
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": '{"action_name":"browser_read_visible_text","parameters":{},"reason":"hidden in reasoning"}',
                            },
                            "finish_reason": "length",
                        }
                    ]
                }
            )
        ]
    )
    client = StepwiseArticleLocalModelClient(
        config=StepwiseArticleLocalModelConfig(
            model_alias="third_model",
            base_url="http://127.0.0.1:8082/v1",
            allow_model_execution=True,
            disable_thinking=True,
        ),
        transport=transport,
    )

    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        client.next_action(
            OBSERVATION.task,
            OBSERVATION,
            memory={"trial_index": 1, "step_results": []},
        )

    diagnostics = exc.value.diagnostics
    assert exc.value.error_code == "model_output_parse_failed"
    assert diagnostics["parse_error_code"] == "no_json_object_found"
    assert diagnostics["content_length"] == 0
    assert diagnostics["reasoning_content_length"] > 0
    assert diagnostics["finish_reason"] == "length"
    assert diagnostics["disable_thinking"] is True
    assert diagnostics["no_think_prefix_used"] == "/no_think"


def test_cli_writes_output_json_on_model_parse_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_cli_module()

    class FakeClient:
        model_name = "third_model"

        def __init__(self, *, config) -> None:  # type: ignore[no-untyped-def]
            self._client = StepwiseArticleLocalModelClient(
                config=config,
                transport=FakeTransport(
                    [
                        FakeTransportResponse(
                            {
                                "id": "resp_stepwise_002",
                                "choices": [
                                    {
                                        "message": {
                                            "content": '{"actions":[{"action_name":"browser_open_url","parameters":{"url":"https://articles.local/harbor-bulletin"}}]}'
                                        },
                                        "finish_reason": "stop",
                                    }
                                ]
                            }
                        )
                    ]
                ),
            )

        @property
        def model_execution_attempted(self) -> bool:
            return self._client.model_execution_attempted

        @property
        def model_execution_completed(self) -> bool:
            return self._client.model_execution_completed

        def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
            return self._client.next_action(task, observation, memory)

    monkeypatch.setattr(module, "StepwiseArticleLocalModelClient", FakeClient)
    output_path = tmp_path / "parse_failure.json"

    exit_code = module.main(
        [
            "--base-url",
            "http://127.0.0.1:8082/v1",
            "--model-alias",
            "third_model",
            "--scenario-id",
            "article_short_single_fact",
            "--trials-per-scenario",
            "1",
            "--max-steps",
            "4",
            "--allow-model-execution",
            "--disable-thinking",
            "--response-max-tokens",
            "512",
            "--output-json",
            str(output_path),
        ]
    )

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert output_path.exists()
    assert stdout_payload == file_payload
    assert file_payload["status"] == "failed"
    assert file_payload["error_code"] == "model_output_parse_failed"
    assert file_payload["model_execution"] is True
    assert file_payload["no_runtime_execution"] is False
    assert file_payload["real_browser_execution"] is False
    assert file_payload["playwright_execution"] is False
    assert file_payload["browser_opened"] is False
    assert file_payload["fixture_only"] is True
    assert file_payload["disable_thinking"] is True
    assert file_payload["response_max_tokens"] == 512
    assert file_payload["no_think_prefix_used"] == "/no_think"
    diagnostics = file_payload["diagnostics"]
    assert diagnostics["parse_error_code"] == "full_workflow_json_rejected"
    assert diagnostics["scenario_id"] == "article_short_single_fact"
