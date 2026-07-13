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

    assert exc.value.error_code == "browser_click_not_allowed"


def test_parser_rejects_unknown_action() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response(
            '{"action_name":"browser_search","parameters":{"query":"anything"}}'
        )

    assert exc.value.error_code == "unknown_action_name"


def test_parser_rejects_full_workflow_json_with_actions_array() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response(
            '{"schema_version":"x","actions":[{"action_name":"browser_open_url","parameters":{"url":"https://articles.local/harbor-bulletin"}}]}'
        )

    assert exc.value.error_code == "workflow_json_not_allowed"


def test_parser_rejects_multiple_actions() -> None:
    with pytest.raises(StepwiseArticleLocalModelError) as exc:
        parse_stepwise_article_action_response(
            '[{"action_name":"browser_open_url","parameters":{"url":"https://articles.local/harbor-bulletin"}},{"action_name":"browser_read_visible_text","parameters":{}}]'
        )

    assert exc.value.error_code == "multiple_actions_not_allowed"


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
        ),
        transport=transport,
    )

    action = client.next_action(OBSERVATION.task, OBSERVATION, memory={})

    assert action.action_name == "browser_read_visible_text"
    assert transport.calls[0]["url"] == "http://127.0.0.1:8082/v1/chat/completions"
    assert transport.calls[0]["json"]["model"] == "third_model"
    assert client.model_execution_attempted is True
    assert client.model_execution_completed is True


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
