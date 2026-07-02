from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .activity_profile import load_activity_profile
from .behavioral_fixtures import load_behavioral_expectations
from .evaluation_scenarios import (
    load_evaluation_scenario,
    verify_evaluation_scenario_references,
)
from .model_behavior_evaluation import load_model_behavior_evaluation_config

ReadinessCheckSeverity = Literal["required", "recommended", "optional"]
ReadinessCheckStatus = Literal["pass", "fail", "warning", "skipped"]
ReadinessArea = Literal[
    "project_framing",
    "runtime_foundation",
    "agent_architecture",
    "parameterized_scripts",
    "behavioral_evaluation",
    "evaluation_scenarios",
    "model_behavior_harness",
    "test_coverage",
    "experiment_readiness",
]


class ReadinessCheck(BaseModel):
    check_id: str
    area: ReadinessArea
    severity: ReadinessCheckSeverity
    status: ReadinessCheckStatus
    message: str
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("check_id", "message")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("check_id and message must be non-empty.")
        return value


class ExperimentReadinessAuditConfig(BaseModel):
    audit_id: str = "experiment_readiness_audit_v1"
    project_root: str = "."
    require_behavioral_readiness: bool = True
    require_evaluation_scenarios: bool = True
    require_model_behavior_harness: bool = True
    require_runtime_scripts: bool = True
    require_tests_present: bool = True
    treat_missing_optional_artifacts_as_warning: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("audit_id", "project_root")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("audit_id and project_root must be non-empty.")
        return value


