from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import src.agent.autonomous_browser_live_model_planner as live_model_planner
from src.agent.autonomous_browser_live_loop import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_live_loop_config,
    run_autonomous_browser_live_loop,
)
from src.agent.autonomous_browser_live_model_planner import ChatCompletionResponse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_live_loop_offline.example.json"
LOCAL_MODEL_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_live_loop_local_model.example.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_live_loop.py"


class FakeChatCompletionClient:
    def __init__(self, responses: list[ChatCompletionResponse]) -> None:
        self.responses = list(responses)
        self.requests = []

    def complete(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected model request")
        return self.responses.pop(0)


def _load_example_config() -> dict[str, Any]:
    return json.loads(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"))


def _write_config(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "browser_live_loop_config.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_local_model_config() -> dict[str, Any]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "scenario_id": "browser_live_loop_local_model_policy_review_v1",
        "loop_backend": "offline_fixture",
        "output_dir": "artifacts/autonomous_runtime_summaries/browser_live_loop_local_model_tests",
        "no_runtime_execution": True,
        "max_steps": 4,
        "max_repeated_action_count": 2,
        "browser_session": {
            "session_id": "browser_live_loop_local_model_session_v1",
            "agent_id": "browser_live_loop_agent",
            "workspace_id": "browser_live_loop_workspace",
            "environment_id": "browser_live_loop_environment",
            "allowed_domains": [
                "local.intranet",
                "local-intranet.test",
                "docs.local",
                "portal.local",
            ],
            "start_url": "https://local.intranet/",
            "fixture_manifest_path": "tests/fixtures/local_intranet/office_site_v1/site_manifest.json",
            "metadata": {
                "fixture_only": True,
            },
        },
        "planner_backend": {
            "kind": "local_model",
            "planner_id": "browser_live_loop_local_model_planner_test",
            "model_alias": "third_model",
            "model_endpoint": "http://127.0.0.1:8082/v1",
            "allow_model_calls": False,
            "allowed_model_aliases": ["first_model", "second_model", "third_model"],
            "temperature": 0.0,
            "max_tokens": 256,
            "timeout_seconds": 120.0,
        },
        "limitations": [
            "fixture-backed local-model live loop only",
        ],
    }


def _load_local_model_no_page_config() -> dict[str, Any]:
    config = _load_local_model_config()
    config["scenario_id"] = "browser_live_loop_local_model_no_page_v1"
    config["browser_session"]["start_url"] = None
    config["browser_session"]["metadata"] = {
        "fixture_only": True,
        "browser_opened": False,
    }
    return config


def test_example_config_loads_with_relative_paths() -> None:
    config = load_autonomous_browser_live_loop_config(EXAMPLE_CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.scenario_id == "browser_live_loop_offline_policy_review_v1"
    assert config.loop_backend == "offline_fixture"
    assert config.no_runtime_execution is True
    assert config.max_steps == 8
    assert config.max_repeated_action_count == 2
    assert config.output_dir == "artifacts/autonomous_runtime_summaries/browser_live_loop_offline"
    assert config.browser_session.fixture_manifest_path == "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
    assert config.planner_backend.kind == "scripted"


def test_local_model_example_config_loads_with_relative_paths() -> None:
    config = load_autonomous_browser_live_loop_config(LOCAL_MODEL_CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.scenario_id == "browser_live_loop_local_model_policy_review_v1"
    assert config.loop_backend == "offline_fixture"
    assert config.no_runtime_execution is True
    assert config.max_steps == 4
    assert config.planner_backend.kind == "local_model"
    assert config.planner_backend.model_alias == "third_model"
    assert config.planner_backend.model_endpoint == "http://127.0.0.1:8082/v1"
    assert config.planner_backend.allow_model_calls is False
    assert config.planner_backend.allowed_model_aliases == ("first_model", "second_model", "third_model")


def test_offline_live_loop_succeeds_with_scripted_backend() -> None:
    summary = run_autonomous_browser_live_loop(EXAMPLE_CONFIG_PATH, repo_root=PROJECT_ROOT)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["scenario_id"] == "browser_live_loop_offline_policy_review_v1"
    assert summary["loop_backend"] == "offline_fixture"
    assert summary["planner_backend"]["kind"] == "scripted"
    assert summary["max_steps"] == 8
    assert summary["steps_attempted"] == 4
    assert summary["actions_attempted"] == 3
    assert summary["actions_succeeded"] == 3
    assert summary["actions_failed"] == 0
    assert summary["expected_results_passed"] == 3
    assert summary["expected_results_failed"] == 0
    assert summary["observations_total"] == 4
    assert summary["stop_reason"] == "planner_signaled_done"
    assert summary["error_code"] is None
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["output_dir"] == "artifacts/autonomous_runtime_summaries/browser_live_loop_offline"
    assert summary["trace_path"] == "artifacts/autonomous_runtime_summaries/browser_live_loop_offline/autonomous_browser_live_loop_trace.json"
    assert [entry["validation_status"] for entry in summary["runtime_trace"]] == ["accepted", "accepted", "accepted", "skipped"]
    assert summary["runtime_trace"][3]["planner_action"]["done"] is True
    assert str(PROJECT_ROOT) not in encoded
    assert "C:\\" not in encoded


def test_max_steps_reached_is_reported() -> None:
    config = _load_example_config()
    config["max_steps"] = 2
    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "max_steps_reached"
    assert summary["stop_reason"] == "max_steps_reached"
    assert summary["steps_attempted"] == 2
    assert summary["actions_attempted"] == 2
    assert summary["no_runtime_execution"] is True


def test_unsupported_action_is_rejected() -> None:
    config = _load_example_config()
    config["planner_backend"]["scripted_steps"][0]["action_name"] = "browser_not_real"
    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "unknown_browser_action"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["steps_attempted"] == 0
    assert summary["actions_attempted"] == 0
    assert summary["no_runtime_execution"] is True


def test_external_url_is_rejected() -> None:
    config = _load_example_config()
    config["planner_backend"]["scripted_steps"][0]["parameters"]["url"] = "https://example.com/"
    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "external_url_not_allowed"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["steps_attempted"] == 0
    assert summary["actions_attempted"] == 0


def test_missing_expected_text_is_rejected() -> None:
    config = _load_example_config()
    del config["planner_backend"]["scripted_steps"][0]["expected_text"]
    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "missing_expected_text"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["steps_attempted"] == 1
    assert summary["actions_attempted"] == 0


def test_repeated_action_guard_rejects_repeated_signatures() -> None:
    config = _load_example_config()
    config["planner_backend"]["scripted_steps"] = [
        {
            "step_id": "open_home_1",
            "action_name": "browser_open_url",
            "parameters": {"url": "https://local.intranet/"},
            "expected_text": "Office Intranet",
        },
        {
            "step_id": "open_home_2",
            "action_name": "browser_open_url",
            "parameters": {"url": "https://local.intranet/"},
            "expected_text": "Office Intranet",
        },
        {
            "step_id": "open_home_3",
            "action_name": "browser_open_url",
            "parameters": {"url": "https://local.intranet/"},
            "expected_text": "Office Intranet",
        },
        {
            "step_id": "done",
            "action_name": "done",
            "parameters": {},
            "expected_text": "",
            "done": True,
        },
    ]
    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "repeated_planner_action_limit_reached"
    assert summary["stop_reason"] == "repeated_action_guard_triggered"
    assert summary["steps_attempted"] == 3
    assert summary["actions_attempted"] == 2


def test_cli_success_exits_zero_and_prints_compact_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(EXAMPLE_CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")


def test_cli_rejects_invalid_config_with_nonzero_exit(tmp_path: Path) -> None:
    config = _load_example_config()
    config["no_runtime_execution"] = False
    config_path = _write_config(tmp_path, config)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(config_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode != 0
    assert payload["status"] == "failed"
    assert payload["error_code"] == "config_validation_failed"
    assert payload["no_runtime_execution"] is True


def test_local_model_backend_refuses_without_allow_model_calls() -> None:
    summary = run_autonomous_browser_live_loop(_load_local_model_config(), repo_root=PROJECT_ROOT)

    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_model_calls_required"
    assert summary["stop_reason"] == "planner_backend_refused"
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["no_runtime_execution"] is True


@pytest.mark.parametrize(
    "action_name",
    [
        "browser_click",
        "browser_extract_text",
        "browser_snapshot",
    ],
)
def test_local_model_backend_rejects_first_action_without_open_page(action_name: str) -> None:
    config = _load_local_model_no_page_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content=(
                    '{"step_id":"first_step","action_name":"'
                    f'{action_name}'
                    '","parameters":'
                    + (
                        '{"target_text":"Workspace policy"}'
                        if action_name == "browser_click"
                        else '{"query":"shared document policy"}'
                    )
                    + ',"expected_text":"Open the page first"}'
                ),
                finish_reason="stop",
            )
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "live_action_requires_open_page"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 0
    assert summary["actions_attempted"] == 0
    assert summary["actions_succeeded"] == 0
    assert summary["actions_failed"] == 0
    assert summary["runtime_trace"][0]["fixture_execution_status"] == "skipped"
    assert summary["runtime_trace"][0]["validation_status"] == "rejected"
    assert summary["runtime_trace"][0]["error_code"] == "live_action_requires_open_page"
    assert summary["runtime_trace"][0]["step_index"] == 1
    assert client.requests[0].endpoint_base_url == "http://127.0.0.1:8082/v1/chat/completions"


def test_local_model_backend_rejects_first_click_with_start_url_before_open_page() -> None:
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content=(
                    '{"step_id":"click_policy","action_name":"browser_click","parameters":{"link_text":"Workspace policy"},'
                    '"expected_text":"Shared Document Policy Review","metadata":{'
                    '"fixture_path_relative":"policy.html","fixture_route":"/policy","fixture_site_id":"office_site_v1"}}'
                ),
                finish_reason="stop",
            )
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "live_action_requires_open_page"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 0
    assert summary["actions_attempted"] == 0
    assert summary["actions_succeeded"] == 0
    assert summary["actions_failed"] == 0
    assert summary["runtime_trace"][0]["fixture_execution_status"] == "skipped"
    assert summary["runtime_trace"][0]["validation_status"] == "rejected"
    assert summary["runtime_trace"][0]["error_code"] == "live_action_requires_open_page"
    assert summary["runtime_trace"][0]["step_index"] == 1
    assert client.requests[0].endpoint_base_url == "http://127.0.0.1:8082/v1/chat/completions"
    assert "Scenario start URL: https://local.intranet/." in client.requests[0].messages[1]["content"]


def test_local_model_backend_accepts_first_open_url_without_start_page() -> None:
    config = _load_local_model_no_page_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"done","action_name":"done","parameters":{},"expected_text":"","done":true}',
                finish_reason="stop",
            ),
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["stop_reason"] == "planner_signaled_done"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 2
    assert summary["actions_attempted"] == 1
    assert summary["actions_succeeded"] == 1
    assert summary["actions_failed"] == 0
    assert summary["expected_results_passed"] == 1
    assert [entry["validation_status"] for entry in summary["runtime_trace"]] == ["accepted", "skipped"]
    assert client.requests[0].messages[1]["content"].find("Scenario start URL:") == -1


def test_local_model_backend_accepts_first_open_url_with_start_page_anchor_text() -> None:
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"done","action_name":"done","parameters":{},"expected_text":"","done":true}',
                finish_reason="stop",
            ),
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["stop_reason"] == "planner_signaled_done"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 2
    assert summary["actions_attempted"] == 1
    assert summary["actions_succeeded"] == 1
    assert summary["actions_failed"] == 0
    assert summary["expected_results_passed"] == 1
    assert [entry["validation_status"] for entry in summary["runtime_trace"]] == ["accepted", "skipped"]


