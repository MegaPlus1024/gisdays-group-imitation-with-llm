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
    repair_enabled: bool = True,
    max_repair_attempts: int = 1,
    no_think: bool | None = None,
    client: FakeChatCompletionClient | None = None,
) -> LocalModelLivePlanner:
    config = LocalModelPlannerConfig(
        kind="local_model",
        model_alias=model_alias,
        model_endpoint=model_endpoint,
        allow_model_calls=allow_model_calls,
        repair_enabled=repair_enabled,
        max_repair_attempts=max_repair_attempts,
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


def test_prompt_reinforces_allowed_actions_and_start_url_guidance() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=False)
    observation = {
        "observation_id": "observation_0002",
        "current_url": None,
        "title": "Office Intranet Home",
        "text_preview": "Office Intranet Home Ticket board Workspace policy Search marker: fixture-backed result for local policy review.",
        "metadata": {
            "scenario_id": "hard_policy_disambiguation",
            "scenario_start_url": "https://docs.local/docs/policy-disambiguation",
            "start_page_visible_anchors": [
                "Office Intranet Home",
                "Workspace policy",
                "Search marker: fixture-backed result for local policy review.",
            ],
        },
    }

    messages = planner.build_messages(observation)
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert system.startswith("/no_think")
    assert "Allowed action names exactly: browser_open_url, browser_click, browser_extract_text, browser_snapshot, done." in system
    assert "Do not use browser_search." in system
    assert "Do not search the web." in system
    assert "Do not invent search actions." in system
    assert "You are already inside a local fixture environment." in system
    assert "Choose only from visible local links/buttons and allowed local fixture actions." in system
    assert 'For browser_click, use parameters {"target_text": "<visible link/button text>"}.' in system
    assert "Do not use link_text, button_text, selector, href, XPath, or CSS selectors for browser_click." in system
    assert "When current_url is null, open the scenario start URL before click, extract, or snapshot actions." in system
    assert "Scenario start URL: https://docs.local/docs/policy-disambiguation. First action must be browser_open_url with that URL." in user
    assert "Do not click before opening." in user
    assert "Start-page visible anchors: Office Intranet Home; Workspace policy; Search marker: fixture-backed result for local policy review." in user
    assert "For the first browser_open_url action, expected_text must be an exact visible substring from the page that will be open after the action." in user
    assert "Do not invent welcome text." in user
    assert 'For this start page, prefer "Office Intranet Home" or "Workspace policy".' in user
    assert "Office Intranet Home" in user
    assert "Workspace policy" in user


def test_prompt_includes_click_destination_anchor_guidance() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=False)
    observation = {
        "observation_id": "observation_0003",
        "current_url": "https://local.intranet/",
        "title": "Office Intranet Home",
        "text_preview": "Office Intranet Home Ticket board Workspace policy Team status Approvals queue Search marker: fixture-backed result for local policy review.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_policy_disambiguation",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }

    messages = planner.build_messages(observation)
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "For browser_click, expected_text must come from the destination page reached by target_text, not the page you are currently reading." in system
    assert "For browser_click, expected_text must be exactly one visible substring, not multiple anchors joined together." in system
    assert "For browser_click, omit expected_url. Runtime resolves the destination URL from target_text and verifies it locally; if you include expected_url anyway, it must match the destination exactly." in system
    assert "Choose the link/button relevant to the scenario goal." in user
    assert 'For hard_policy_disambiguation from the home page, click "Workspace policy", not "Ticket board".' in user
    assert "Avoid for this goal: Ticket board; Team status; Approvals queue." in user
    assert 'For hard_policy_disambiguation, expected_text must be one exact visible substring; choose one of "Workspace Policy", "Allowed activity", or "Search marker: fixture-backed result for workspace policy review."' in user
    assert "Runtime destination URL for Workspace policy: https://local.intranet/docs/policy." in user
    assert "For browser_click, omit expected_url." in user
    assert "Do not choose a link just because it is visible." in user
    assert "Click destination guidance:" in user
    assert "Exact click destinations: Ticket board -> https://local.intranet/tickets; Workspace policy -> https://local.intranet/docs/policy; Team status -> https://local.intranet/team/status; Approvals queue -> https://local.intranet/portal/approvals" in user
    assert "Visible page anchors: Office Intranet Home; Workspace policy; Search marker: fixture-backed result for local policy review." in user
    assert "Visible click targets: Ticket board; Workspace policy; Team status; Approvals queue." in user
    assert "Workspace policy anchors: Workspace Policy; Allowed activity; Disallowed activity" in user
    assert "For browser_click, omit expected_url; runtime verifies the destination URL from target_text." in user
    assert "If you include expected_url for a click anyway, it must exactly match the listed destination URL." in user
    assert "Do not invent URL paths such as /ticket_board." in user
    assert "Workspace Policy" in user
    assert "Allowed activity" in user


