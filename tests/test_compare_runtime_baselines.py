from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compare_runtime_baselines import (
    build_comparison,
    build_markdown,
    delta,
    load_summary,
    ratio,
)


def make_summary(model_name: str) -> dict:
    return {
        "model_name": model_name,
        "run_count": 3,
        "success_count": 3,
        "failure_count": 0,
        "json_parse_success_count": 3,
        "wall_time_seconds": {"avg": 1.0, "min": 0.9, "max": 1.1},
        "cpu_percent": {"avg_of_avg": 2.0, "max": 4.0},
        "system_ram_delta_mb": {"avg": 1.0, "min": 0.5, "max": 1.5},
        "server_rss_delta_mb": {"avg": None, "min": None, "max": None},
        "tokens": {"prompt_tokens_avg": 10.0, "completion_tokens_avg": 20.0, "total_tokens_avg": 30.0},
        "llama_tokens_per_second": {"prompt_per_second_avg": 40.0, "predicted_per_second_avg": 50.0},
        "failure_cases": [],
    }


def test_load_summary_extracts_model_name_and_counts(tmp_path: Path) -> None:
    p = tmp_path / "summary.json"
    p.write_text(json.dumps(make_summary("first_model.gguf")), encoding="utf-8")
    summary = load_summary(p)
    assert summary["model_name"] == "first_model.gguf"
    assert summary["success_count"] == 3


def test_missing_summary_file_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_summary(tmp_path / "missing.json")


def test_delta_helper_handles_numbers() -> None:
    assert delta(2.0, 5.5) == 3.5


def test_ratio_helper_handles_zero_and_null() -> None:
    assert ratio(None, 2.0) is None
    assert ratio(0.0, 2.0) is None
    assert ratio(2.0, 4.0) == 2.0


def test_comparison_builder_preserves_null_for_missing_metrics() -> None:
    first = make_summary("first_model.gguf")
    second = make_summary("second_model.gguf")
    second["tokens"]["total_tokens_avg"] = None
    comp = build_comparison(first, second, "a", "b")
    assert comp["second"]["tokens"]["total_tokens_avg"] is None
    assert comp["deltas"]["total_tokens_avg_delta"] is None


def test_comparison_markdown_contains_both_model_names() -> None:
    first = make_summary("first_model.gguf")
    second = make_summary("second_model.gguf")
    comp = build_comparison(first, second, "a", "b")
    md = build_markdown(comp)
    assert "first_model.gguf" in md
    assert "second_model.gguf" in md


def test_comparison_is_json_serializable() -> None:
    first = make_summary("first_model.gguf")
    second = make_summary("second_model.gguf")
    comp = build_comparison(first, second, "a", "b")
    text = json.dumps(comp)
    assert isinstance(text, str)