def test_local_model_backend_accepts_click_with_destination_anchor_text() -> None:
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"click_policy","action_name":"browser_click","parameters":{"target_text":"Workspace policy"},"expected_text":"Workspace Policy","expected_url":"https://local.intranet/docs/policy"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"done","action_name":"done","parameters":{},"expected_text":"","done":true}',
                finish_reason="stop",
            ),
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["stop_reason"] == "planner_signaled_done"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 3
    assert summary["actions_attempted"] == 2
    assert summary["actions_succeeded"] == 2
    assert summary["actions_failed"] == 0
    assert summary["expected_results_passed"] == 2
    assert [entry["validation_status"] for entry in summary["runtime_trace"]] == ["accepted", "accepted", "skipped"]
    assert summary["runtime_trace"][1]["expected_result"]["passed"] is True


def test_local_model_backend_rejects_click_with_current_page_expected_text() -> None:
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"click_policy","action_name":"browser_click","parameters":{"target_text":"Workspace policy"},"expected_text":"Review ticket updates, check shared document policy, and leave concise local notes.","expected_url":"https://local.intranet/docs/policy"}',
                finish_reason="stop",
            ),
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "model_output_expected_text_not_visible"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 2
    assert summary["actions_attempted"] == 1
    assert summary["actions_succeeded"] == 1
    assert summary["actions_failed"] == 0
    assert summary["runtime_trace"][0]["validation_status"] == "accepted"
    assert summary["runtime_trace"][1]["validation_status"] == "accepted"
    assert summary["runtime_trace"][1]["fixture_execution_status"] == "skipped"
    assert summary["runtime_trace"][1]["error_code"] == "model_output_expected_text_not_visible"
    assert summary["runtime_trace"][1]["expected_result"]["reason"] == "model_output_expected_text_not_visible"
    assert summary["runtime_trace"][1]["expected_result"]["metadata"]["target_text"] == "Workspace policy"