class ExperimentReadinessAuditResult(BaseModel):
    audit_id: str
    ready: bool
    required_pass_count: int
    required_fail_count: int
    warning_count: int
    optional_missing_count: int
    checks: list[ReadinessCheck]
    summary: str
    next_recommended_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("audit_id", "summary")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("audit_id and summary must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_counts(self) -> ExperimentReadinessAuditResult:
        ints = [
            self.required_pass_count,
            self.required_fail_count,
            self.warning_count,
            self.optional_missing_count,
        ]
        if any(v < 0 for v in ints):
            raise ValueError("counts must be >= 0.")
        if not self.checks:
            raise ValueError("checks must not be empty.")
        if len(self.next_recommended_actions) != len(set(self.next_recommended_actions)):
            raise ValueError("next_recommended_actions must not contain duplicates.")
        return self

    def failed_required_checks(self) -> list[ReadinessCheck]:
        return [
            c
            for c in self.checks
            if c.severity == "required" and c.status == "fail"
        ]

    def warnings(self) -> list[ReadinessCheck]:
        return [c for c in self.checks if c.status == "warning"]

    def checks_by_area(self) -> dict[str, list[ReadinessCheck]]:
        out: dict[str, list[ReadinessCheck]] = {}
        for c in self.checks:
            out.setdefault(c.area, []).append(c)
        return out

    def as_markdown(self) -> str:
        lines = [
            f"# {self.audit_id}",
            f"ready: {self.ready}",
            f"required_pass_count: {self.required_pass_count}",
            f"required_fail_count: {self.required_fail_count}",
            f"warning_count: {self.warning_count}",
            "",
            "## Checks",
        ]
        for c in self.checks:
            lines.append(f"- [{c.status}] ({c.severity}) {c.check_id}: {c.message}")
        return "\n".join(lines)


def path_exists(project_root: Path, relative_path: str) -> bool:
    return (project_root / relative_path).exists()


def make_path_check(
    check_id: str,
    area: ReadinessArea,
    severity: ReadinessCheckSeverity,
    project_root: Path,
    relative_path: str,
    message_if_present: str,
    message_if_missing: str,
) -> ReadinessCheck:
    exists = path_exists(project_root, relative_path)
    if exists:
        status: ReadinessCheckStatus = "pass"
        msg = message_if_present
    else:
        status = "fail" if severity == "required" else "warning"
        msg = message_if_missing
    return ReadinessCheck(
        check_id=check_id,
        area=area,
        severity=severity,
        status=status,
        message=msg,
        path=relative_path,
    )


def load_experiment_readiness_audit_config(path: str | Path) -> ExperimentReadinessAuditConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ExperimentReadinessAuditConfig.model_validate(payload)


class ExperimentReadinessAuditor:
    def __init__(self, config: ExperimentReadinessAuditConfig | None = None) -> None:
        self.config = config or ExperimentReadinessAuditConfig()

    def run_audit(self) -> ExperimentReadinessAuditResult:
        project_root = Path(self.config.project_root).resolve()
        checks: list[ReadinessCheck] = []

        def add_path(
            check_id: str,
            area: ReadinessArea,
            severity: ReadinessCheckSeverity,
            rel: str,
        ) -> None:
            checks.append(
                make_path_check(
                    check_id=check_id,
                    area=area,
                    severity=severity,
                    project_root=project_root,
                    relative_path=rel,
                    message_if_present=f"Found required artifact: {rel}",
                    message_if_missing=f"Missing artifact: {rel}",
                )
            )

        # Project framing
        add_path("readme_exists", "project_framing", "required", "README.md")
        add_path(
            "objective_doc_exists",
            "project_framing",
            "required",
            "docs/ai/project_objective_normal_activity_v1.md",
        )

        # Runtime foundation
        runtime_severity: ReadinessCheckSeverity = (
            "required" if self.config.require_runtime_scripts else "recommended"
        )
        add_path("requirements_exists", "runtime_foundation", runtime_severity, "requirements.txt")
        add_path("run_llama_smoke_script", "runtime_foundation", runtime_severity, "scripts/run_llama_smoke.py")
        add_path("run_runtime_baseline_script", "runtime_foundation", runtime_severity, "scripts/run_runtime_baseline.py")
        add_path("compare_runtime_script", "runtime_foundation", runtime_severity, "scripts/compare_runtime_baselines.py")
        add_path("model_registry_doc", "runtime_foundation", "recommended", "docs/ai/model_registry.md")
        add_path("model_registry_config", "runtime_foundation", "recommended", "configs/models.local.example.json")
        add_path(
            "baseline_summary_local_model",
            "runtime_foundation",
            "recommended",
            "experiments/baselines/local_runtime_baseline_v1/summary.json",
        )
        comp_path = "experiments/comparisons/two_model_runtime_comparison_v1/comparison.json"
        comp_tpl = "experiments/comparisons/two_model_runtime_comparison_v1/comparison_template.json"
        if path_exists(project_root, comp_path) or path_exists(project_root, comp_tpl):
            checks.append(
                ReadinessCheck(
                    check_id="comparison_artifact_present",
                    area="runtime_foundation",
                    severity="recommended",
                    status="pass",
                    message="Found comparison artifact (comparison.json or comparison_template.json).",
                    path=comp_path if path_exists(project_root, comp_path) else comp_tpl,
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    check_id="comparison_artifact_present",
                    area="runtime_foundation",
                    severity="recommended",
                    status="warning",
                    message="Missing comparison artifact (comparison.json/comparison_template.json).",
                )
            )
        for rel, cid in [
            ("experiments/model_behavior/results", "optional_behavior_results_dir"),
            ("reports/experiments", "optional_experiment_reports_dir"),
        ]:
            checks.append(
                make_path_check(
                    check_id=cid,
                    area="experiment_readiness",
                    severity="optional",
                    project_root=project_root,
                    relative_path=rel,
                    message_if_present=f"Found optional artifact: {rel}",
                    message_if_missing=f"Optional artifact not present yet: {rel}",
                )
            )

        # Agent architecture
        for rel, cid in [
            ("src/agent/state.py", "agent_state_module"),
            ("src/agent/action_contract.py", "next_action_contract_module"),
            ("src/agent/prompt_contract.py", "prompt_contract_module"),
            ("src/agent/action_selector.py", "action_selector_module"),
            ("src/agent/script_registry.py", "script_registry_module"),
            ("src/agent/script_execution_bridge.py", "script_execution_bridge_module"),
            ("src/agent/execution_history.py", "execution_history_module"),
            ("src/agent/recovery_loop.py", "recovery_loop_module"),
            ("src/agent/autonomous_stop_criteria.py", "autonomous_stop_criteria_module"),
            ("src/agent/multi_agent_orchestrator.py", "multi_agent_orchestrator_module"),
        ]:
            add_path(cid, "agent_architecture", "required", rel)

        # Parameterized scripts
        for rel, cid in [
            ("src/agent/scripts/file_activity.py", "file_activity_script"),
            ("src/agent/scripts/browser_activity.py", "browser_activity_script"),
            ("src/agent/scripts/office_document_activity.py", "office_activity_script"),
            ("src/agent/scripts/shell_command_activity.py", "shell_activity_script"),
        ]:
            add_path(cid, "parameterized_scripts", "required", rel)

        # Behavioral evaluation readiness
        behavioral_severity: ReadinessCheckSeverity = (
            "required" if self.config.require_behavioral_readiness else "recommended"
        )
        for rel, cid in [
            ("src/agent/activity_profile.py", "activity_profile_module"),
            ("src/agent/activity_evaluator.py", "activity_evaluator_module"),
            ("configs/activity_profiles/office_worker.json", "office_profile"),
            ("configs/activity_profiles/developer.json", "developer_profile"),
            ("configs/activity_profiles/student_researcher.json", "student_profile"),
            ("docs/ai/normal_activity_profile_schema_v1.md", "activity_profile_doc"),
            ("docs/ai/normal_activity_trajectory_evaluator_v1.md", "activity_evaluator_doc"),
            ("src/agent/behavioral_fixtures.py", "behavioral_fixtures_module"),
            ("tests/fixtures/behavioral_trajectories/README.md", "behavioral_fixtures_readme"),
            (
                "tests/fixtures/behavioral_trajectories/expected_results/behavioral_expectations.json",
                "behavioral_expectations_fixture",
            ),
            ("tests/fixtures/behavioral_trajectories/trajectories/office_worker_normal.json", "fixture_office_normal"),
            ("tests/fixtures/behavioral_trajectories/trajectories/developer_normal.json", "fixture_dev_normal"),
            ("tests/fixtures/behavioral_trajectories/trajectories/student_researcher_normal.json", "fixture_student_normal"),
        ]:
            add_path(cid, "behavioral_evaluation", behavioral_severity, rel)

        # Evaluation scenarios
        scenario_severity: ReadinessCheckSeverity = (
            "required" if self.config.require_evaluation_scenarios else "recommended"
        )
        for rel, cid in [
            ("src/agent/evaluation_scenarios.py", "evaluation_scenarios_module"),
            ("configs/evaluation_scenarios/office_worker_basic_session.json", "scenario_office"),
            ("configs/evaluation_scenarios/developer_project_maintenance.json", "scenario_dev"),
            ("configs/evaluation_scenarios/student_researcher_experiment_report.json", "scenario_student"),
            ("configs/evaluation_scenarios/mixed_roles_multi_agent_session.json", "scenario_multi"),
            ("docs/ai/evaluation_scenario_v1.md", "evaluation_scenario_doc"),
        ]:
            add_path(cid, "evaluation_scenarios", scenario_severity, rel)

        # Model behavior harness
        harness_severity: ReadinessCheckSeverity = (
            "required" if self.config.require_model_behavior_harness else "recommended"
        )
        for rel, cid in [
            ("src/agent/model_behavior_evaluation.py", "model_behavior_harness_module"),
            ("configs/model_behavior_evaluation.example.json", "model_behavior_harness_config"),
            ("docs/ai/model_behavior_evaluation_v1.md", "model_behavior_harness_doc"),
        ]:
            add_path(cid, "model_behavior_harness", harness_severity, rel)

        # Test coverage
        tests_severity: ReadinessCheckSeverity = (
            "required" if self.config.require_tests_present else "recommended"
        )
        for rel, cid in [
            ("tests/test_normal_activity_profile_schema.py", "test_activity_profile"),
            ("tests/test_normal_activity_trajectory_evaluator.py", "test_activity_evaluator"),
            ("tests/test_behavioral_validation_fixtures.py", "test_behavioral_fixtures"),
            ("tests/test_evaluation_scenario_v1.py", "test_evaluation_scenario"),
            ("tests/test_model_behavior_evaluation.py", "test_model_behavior_harness"),
        ]:
            add_path(cid, "test_coverage", tests_severity, rel)
        for rel, cid in [
            ("tests/test_script_execution_bridge.py", "recommended_bridge_test"),
            ("tests/test_multi_agent_orchestrator_smoke.py", "recommended_multi_agent_test"),
            ("tests/test_autonomous_session_stop_criteria.py", "recommended_stop_criteria_test"),
        ]:
            add_path(cid, "test_coverage", "recommended", rel)

        # Semantic checks
        checks.extend(
            self._semantic_checks(
                project_root=project_root,
                behavioral_severity=behavioral_severity,
                scenario_severity=scenario_severity,
                harness_severity=harness_severity,
            )
        )

        required_pass_count = sum(
            1 for c in checks if c.severity == "required" and c.status == "pass"
        )
        required_fail_count = sum(
            1 for c in checks if c.severity == "required" and c.status == "fail"
        )
        warning_count = sum(1 for c in checks if c.status == "warning")
        optional_missing_count = sum(
            1
            for c in checks
            if c.severity == "optional" and c.status in {"warning", "skipped", "fail"}
        )
        ready = required_fail_count == 0

        if ready:
            next_actions = [
                "Select model comparison set.",
                "Run one single-model scenario dry run.",
                "Collect behavioral and resource metrics.",
                "Run two-model behavior comparison.",
                "Prepare final evaluation report.",
            ]
            summary = "Project is ready to start Experiments and Evaluation."
        else:
            failed = [
                f"{c.check_id}: {c.message}" for c in checks if c.severity == "required" and c.status == "fail"
            ][:5]
            next_actions = failed
            summary = "Project is not ready: required foundations are missing."

        return ExperimentReadinessAuditResult(
            audit_id=self.config.audit_id,
            ready=ready,
            required_pass_count=required_pass_count,
            required_fail_count=required_fail_count,
            warning_count=warning_count,
            optional_missing_count=optional_missing_count,
            checks=checks,
            summary=summary,
            next_recommended_actions=next_actions,
        )

    def _semantic_checks(
        self,
        project_root: Path,
        behavioral_severity: ReadinessCheckSeverity,
        scenario_severity: ReadinessCheckSeverity,
        harness_severity: ReadinessCheckSeverity,
    ) -> list[ReadinessCheck]:
        checks: list[ReadinessCheck] = []
        # Activity profiles
        profile_paths = [
            "configs/activity_profiles/office_worker.json",
            "configs/activity_profiles/developer.json",
            "configs/activity_profiles/student_researcher.json",
        ]
        try:
            for p in profile_paths:
                load_activity_profile(project_root / p)
            checks.append(
                ReadinessCheck(
                    check_id="profiles_loadable",
                    area="behavioral_evaluation",
                    severity=behavioral_severity,
                    status="pass",
                    message="All required activity profiles loaded successfully.",
                )
            )
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    check_id="profiles_loadable",
                    area="behavioral_evaluation",
                    severity=behavioral_severity,
                    status="fail" if behavioral_severity == "required" else "warning",
                    message=f"Failed loading activity profiles: {exc}",
                )
            )

        # Evaluation scenarios
        scenario_paths = [
            "configs/evaluation_scenarios/office_worker_basic_session.json",
            "configs/evaluation_scenarios/developer_project_maintenance.json",
            "configs/evaluation_scenarios/student_researcher_experiment_report.json",
            "configs/evaluation_scenarios/mixed_roles_multi_agent_session.json",
        ]
        try:
            missing_refs: list[str] = []
            for p in scenario_paths:
                scenario = load_evaluation_scenario(project_root / p)
                missing_refs.extend(verify_evaluation_scenario_references(scenario))
            if missing_refs:
                checks.append(
                    ReadinessCheck(
                        check_id="scenario_references_resolve",
                        area="evaluation_scenarios",
                        severity=scenario_severity,
                        status="fail" if scenario_severity == "required" else "warning",
                        message=f"Missing scenario references: {sorted(set(missing_refs))}",
                    )
                )
            else:
                checks.append(
                    ReadinessCheck(
                        check_id="scenario_references_resolve",
                        area="evaluation_scenarios",
                        severity=scenario_severity,
                        status="pass",
                        message="Scenario references resolved successfully.",
                    )
                )
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    check_id="scenario_references_resolve",
                    area="evaluation_scenarios",
                    severity=scenario_severity,
                    status="fail" if scenario_severity == "required" else "warning",
                    message=f"Scenario loading/check failed: {exc}",
                )
            )

        # Behavioral expectations
        try:
            load_behavioral_expectations()
            checks.append(
                ReadinessCheck(
                    check_id="behavioral_expectations_loadable",
                    area="behavioral_evaluation",
                    severity=behavioral_severity,
                    status="pass",
                    message="Behavioral expectation suite loaded successfully.",
                )
            )
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    check_id="behavioral_expectations_loadable",
                    area="behavioral_evaluation",
                    severity=behavioral_severity,
                    status="fail" if behavioral_severity == "required" else "warning",
                    message=f"Behavioral expectation suite failed to load: {exc}",
                )
            )

        # Model behavior config
        try:
            load_model_behavior_evaluation_config(project_root / "configs/model_behavior_evaluation.example.json")
            checks.append(
                ReadinessCheck(
                    check_id="model_behavior_config_loadable",
                    area="model_behavior_harness",
                    severity=harness_severity,
                    status="pass",
                    message="Model behavior evaluation config loaded successfully.",
                )
            )
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    check_id="model_behavior_config_loadable",
                    area="model_behavior_harness",
                    severity=harness_severity,
                    status="fail" if harness_severity == "required" else "warning",
                    message=f"Model behavior evaluation config failed to load: {exc}",
                )
            )
        return checks
