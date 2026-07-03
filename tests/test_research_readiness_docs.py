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
        "docs/ai/local_orchestrator_executor_runtime_audit.md",
        "docs/ai/local_orchestrator_executor_poc_v1.md",
        "docs/ai/local_orchestrator_executor_poc_blocker.md",
        "docs/ai/local_orchestrator_executor_poc_v2_repair.md",
        "docs/ai/local_orchestrator_executor_executor_failure_analysis.md",
        "docs/ai/local_orchestrator_executor_poc_v3_executor_repair.md",
        "docs/ai/repeated_local_orchestrator_executor_trials_v1.md",
        "docs/ai/orchestrator_executor_pair_matrix_v1.md",
        "docs/ai/heavy_multi_agent_scenario_v1.md",
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
        "Local proof-of-concept follow-up",
        "Plan repair",
        "Executor prompt and repair",
        "Repeated local group trials",
        "Pair matrix comparison",
        "local_orchestrator_executor_poc_blocker.md",
        "local_orchestrator_executor_poc_v2_repair.md",
        "local_orchestrator_executor_poc_v3_executor_repair.md",
        "repeated_local_orchestrator_executor_trials_v1.md",
        "orchestrator_executor_pair_matrix_v1.md",
    ]:
        assert required in text


def test_local_orchestrator_executor_poc_docs_record_blocked_attempt() -> None:
    poc = _read("docs/ai/local_orchestrator_executor_poc_v1.md")
    blocker = _read("docs/ai/local_orchestrator_executor_poc_blocker.md")

    for required in [
        "second_model",
        "first_model",
        "http://127.0.0.1:8081/v1",
        "http://127.0.0.1:8082/v1",
        "invalid orchestrator JSON",
    ]:
        assert required in poc or required in blocker

    assert "No final model-pair recommendation" in blocker


def test_local_orchestrator_executor_v2_doc_records_executor_reachability() -> None:
    text = _read("docs/ai/local_orchestrator_executor_poc_v2_repair.md")

    for required in [
        "completed_with_failures",
        "initial plan parse success",
        "executor calls attempted",
        "2",
        "0.291764",
        "missing_required_parameter",
        "unsafe_path",
    ]:
        assert required in text


def test_local_orchestrator_executor_v3_doc_records_successful_executor_actions() -> None:
    text = _read("docs/ai/local_orchestrator_executor_poc_v3_executor_repair.md")

    for required in [
        "completed",
        "success",
        "0.890597",
        "per_agent_attempts.jsonl",
        "docs/ai/model_research_metadata.md",
        "configs/evaluation_models.json",
        "repair was enabled but not needed",
        "repeated_local_orchestrator_executor_trials_v1.md",
    ]:
        assert required in text


def test_repeated_local_orchestrator_executor_trials_doc_records_n3_result() -> None:
    text = _read("docs/ai/repeated_local_orchestrator_executor_trials_v1.md")

    for required in [
        "Repeated Local Orchestrator/Executor Trials v1",
        "repeated_local_second_to_first_group_n3_v1",
        "attempted trials",
        "completed trials",
        "0.890528",
        "0.000088",
        "read_file: 6",
        "No final model recommendation",
        "orchestrator_executor_pair_matrix_v1.md",
    ]:
        assert required in text


def test_orchestrator_executor_pair_matrix_doc_records_result() -> None:
    text = _read("docs/ai/orchestrator_executor_pair_matrix_v1.md")

    for required in [
        "Orchestrator/Executor Pair Matrix v1",
        "pair_matrix_office_developer_group_n3_v1",
        "second_model -> first_model",
        "second_model -> second_model",
        "first_model -> first_model",
        "first_model -> second_model",
        "0.952618",
        "0.948958",
        "orchestrator_plan_parse_failed: 6",
        "current best observed pair",
        "No final production recommendation",
        "pair_matrix_heavy_group_n3_workspace_policy_v1",
        "cross_scenario_pair_matrix_workspace_policy_v1",
        "stable_but_low_confidence",
    ]:
        assert required in text


def test_heavy_multi_agent_scenario_doc_records_matrix_result() -> None:
    text = _read("docs/ai/heavy_multi_agent_scenario_v1.md")

    for required in [
        "Heavy Multi-Agent Scenario v1",
        "office_developer_maintenance_group_heavy_v1",
        "office_agent_1",
        "developer_agent_2",
        "artifact_workspace_only",
        "fake_heavy_group_scenario_smoke_workspace_policy_v1",
        "repeated_local_second_to_first_heavy_group_n3_workspace_policy_v1",
        "0.820328",
        "write_path_outside_artifact_workspace",
        "pair_matrix_heavy_group_n3_workspace_policy_v1",
        "second_model -> second_model",
        "0.759188",
        "cross_scenario_pair_matrix_workspace_policy_v1",
        "stable_but_low_confidence",
        "not a final recommendation",
    ]:
        assert required in text