def test_local_model_backend_rejects_invented_open_url_expected_text() -> None:
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Welcome to the local intranet","expected_url":"https://local.intranet/"}',
                finish_reason="stop",
            )
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "model_output_expected_text_not_visible"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 1
    assert summary["actions_attempted"] == 0
    assert summary["actions_succeeded"] == 0
    assert summary["actions_failed"] == 0
    assert summary["runtime_trace"][0]["fixture_execution_status"] == "skipped"
    assert summary["runtime_trace"][0]["validation_status"] == "accepted"
    assert summary["runtime_trace"][0]["error_code"] == "model_output_expected_text_not_visible"
    assert summary["runtime_trace"][0]["expected_result"]["reason"] == "model_output_expected_text_not_visible"
    assert client.requests[0].endpoint_base_url == "http://127.0.0.1:8082/v1/chat/completions"


def test_local_model_backend_succeeds_with_fake_client() -> None:
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://localhost:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"open_policy","action_name":"browser_open_url","parameters":{"url":"https://docs.local/docs/policy"},"expected_text":"Allowed activity"}',
                finish_reason="stop",
            ),
            ChatCompletionResponse(
                content='{"step_id":"done","action_name":"done","parameters":{},"expected_text":"","done":true}',
                finish_reason="stop",
            ),
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "succeeded"
    assert summary["scenario_id"] == "browser_live_loop_local_model_policy_review_v1"
    assert summary["planner_backend"]["kind"] == "local_model"
    assert summary["planner_backend"]["model_alias"] == "third_model"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["no_runtime_execution"] is True
    assert summary["steps_attempted"] == 3
    assert summary["actions_attempted"] == 2
    assert summary["actions_succeeded"] == 2
    assert summary["expected_results_passed"] == 2
    assert [entry["validation_status"] for entry in summary["runtime_trace"]] == ["accepted", "accepted", "skipped"]
    assert client.requests[0].model == "third_model"
    assert client.requests[0].messages[0]["content"].startswith("/no_think")
    assert client.requests[0].stream is False
    assert client.requests[0].max_tokens >= 1200
    assert client.requests[0].endpoint_base_url == "http://localhost:8082/v1/chat/completions"
    assert summary["planner_backend"]["request_payload_metadata"]["stream"] is False
    assert summary["planner_backend"]["request_payload_metadata"]["max_tokens"] >= 1200
    assert summary["planner_backend"]["model_endpoint"] == "http://localhost:8082/v1/chat/completions"


