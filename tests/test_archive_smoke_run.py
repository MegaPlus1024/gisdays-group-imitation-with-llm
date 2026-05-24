from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from archive_smoke_run import build_manifest, find_latest_successful_smoke_log, sha256_text


def test_sha256_text_known_value() -> None:
    assert sha256_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_find_latest_successful_smoke_log_prefers_newest_success(tmp_path: Path) -> None:
    older_success = tmp_path / "20260101_000001_smoke.json"
    newer_failed = tmp_path / "20260101_000002_smoke.json"
    newest_success = tmp_path / "20260101_000003_smoke.json"

    older_success.write_text(json.dumps({"success": True}), encoding="utf-8")
    newer_failed.write_text(json.dumps({"success": False}), encoding="utf-8")
    newest_success.write_text(json.dumps({"success": True}), encoding="utf-8")

    selected = find_latest_successful_smoke_log(tmp_path)
    assert selected.name == newest_success.name


def test_build_manifest_preserves_core_fields(tmp_path: Path) -> None:
    smoke_path = tmp_path / "20260101_000001_smoke.json"
    smoke_path.write_text("{}", encoding="utf-8")
    model_path = tmp_path / "first_model.gguf"
    model_path.write_bytes(b"not-a-real-model")

    raw_smoke = {
        "success": True,
        "runtime": "llama.cpp / llama-server",
        "base_url": "http://127.0.0.1:8080/v1",
        "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
        "model_name": "first_model.gguf",
        "wall_time_seconds": 1.23,
        "resource_estimate": {"system_cpu_percent_avg": 1.1},
        "raw_response": {
            "system_fingerprint": "abc",
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "timings": {"prompt_ms": 10.0},
        },
    }

    manifest = build_manifest(
        experiment_id="exp1",
        smoke_log_path=smoke_path,
        prompt_source_path=None,
        output_source_path=None,
        model_path=model_path,
        raw_smoke=raw_smoke,
        prompt_text="prompt",
        output_text='{"action":"read_file","parameters":{},"reason":"r","expected_result":"e"}',
    )

    assert manifest["status"]["success"] is True
    assert manifest["timing"]["wall_time_seconds"] == 1.23
    assert manifest["resource_estimate"]["system_cpu_percent_avg"] == 1.1
    assert manifest["output"]["json_parse_success"] is True
