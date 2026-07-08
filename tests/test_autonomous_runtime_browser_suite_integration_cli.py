from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_suite_integration.py"
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "autonomous_browser_suite_integration.example.json"
SUMMARY_FILENAME = "autonomous_browser_suite_integration_summary.json"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_stdout_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stderr == "" or "Traceback" not in result.stderr
    return json.loads(result.stdout)


def test_cli_success_writes_summary_and_optional_markdown(tmp_path: Path) -> None:
    output_dir = tmp_path / "integration_out"
    markdown_output = tmp_path / "integration_out.md"
    result = _run_cli(
        [
            "--config",
            str(CONFIG_PATH),
            "--output-dir",
            str(output_dir),
            "--markdown-output",
            str(markdown_output),
        ]
    )
    payload = _load_stdout_json(result)

    assert result.returncode == 0
    assert result.stdout.strip()
    assert "\n" not in result.stdout.strip()
    assert payload["schema_version"] == "autonomous_runtime_browser_suite_integration_summary_v1"
    assert payload["status"] == "succeeded"
    assert payload["no_runtime_execution"] is True
    assert payload["runtime_task_count"] == 1
    assert payload["browser_suite_status"] == "passed"
    assert payload["scenarios_attempted"] == 4
    assert payload["scenarios_succeeded"] == 4
    assert payload["scenarios_failed"] == 0
    assert payload["actions_attempted"] == 30
    assert payload["actions_succeeded"] == 30
    assert payload["actions_failed"] == 0
    assert payload["expected_results_total"] == 18
    assert payload["expected_results_passed"] == 18
    assert payload["expected_results_failed"] == 0
    assert payload["required_actions_missing"] == []
    assert payload["required_actions_covered"] == [
        "browser_click",
        "browser_extract_text",
        "browser_fill",
        "browser_open_url",
        "browser_search",
        "browser_snapshot",
        "browser_submit",
        "browser_wait",
    ]
    assert payload["browser_suite_summary"]["schema_version"] == "autonomous_browser_scenario_suite_summary_v1"
    assert payload["browser_suite_summary"]["no_runtime_execution"] is True
    assert payload["output_files"] == [SUMMARY_FILENAME, markdown_output.name]
    assert (output_dir / SUMMARY_FILENAME).is_file()
    assert markdown_output.is_file()
    assert str(PROJECT_ROOT) not in result.stdout
    assert "C:\\" not in result.stdout


def test_cli_invalid_config_returns_structured_error(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad_config.json"
    bad_config.write_text(
        json.dumps(
            {
                "schema_version": "wrong",
                "integration_id": "bad",
                "suite_config_path": "configs/autonomous_runtime/browser_scenario_suite.example.json",
                "output_dir": "artifacts/autonomous_runtime_summaries/browser_suite_integration",
                "expected_required_actions": [],
                "no_runtime_execution": True,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = _run_cli(["--config", str(bad_config)])
    payload = _load_stdout_json(result)

    assert result.returncode == 2
    assert payload["status"] == "invalid_input"
    assert payload["error_code"] == "config_validation_failed"
    assert payload["no_runtime_execution"] is True


def test_cli_imports_without_playwright_backend() -> None:
    spec = importlib.util.spec_from_file_location("run_autonomous_browser_suite_integration_test_module", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert "playwright" not in sys.modules


def test_cli_output_summary_path_stays_relative_to_repo(tmp_path: Path) -> None:
    result = _run_cli(["--config", str(CONFIG_PATH), "--output-dir", str(tmp_path / "integration_out")])
    payload = _load_stdout_json(result)

    assert result.returncode == 0
    assert payload["output_files"] == [SUMMARY_FILENAME]
    assert str(tmp_path) not in result.stdout
    assert "C:\\" not in result.stdout
