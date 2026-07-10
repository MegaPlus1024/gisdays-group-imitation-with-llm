from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_live_model_planner import ChatCompletionResponse
from src.agent.autonomous_browser_live_loop_variance_suite import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_live_loop_variance_suite_config,
    run_autonomous_browser_live_loop_variance_suite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_live_loop_variance_suite.example.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_live_loop_variance_suite.py"
TEST_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/live_loop_variance_suite_tests"


class FakeChatCompletionClient:
    def __init__(self, responses: list[ChatCompletionResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[Any] = []

    def complete(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected model request")
        return self.responses.pop(0)


def _config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _configure_suite(payload: dict[str, Any], *, allow_model_calls: bool, trial_count: int = 2) -> dict[str, Any]:
    payload["allow_model_calls"] = allow_model_calls
    payload["trial_count_per_scenario"] = trial_count
    payload["output_dir"] = TEST_OUTPUT_DIR
    return payload


def _cleanup_outputs() -> None:
    shutil.rmtree(PROJECT_ROOT / TEST_OUTPUT_DIR, ignore_errors=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _policy_responses() -> list[ChatCompletionResponse]:
    return [
        ChatCompletionResponse(
            content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_policy","action_name":"browser_click","parameters":{"target_text":"Workspace policy"},"expected_text":"Workspace Policy","expected_url":"https://local.intranet/docs/policy"}',
            finish_reason="stop",
        ),
    ]


def _ticket_success_responses() -> list[ChatCompletionResponse]:
    return [
        ChatCompletionResponse(
            content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_ticket_board","action_name":"browser_click","parameters":{"target_text":"Ticket board"},"expected_text":"Ticket Board","expected_url":"https://local.intranet/tickets"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_ticket_1","action_name":"browser_click","parameters":{"target_text":"Ticket 1"},"expected_text":"Ticket 1 - Quarterly Access Review","expected_url":"https://local.intranet/tickets/1"}',
            finish_reason="stop",
        ),
    ]


def _ticket_repair_failure_responses() -> list[ChatCompletionResponse]:
    return [
        ChatCompletionResponse(
            content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_ticket_board","action_name":"browser_click","parameters":{"target_text":"Ticket board"},"expected_text":"Ticket Board","expected_url":"https://local.intranet/tickets"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_ticket_1","action_name":"browser_click","parameters":{"target_text":"Ticket 1"},"expected_text":"Quarterly Access Review requires an office-worker status note.","expected_url":"https://local.intranet/tickets/1"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_ticket_1_repair","action_name":"browser_click","parameters":{"target_text":"Ticket 1"},"expected_text":"Quarterly Access Review requires an office-worker status note."}',
            finish_reason="stop",
        ),
    ]


def _approval_responses() -> list[ChatCompletionResponse]:
    return [
        ChatCompletionResponse(
            content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_approvals_queue","action_name":"browser_click","parameters":{"target_text":"Approvals queue"},"expected_text":"Approvals Queue","expected_url":"https://local.intranet/portal/approvals"}',
            finish_reason="stop",
        ),
        ChatCompletionResponse(
            content='{"step_id":"click_policy_match_review","action_name":"browser_click","parameters":{"target_text":"Policy match review"},"expected_text":"Approval Policy Match","expected_url":"https://local.intranet/portal/approval-match"}',
            finish_reason="stop",
        ),
    ]


def _trial_client_factory(*, repaired_ticket_trial: bool = False, failing_ticket_trial: bool = False):
    def factory(scenario_id: str, trial_index: int, trial_config: Mapping[str, Any]) -> FakeChatCompletionClient:
        del trial_config
        if scenario_id == "hard_policy_disambiguation":
            return FakeChatCompletionClient(_policy_responses())
        if scenario_id == "hard_ticket_priority_crosscheck":
            if failing_ticket_trial:
                if trial_index == 2:
                    return FakeChatCompletionClient(_ticket_repair_failure_responses())
                return FakeChatCompletionClient(_ticket_success_responses())
            if repaired_ticket_trial and trial_index == 2:
                return FakeChatCompletionClient(
                    [
                        ChatCompletionResponse(
                            content='{"step_id":"open_home","action_name":"browser_open_url","parameters":{"url":"https://local.intranet/"},"expected_text":"Office Intranet Home","expected_url":"https://local.intranet/"}',
                            finish_reason="stop",
                        ),
                        ChatCompletionResponse(
                            content='{"step_id":"click_ticket_board","action_name":"browser_click","parameters":{"target_text":"Ticket board"},"expected_text":"Ticket Board","expected_url":"https://local.intranet/tickets"}',
                            finish_reason="stop",
                        ),
                        ChatCompletionResponse(
                            content='{"step_id":"click_ticket_1","action_name":"browser_click","parameters":{"target_text":"Ticket 1"},"expected_text":"Quarterly Access Review requires an office-worker status note.","expected_url":"https://local.intranet/tickets/1"}',
                            finish_reason="stop",
                        ),
                        ChatCompletionResponse(
                            content='{"step_id":"click_ticket_1_repair","action_name":"browser_click","parameters":{"target_text":"Ticket 1"},"expected_text":"Ticket 1 - Quarterly Access Review"}',
                            finish_reason="stop",
                        ),
                    ]
                )
            return FakeChatCompletionClient(_ticket_success_responses())
        if scenario_id == "hard_approval_policy_match":
            return FakeChatCompletionClient(_approval_responses())
        raise AssertionError(f"unexpected scenario_id: {scenario_id}")

    return factory


def test_variance_suite_config_loads_with_relative_paths() -> None:
    config = load_autonomous_browser_live_loop_variance_suite_config(CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.suite_id == "phase_13c_guarded_local_model_live_loop_variance"
    assert config.base_live_loop_config == "configs/autonomous_runtime/browser_live_loop_local_model.example.json"
    assert config.planner_backend == "local_model"
    assert config.model_alias == "third_model"
    assert config.model_endpoint == "http://127.0.0.1:8082/v1/chat/completions"
    assert config.trial_count_per_scenario == 3
    assert config.scenario_ids == (
        "hard_policy_disambiguation",
        "hard_ticket_priority_crosscheck",
        "hard_approval_policy_match",
    )
    assert config.output_dir == "artifacts/autonomous_runtime_summaries/live_loop_variance_suite"
    assert config.allow_model_calls is False
    assert config.require_explicit_allow_model_calls is True
    assert config.no_real_browser is True
    assert config.no_playwright is True
    assert config.trial_label_prefix == "trial"


def test_default_local_model_suite_refuses_before_trials() -> None:
    summary = run_autonomous_browser_live_loop_variance_suite(_config(), repo_root=PROJECT_ROOT)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_model_calls_required"
    assert summary["trials_total"] == 0
    assert summary["trials_succeeded"] == 0
    assert summary["trials_failed"] == 0
    assert summary["trials_rejected"] == 0
    assert summary["model_execution_attempted"] is False
    assert summary["model_execution_completed"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["no_runtime_execution"] is True
    assert summary["trial_summaries"] == []
    assert summary["scenario_summaries"] == []
    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded
    assert not (PROJECT_ROOT / TEST_OUTPUT_DIR).exists()


def test_successful_suite_aggregates_trials_and_route_stability() -> None:
    payload = _configure_suite(_config(), allow_model_calls=True, trial_count=2)
    summary = run_autonomous_browser_live_loop_variance_suite(
        payload,
        repo_root=PROJECT_ROOT,
        model_client_factory=_trial_client_factory(repaired_ticket_trial=True),
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["trials_total"] == 6
    assert summary["trials_succeeded"] == 6
    assert summary["trials_failed"] == 0
    assert summary["trials_rejected"] == 0
    assert summary["pass_rate_overall"] == 1.0
    assert summary["model_execution_attempted"] is True
    assert summary["model_execution_completed"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["no_runtime_execution"] is True
    assert len(summary["trial_summaries"]) == 6
    assert len(summary["scenario_summaries"]) == 3
    assert all(item["pass_rate"] == 1.0 for item in summary["scenario_summaries"])
    assert all(item["route_stable"] is True for item in summary["scenario_summaries"])
    assert all(item["matched_url_stable"] is True for item in summary["scenario_summaries"])
    assert all(len(item["unique_route_fingerprints"]) == 1 for item in summary["scenario_summaries"])
    assert all(len(item["unique_matched_urls"]) == 1 for item in summary["scenario_summaries"])
    assert any(item["repair_attempts_total"] == 1 for item in summary["trial_summaries"])
    assert any(
        item["matched_completion_criteria_scenario"] == item["scenario_id"]
        for item in summary["trial_summaries"]
        if item["goal_satisfied"]
    )
    assert all(not Path(item["trace_path"]).is_absolute() for item in summary["trial_summaries"] if item["trace_path"])
    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded
    _cleanup_outputs()


def test_successful_suite_persists_per_trial_trace_files() -> None:
    payload = _configure_suite(_config(), allow_model_calls=True, trial_count=1)
    summary = run_autonomous_browser_live_loop_variance_suite(
        payload,
        repo_root=PROJECT_ROOT,
        model_client_factory=_trial_client_factory(repaired_ticket_trial=True),
    )

    try:
        assert summary["status"] == "succeeded"
        assert len(summary["trial_summaries"]) == 3
        for trial_summary in summary["trial_summaries"]:
            trace_path = trial_summary["trace_path"]
            assert trace_path is not None
            assert not Path(trace_path).is_absolute()
            assert (PROJECT_ROOT / trace_path).exists()
    finally:
        _cleanup_outputs()


def test_partial_failure_suite_reports_completed_with_failures_and_error_codes() -> None:
    payload = _configure_suite(_config(), allow_model_calls=True, trial_count=2)
    summary = run_autonomous_browser_live_loop_variance_suite(
        payload,
        repo_root=PROJECT_ROOT,
        model_client_factory=_trial_client_factory(failing_ticket_trial=True),
    )

    ticket_scenario = next(item for item in summary["scenario_summaries"] if item["scenario_id"] == "hard_ticket_priority_crosscheck")

    assert summary["status"] == "completed_with_failures"
    assert summary["error_code"] in {"model_output_expected_text_not_visible", "suite_completed_with_failures"}
    assert summary["trials_total"] == 6
    assert summary["trials_succeeded"] == 5
    assert summary["trials_rejected"] == 1
    assert summary["trials_failed"] == 0
    assert summary["pass_rate_overall"] == pytest.approx(5 / 6, abs=0.001)
    assert ticket_scenario["trials_total"] == 2
    assert ticket_scenario["trials_succeeded"] == 1
    assert ticket_scenario["trials_rejected"] == 1
    assert ticket_scenario["pass_rate"] == 0.5
    assert ticket_scenario["error_codes"]
    assert "model_output_expected_text_not_visible" in ticket_scenario["error_codes"]
    assert ticket_scenario["route_stable"] is True
    assert ticket_scenario["matched_url_stable"] is True
    assert any(item["status"] == "rejected" for item in summary["trial_summaries"])
    assert any(item["route_fingerprint"] for item in summary["trial_summaries"] if item["status"] == "succeeded")
    _cleanup_outputs()


def test_trial_summaries_include_relative_paths_and_matching_scenario_ids() -> None:
    payload = _configure_suite(_config(), allow_model_calls=True, trial_count=2)
    summary = run_autonomous_browser_live_loop_variance_suite(
        payload,
        repo_root=PROJECT_ROOT,
        model_client_factory=_trial_client_factory(repaired_ticket_trial=True),
    )

    encoded = json.dumps(summary, ensure_ascii=False)
    assert all(not Path(item["trace_path"]).is_absolute() for item in summary["trial_summaries"] if item["trace_path"])
    assert all(
        item["matched_completion_criteria_scenario"] == item["scenario_id"]
        for item in summary["trial_summaries"]
        if item["goal_satisfied"]
    )
    assert "C:\\" not in encoded
    assert str(PROJECT_ROOT) not in encoded
    _cleanup_outputs()


def test_cli_default_refusal_exits_nonzero_and_reports_allow_model_calls_required(tmp_path: Path) -> None:
    config_path = tmp_path / "browser_live_loop_variance_suite.example.json"
    config_payload = _config()
    config_payload["output_dir"] = "artifacts/autonomous_runtime_summaries/live_loop_variance_suite_temp_refusal"
    _write_json(config_path, config_payload)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(config_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "refused"
    assert payload["error_code"] == "allow_model_calls_required"
    assert payload["model_execution_attempted"] is False
    assert payload["model_execution_completed"] is False
    assert payload["browser_opened"] is False
    assert not (PROJECT_ROOT / "artifacts" / "autonomous_runtime_summaries" / "live_loop_variance_suite_temp_refusal").exists()
