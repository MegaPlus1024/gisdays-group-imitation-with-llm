from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.model_catalog import ModelCatalog, load_model_catalog
from src.agent.model_comparison_plan import (
    ModelComparisonPlan,
    ModelComparisonPlanConfig,
    build_model_comparison_plan,
    write_model_comparison_plan,
)
from src.agent.model_comparison_readiness import (
    MODEL_COMPARISON_READINESS_REPORT_FILENAME,
    MODEL_COMPARISON_READINESS_PREVIEW_FILENAME,
    MODEL_COMPARISON_READINESS_SCHEMA_VERSION,
    ModelComparisonReadinessReport,
    validate_model_comparison_readiness,
    write_model_comparison_readiness_report,
)
from src.agent.model_comparison_readiness_cli import main as readiness_cli_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
REGISTRY_PATH = "configs/script_registry.example.json"


def _catalog() -> ModelCatalog:
    return load_model_catalog(CATALOG_PATH)


def _plan(**overrides: object) -> ModelComparisonPlan:
    return build_model_comparison_plan(
        _catalog(),
        [SCENARIO_PATH],
        ModelComparisonPlanConfig.model_validate(
            {
                "plan_id": "readiness_test_plan",
                "include_self_pairs": True,
                **overrides,
            }
        ),
        project_root=PROJECT_ROOT,
    )


def _payload(plan: ModelComparisonPlan) -> dict[str, object]:
    return plan.model_dump(mode="json")


def _from_payload(payload: dict[str, object]) -> ModelComparisonPlan:
    return ModelComparisonPlan.model_validate(payload)


def _issue_codes(report: ModelComparisonReadinessReport) -> set[str]:
    return {issue.code for issue in report.issues}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_offline_model_comparison_plan_is_ready() -> None:
    report = validate_model_comparison_readiness(
        _plan(),
        model_catalog=_catalog(),
        registry_path=REGISTRY_PATH,
        scenario_root=PROJECT_ROOT,
    )

    assert report.schema_version == MODEL_COMPARISON_READINESS_SCHEMA_VERSION
    assert report.status == "ready"
    assert report.no_runtime_execution is True
    assert report.checked_catalog is True
    assert report.checked_scenarios is True
    assert report.checked_registry is True
    assert report.checked_evaluators is True
    assert report.trial_count == 2
    assert report.candidate_pair_count == 2
    assert report.summary["error_count"] == 0
    assert report.summary["warning_count"] == 0
    assert "scenario_execute_actions_disabled" in _issue_codes(report)
    assert "scenario_artifact_workspace_policy" in _issue_codes(report)
    assert "registry_actions_available" in _issue_codes(report)
    assert "evaluator_importable" in _issue_codes(report)


def test_unknown_pair_reference_is_not_ready() -> None:
    payload = _payload(_plan())
    payload["trials"][0]["pair_id"] = "missing_pair"
    plan = _from_payload(payload)

    report = validate_model_comparison_readiness(plan, model_catalog=_catalog())

    assert report.status == "not_ready"
    assert "trial_unknown_pair" in _issue_codes(report)


def test_duplicate_trial_ids_are_errors() -> None:
    payload = _payload(_plan())
    payload["trials"][1]["trial_id"] = payload["trials"][0]["trial_id"]
    plan = _from_payload(payload)

    report = validate_model_comparison_readiness(plan, model_catalog=_catalog())

    assert report.status == "not_ready"
    assert "duplicate_trial_id" in _issue_codes(report)


def test_unknown_catalog_model_is_error() -> None:
    payload = _payload(_plan(include_self_pairs=False))
    payload["candidate_pairs"][0]["executor_model_id"] = "unknown_executor"
    payload["trials"][0]["executor_model_id"] = "unknown_executor"
    plan = _from_payload(payload)

    report = validate_model_comparison_readiness(plan, model_catalog=_catalog())

    assert report.status == "not_ready"
    assert "catalog_model_missing" in _issue_codes(report)


def test_explicit_role_mismatch_pair_is_warning_not_error() -> None:
    plan = _plan(include_role_mismatch_pairs=True)

    report = validate_model_comparison_readiness(plan, model_catalog=_catalog())

    mismatch = [
        issue
        for issue in report.issues
        if issue.code == "orchestrator_role_not_catalog_candidate"
        and issue.reference == "first_model__to__first_model"
    ]
    assert report.status == "ready_with_warnings"
    assert mismatch
    assert mismatch[0].severity == "warning"


