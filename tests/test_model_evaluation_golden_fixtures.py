from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from src.agent import model_evaluation_artifact_registry as registry
from src.agent.model_evaluation_artifact_contracts import (
    export_artifact_schema_contracts,
    get_artifact_schema_contract,
    validate_artifact_against_contract,
)
from src.agent.model_evaluation_artifact_validator import (
    validate_model_evaluation_workflow_output_dir,
)
from src.agent.model_evaluation_cli import main as model_evaluation_cli_main
from src.agent.model_evaluation_workflow_runner import (
    ModelEvaluationWorkflowRunConfig,
    run_offline_model_evaluation_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = PROJECT_ROOT / "tests" / "fixtures" / "model_evaluation_workflow_golden"
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
EXPECTED_PAIRS = {
    "second_model__to__first_model",
    "second_model__to__second_model",
}
SAFE_SCENARIO_ID = "office_document_file_workflow_basic_v1"
MAX_GOLDEN_PACK_BYTES = 100_000

FIXTURE_ARTIFACTS = {
    registry.MODEL_CATALOG: Path("model_catalog.json"),
    registry.MODEL_COMPARISON_PLAN: Path("plan/model_comparison_plan.json"),
    registry.READINESS_REPORT: Path("readiness/model_comparison_readiness_report.json"),
    registry.NORMALITY_COMPARISON_SUMMARY: Path("normality/normality_comparison_summary.json"),
    registry.MODEL_RESOURCE_SUMMARY: Path("resource/model_resource_summary.json"),
    registry.MODEL_EVALUATION_SCORECARD: Path("scorecard/model_evaluation_scorecard.json"),
    registry.WORKFLOW_BUNDLE: Path("bundle/model_evaluation_workflow_bundle.json"),
    registry.WORKFLOW_RUN_MANIFEST: Path("workflow_run_manifest.json"),
    registry.ARTIFACT_VALIDATION_REPORT: Path("validation/model_evaluation_artifact_validation_report.json"),
}

WORKFLOW_FIXTURE_TYPES = (
    registry.MODEL_COMPARISON_PLAN,
    registry.READINESS_REPORT,
    registry.NORMALITY_COMPARISON_SUMMARY,
    registry.MODEL_RESOURCE_SUMMARY,
    registry.MODEL_EVALUATION_SCORECARD,
    registry.WORKFLOW_BUNDLE,
    registry.WORKFLOW_RUN_MANIFEST,
)

SUSPICIOUS_KEYS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "secret",
    "password",
    "credential",
    "credentials",
    "private_key",
    "key",
    "raw_response",
    "full_prompt",
    "system_prompt",
    "user_prompt",
    "prompt",
}
SECRET_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9]|ghp_[A-Za-z0-9]|hf_[A-Za-z0-9]|bearer\s+|authorization\s*:|"
    r"access_token|refresh_token|id_token|password|secret)",
    re.I,
)
WINDOWS_ABSOLUTE_RE = re.compile(r"[A-Za-z]:[\\/]")
POSIX_ABSOLUTE_RE = re.compile(r"(?<![:\w])/(?:[^\s\"']+/)+[^\s\"']+")
UNC_ABSOLUTE_RE = re.compile(r"\\\\[^\s\"']+")
BAD_PRODUCTION_PHRASES = (
    "production-ready",
    "production ready",
    "recommended for production",
    "production deployment recommendation",
    "final deployment recommendation",
)


def _fixture_path(artifact_type: str) -> Path:
    return GOLDEN_DIR / FIXTURE_ARTIFACTS[artifact_type]


