from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_llama_smoke import extract_output_text, make_resource_estimate, make_timestamp


def test_make_timestamp_format() -> None:
    value = make_timestamp()
    assert re.fullmatch(r"\d{8}_\d{6}", value) is not None


def test_make_resource_estimate_shape() -> None:
    data = make_resource_estimate(
        ram_before_mb=100.0,
        ram_after_mb=105.5,
        cpu_avg=15.0,
        cpu_max=32.0,
        server_pid=123,
        server_rss_before_mb=800.0,
        server_rss_after_mb=810.25,
        server_metric_error=None,
    )
    expected_keys = {
        "system_ram_used_before_mb",
        "system_ram_used_after_mb",
        "system_ram_delta_mb",
        "system_cpu_percent_avg",
        "system_cpu_percent_max",
        "server_pid",
        "server_rss_before_mb",
        "server_rss_after_mb",
        "server_rss_delta_mb",
        "server_metric_error",
    }
    assert set(data.keys()) == expected_keys
    assert data["system_ram_delta_mb"] == 5.5
    assert data["server_rss_delta_mb"] == 10.25


def test_extract_output_text_openai_compatible() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"action":"read_file","parameters":{},"reason":"x","expected_result":"y"}'
                }
            }
        ]
    }
    assert extract_output_text(payload).startswith('{"action":"read_file"')


def test_extract_output_text_raises_for_missing_path() -> None:
    with pytest.raises((KeyError, IndexError, TypeError)):
        extract_output_text({"choices": []})