def test_prompt_on_workspace_policy_page_includes_completion_and_visible_targets() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=False)
    observation = {
        "observation_id": "observation_0003_policy",
        "current_url": "https://local.intranet/docs/policy",
        "title": "Workspace Policy",
        "text_preview": "Workspace Policy Home Ticket 1 Allowed activity Disallowed activity Search marker: fixture-backed result for workspace policy review.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_policy_disambiguation",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }

    messages = planner.build_messages(observation)
    user = messages[1]["content"]

    assert "Visible page anchors: Workspace Policy; Allowed activity; Disallowed activity; Search marker: fixture-backed result for workspace policy review." in user
    assert "Visible click targets: Home; Ticket 1." in user
    assert "Only click listed visible click targets." in user
    assert "Do not click page titles or headings unless they are listed as click targets." in user
    assert "You are on the relevant policy page." in user
    assert "The scenario goal is satisfied when you have evidence of the live policy source." in user
    assert "Do not click Office Intranet Home." in user
    assert "Do not click Home unless the goal explicitly requires navigation back." in user
    assert "Prefer done if the goal is already satisfied and no more action is required." in user
    assert 'Next valid choices: done; browser_extract_text with expected_text "Allowed activity" or "Search marker: fixture-backed result for workspace policy review."; browser_snapshot with expected_text "Workspace Policy".' in user


