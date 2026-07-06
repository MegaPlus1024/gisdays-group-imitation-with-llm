from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from src.agent import model_evaluation_artifact_registry as registry
from src.agent.model_evaluation_artifact_validator import (
    EXPECTED_SCHEMA_VERSIONS,
    KNOWN_WORKFLOW_ARTIFACT_LOCATIONS,
)
from src.agent.model_evaluation_cli import main as model_evaluation_cli_main
from src.agent.model_evaluation_workflow_bundle import (
    OPTIONAL_WORKFLOW_ARTIFACTS,
    REQUIRED_WORKFLOW_ARTIFACTS,
)
from src.agent.model_evaluation_workflow_runner import WORKFLOW_RUN_MANIFEST_FILENAME


def test_registry_lists_all_expected_artifact_types() -> None:
    artifact_types = {info.artifact_type for info in registry.list_artifact_schema_infos()}

    assert artifact_types == {
        registry.MODEL_CATALOG,
        registry.MODEL_COMPARISON_PLAN,
        registry.MODEL_PAIR_MATRIX_RUN_SUMMARY,
        registry.TASK_CORRECTNESS_EVALUATION_RESULT,
        registry.TASK_CORRECTNESS_BATCH_SUMMARY,
        registry.READINESS_REPORT,
        registry.NORMALITY_COMPARISON_SUMMARY,
        registry.MODEL_RESOURCE_SUMMARY,
        registry.MODEL_EVALUATION_SCORECARD,
        registry.WORKFLOW_BUNDLE,
        registry.WORKFLOW_RUN_MANIFEST,
        registry.ARTIFACT_VALIDATION_REPORT,
        registry.WORKFLOW_CONFIG,
        registry.MODEL_EVALUATION_COMPATIBILITY_REPORT,
    }


def test_each_artifact_has_schema_version_and_default_filename() -> None:
    for info in registry.list_artifact_schema_infos():
        assert info.schema_version
        assert info.default_filename
        assert info.expected_top_level_type == "object"


def test_workflow_known_relative_paths_include_core_outputs() -> None:
    paths = registry.get_workflow_known_relative_paths()

    assert paths[registry.MODEL_COMPARISON_PLAN] == "plan/model_comparison_plan.json"
    assert paths[registry.READINESS_REPORT] == "readiness/model_comparison_readiness_report.json"
    assert paths[registry.MODEL_EVALUATION_SCORECARD] == "scorecard/model_evaluation_scorecard.json"
    assert paths[registry.WORKFLOW_BUNDLE] == "bundle/model_evaluation_workflow_bundle.json"
    assert paths[registry.WORKFLOW_RUN_MANIFEST] == "workflow_run_manifest.json"


def test_required_workflow_artifacts_are_catalog_plan_readiness() -> None:
    assert registry.get_required_workflow_artifact_types() == (
        registry.MODEL_CATALOG,
        registry.MODEL_COMPARISON_PLAN,
        registry.READINESS_REPORT,
    )


def test_optional_workflow_artifacts_include_normality_resource_scorecard() -> None:
    assert registry.get_optional_workflow_artifact_types() == (
        registry.NORMALITY_COMPARISON_SUMMARY,
        registry.MODEL_RESOURCE_SUMMARY,
        registry.MODEL_EVALUATION_SCORECARD,
    )


def test_artifact_type_from_workflow_relative_path_resolves_known_paths() -> None:
    assert (
        registry.artifact_type_from_workflow_relative_path("plan/model_comparison_plan.json")
        == registry.MODEL_COMPARISON_PLAN
    )
    assert (
        registry.artifact_type_from_workflow_relative_path("readiness\\model_comparison_readiness_report.json")
        == registry.READINESS_REPORT
    )
    assert (
        registry.artifact_type_from_workflow_relative_path("bundle/model_evaluation_workflow_bundle.json")
        == registry.WORKFLOW_BUNDLE
    )


def test_unknown_workflow_relative_path_returns_none() -> None:
    assert registry.artifact_type_from_workflow_relative_path("unknown/artifact.json") is None


def test_build_version_payload_includes_subcommands() -> None:
    payload = registry.build_version_payload()

    assert payload["status"] == "ok"
    assert payload["tool"] == "offline_model_evaluation_cli"
    assert payload["supported_subcommands"] == ["run", "validate", "compatibility", "check", "schema", "version"]
    assert payload["artifact_contract_version"] == "artifact_contract_v1"
    assert registry.MODEL_COMPARISON_PLAN in payload["artifact_contract_supported_types"]
    assert registry.MODEL_PAIR_MATRIX_RUN_SUMMARY in payload["artifact_contract_supported_types"]
    assert registry.TASK_CORRECTNESS_BATCH_SUMMARY in payload["artifact_contract_supported_types"]
    assert payload["no_runtime_execution"] is True


def test_build_version_payload_includes_schema_versions_from_registry() -> None:
    payload = registry.build_version_payload()

    assert payload["supported_schema_versions"] == list(registry.get_supported_schema_versions())
    assert "model_evaluation_workflow_config_v1" in payload["supported_schema_versions"]
    assert "model_pair_matrix_run_summary_v1" in payload["supported_schema_versions"]
    assert "task_correctness_batch_summary_v1" in payload["supported_schema_versions"]
    assert "model_evaluation_artifact_validation_v1" in payload["supported_schema_versions"]
    assert "model_evaluation_compatibility_report_v1" in payload["supported_schema_versions"]


def test_unified_cli_version_matches_registry_payload(capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(["version"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload == registry.build_version_payload()


def test_validator_uses_registry_schema_expectations_for_core_artifacts() -> None:
    expected = registry.get_expected_schema_versions_for_workflow_outputs()

    assert EXPECTED_SCHEMA_VERSIONS[registry.MODEL_COMPARISON_PLAN] == expected[registry.MODEL_COMPARISON_PLAN]
    assert EXPECTED_SCHEMA_VERSIONS[registry.READINESS_REPORT] == expected[registry.READINESS_REPORT]
    assert EXPECTED_SCHEMA_VERSIONS[registry.WORKFLOW_BUNDLE] == expected[registry.WORKFLOW_BUNDLE]
    assert KNOWN_WORKFLOW_ARTIFACT_LOCATIONS == registry.get_workflow_known_relative_paths()


def test_bundle_uses_registry_required_and_optional_classification() -> None:
    assert REQUIRED_WORKFLOW_ARTIFACTS == registry.get_required_workflow_artifact_types()
    assert OPTIONAL_WORKFLOW_ARTIFACTS == registry.get_optional_workflow_artifact_types()


def test_runner_output_filenames_remain_unchanged() -> None:
    assert WORKFLOW_RUN_MANIFEST_FILENAME == "workflow_run_manifest.json"
    assert (
        WORKFLOW_RUN_MANIFEST_FILENAME
        == registry.get_default_artifact_filename(registry.WORKFLOW_RUN_MANIFEST)
    )


def test_registry_import_has_no_file_reads_model_imports_or_gguf_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_exists(self: Path) -> bool:
        raise AssertionError("registry import must not touch filesystem")

    def forbid_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError("registry import must not read files")

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("registry must not import runtime backends")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_exists)
    monkeypatch.setattr(Path, "read_text", forbid_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    reloaded = importlib.reload(registry)

    assert reloaded.get_default_artifact_filename(reloaded.MODEL_COMPARISON_PLAN) == "model_comparison_plan.json"
    monkeypatch.setattr(Path, "exists", original_exists)
    monkeypatch.setattr(Path, "read_text", original_read_text)
