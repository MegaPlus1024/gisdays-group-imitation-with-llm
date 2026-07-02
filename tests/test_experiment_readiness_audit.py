from __future__ import annotations

from pathlib import Path

from agent.experiment_readiness_audit import (
    ExperimentReadinessAuditConfig,
    ExperimentReadinessAuditResult,
    ExperimentReadinessAuditor,
    ReadinessCheck,
    load_experiment_readiness_audit_config,
    make_path_check,
    path_exists,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_experiment_readiness_audit_config_defaults_are_valid() -> None:
    cfg = ExperimentReadinessAuditConfig()
    assert cfg.audit_id == "experiment_readiness_audit_v1"
    assert cfg.project_root == "."


def test_load_experiment_readiness_audit_config_loads_example() -> None:
    cfg = load_experiment_readiness_audit_config(
        _repo_root() / "configs/experiment_readiness_audit.example.json"
    )
    assert cfg.require_behavioral_readiness is True


def test_path_exists_true_false(tmp_path: Path) -> None:
    (tmp_path / "present.txt").write_text("ok", encoding="utf-8")
    assert path_exists(tmp_path, "present.txt") is True
    assert path_exists(tmp_path, "missing.txt") is False


def test_make_path_check_pass_for_existing_required(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("ok", encoding="utf-8")
    check = make_path_check(
        check_id="c1",
        area="runtime_foundation",
        severity="required",
        project_root=tmp_path,
        relative_path="a.txt",
        message_if_present="present",
        message_if_missing="missing",
    )
    assert check.status == "pass"


def test_make_path_check_fail_for_missing_required(tmp_path: Path) -> None:
    check = make_path_check(
        check_id="c2",
        area="runtime_foundation",
        severity="required",
        project_root=tmp_path,
        relative_path="missing.txt",
        message_if_present="present",
        message_if_missing="missing",
    )
    assert check.status == "fail"


def test_make_path_check_warning_for_missing_recommended(tmp_path: Path) -> None:
    check = make_path_check(
        check_id="c3",
        area="runtime_foundation",
        severity="recommended",
        project_root=tmp_path,
        relative_path="missing.txt",
        message_if_present="present",
        message_if_missing="missing",
    )
    assert check.status == "warning"


def test_experiment_readiness_audit_result_helpers_work() -> None:
    checks = [
        ReadinessCheck(
            check_id="a",
            area="project_framing",
            severity="required",
            status="pass",
            message="ok",
        ),
        ReadinessCheck(
            check_id="b",
            area="runtime_foundation",
            severity="required",
            status="fail",
            message="missing",
        ),
        ReadinessCheck(
            check_id="c",
            area="runtime_foundation",
            severity="recommended",
            status="warning",
            message="warn",
        ),
    ]
    result = ExperimentReadinessAuditResult(
        audit_id="x",
        ready=False,
        required_pass_count=1,
        required_fail_count=1,
        warning_count=1,
        optional_missing_count=0,
        checks=checks,
        summary="not ready",
    )
    assert len(result.failed_required_checks()) == 1
    assert len(result.warnings()) == 1
    by_area = result.checks_by_area()
    assert "runtime_foundation" in by_area
    md = result.as_markdown()
    assert "x" in md
    assert "ready: False" in md


def test_run_audit_returns_result_with_checks() -> None:
    auditor = ExperimentReadinessAuditor(
        ExperimentReadinessAuditConfig(project_root=str(_repo_root()))
    )
    result = auditor.run_audit()
    assert result.audit_id == "experiment_readiness_audit_v1"
    assert len(result.checks) > 0


def test_run_audit_includes_project_framing_checks() -> None:
    auditor = ExperimentReadinessAuditor(
        ExperimentReadinessAuditConfig(project_root=str(_repo_root()))
    )
    ids = {c.check_id for c in auditor.run_audit().checks}
    assert "readme_exists" in ids
    assert "objective_doc_exists" in ids


def test_run_audit_includes_activity_profile_checks() -> None:
    auditor = ExperimentReadinessAuditor(
        ExperimentReadinessAuditConfig(project_root=str(_repo_root()))
    )
    ids = {c.check_id for c in auditor.run_audit().checks}
    assert "office_profile" in ids
    assert "profiles_loadable" in ids


def test_run_audit_includes_evaluation_scenario_checks() -> None:
    auditor = ExperimentReadinessAuditor(
        ExperimentReadinessAuditConfig(project_root=str(_repo_root()))
    )
    ids = {c.check_id for c in auditor.run_audit().checks}
    assert "scenario_office" in ids
    assert "scenario_references_resolve" in ids


def test_run_audit_includes_model_behavior_harness_checks() -> None:
    auditor = ExperimentReadinessAuditor(
        ExperimentReadinessAuditConfig(project_root=str(_repo_root()))
    )
    ids = {c.check_id for c in auditor.run_audit().checks}
    assert "model_behavior_harness_module" in ids
    assert "model_behavior_config_loadable" in ids


def test_if_required_files_exist_result_ready_is_true() -> None:
    auditor = ExperimentReadinessAuditor(
        ExperimentReadinessAuditConfig(project_root=str(_repo_root()))
    )
    result = auditor.run_audit()
    assert result.ready is True
    assert result.required_fail_count == 0


def test_ready_result_has_next_recommended_actions() -> None:
    auditor = ExperimentReadinessAuditor(
        ExperimentReadinessAuditConfig(project_root=str(_repo_root()))
    )
    result = auditor.run_audit()
    if result.ready:
        assert any("Select model comparison set" in x for x in result.next_recommended_actions)


def test_docs_exists_and_mentions_experiments_and_evaluation() -> None:
    doc_path = _repo_root() / "docs/ai/experiment_readiness_audit.md"
    assert doc_path.exists()
    text = doc_path.read_text(encoding="utf-8").lower()
    assert "experiments and evaluation" in text