def test_absolute_scenario_path_is_rejected_by_readiness_validator() -> None:
    payload = _payload(_plan(include_self_pairs=False))
    absolute_path = "\\".join(["C:", "Temp", "outside_workspace", "scenario.json"])
    payload["scenarios"][0]["scenario_path"] = absolute_path
    payload["trials"][0]["scenario_path"] = absolute_path
    plan = _from_payload(payload)

    report = validate_model_comparison_readiness(plan)

    assert report.status == "not_ready"
    assert "scenario_path_unsafe" in _issue_codes(report)


def test_traversal_scenario_path_is_rejected_by_readiness_validator() -> None:
    payload = _payload(_plan(include_self_pairs=False))
    payload["scenarios"][0]["scenario_path"] = "../scenario.json"
    payload["trials"][0]["scenario_path"] = "../scenario.json"
    plan = _from_payload(payload)

    report = validate_model_comparison_readiness(plan)

    assert report.status == "not_ready"
    assert "scenario_path_unsafe" in _issue_codes(report)


def test_office_role_broad_action_is_warning(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "office.json"
    role_path = tmp_path / "roles" / "office_role.json"
    registry_path = tmp_path / "registry.json"
    scenario_path.parent.mkdir(parents=True)
    role_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "registry_id": "test_registry",
                "schema_version": "script_registry_v1",
                "scripts": [
                    {"name": "office_create_docx", "description": "d"},
                    {"name": "run_shell_command", "description": "d"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    role_path.write_text(
        json.dumps(
            {
                "role_id": "office_document_worker",
                "resources": {"tools": ["office_create_docx", "run_shell_command"]},
                "constraints": {"allowed_action_names": ["office_create_docx", "run_shell_command"]},
                "metadata": {"optional_office_document_role": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    scenario_path.write_text(
        json.dumps(
            {
                "scenario_id": "synthetic_office_document",
                "execute_actions": False,
                "agents": [{"role_template_path": "roles/office_role.json"}],
                "metadata": {
                    "offline_fake_compatible": True,
                    "write_path_policy": "artifact_workspace_only",
                    "expected_safe_actions": ["office_create_docx"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = _payload(_plan(include_self_pairs=False))
    payload["scenarios"][0]["scenario_id"] = "synthetic_office_document"
    payload["scenarios"][0]["scenario_path"] = "scenarios/office.json"
    payload["trials"][0]["scenario_id"] = "synthetic_office_document"
    payload["trials"][0]["scenario_path"] = "scenarios/office.json"
    plan = _from_payload(payload)

    report = validate_model_comparison_readiness(
        plan,
        registry_path=registry_path,
        scenario_root=tmp_path,
    )

    assert report.status == "ready_with_warnings"
    assert "broad_action_in_office_role" in _issue_codes(report)
    assert "registry_action_missing" not in _issue_codes(report)


def test_missing_role_action_is_registry_error(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenarios" / "office.json"
    role_path = tmp_path / "roles" / "office_role.json"
    registry_path = tmp_path / "registry.json"
    scenario_path.parent.mkdir(parents=True)
    role_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "registry_id": "test_registry",
                "schema_version": "script_registry_v1",
                "scripts": [{"name": "office_create_docx", "description": "d"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    role_path.write_text(
        json.dumps(
            {
                "role_id": "office_document_worker",
                "resources": {"tools": ["office_create_docx", "office_missing_action"]},
                "metadata": {"optional_office_document_role": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    scenario_path.write_text(
        json.dumps(
            {
                "scenario_id": "synthetic_office_document",
                "execute_actions": False,
                "agents": [{"role_template_path": "roles/office_role.json"}],
                "metadata": {
                    "offline_fake_compatible": True,
                    "write_path_policy": "artifact_workspace_only",
                    "expected_safe_actions": ["office_create_docx"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = _payload(_plan(include_self_pairs=False))
    payload["scenarios"][0]["scenario_id"] = "synthetic_office_document"
    payload["scenarios"][0]["scenario_path"] = "scenarios/office.json"
    payload["trials"][0]["scenario_id"] = "synthetic_office_document"
    payload["trials"][0]["scenario_path"] = "scenarios/office.json"
    plan = _from_payload(payload)

    report = validate_model_comparison_readiness(
        plan,
        registry_path=registry_path,
        scenario_root=tmp_path,
    )

    assert report.status == "not_ready"
    assert "registry_action_missing" in _issue_codes(report)


def test_report_writer_outputs_json_and_optional_markdown(tmp_path: Path) -> None:
    report = validate_model_comparison_readiness(
        _plan(include_self_pairs=False),
        model_catalog=_catalog(),
        registry_path=REGISTRY_PATH,
        scenario_root=PROJECT_ROOT,
    )

    report_path, preview_path = write_model_comparison_readiness_report(
        report,
        tmp_path / "readiness",
        write_markdown_preview=True,
    )
    payload = _load_json(report_path)

    assert report_path == tmp_path / "readiness" / MODEL_COMPARISON_READINESS_REPORT_FILENAME
    assert preview_path == tmp_path / "readiness" / MODEL_COMPARISON_READINESS_PREVIEW_FILENAME
    assert payload["schema_version"] == MODEL_COMPARISON_READINESS_SCHEMA_VERSION
    assert payload["report_path_relative"] == MODEL_COMPARISON_READINESS_REPORT_FILENAME
    assert payload["markdown_preview_path_relative"] == MODEL_COMPARISON_READINESS_PREVIEW_FILENAME
    assert preview_path is not None and preview_path.is_file()


def test_cli_writes_concise_readiness_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan = _plan(include_self_pairs=False)
    plan_path = write_model_comparison_plan(plan, tmp_path / "plan")

    code = readiness_cli_main(
        [
            "--plan",
            str(plan_path),
            "--model-catalog",
            str(CATALOG_PATH),
            "--registry",
            REGISTRY_PATH,
            "--scenario-root",
            str(PROJECT_ROOT),
            "--output-dir",
            str(tmp_path / "readiness"),
            "--write-markdown-preview",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ready"
    assert payload["plan_id"] == "readiness_test_plan"
    assert payload["trial_count"] == 1
    assert payload["error_count"] == 0
    assert payload["warning_count"] == 0
    assert payload["report_path"] == MODEL_COMPARISON_READINESS_REPORT_FILENAME
    assert (tmp_path / "readiness" / MODEL_COMPARISON_READINESS_REPORT_FILENAME).is_file()
    assert (tmp_path / "readiness" / MODEL_COMPARISON_READINESS_PREVIEW_FILENAME).is_file()


def test_cli_strict_mode_returns_nonzero_on_warnings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan(include_role_mismatch_pairs=True)
    plan_path = write_model_comparison_plan(plan, tmp_path / "plan")

    code = readiness_cli_main(
        [
            "--plan",
            str(plan_path),
            "--model-catalog",
            str(CATALOG_PATH),
            "--registry",
            REGISTRY_PATH,
            "--scenario-root",
            str(PROJECT_ROOT),
            "--output-dir",
            str(tmp_path / "readiness"),
            "--strict",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "ready_with_warnings"
    assert payload["warning_count"] > 0


def test_cli_reports_malformed_plan_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "bad_plan.json"
    plan_path.write_text("{not-json", encoding="utf-8")

    code = readiness_cli_main(["--plan", str(plan_path), "--output-dir", str(tmp_path / "out")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["report_path"] is None


def test_cli_reports_missing_plan_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = readiness_cli_main(["--plan", str(tmp_path / "missing.json"), "--output-dir", str(tmp_path / "out")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["report_path"] is None


def test_readiness_validator_does_not_check_or_read_gguf_files(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = _catalog()
    original_exists = Path.exists
    original_read_text = Path.read_text

    def forbid_gguf_exists(self: Path) -> bool:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF exists check")
        return original_exists(self)

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)

    report = validate_model_comparison_readiness(
        _plan(),
        model_catalog=catalog,
        registry_path=REGISTRY_PATH,
        scenario_root=PROJECT_ROOT,
    )

    assert report.status == "ready"
    assert not (PROJECT_ROOT / "reports" / MODEL_COMPARISON_READINESS_REPORT_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_COMPARISON_READINESS_REPORT_FILENAME).exists()