def _load_fixture(artifact_type: str) -> dict[str, Any]:
    payload = json.loads(_fixture_path(artifact_type).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _all_fixture_paths() -> list[Path]:
    return sorted(path for path in GOLDEN_DIR.rglob("*.json") if path.is_file())


def _copy_golden_pack(tmp_path: Path) -> Path:
    target = tmp_path / "golden_workflow"
    shutil.copytree(GOLDEN_DIR, target)
    return target


def _walk_json(value: Any, *, path: str = "$") -> list[tuple[str, Any]]:
    rows = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_walk_json(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_walk_json(child, path=f"{path}[{index}]"))
    return rows


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _normality_batch_summary_path(tmp_path: Path) -> Path:
    entries = [
        {
            "scenario_id": SAFE_SCENARIO_ID,
            "trial_id": "runner_golden_second_to_first_normality",
            "model_pair": {"orchestrator": "second_model", "executor": "first_model"},
            "tags": ["golden_runner_compatibility"],
            "status": "ok",
            "label": "normal",
            "overall_score": 0.88,
            "findings": ["synthetic_fixture_normality"],
            "warnings": [],
        },
        {
            "scenario_id": SAFE_SCENARIO_ID,
            "trial_id": "runner_golden_second_to_second_normality",
            "model_pair": {"orchestrator": "second_model", "executor": "second_model"},
            "tags": ["golden_runner_compatibility"],
            "status": "ok",
            "label": "normal",
            "overall_score": 0.91,
            "findings": ["synthetic_fixture_normality"],
            "warnings": [],
        },
    ]
    return _write_json(
        tmp_path / "inputs" / "normality_batch.json",
        {
            "status": "ok",
            "batch_id": "golden_runner_compatibility_batch",
            "input_count": 1,
            "evaluated_count": len(entries),
            "failed_count": 0,
            "entries": entries,
        },
    )


def _resource_observation_path(tmp_path: Path) -> Path:
    rows = [
        {
            "observation_id": "runner_golden_resource_second_to_first",
            "orchestrator_model_id": "second_model",
            "executor_model_id": "first_model",
            "pair_id": "second_model__to__first_model",
            "scenario_id": SAFE_SCENARIO_ID,
            "trial_id": "runner_golden_second_to_first_resource",
            "runtime_mode": "offline_fixture",
            "backend": "synthetic_fixture",
            "success": True,
            "wall_time_s": 1.2,
            "peak_ram_gb": 2.4,
            "peak_vram_gb": 0.0,
            "tags": ["golden_runner_compatibility"],
        },
        {
            "observation_id": "runner_golden_resource_second_to_second",
            "orchestrator_model_id": "second_model",
            "executor_model_id": "second_model",
            "pair_id": "second_model__to__second_model",
            "scenario_id": SAFE_SCENARIO_ID,
            "trial_id": "runner_golden_second_to_second_resource",
            "runtime_mode": "offline_fixture",
            "backend": "synthetic_fixture",
            "success": True,
            "wall_time_s": 1.4,
            "peak_ram_gb": 3.1,
            "peak_vram_gb": 0.0,
            "tags": ["golden_runner_compatibility"],
        },
    ]
    return _write_json(tmp_path / "inputs" / "resource_observations.json", rows)


def _runner_config(tmp_path: Path) -> ModelEvaluationWorkflowRunConfig:
    return ModelEvaluationWorkflowRunConfig.model_validate(
        {
            "workflow_id": "golden_runner_compatibility",
            "model_catalog_path": str(CATALOG_PATH),
            "scenario_paths": [SCENARIO_PATH],
            "output_dir": str(tmp_path / "workflow"),
            "repetitions_per_pair": 1,
            "include_self_pairs": True,
            "normality_batch_summary_paths": [str(_normality_batch_summary_path(tmp_path))],
            "resource_observation_paths": [str(_resource_observation_path(tmp_path))],
            "tags": ["golden_runner_compatibility"],
        }
    )


def test_all_expected_fixture_files_exist() -> None:
    for relative_path in FIXTURE_ARTIFACTS.values():
        assert (GOLDEN_DIR / relative_path).is_file()


def test_all_fixture_files_parse_as_json_objects() -> None:
    for path in _all_fixture_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path


def test_fixture_files_do_not_contain_absolute_windows_paths() -> None:
    for path in _all_fixture_paths():
        text = path.read_text(encoding="utf-8")
        assert WINDOWS_ABSOLUTE_RE.search(text) is None, path
        assert UNC_ABSOLUTE_RE.search(text) is None, path


def test_fixture_files_do_not_contain_absolute_posix_paths() -> None:
    for path in _all_fixture_paths():
        text = path.read_text(encoding="utf-8")
        assert POSIX_ABSOLUTE_RE.search(text) is None, path


def test_fixture_files_do_not_contain_secret_like_values_or_forbidden_keys() -> None:
    for path in _all_fixture_paths():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for field_path, value in _walk_json(payload):
            if isinstance(value, dict):
                for key in value:
                    assert key.strip().lower() not in SUSPICIOUS_KEYS, (path, key)
            if isinstance(value, str):
                assert SECRET_VALUE_RE.search(value) is None, (path, field_path)


def test_fixture_files_do_not_contain_production_overclaim_wording() -> None:
    for path in _all_fixture_paths():
        text = path.read_text(encoding="utf-8").lower()
        assert all(phrase not in text for phrase in BAD_PRODUCTION_PHRASES), path
        for field_path, value in _walk_json(json.loads(path.read_text(encoding="utf-8"))):
            if isinstance(value, str) and "production recommendation" in value.lower():
                assert "not a production recommendation" in value.lower(), (path, field_path)


def test_fixture_files_do_not_contain_gguf_content_or_absolute_gguf_paths() -> None:
    for path in _all_fixture_paths():
        text = path.read_text(encoding="utf-8").lower()
        assert ".gguf" not in text, path


def test_registry_resolves_every_fixture_artifact_type() -> None:
    for artifact_type in FIXTURE_ARTIFACTS:
        assert registry.get_artifact_schema_info(artifact_type).artifact_type == artifact_type


def test_contract_validation_passes_for_every_fixture_artifact() -> None:
    for artifact_type in FIXTURE_ARTIFACTS:
        issues = validate_artifact_against_contract(_load_fixture(artifact_type), artifact_type)
        assert issues == [], artifact_type


def test_artifact_validator_accepts_golden_workflow_pack() -> None:
    report = validate_model_evaluation_workflow_output_dir(GOLDEN_DIR)

    assert report.status == "valid"
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.cross_link_summary["plan_pair_count"] == 2
    assert report.cross_link_summary["scorecard_pair_count"] == 2


def test_validation_fixture_validates_against_validation_report_contract() -> None:
    issues = validate_artifact_against_contract(
        _load_fixture(registry.ARTIFACT_VALIDATION_REPORT),
        registry.ARTIFACT_VALIDATION_REPORT,
    )

    assert issues == []


def test_bundle_fixture_references_required_artifacts_as_present() -> None:
    bundle = _load_fixture(registry.WORKFLOW_BUNDLE)
    for artifact_type in registry.get_required_workflow_artifact_types():
        row = bundle["artifacts"][artifact_type]
        assert row["present"] is True
        assert row["status"] == "ok"


def test_workflow_manifest_fixture_references_expected_relative_locations_only() -> None:
    manifest = _load_fixture(registry.WORKFLOW_RUN_MANIFEST)
    known_paths = registry.get_workflow_known_relative_paths()
    for artifact_type, relative_path in known_paths.items():
        value = manifest["artifact_paths"][artifact_type]
        assert value == relative_path
        assert not Path(value).is_absolute()


def test_scorecard_fixture_includes_normality_and_resource_metrics_for_a_pair() -> None:
    scorecard = _load_fixture(registry.MODEL_EVALUATION_SCORECARD)

    assert any(
        pair.get("normality_metrics") and pair.get("resource_metrics")
        for pair in scorecard["model_pairs"]
    )


def test_plan_fixture_includes_expected_model_pairs() -> None:
    plan = _load_fixture(registry.MODEL_COMPARISON_PLAN)
    pair_ids = {pair["pair_id"] for pair in plan["candidate_pairs"]}

    assert pair_ids == EXPECTED_PAIRS


def test_readiness_counts_match_plan_fixture() -> None:
    plan = _load_fixture(registry.MODEL_COMPARISON_PLAN)
    readiness = _load_fixture(registry.READINESS_REPORT)

    assert readiness["candidate_pair_count"] == len(plan["candidate_pairs"])
    assert readiness["trial_count"] == len(plan["trials"])
    assert readiness["plan_id"] == plan["plan_id"]


def test_unified_cli_validate_accepts_tmp_copy_of_golden_pack(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir = _copy_golden_pack(tmp_path)

    code = model_evaluation_cli_main(
        [
            "validate",
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
            "--validation-id",
            "golden_fixture_cli_validation",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "valid"
    assert payload["checked_artifact_count"] == len(WORKFLOW_FIXTURE_TYPES)
    assert (tmp_path / "validation" / "model_evaluation_artifact_validation_report.json").is_file()


def test_unified_cli_schema_accepts_fixture_artifact_types(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for artifact_type in FIXTURE_ARTIFACTS:
        code = model_evaluation_cli_main(["schema", "--artifact-type", artifact_type])
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert payload["artifact_count"] == 1
        assert payload["artifacts"][0]["artifact_type"] == artifact_type


def test_unified_cli_version_schema_versions_match_fixture_schema_versions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(["version"])
    payload = json.loads(capsys.readouterr().out)
    supported = set(payload["supported_schema_versions"])

    assert code == 0
    for artifact_type in FIXTURE_ARTIFACTS:
        assert _load_fixture(artifact_type)["schema_version"] in supported


def test_golden_fixture_pack_remains_small() -> None:
    total_size = sum(path.stat().st_size for path in _all_fixture_paths())

    assert total_size < MAX_GOLDEN_PACK_BYTES


def test_no_reports_or_experiments_files_are_written_by_fixture_cli_validation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir = _copy_golden_pack(tmp_path)

    code = model_evaluation_cli_main(
        [
            "validate",
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
        ]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"
    assert not (PROJECT_ROOT / "reports" / "model_evaluation_artifact_validation_report.json").exists()
    assert not (PROJECT_ROOT / "experiments" / "model_evaluation_artifact_validation_report.json").exists()


def test_no_runtime_model_gguf_probe_browser_or_office_calls_are_made(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_dir = _copy_golden_pack(tmp_path)
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_gguf_exists(self: Path) -> bool:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF exists check")
        return original_exists(self)

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF read")
        return original_read_text(self, *args, **kwargs)

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("golden fixture validation must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "valid"


def test_runner_output_remains_compatible_with_golden_expectations(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(_runner_config(tmp_path))
    output_dir = tmp_path / "workflow"
    known_paths = registry.get_workflow_known_relative_paths()

    assert result.status == "ok"
    assert set(result.artifact_paths).issuperset(known_paths)
    for artifact_type in WORKFLOW_FIXTURE_TYPES:
        relative_path = known_paths[artifact_type]
        generated_path = output_dir / relative_path
        generated = json.loads(generated_path.read_text(encoding="utf-8"))
        golden = _load_fixture(artifact_type)
        schema_info = registry.get_artifact_schema_info(artifact_type)
        contract = get_artifact_schema_contract(artifact_type)
        contract_fields = {field.name for field in contract.required_fields}

        assert generated_path.name == Path(relative_path).name
        assert generated["schema_version"] == golden["schema_version"] == schema_info.schema_version
        assert contract_fields.issubset(generated)
        if "no_runtime_execution" in generated:
            assert generated["no_runtime_execution"] is True
        if contract.status_allowed_values:
            assert generated["status"] in contract.status_allowed_values


def test_exported_contracts_include_every_golden_fixture_artifact_type() -> None:
    payload = export_artifact_schema_contracts()
    artifact_types = {artifact["artifact_type"] for artifact in payload["artifacts"]}

    json.dumps(payload, ensure_ascii=False)
    assert set(FIXTURE_ARTIFACTS).issubset(artifact_types)


def test_compact_cli_schema_output_includes_all_fixture_artifact_types(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(["schema"])
    payload = json.loads(capsys.readouterr().out)
    artifact_types = {artifact["artifact_type"] for artifact in payload["artifacts"]}

    assert code == 0
    assert set(FIXTURE_ARTIFACTS).issubset(artifact_types)
    assert all("required_fields" not in artifact for artifact in payload["artifacts"])