def test_prompt_for_hard_ticket_priority_crosscheck_scopes_home_board_and_ticket_page() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=False)

    home_observation = {
        "observation_id": "observation_ticket_home",
        "current_url": None,
        "title": "Office Intranet Home",
        "text_preview": "Office Intranet Home Ticket board Workspace policy Team status Approvals queue Search marker: fixture-backed result for local policy review.",
        "metadata": {
            "fixture_source": True,
            "scenario_id": "hard_ticket_priority_crosscheck",
            "scenario_start_url": "https://local.intranet/",
            "start_page_visible_anchors": [
                "Office Intranet Home",
                "Ticket board",
                "Workspace policy",
            ],
        },
    }
    board_observation = {
        "observation_id": "observation_ticket_board",
        "current_url": "https://local.intranet/tickets",
        "title": "Ticket Board",
        "text_preview": "Ticket Board Home Ticket 1 Open tickets Ticket 1: Quarterly Access Review requires an office-worker status note.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_ticket_priority_crosscheck",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    ticket_observation = {
        "observation_id": "observation_ticket_1",
        "current_url": "https://local.intranet/tickets/1",
        "title": "Ticket 1 - Quarterly Access Review",
        "text_preview": "Ticket 1 - Quarterly Access Review Priority: high. Assigned role: office worker. Quarterly Access Review.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_ticket_priority_crosscheck",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }

    home_user = planner.build_messages(home_observation)[1]["content"]
    board_user = planner.build_messages(board_observation)[1]["content"]
    ticket_user = planner.build_messages(ticket_observation)[1]["content"]

    assert 'For hard_ticket_priority_crosscheck from the home page, click "Ticket board", not "Workspace policy".' in home_user
    assert "Avoid for this goal: Workspace policy; Team status; Approvals queue." in home_user
    assert "Start-page visible anchors: Office Intranet Home; Ticket board; Workspace policy" in home_user
    assert 'For hard_ticket_priority_crosscheck from Ticket board, click "Ticket 1".' in board_user
    assert "Visible click targets: Home; Ticket 1; Team status." in board_user
    assert "Visible page anchors: Ticket 1 - Quarterly Access Review; Quarterly Access Review; Priority: high; Assigned role: office worker" in ticket_user
    assert "You are on the relevant ticket page." in ticket_user
    assert 'Next valid choices: done; browser_extract_text with expected_text "Quarterly Access Review" or "Assigned role: office worker"; browser_snapshot with expected_text "Ticket 1 - Quarterly Access Review".' in ticket_user


def test_prompt_for_hard_approval_policy_match_scopes_home_queue_and_match_page() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=False)

    home_observation = {
        "observation_id": "observation_approval_home",
        "current_url": None,
        "title": "Portal Home",
        "text_preview": "Portal Home Approvals queue Approval status New request Portal fixture for local approval checks only.",
        "metadata": {
            "fixture_source": True,
            "scenario_id": "hard_approval_policy_match",
            "scenario_start_url": "https://local.intranet/portal",
            "start_page_visible_anchors": [
                "Portal Home",
                "Approvals queue",
                "Approval status",
            ],
        },
    }
    queue_observation = {
        "observation_id": "observation_approval_queue",
        "current_url": "https://local.intranet/portal/approvals",
        "title": "Approvals Queue",
        "text_preview": "Approvals Queue Portal home Approval status Pending approval check Approval item APR-42 is waiting for local policy verification. Owner: office worker.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_approval_policy_match",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    match_observation = {
        "observation_id": "observation_approval_match",
        "current_url": "https://local.intranet/portal/approval-match",
        "title": "Approval Policy Match",
        "text_preview": "Approval Policy Match Local-only approval review Request id: APR-51. Policy match: confirmed. Search marker: approval-policy match is the fixture-backed answer.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_approval_policy_match",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }

    home_user = planner.build_messages(home_observation)[1]["content"]
    queue_user = planner.build_messages(queue_observation)[1]["content"]
    match_user = planner.build_messages(match_observation)[1]["content"]

    assert 'For hard_approval_policy_match from the home page, click "Approvals queue", not "Workspace policy".' in home_user
    assert "Avoid for this goal: Workspace policy; Ticket board; Team status." in home_user
    assert "Start-page visible anchors: Portal Home; Approvals queue; Approval status" in home_user
    assert 'For hard_approval_policy_match from Approvals queue, click "Policy match review".' in queue_user
    assert "Do not click Ticket board or Team status from here." in queue_user
    assert "Visible click targets: Portal home; Approval status; Policy match review." in queue_user
    assert "Visible page anchors: Approval Policy Match; Local-only approval review; Request id: APR-51.; Policy match: confirmed." in match_user
    assert "You are on the relevant approval policy match page." in match_user
    assert 'Next valid choices: done; browser_extract_text with expected_text "Policy match: confirmed." or "Search marker: approval-policy match is the fixture-backed answer."; browser_snapshot with expected_text "Approval Policy Match".' in match_user


def test_valid_next_action_returns_step() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet","expected_url":"https://local.intranet/"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client, repair_enabled=False, max_repair_attempts=0)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert step.step_id == "open_home"
    assert step.action_name == "browser_open_url"
    assert step.parameters["url"] == "https://local.intranet/"
    assert step.expected_text == "Office Intranet"
    assert step.expected_url == "https://local.intranet/"
    assert step.done is False
    assert planner.model_execution_attempted is True
    assert planner.model_execution_completed is True
    assert client.requests[0].model == "third_model"
    assert client.requests[0].stream is False
    assert client.requests[0].max_tokens >= 1200
    assert client.requests[0].endpoint_base_url == "http://127.0.0.1:8082/v1/chat/completions"
    assert client.requests[0].messages[0]["content"].startswith("/no_think")
    assert planner.to_summary()["request_payload_metadata"]["stream"] is False
    assert planner.to_summary()["request_payload_metadata"]["max_tokens"] >= 1200
    assert planner.to_summary()["model_endpoint"] == "http://127.0.0.1:8082/v1/chat/completions"


@pytest.mark.parametrize(
    "click_key",
    [
        "target_text",
        "text",
        "link_text",
        "button_text",
    ],
)
def test_browser_click_aliases_normalize_to_target_text(click_key: str) -> None:
    content = json.dumps(
        {
            "step_id": "click_policy",
            "action_name": "browser_click",
            "parameters": {click_key: "Workspace policy"},
            "expected_text": "Policy review",
            "expected_url": "https://docs.local/docs/policy",
        },
        ensure_ascii=False,
    )
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content=content,
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client, repair_enabled=False, max_repair_attempts=0)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert step.action_name == "browser_click"
    assert step.parameters == {"target_text": "Workspace policy"}
    assert "target_text" in step.parameters
    assert "link_text" not in step.parameters
    assert "button_text" not in step.parameters
    assert "text" not in step.parameters


