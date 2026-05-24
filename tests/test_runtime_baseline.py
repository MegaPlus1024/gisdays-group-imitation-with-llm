from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_runtime_baseline import (
    build_summary,
    extract_assistant_content,
    get_package_version,
    max_ignore_none,
    mean_ignore_none,
    min_ignore_none,
)


def test_none_ignoring_stats_helpers() -> None:
    values = [None, 2.0, 4.0, None]
    assert mean_ignore_none(values) == 3.0
    assert min_ignore_none(values) == 2.0
    assert max_ignore_none(values) == 4.0


def test_extract_assistant_content_openai_shape() -> None:
    payload = {"choices": [{"message": {"content": '{"ok":true}'}}]}
    assert extract_assistant_content(payload) == '{"ok":true}'


def test_extract_assistant_content_invalid_shape_raises() -> None:
    try:
        extract_assistant_content({"choices": []})
    except ValueError as exc:
        assert "Missing assistant content" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid response shape")


def test_build_summary_counts_success_and_failures() -> None:
    runs = [
        {
            "run_index": 1,
            "success": True,
            "json_parse_success": True,
            "wall_time_seconds": 1.0,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "llama_timings": {"prompt_per_second": 20.0, "predicted_per_second": 30.0},
            "resource_estimate": {
                "system_cpu_percent_avg": 4.0,
                "system_cpu_percent_max": 7.0,
                "system_ram_delta_mb": 1.0,
                "server_rss_delta_mb": None,
            },
        },
        {
            "run_index": 2,
            "success": False,
            "error_type": "request_error",
            "error_message": "boom",
            "json_parse_success": False,
            "wall_time_seconds": 2.0,
            "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
            "llama_timings": {"prompt_per_second": None, "predicted_per_second": None},
            "resource_estimate": {
                "system_cpu_percent_avg": None,
                "system_cpu_percent_max": None,
                "system_ram_delta_mb": None,
                "server_rss_delta_mb": None,
            },
        },
    ]
    summary = build_summary(
        experiment_id="local_runtime_baseline_v1",
        runtime="llama.cpp / llama-server",
        base_url="http://127.0.0.1:8080/v1",
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        model_name="first_model.gguf",
        prompt_file="prompts/smoke/agent_next_action_v1.txt",
        runs_requested=2,
        runs=runs,
    )
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 1
    assert summary["json_parse_success_count"] == 1
    assert summary["wall_time_seconds"]["avg"] == 1.0
    assert summary["failure_cases"][0]["run_index"] == 2
    assert summary["failure_cases"][0]["error_type"] == "request_error"


def test_get_package_version_missing_package_returns_none() -> None:
    assert get_package_version("definitely_not_installed_package_123") is None
