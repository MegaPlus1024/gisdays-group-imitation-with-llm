from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_final_multi_agent_report_exists_and_mentions_core_findings() -> None:
    path = PROJECT_ROOT / "reports/experiments/final_multi_agent_research_report.md"

    assert path.exists()
    text = path.read_text(encoding="utf-8")

    for required in [
        "second_model -> second_model",
        "second_model -> first_model",
        "first_model as orchestrator not recommended",
        "concurrency 2 unstable",
        "production recommendation not made",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "qwen2.5-3b-instruct-q4_k_m.gguf",
    ]:
        assert required in text


def test_readme_links_final_multi_agent_report() -> None:
    readme = _read("README.md")

    assert "reports/experiments/final_multi_agent_research_report.md" in readme


def test_final_evaluation_summary_json_has_multi_agent_extension() -> None:
    payload = json.loads(_read("reports/experiments/final_evaluation_summary.json"))

    extension = payload["multi_agent_extension"]
    assert extension["status"] == "research_prototype_validated"
    assert extension["best_observed_quality_pair"] == "second_model->second_model"
    assert extension["resource_balanced_pair"] == "second_model->first_model"
    assert extension["not_recommended_orchestrator"] == "first_model"
    assert extension["production_recommendation"] is False
    assert "concurrency_2_unstable" in extension["bounded_stress_status"]