def test_browser_click_without_expected_url_is_allowed() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"click_policy","action_name":"browser_click","parameters":{"target_text":"Workspace policy"},"expected_text":"Workspace Policy"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client, repair_enabled=False, max_repair_attempts=0)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert step.action_name == "browser_click"
    assert step.parameters == {"target_text": "Workspace policy"}
    assert step.expected_text == "Workspace Policy"
    assert step.expected_url is None


def test_browser_click_without_visible_target_is_rejected() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"click_policy","action_name":"browser_click","parameters":{"selector":"#policy"},"expected_text":"Policy review"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    diagnostics = excinfo.value.diagnostics
    diagnostics_text = json.dumps(diagnostics, ensure_ascii=False)

    assert excinfo.value.error_code == "missing_required_parameter"
    assert diagnostics["action_name"] == "browser_click"
    assert diagnostics["parameter_key"] == "target_text"
    assert "selector" not in diagnostics_text
    assert "Traceback" not in diagnostics_text


@pytest.mark.parametrize(
    "expected_url",
    [
        "https://example.com/",
        "http<absolute_path>",
    ],
)
def test_non_local_expected_url_is_rejected(expected_url: str) -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content=(
                    '{"step_id":"open_external","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"'
                    f'expected_text":"Office Intranet","expected_url":"{expected_url}"}}'
                ),
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client, repair_enabled=False, max_repair_attempts=0)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    diagnostics = excinfo.value.diagnostics
    diagnostics_text = json.dumps(diagnostics, ensure_ascii=False)

    assert excinfo.value.error_code == "model_output_invalid_expected_url"
    assert diagnostics["expected_url_path"] == "expected_url"
    assert "Traceback" not in diagnostics_text


@pytest.mark.parametrize(
    "expected_text",
    [
        "Workspace Policy; Allowed activity; Search marker: fixture-backed result for workspace policy review.",
        "Workspace Policy\nAllowed activity\nSearch marker: fixture-backed result for workspace policy review.",
    ],
)
def test_non_atomic_expected_text_is_rejected(expected_text: str) -> None:
    content = json.dumps(
        {
            "step_id": "click_policy",
            "action_name": "browser_click",
            "parameters": {"target_text": "Workspace policy"},
            "expected_text": expected_text,
            "expected_url": "https://local.intranet/docs/policy",
        },
        ensure_ascii=False,
    )
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content=content,
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client, repair_enabled=False, max_repair_attempts=0)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    diagnostics = excinfo.value.diagnostics
    diagnostics_text = json.dumps(diagnostics, ensure_ascii=False)

    assert excinfo.value.error_code == "model_output_expected_text_not_atomic"
    assert diagnostics["expected_text_path"] == "expected_text"
    assert "missing expected_text" not in str(excinfo.value).lower()
    assert "Traceback" not in diagnostics_text


