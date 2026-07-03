from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_research_readiness_docs_exist() -> None:
    for relative_path in [
        "docs/ai/model_research_metadata.md",
        "docs/ai/final_tz_readiness_audit.md",
        "docs/ai/orchestrator_executor_pipeline_v1.md",
        "docs/ai/orchestrator_executor_quality_spec.md",
        "docs/ai/gpu_runtime_readiness_audit.md",
        "docs/ai/next_implementation_plan_orchestrator_executor.md",
    ]:
        assert (PROJECT_ROOT / relative_path).exists(), relative_path


def test_readme_links_research_model_metadata() -> None:
    readme = _read("README.md")

    assert "docs/ai/model_research_metadata.md" in readme


def test_evaluation_model_registry_has_current_models_and_legacy_alias() -> None:
    payload = json.loads(_read("configs/evaluation_models.json"))
    models = {item["model_id"]: item for item in payload["models"]}

    assert "first_model" in models
    assert "second_model" in models
    assert models["first_model"]["upstream_model_name"] == "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    assert models["second_model"]["upstream_model_name"] == "qwen2.5-3b-instruct-q4_k_m.gguf"
    assert "qwen2_5_3b_instruct_q4_k_m" in models["second_model"].get("aliases", [])


def test_model_research_metadata_contains_required_table_fields() -> None:
    text = _read("docs/ai/model_research_metadata.md")

    for required in [
        "project model_id",
        "local GGUF file",
        "llama-server model_name",
        "upstream/full model name",
        "parameter size",
        "quantization",
        "first_model",
        "second_model",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "qwen2.5-3b-instruct-q4_k_m.gguf",
    ]:
        assert required in text


def test_final_tz_readiness_audit_names_critical_statuses() -> None:
    text = _read("docs/ai/final_tz_readiness_audit.md").lower()

    for required in [
        "group of agents",
        "orchestrator/executor pair",
        "gpu runtime",
        "measured multi-agent capacity",
        "partially complete",
        "missing",
        "estimated only",
    ]:
        assert required in text


def test_gpu_audit_is_explicit_about_unmeasured_gpu_runtime() -> None:
    text = _read("docs/ai/gpu_runtime_readiness_audit.md").lower()

    assert "gpu runtime configured: no" in text
    assert "gpu runtime measured: no" in text
    assert "cpu-only short single-agent runs demonstrated: yes" in text


def test_orchestrator_executor_quality_spec_names_prototype_status() -> None:
    text = _read("docs/ai/orchestrator_executor_quality_spec.md").lower()

    assert "pair_quality_score" in text
    assert "prototype implementation" in text
    assert "not a final scientific metric" in text
    assert "group_coordination_score" in text
    assert "task_completion_score" in text


def test_orchestrator_executor_pipeline_doc_names_default_pair_and_artifacts() -> None:
    text = _read("docs/ai/orchestrator_executor_pipeline_v1.md")

    for required in [
        "Orchestrator/Executor Pipeline v1",
        "second_model",
        "first_model",
        "office_developer_group_basic_v1",
        "pair_quality_score",
        "experiments/multi_agent/orchestrator_executor/fake_office_developer_group_v1",
    ]:
        assert required in text