def test_local_model_backend_http_400_reports_safe_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadRequestClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self) -> BadRequestClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def post(self, url: str, json: dict[str, Any]) -> live_model_planner.httpx.Response:
            del json
            return live_model_planner.httpx.Response(
                400,
                text='{"error":"bad model","raw_prompt":"PROMPT_DO_NOT_COPY","token":"SECRET_TOKEN","path":"C:\\\\Users\\\\m\\\\secret.txt"}',
                request=live_model_planner.httpx.Request("POST", url),
            )

    monkeypatch.setattr(live_model_planner.httpx, "Client", BadRequestClient)
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT)
    diagnostics = summary["planner_backend"]["last_error_diagnostics"]
    diagnostics_text = str(diagnostics)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "model_http_status_error"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["planner_backend"]["last_error_code"] == "model_http_status_error"
    assert summary["planner_backend"]["last_exception_type"] == "HTTPStatusError"
    assert diagnostics["http_status"] == 400
    assert diagnostics["endpoint_path"] == "/v1/chat/completions"
    assert diagnostics["request_payload_metadata"]["message_count"] == 2
    assert diagnostics["request_payload_metadata"]["stream"] is False
    assert diagnostics["request_payload_metadata"]["endpoint_path"] == "/v1/chat/completions"
    assert diagnostics["response_text_preview_sanitized"] is not None
    assert "bad model" in diagnostics["response_text_preview_sanitized"]
    assert "PROMPT_DO_NOT_COPY" not in diagnostics_text
    assert "SECRET_TOKEN" not in diagnostics_text
    assert "C:\\Users" not in diagnostics_text