def test_repair_prompt_for_hard_policy_disambiguation_contains_exact_constraints() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=True)
    observation = {
        "observation_id": "observation_0004",
        "current_url": "https://local.intranet/",
        "title": "Office Intranet Home",
        "text_preview": "Office Intranet Home Ticket board Workspace policy Team status Approvals queue Search marker: fixture-backed result for local policy review.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_policy_disambiguation",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    invalid_action = {
        "step_id": "click_policy",
        "action_name": "browser_click",
        "parameters": {"target_text": "Ticket board"},
        "expected_text": "Ticket Board",
        "expected_url": "https://local.intranet/ticket_board",
    }

    messages = planner._build_repair_messages(
        observation_payload=observation,
        invalid_action=invalid_action,
        error_code="model_output_expected_url_not_matching_destination",
        error_message="Model response expected_url must match the click destination exactly.",
        error_diagnostics={
            "expected_url": "https://local.intranet/ticket_board",
            "resolved_destination_url": "https://local.intranet/tickets",
        },
    )

    system = messages[0]["content"]
    user = messages[1]["content"]

    assert system.startswith("/no_think")
    assert "Return exactly one JSON object only." in system or "Return exactly one JSON object." in user
    assert "Keep action_name browser_click." in user
    assert 'Use parameters {"target_text": "<visible link/button text>"}. ' not in user
    assert 'Use parameters {"target_text": "<visible link/button text>"}.' in user
    assert 'For hard_policy_disambiguation from the home page, click "Workspace policy", not "Ticket board".' in user
    assert "Avoid for this goal: Ticket board; Team status; Approvals queue." in user
    assert "Use destination-page anchors only." in user
    assert 'For hard_policy_disambiguation, expected_text must be one exact visible substring; choose one of "Workspace Policy", "Allowed activity", or "Search marker: fixture-backed result for workspace policy review."' in user
    assert "Runtime destination URL for Workspace policy: https://local.intranet/docs/policy." in user
    assert "For browser_click, omit expected_url." in user
    assert "Do not use http<absolute_path>, https<absolute_path>, or <absolute_path>." in user
    assert "Do not use semicolons." in user
    assert "Do not use multiple expected_text anchors." in user
    assert "Do not use start-page/home-page text." in user
    assert '{"step_id": "step_001_repair", "action_name": "browser_click", "parameters": {"target_text": "Workspace policy"}, "expected_text": "Workspace Policy"}' in user
    assert "Do not output expected_url." in user
    assert "Do not output http<absolute_path>." in user
    assert "No prose, no markdown." in user
    assert "Rejection diagnostics:" in user
    assert "model_output_expected_url_not_matching_destination" in user
    assert "Current page anchors: Office Intranet Home; Workspace policy; Search marker: fixture-backed result for local policy review." in user
    assert "Current page visible click targets: Ticket board; Workspace policy; Team status; Approvals queue." in user


def test_repair_prompt_for_invisible_click_targets_is_page_state_aware() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=True)
    observation = {
        "observation_id": "observation_0005",
        "current_url": "https://local.intranet/docs/policy",
        "title": "Workspace Policy",
        "text_preview": "Workspace Policy Home Ticket 1 Allowed activity Disallowed activity Search marker: fixture-backed result for workspace policy review.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_policy_disambiguation",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    invalid_action = {
        "step_id": "click_home",
        "action_name": "browser_click",
        "parameters": {"target_text": "Office Intranet Home"},
        "expected_text": "Welcome to the Office Site",
    }

    messages = planner._build_repair_messages(
        observation_payload=observation,
        invalid_action=invalid_action,
        error_code="model_output_click_target_not_visible",
        error_message="Model response click target is not visible on the current page.",
        error_diagnostics={
            "target_text": "Office Intranet Home",
            "current_url": "https://local.intranet/docs/policy",
            "visible_click_targets": ["Home", "Ticket 1"],
        },
    )

    user = messages[1]["content"]

    assert "The previous target_text was not visible or clickable on the current page." in user
    assert "Current page visible click targets: Home; Ticket 1." in user
    assert "Current page anchors: Workspace Policy; Allowed activity; Disallowed activity; Search marker: fixture-backed result for workspace policy review." in user
    assert "You are on the relevant policy page." in user
    assert "Do not click Office Intranet Home." in user
    assert "Do not click Home unless the goal explicitly requires navigation back." in user
    assert "Prefer done if the goal is already satisfied and no more action is required." in user
    assert 'Use browser_extract_text with expected_text "Allowed activity" or "Search marker: fixture-backed result for workspace policy review." to collect evidence.' in user
    assert 'Use browser_snapshot with expected_text "Workspace Policy" if you need a compact page capture.' in user


def test_repair_prompt_for_hard_ticket_priority_crosscheck_is_page_state_aware() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=True)
    observation = {
        "observation_id": "observation_ticket_repair",
        "current_url": "https://local.intranet/",
        "title": "Office Intranet Home",
        "text_preview": "Office Intranet Home Ticket board Workspace policy Team status Approvals queue Search marker: fixture-backed result for local policy review.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_ticket_priority_crosscheck",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    invalid_action = {
        "step_id": "click_policy",
        "action_name": "browser_click",
        "parameters": {"target_text": "Workspace policy"},
        "expected_text": "Workspace Policy",
        "expected_url": "https://local.intranet/docs/policy",
    }

    messages = planner._build_repair_messages(
        observation_payload=observation,
        invalid_action=invalid_action,
        error_code="model_output_expected_url_not_matching_destination",
        error_message="Model response expected_url must match the click destination exactly.",
        error_diagnostics={
            "target_text": "Workspace policy",
            "current_url": "https://local.intranet/",
            "visible_click_targets": ["Ticket board", "Workspace policy"],
        },
    )

    user = messages[1]["content"]

    assert 'For hard_ticket_priority_crosscheck from the home page, click "Ticket board", not "Workspace policy".' in user
    assert "Runtime destination URL for Ticket 1: https://local.intranet/tickets/1." in user
    assert "Current page visible click targets: Ticket board; Workspace policy; Team status; Approvals queue." in user
    assert '{"step_id": "step_001_repair", "action_name": "browser_click", "parameters": {"target_text": "Ticket board"}, "expected_text": "Ticket Board"}' in user


def test_repair_prompt_for_hard_approval_policy_match_is_page_state_aware() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=True)
    observation = {
        "observation_id": "observation_approval_repair",
        "current_url": "https://local.intranet/portal/approvals",
        "title": "Approvals Queue",
        "text_preview": "Approvals Queue Portal home Approval status Pending approval check Approval item APR-42 is waiting for local policy verification. Owner: office worker.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_approval_policy_match",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    invalid_action = {
        "step_id": "click_policy",
        "action_name": "browser_click",
        "parameters": {"target_text": "Workspace policy"},
        "expected_text": "Workspace Policy",
        "expected_url": "https://local.intranet/docs/policy",
    }

    messages = planner._build_repair_messages(
        observation_payload=observation,
        invalid_action=invalid_action,
        error_code="model_output_expected_url_not_matching_destination",
        error_message="Model response expected_url must match the click destination exactly.",
        error_diagnostics={
            "target_text": "Workspace policy",
            "current_url": "https://local.intranet/portal/approvals",
            "visible_click_targets": ["Portal home", "Approval status", "Policy match review"],
        },
    )

    user = messages[1]["content"]

    assert "You are on the relevant approvals queue page." in user
    assert 'The next goal-relevant click is "Policy match review".' in user
    assert 'Use browser_click with expected_text "Approval Policy Match" if you need to open the approval evidence page.' in user
    assert 'Use browser_extract_text with expected_text "Approval item APR-42 is waiting for local policy verification." or "Owner: office worker." to collect queue evidence.' in user
    assert 'Use browser_snapshot with expected_text "Approvals Queue" if you need a compact page capture.' in user


def test_repair_prompt_for_irrelevant_approval_click_routes_toward_goal_relevant_target() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=True)
    observation = {
        "observation_id": "observation_approval_repair",
        "current_url": "https://local.intranet/",
        "title": "Office Intranet Home",
        "text_preview": "Office Intranet Home Ticket board Workspace policy Team status Approvals queue Search marker: fixture-backed result for local policy review.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_approval_policy_match",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    invalid_action = {
        "step_id": "click_policy",
        "action_name": "browser_click",
        "parameters": {"target_text": "Workspace policy"},
        "expected_text": "Workspace Policy",
        "expected_url": "https://local.intranet/docs/policy",
    }

    messages = planner._build_repair_messages(
        observation_payload=observation,
        invalid_action=invalid_action,
        error_code="model_output_irrelevant_click_target",
        error_message="Model response click target is visible but irrelevant to the current scenario goal.",
        error_diagnostics={
            "scenario_id": "hard_approval_policy_match",
            "current_url": "https://local.intranet/",
            "target_text": "Workspace policy",
            "allowed_relevant_click_targets": ["Approvals queue"],
            "rejected_reason": "irrelevant_to_scenario_goal",
        },
    )

    user = messages[1]["content"]

    assert "The previous target was visible but irrelevant to this scenario." in user
    assert 'For hard_approval_policy_match from the home page, click "Approvals queue".' in user
    assert 'Use browser_click with expected_text "Approvals Queue" if you need to open the approvals queue page.' in user
    assert "Avoid for this goal: Workspace policy; Ticket board; Team status." in user
    assert "No prose, one JSON object." in user


def test_repair_prompt_for_irrelevant_approval_click_on_queue_page_routes_to_policy_match_review() -> None:
    planner = _planner(model_alias="third_model", allow_model_calls=True)
    observation = {
        "observation_id": "observation_approval_queue_repair",
        "current_url": "https://local.intranet/portal/approvals",
        "title": "Approvals Queue",
        "text_preview": "Approvals Queue Portal home Approval status Pending approval check Approval item APR-42 is waiting for local policy verification. Owner: office worker.",
        "metadata": {
            "fixture_source": True,
            "page_opened": True,
            "scenario_id": "hard_approval_policy_match",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
        },
    }
    invalid_action = {
        "step_id": "click_policy",
        "action_name": "browser_click",
        "parameters": {"target_text": "Workspace policy"},
        "expected_text": "Workspace Policy",
        "expected_url": "https://local.intranet/docs/policy",
    }

    messages = planner._build_repair_messages(
        observation_payload=observation,
        invalid_action=invalid_action,
        error_code="model_output_irrelevant_click_target",
        error_message="Model response click target is visible but irrelevant to the current scenario goal.",
        error_diagnostics={
            "scenario_id": "hard_approval_policy_match",
            "current_url": "https://local.intranet/portal/approvals",
            "target_text": "Workspace policy",
            "allowed_relevant_click_targets": ["Policy match review"],
            "rejected_reason": "irrelevant_to_scenario_goal",
        },
    )

    user = messages[1]["content"]

    assert "The previous target was visible but irrelevant to this scenario." in user
    assert 'For hard_approval_policy_match from Approvals queue, click "Policy match review".' in user
    assert 'Use browser_click with expected_text "Approval Policy Match" if you need the approval evidence page.' in user
    assert "Avoid for this goal: Workspace policy; Ticket board; Team status." in user
    assert "No prose, one JSON object." in user


def test_repair_success_returns_repaired_step_and_tracks_attempts() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"click_policy","action_name":"browser_click","parameters":{"target_text":"Workspace policy"},"expected_text":"Workspace Policy; Allowed activity; Search marker: fixture-backed result for workspace policy review.","expected_url":"https://local.intranet/docs/policy"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"step_001_repair","action_name":"browser_click","parameters":{"target_text":"Workspace policy"},"expected_text":"Workspace Policy"}',
                finish_reason="stop",
            ),
        ]
    )
    planner = _planner(client=client)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert step.step_id == "step_001_repair"
    assert step.action_name == "browser_click"
    assert step.parameters == {"target_text": "Workspace policy"}
    assert step.expected_text == "Workspace Policy"
    assert step.expected_url is None
    assert planner.repair_attempts == 1
    assert planner.repair_attempts_succeeded == 1
    assert planner.repair_attempts_failed == 0
    assert planner.original_error_code == "model_output_expected_text_not_atomic"
    assert planner.last_error_code is None
    assert len(client.requests) == 2
    repair_user = client.requests[1].messages[1]["content"]
    assert "Omit expected_url for browser_click." in repair_user
    assert "Exact error_code: model_output_expected_text_not_atomic" in repair_user


