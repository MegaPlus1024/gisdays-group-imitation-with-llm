from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from src.agent.autonomous_browser_stateful_readonly_workflow_suite import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_stateful_readonly_workflow_suite_config,
    run_autonomous_browser_stateful_readonly_workflow_suite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_stateful_readonly_workflow_suite.example.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_stateful_readonly_workflow_suite.py"
TEST_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_workflow_suite_tests"


def _config() -> dict[str, object]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _cleanup() -> None:
    shutil.rmtree(PROJECT_ROOT / TEST_OUTPUT_DIR, ignore_errors=True)


def test_suite_config_loads_with_read_only_policy() -> None:
    config = load_autonomous_browser_stateful_readonly_workflow_suite_config(CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.suite_id == "phase_13e_readonly_stateful_workflows"
    assert config.planner_backend == "scripted"
    assert config.fixture_only is True
    assert config.real_browser_execution is False
    assert config.playwright_execution is False
    assert config.browser_opened is False
    assert config.external_network_allowed is False
    assert config.writes_allowed is False
    assert config.output_dir == "artifacts/autonomous_runtime_summaries/stateful_readonly_workflows"
    assert config.max_steps_per_scenario == 12
    assert config.scenario_ids == (
        "stateful_policy_ticket_crosscheck",
        "stateful_approval_policy_crosscheck",
        "stateful_intranet_overview_digest",
        "stateful_ticket_priority_digest",
        "stateful_policy_search_marker_review",
    )
    assert config.fixture_manifest_path == "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
    assert config.read_only_policy.allowed_actions == (
        "browser_open_url",
        "browser_click",
        "browser_extract_text",
        "browser_snapshot",
    )
    assert config.read_only_policy.external_network_allowed is False
    assert config.read_only_policy.writes_allowed is False


def test_scripted_suite_succeeds_and_aggregates_counts() -> None:
    payload = _config()
    payload["output_dir"] = TEST_OUTPUT_DIR
    try:
        summary = run_autonomous_browser_stateful_readonly_workflow_suite(payload, repo_root=PROJECT_ROOT)
        encoded = json.dumps(summary, ensure_ascii=False)

        assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
        assert summary["status"] == "succeeded"
        assert summary["error_code"] is None
        assert summary["scenarios_total"] == 5
        assert summary["scenarios_succeeded"] == 5
        assert summary["scenarios_failed"] == 0
        assert summary["scenarios_rejected"] == 0
        assert summary["workflows_total"] == 5
        assert summary["workflows_succeeded"] == 5
        assert summary["facts_collected_total"] > 0
        assert summary["evidence_items_total"] > 0
        assert summary["actions_attempted_total"] > 0
        assert summary["actions_succeeded_total"] > 0
        assert summary["actions_failed_total"] == 0
        assert summary["failure_class_counts"]["none"] == 5
        assert summary["fixture_only"] is True
        assert summary["no_runtime_execution"] is True
        assert summary["model_execution"] is False
        assert summary["real_browser_execution"] is False
        assert summary["playwright_execution"] is False
        assert summary["browser_opened"] is False
        assert summary["real_network_traffic"] is False
        assert len(summary["scenario_summaries"]) == 5
        assert all(not Path(item["trace_path"]).is_absolute() for item in summary["scenario_summaries"])
        assert all(not Path(item["state_path"]).is_absolute() for item in summary["scenario_summaries"])
        assert all(not Path(item["summary_path"]).is_absolute() for item in summary["scenario_summaries"])
        assert "C:\\" not in encoded
        assert str(PROJECT_ROOT) not in encoded
    finally:
        _cleanup()


def test_cli_smoke_succeeds_without_model_or_browser(tmp_path: Path) -> None:
    config_path = tmp_path / "stateful_readonly_workflow_suite.example.json"
    config_payload = _config()
    config_payload["output_dir"] = TEST_OUTPUT_DIR
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--config", str(config_path)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(completed.stdout)

        assert completed.returncode == 0
        assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
        assert payload["status"] == "succeeded"
        assert payload["fixture_only"] is True
        assert payload["model_execution"] is False
        assert payload["real_browser_execution"] is False
        assert payload["playwright_execution"] is False
        assert payload["browser_opened"] is False
        assert payload["real_network_traffic"] is False
        assert payload["no_runtime_execution"] is True
    finally:
        _cleanup()