def test_local_model_backend_unsupported_browser_search_is_rejected_before_fixture_execution() -> None:
    config = _load_local_model_config()
    config["planner_backend"]["allow_model_calls"] = True
    config["planner_backend"]["model_endpoint"] = "http://127.0.0.1:8082/v1"
    client = FakeChatCompletionClient(
        [
            ChatCompletionResponse(
                content='{"step_id":"search_docs","action_name":"browser_search","parameters":{"query":"shared document policy"},"expected_text":"check shared document policy"}',
                finish_reason="stop",
            )
        ]
    )

    summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT, model_client=client)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "model_output_unsupported_action"
    assert summary["stop_reason"] == "planner_action_rejected"
    assert summary["model_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["steps_attempted"] == 0
    assert summary["actions_attempted"] == 0
    assert summary["actions_succeeded"] == 0
    assert summary["actions_failed"] == 0
    assert summary["runtime_trace"][0]["fixture_execution_status"] == "skipped"
    assert summary["runtime_trace"][0]["validation_status"] == "skipped"
    assert summary["runtime_trace"][0]["error_code"] == "model_output_unsupported_action"
    assert summary["runtime_trace"][0]["step_index"] == 1
    assert client.requests[0].endpoint_base_url == "http://127.0.0.1:8082/v1/chat/completions"


def test_local_model_cli_refuses_without_allow_flag() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(LOCAL_MODEL_CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode != 0
    assert payload["status"] == "refused"
    assert payload["error_code"] == "allow_model_calls_required"
    assert payload["no_runtime_execution"] is True


def test_live_loop_does_not_import_playwright_or_browser_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_live_loop(EXAMPLE_CONFIG_PATH, repo_root=PROJECT_ROOT)

    assert summary["status"] == "succeeded"