def test_repair_can_be_disabled_with_zero_attempts() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"click_policy","action_name":"browser_click","parameters":{"target_text":"Workspace policy"},"expected_text":"Workspace Policy; Allowed activity; Search marker: fixture-backed result for workspace policy review.","expected_url":"https://local.intranet/docs/policy"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client, repair_enabled=False, max_repair_attempts=0)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_output_expected_text_not_atomic"
    assert planner.repair_attempts == 0
    assert planner.repair_attempts_succeeded == 0
    assert planner.repair_attempts_failed == 0
    assert len(client.requests) == 1


def test_non_repairable_http_error_does_not_attempt_repair() -> None:
    class BrokenClient:
        def complete(self, request):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("boom", request=httpx.Request("POST", request.endpoint_base_url))

    planner = _planner(client=BrokenClient())

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "planner_request_failed"
    assert planner.repair_attempts == 0
    assert planner.repair_attempts_succeeded == 0
    assert planner.repair_attempts_failed == 0


@pytest.mark.parametrize(
    "model_endpoint",
    [
        "http://127.0.0.1:8082",
        "http://127.0.0.1:8082/v1",
        "http://127.0.0.1:8082/v1/",
        "http://127.0.0.1:8082/v1/chat/completions",
        "http://127.0.0.1:8082/v1/chat/completions/",
    ],
)
def test_endpoint_normalization_accepts_base_and_full_chat_completions_url(model_endpoint: str) -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(model_endpoint=model_endpoint, client=client)

    step = planner.next_step(OBSERVATION)

    assert step is not None
    assert client.requests[0].endpoint_base_url == "http://127.0.0.1:8082/v1/chat/completions"
    assert planner.to_summary()["model_endpoint"] == "http://127.0.0.1:8082/v1/chat/completions"


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
    assert planner.repair_attempts == 0


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
    assert client.requests[0].endpoint_base_url == "http://localhost:8082/v1/chat/completions"


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


def test_unsupported_action_is_rejected_before_validation() -> None:
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"search_docs","action_name":"browser_search","parameters":{"query":"shared document policy"},"expected_text":"check shared document policy"}',
                finish_reason="stop",
            )
        ]
    )
    planner = _planner(client=client)

    with pytest.raises(LocalModelLivePlannerError) as excinfo:
        planner.next_step(OBSERVATION)

    assert excinfo.value.error_code == "model_output_unsupported_action"
    assert client.requests[0].endpoint_base_url == "http://127.0.0.1:8082/v1/chat/completions"
