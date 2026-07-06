from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .model_evaluation_artifact_contracts import (
    ArtifactContractIssue,
    validate_artifact_against_contract,
)
from .model_evaluation_artifact_registry import (
    ARTIFACT_VALIDATION_REPORT,
    TASK_CORRECTNESS_BATCH_SUMMARY,
    get_all_workflow_output_artifact_types,
    get_artifact_schema_info,
    get_default_artifact_filename,
    get_expected_schema_versions_for_workflow_outputs,
    get_optional_workflow_output_artifact_types,
    get_required_workflow_output_artifact_types,
    get_workflow_known_relative_paths,
)

MODEL_EVALUATION_ARTIFACT_VALIDATION_SCHEMA_VERSION = get_artifact_schema_info(
    ARTIFACT_VALIDATION_REPORT
).schema_version
MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME = get_default_artifact_filename(
    ARTIFACT_VALIDATION_REPORT
)
MODEL_EVALUATION_ARTIFACT_VALIDATION_PREVIEW_FILENAME = "model_evaluation_artifact_validation_preview.md"

ArtifactIssueSeverity = Literal["info", "warning", "error"]
ArtifactValidationStatus = Literal["valid", "valid_with_warnings", "invalid"]
LoadedArtifactStatus = Literal["ok", "missing", "invalid_input", "not_provided"]
WorkflowArtifactType = Literal[
    "model_comparison_plan",
    "readiness_report",
    "normality_comparison_summary",
    "model_resource_summary",
    "task_correctness_batch_summary",
    "model_evaluation_scorecard",
    "workflow_bundle",
    "workflow_run_manifest",
]

KNOWN_WORKFLOW_ARTIFACT_LOCATIONS: dict[WorkflowArtifactType, str] = get_workflow_known_relative_paths()

REQUIRED_WORKFLOW_OUTPUT_ARTIFACTS: tuple[WorkflowArtifactType, ...] = (
    get_required_workflow_output_artifact_types()
)
OPTIONAL_WORKFLOW_OUTPUT_ARTIFACTS: tuple[WorkflowArtifactType, ...] = (
    get_optional_workflow_output_artifact_types()
)
ALL_WORKFLOW_OUTPUT_ARTIFACTS: tuple[WorkflowArtifactType, ...] = (
    get_all_workflow_output_artifact_types()
)

EXPECTED_SCHEMA_VERSIONS: dict[WorkflowArtifactType, str] = (
    get_expected_schema_versions_for_workflow_outputs()
)
EXPECTED_SCHEMA_VERSIONS[TASK_CORRECTNESS_BATCH_SUMMARY] = get_artifact_schema_info(
    TASK_CORRECTNESS_BATCH_SUMMARY
).schema_version

RECOGNIZED_STATUSES: dict[WorkflowArtifactType, set[str]] = {
    "readiness_report": {"ready", "ready_with_warnings", "not_ready"},
    "normality_comparison_summary": {"ok", "invalid_input"},
    "model_resource_summary": {"ok", "invalid_input"},
    "model_evaluation_scorecard": {"ok", "invalid_input"},
    "workflow_bundle": {"complete", "partial", "invalid"},
    "workflow_run_manifest": {"ok", "partial", "invalid", "write_failed"},
}

VALIDATION_NOTES = [
    "Offline artifact validation only; no model execution performed.",
    "Validation report only; not a production recommendation.",
]

_MAX_INPUT_BYTES = 1_000_000
_MAX_TEXT_CHARS = 300
_MAX_SCAN_LIST_ITEMS = 500
_SUSPICIOUS_KEY_NAMES = {
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
_RAW_MARKER_RE = re.compile(r"(RAW_FULL|raw_response|full_prompt|BEGIN\s+PROMPT)", re.I)
_WINDOWS_ABSOLUTE_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_POSIX_ABSOLUTE_RE = re.compile(r"(?<![:\w])/(?:[^\s\"']+/)+[^\s\"']+")
_UNC_ABSOLUTE_RE = re.compile(r"\\\\[^\s\"']+")


class ModelEvaluationArtifactIssue(BaseModel):
    severity: ArtifactIssueSeverity
    code: str
    message: str
    artifact_type: str | None = None
    artifact_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("issue code and message must be non-empty.")
        return _safe_text(cleaned)

    @field_validator("artifact_type", "artifact_path")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _safe_text(value)


class ModelEvaluationArtifactValidationReport(BaseModel):
    schema_version: str = MODEL_EVALUATION_ARTIFACT_VALIDATION_SCHEMA_VERSION
    status: ArtifactValidationStatus
    validation_id: str
    artifact_count: int
    checked_artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    issue_count: int
    warning_count: int
    error_count: int
    cross_link_summary: dict[str, Any] = Field(default_factory=dict)
    issues: list[ModelEvaluationArtifactIssue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=lambda: list(VALIDATION_NOTES))
    no_runtime_execution: bool = True
    report_path_relative: str | None = None
    markdown_preview_path_relative: str | None = None

    @field_validator("validation_id")
    @classmethod
    def validate_validation_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("validation_id must be non-empty.")
        return _safe_text(cleaned)


class LoadedWorkflowArtifact(BaseModel):
    artifact_type: WorkflowArtifactType
    path: str | None = None
    present: bool = False
    status: LoadedArtifactStatus
    payload: dict[str, Any] | None = None
    issues: list[ModelEvaluationArtifactIssue] = Field(default_factory=list)


def load_artifact_json(
    path: str | Path | None,
    artifact_type: WorkflowArtifactType,
    *,
    base_dir: str | Path | None = None,
    required: bool = False,
    max_input_bytes: int = _MAX_INPUT_BYTES,
) -> LoadedWorkflowArtifact:
    display_path = _display_path(path, base_dir=base_dir)
    if path is None:
        severity: ArtifactIssueSeverity = "error" if required else "warning"
        return LoadedWorkflowArtifact(
            artifact_type=artifact_type,
            path=display_path,
            status="not_provided",
            issues=[
                _issue(
                    severity,
                    "artifact_not_provided",
                    "Artifact path was not provided.",
                    artifact_type=artifact_type,
                    artifact_path=display_path,
                )
            ],
        )

    path_obj = Path(path)
    if not path_obj.exists() or not path_obj.is_file():
        severity = "error" if required else "warning"
        return LoadedWorkflowArtifact(
            artifact_type=artifact_type,
            path=display_path,
            status="missing",
            issues=[
                _issue(
                    severity,
                    "artifact_missing",
                    "Artifact file is missing.",
                    artifact_type=artifact_type,
                    artifact_path=display_path,
                )
            ],
        )

    try:
        if path_obj.stat().st_size > max_input_bytes:
            return LoadedWorkflowArtifact(
                artifact_type=artifact_type,
                path=display_path,
                present=True,
                status="invalid_input",
                issues=[
                    _issue(
                        "error",
                        "artifact_too_large",
                        "Artifact file is larger than the validation limit.",
                        artifact_type=artifact_type,
                        artifact_path=display_path,
                    )
                ],
            )
        text = path_obj.read_text(encoding="utf-8")
    except OSError:
        return LoadedWorkflowArtifact(
            artifact_type=artifact_type,
            path=display_path,
            present=True,
            status="invalid_input",
            issues=[
                _issue(
                    "error",
                    "artifact_unreadable",
                    "Artifact file could not be read.",
                    artifact_type=artifact_type,
                    artifact_path=display_path,
                )
            ],
        )
    except UnicodeDecodeError:
        return LoadedWorkflowArtifact(
            artifact_type=artifact_type,
            path=display_path,
            present=True,
            status="invalid_input",
            issues=[
                _issue(
                    "error",
                    "artifact_not_utf8_text",
                    "Artifact file is not UTF-8 text.",
                    artifact_type=artifact_type,
                    artifact_path=display_path,
                )
            ],
        )

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return LoadedWorkflowArtifact(
            artifact_type=artifact_type,
            path=display_path,
            present=True,
            status="invalid_input",
            issues=[
                _issue(
                    "error",
                    "artifact_json_decode_error",
                    "Artifact file is not valid JSON.",
                    artifact_type=artifact_type,
                    artifact_path=display_path,
                )
            ],
        )
    if not isinstance(payload, dict):
        return LoadedWorkflowArtifact(
            artifact_type=artifact_type,
            path=display_path,
            present=True,
            status="invalid_input",
            issues=[
                _issue(
                    "error",
                    "artifact_payload_not_object",
                    "Artifact JSON must be an object.",
                    artifact_type=artifact_type,
                    artifact_path=display_path,
                )
            ],
        )

    issues: list[ModelEvaluationArtifactIssue] = []
    _validate_generic_artifact(payload, artifact_type, display_path, issues)
    return LoadedWorkflowArtifact(
        artifact_type=artifact_type,
        path=display_path,
        present=True,
        status="ok",
        payload=payload,
        issues=issues,
    )


def validate_model_evaluation_artifacts(
    *,
    plan_path: str | Path | None = None,
    readiness_report_path: str | Path | None = None,
    normality_comparison_summary_path: str | Path | None = None,
    model_resource_summary_path: str | Path | None = None,
    task_correctness_summary_path: str | Path | None = None,
    scorecard_path: str | Path | None = None,
    workflow_bundle_path: str | Path | None = None,
    workflow_run_manifest_path: str | Path | None = None,
    validation_id: str = "model_evaluation_artifact_validation",
    base_dir: str | Path | None = None,
    required_artifacts: tuple[WorkflowArtifactType, ...] = (),
) -> ModelEvaluationArtifactValidationReport:
    artifact_paths: dict[WorkflowArtifactType, str | Path | None] = {
        "model_comparison_plan": plan_path,
        "readiness_report": readiness_report_path,
        "normality_comparison_summary": normality_comparison_summary_path,
        "model_resource_summary": model_resource_summary_path,
        "task_correctness_batch_summary": task_correctness_summary_path,
        "model_evaluation_scorecard": scorecard_path,
        "workflow_bundle": workflow_bundle_path,
        "workflow_run_manifest": workflow_run_manifest_path,
    }
    requested = {
        artifact_type: path
        for artifact_type, path in artifact_paths.items()
        if path is not None or artifact_type in required_artifacts
    }
    issues: list[ModelEvaluationArtifactIssue] = []
    if not requested:
        issues.append(_issue("error", "no_artifacts_provided", "No artifacts were provided for validation."))
        return _report(validation_id=validation_id, artifacts={}, issues=issues, cross_link_summary={})

    artifacts = {
        artifact_type: load_artifact_json(
            path,
            artifact_type,
            base_dir=base_dir,
            required=artifact_type in required_artifacts,
        )
        for artifact_type, path in requested.items()
    }
    for artifact in artifacts.values():
        issues.extend(artifact.issues)

    payloads = {
        artifact_type: artifact.payload
        for artifact_type, artifact in artifacts.items()
        if artifact.payload is not None
    }
    _validate_plan(payloads.get("model_comparison_plan"), artifacts.get("model_comparison_plan"), issues)
    _validate_readiness(
        payloads.get("readiness_report"),
        artifacts.get("readiness_report"),
        payloads.get("model_comparison_plan"),
        issues,
    )
    _validate_scorecard(
        payloads.get("model_evaluation_scorecard"),
        artifacts.get("model_evaluation_scorecard"),
        payloads.get("model_comparison_plan"),
        payloads.get("normality_comparison_summary"),
        payloads.get("model_resource_summary"),
        payloads.get("task_correctness_batch_summary"),
        issues,
    )
    _validate_bundle(payloads.get("workflow_bundle"), artifacts, issues)
    _validate_manifest(payloads.get("workflow_run_manifest"), artifacts, issues)
    _cross_link_artifacts(payloads, issues)
    cross_link_summary = _cross_link_summary(payloads, artifacts)
    return _report(validation_id=validation_id, artifacts=artifacts, issues=issues, cross_link_summary=cross_link_summary)


def validate_model_evaluation_workflow_output_dir(
    output_dir: str | Path,
    validation_output_dir: str | Path | None = None,
    *,
    validation_id: str = "model_evaluation_artifact_validation",
    write_markdown_preview: bool = False,
) -> ModelEvaluationArtifactValidationReport:
    root = Path(output_dir)
    paths = {
        artifact_type: root / relative_path
        for artifact_type, relative_path in KNOWN_WORKFLOW_ARTIFACT_LOCATIONS.items()
    }
    report = validate_model_evaluation_artifacts(
        plan_path=paths["model_comparison_plan"],
        readiness_report_path=paths["readiness_report"],
        normality_comparison_summary_path=paths["normality_comparison_summary"],
        model_resource_summary_path=paths["model_resource_summary"],
        scorecard_path=paths["model_evaluation_scorecard"],
        workflow_bundle_path=paths["workflow_bundle"],
        workflow_run_manifest_path=paths["workflow_run_manifest"],
        validation_id=validation_id,
        base_dir=root,
        required_artifacts=REQUIRED_WORKFLOW_OUTPUT_ARTIFACTS,
    )
    if validation_output_dir is not None:
        write_model_evaluation_artifact_validation_report(
            report,
            validation_output_dir,
            write_markdown_preview=write_markdown_preview,
        )
    return report


def write_model_evaluation_artifact_validation_report(
    report: ModelEvaluationArtifactValidationReport,
    output_dir: str | Path,
    *,
    write_markdown_preview: bool = False,
) -> tuple[Path, Path | None]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME
    preview_path = out_dir / MODEL_EVALUATION_ARTIFACT_VALIDATION_PREVIEW_FILENAME
    report_to_write = report.model_copy(
        update={
            "report_path_relative": MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME,
            "markdown_preview_path_relative": (
                MODEL_EVALUATION_ARTIFACT_VALIDATION_PREVIEW_FILENAME if write_markdown_preview else None
            ),
        }
    )
    report_path.write_text(
        json.dumps(report_to_write.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if write_markdown_preview:
        preview_path.write_text(_markdown_preview(report_to_write), encoding="utf-8")
        return report_path, preview_path
    return report_path, None


def _validate_generic_artifact(
    payload: dict[str, Any],
    artifact_type: WorkflowArtifactType,
    artifact_path: str | None,
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    expected_schema = EXPECTED_SCHEMA_VERSIONS[artifact_type]
    schema_version = payload.get("schema_version")
    if schema_version != expected_schema:
        issues.append(
            _issue(
                "error",
                "schema_version_unexpected",
                "Artifact schema_version is missing or unexpected.",
                artifact_type=artifact_type,
                artifact_path=artifact_path,
                metadata={"expected_schema_version": expected_schema, "actual_schema_version": _safe_optional(schema_version)},
            )
        )

    status = payload.get("status")
    recognized = RECOGNIZED_STATUSES.get(artifact_type)
    if recognized is not None and status not in recognized:
        issues.append(
            _issue(
                "error",
                "status_unrecognized",
                "Artifact status is missing or not recognized.",
                artifact_type=artifact_type,
                artifact_path=artifact_path,
                metadata={"status": _safe_optional(status)},
            )
        )

    for contract_issue in validate_artifact_against_contract(payload, artifact_type):
        issues.append(_contract_issue_to_validation_issue(contract_issue, artifact_path))

    _scan_value_safety(
        payload,
        artifact_type=artifact_type,
        artifact_path=artifact_path,
        issues=issues,
    )


def _contract_issue_to_validation_issue(
    contract_issue: ArtifactContractIssue,
    artifact_path: str | None,
) -> ModelEvaluationArtifactIssue:
    return _issue(
        contract_issue.severity,
        contract_issue.code,
        contract_issue.message,
        artifact_type=contract_issue.artifact_type,
        artifact_path=artifact_path,
        metadata={
            "field": contract_issue.field,
            **(contract_issue.metadata or {}),
        },
    )


def _validate_plan(
    plan: dict[str, Any] | None,
    artifact: LoadedWorkflowArtifact | None,
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    if plan is None:
        return
    artifact_path = artifact.path if artifact else None
    if plan.get("no_runtime_execution") is not True:
        issues.append(_issue("error", "plan_runtime_execution_enabled", "Plan must declare no_runtime_execution=true.", artifact_type="model_comparison_plan", artifact_path=artifact_path))

    pairs = _dict_rows(plan.get("candidate_pairs"))
    trials = _dict_rows(plan.get("trials"))
    scenarios = _dict_rows(plan.get("scenarios"))
    if not pairs:
        issues.append(_issue("error", "plan_candidate_pairs_missing", "Plan candidate_pairs must be non-empty.", artifact_type="model_comparison_plan", artifact_path=artifact_path))
    if not trials:
        issues.append(_issue("error", "plan_trials_missing", "Plan trials must be non-empty.", artifact_type="model_comparison_plan", artifact_path=artifact_path))

    pair_ids = [_text(pair.get("pair_id")) for pair in pairs if _text(pair.get("pair_id"))]
    trial_ids = [_text(trial.get("trial_id")) for trial in trials if _text(trial.get("trial_id"))]
    scenario_ids = {_text(scenario.get("scenario_id")) for scenario in scenarios if _text(scenario.get("scenario_id"))}
    _duplicate_errors(pair_ids, "duplicate_pair_id", "Duplicate candidate pair id.", "model_comparison_plan", artifact_path, issues)
    _duplicate_errors(trial_ids, "duplicate_trial_id", "Duplicate trial id.", "model_comparison_plan", artifact_path, issues)

    pair_set = set(pair_ids)
    for trial in trials:
        trial_id = _text(trial.get("trial_id")) or "<unknown_trial>"
        pair_id = _text(trial.get("pair_id"))
        scenario_id = _text(trial.get("scenario_id"))
        if pair_id and pair_id not in pair_set:
            issues.append(_issue("error", "trial_references_missing_pair", "Trial references a pair_id absent from candidate_pairs.", artifact_type="model_comparison_plan", artifact_path=artifact_path, metadata={"trial_id": trial_id, "pair_id": _safe_text(pair_id)}))
        if scenario_id and scenario_ids and scenario_id not in scenario_ids:
            issues.append(_issue("error", "trial_references_missing_scenario", "Trial references a scenario_id absent from plan scenarios.", artifact_type="model_comparison_plan", artifact_path=artifact_path, metadata={"trial_id": trial_id, "scenario_id": _safe_text(scenario_id)}))


def _validate_readiness(
    readiness: dict[str, Any] | None,
    artifact: LoadedWorkflowArtifact | None,
    plan: dict[str, Any] | None,
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    if readiness is None:
        return
    artifact_path = artifact.path if artifact else None
    if readiness.get("no_runtime_execution") is not True:
        issues.append(_issue("error", "readiness_runtime_execution_enabled", "Readiness report must declare no_runtime_execution=true.", artifact_type="readiness_report", artifact_path=artifact_path))

    status = readiness.get("status")
    if status == "not_ready":
        issues.append(_issue("error", "readiness_not_ready", "Readiness report status is not_ready.", artifact_type="readiness_report", artifact_path=artifact_path))
    elif status == "ready_with_warnings":
        issues.append(_issue("warning", "readiness_has_warnings", "Readiness report status is ready_with_warnings.", artifact_type="readiness_report", artifact_path=artifact_path))

    if plan is not None:
        _count_match(
            left_value=len(_dict_rows(plan.get("trials"))),
            right_value=readiness.get("trial_count"),
            code="readiness_trial_count_mismatch",
            message="Readiness trial_count does not match plan trials.",
            artifact_type="readiness_report",
            artifact_path=artifact_path,
            issues=issues,
        )
        _count_match(
            left_value=len(_dict_rows(plan.get("candidate_pairs"))),
            right_value=readiness.get("candidate_pair_count"),
            code="readiness_candidate_pair_count_mismatch",
            message="Readiness candidate_pair_count does not match plan candidate_pairs.",
            artifact_type="readiness_report",
            artifact_path=artifact_path,
            issues=issues,
        )


def _validate_scorecard(
    scorecard: dict[str, Any] | None,
    artifact: LoadedWorkflowArtifact | None,
    plan: dict[str, Any] | None,
    normality: dict[str, Any] | None,
    resource: dict[str, Any] | None,
    task_correctness: dict[str, Any] | None,
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    if scorecard is None:
        return
    artifact_path = artifact.path if artifact else None
    if scorecard.get("no_runtime_execution") is not True:
        issues.append(_issue("error", "scorecard_runtime_execution_enabled", "Scorecard must declare no_runtime_execution=true.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))

    notes_text = " ".join(str(item).lower() for item in _list_value(scorecard.get("notes")))
    if "no model execution" not in notes_text and "no-runtime" not in notes_text:
        issues.append(_issue("warning", "scorecard_no_runtime_note_missing", "Scorecard notes should include offline/no-runtime wording.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))
    if "not a production recommendation" not in notes_text and "production_recommendation" not in json.dumps(scorecard.get("overall", {}), ensure_ascii=False).lower():
        issues.append(_issue("warning", "scorecard_not_production_note_missing", "Scorecard should include not-production wording.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))

    model_pairs = _dict_rows(scorecard.get("model_pairs"))
    if isinstance(scorecard.get("model_pair_count"), int) and scorecard.get("model_pair_count") != len(model_pairs):
        issues.append(_issue("warning", "scorecard_model_pair_count_mismatch", "Scorecard model_pair_count does not match model_pairs length.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))

    if plan is not None:
        planned_pair_ids = _pair_ids_from_plan(plan)
        scorecard_pair_ids = _scorecard_pair_ids(scorecard)
        for pair_id in sorted(planned_pair_ids - scorecard_pair_ids):
            issues.append(_issue("warning", "scorecard_missing_planned_pair", "Scorecard is missing a planned pair.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path, metadata={"pair_id": pair_id}))

    if _raw_collection_present(scorecard):
        issues.append(_issue("warning", "scorecard_raw_collection_present", "Scorecard appears to include raw observation/event collections.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))
    if normality is not None and scorecard.get("normality_summary_used") is not True:
        issues.append(_issue("warning", "scorecard_normality_summary_not_marked_used", "Normality artifact is present but scorecard does not mark it as used.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))
    if resource is not None and scorecard.get("resource_summary_used") is not True:
        issues.append(_issue("warning", "scorecard_resource_summary_not_marked_used", "Resource artifact is present but scorecard does not mark it as used.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))
    if task_correctness is not None and scorecard.get("task_correctness_summary_used") is not True:
        issues.append(_issue("warning", "scorecard_task_correctness_summary_not_marked_used", "Task correctness artifact is present but scorecard does not mark it as used.", artifact_type="model_evaluation_scorecard", artifact_path=artifact_path))


def _validate_bundle(
    bundle: dict[str, Any] | None,
    artifacts: dict[WorkflowArtifactType, LoadedWorkflowArtifact],
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    if bundle is None:
        return
    artifact_path = artifacts.get("workflow_bundle").path if artifacts.get("workflow_bundle") else None
    bundle_artifacts = bundle.get("artifacts") if isinstance(bundle.get("artifacts"), dict) else {}
    if not bundle_artifacts:
        issues.append(_issue("error", "bundle_artifacts_missing", "Workflow bundle artifacts map is missing.", artifact_type="workflow_bundle", artifact_path=artifact_path))
        return

    for artifact_type in (
        "model_comparison_plan",
        "readiness_report",
        "normality_comparison_summary",
        "model_resource_summary",
        "task_correctness_batch_summary",
        "model_evaluation_scorecard",
    ):
        bundle_row = bundle_artifacts.get(artifact_type)
        if not isinstance(bundle_row, dict):
            continue
        actual = artifacts.get(artifact_type)
        if artifact_type == "task_correctness_batch_summary" and actual is None:
            continue
        bundle_present = bundle_row.get("present") is True or bundle_row.get("status") == "ok"
        if bundle_present and (actual is None or actual.status != "ok"):
            issues.append(_issue("error", "bundle_marks_missing_artifact_present", "Bundle marks an artifact present, but the actual artifact is missing or invalid.", artifact_type="workflow_bundle", artifact_path=artifact_path, metadata={"referenced_artifact_type": artifact_type}))
        if actual is not None and actual.status == "ok" and not bundle_present:
            issues.append(_issue("warning", "bundle_marks_existing_artifact_missing", "Bundle does not mark an existing artifact as present.", artifact_type="workflow_bundle", artifact_path=artifact_path, metadata={"referenced_artifact_type": artifact_type}))

    expected_status = _expected_bundle_status(bundle_artifacts)
    if expected_status is not None and bundle.get("status") != expected_status:
        issues.append(_issue("warning", "bundle_status_inconsistent", "Bundle status is not consistent with artifact statuses.", artifact_type="workflow_bundle", artifact_path=artifact_path, metadata={"expected_status": expected_status, "actual_status": _safe_optional(bundle.get("status"))}))


def _validate_manifest(
    manifest: dict[str, Any] | None,
    artifacts: dict[WorkflowArtifactType, LoadedWorkflowArtifact],
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    if manifest is None:
        return
    artifact_path = artifacts.get("workflow_run_manifest").path if artifacts.get("workflow_run_manifest") else None
    manifest_paths = manifest.get("artifact_paths") if isinstance(manifest.get("artifact_paths"), dict) else {}
    if not manifest_paths:
        issues.append(_issue("warning", "manifest_artifact_paths_missing", "Workflow manifest artifact_paths map is missing.", artifact_type="workflow_run_manifest", artifact_path=artifact_path))
    for manifest_key, expected_path in _manifest_expected_paths().items():
        value = manifest_paths.get(manifest_key)
        if value is None:
            continue
        if isinstance(value, str) and _is_absolute_path(value):
            issues.append(_issue("error", "manifest_absolute_path_leak", "Workflow manifest contains an absolute artifact path.", artifact_type="workflow_run_manifest", artifact_path=artifact_path, metadata={"field_path": f"artifact_paths.{manifest_key}", "redacted_value": "<absolute_path>"}))
            continue
        if isinstance(value, str) and value.replace("\\", "/") != expected_path:
            issues.append(_issue("warning", "manifest_artifact_path_unexpected", "Workflow manifest artifact path does not match the known workflow location.", artifact_type="workflow_run_manifest", artifact_path=artifact_path, metadata={"field_path": f"artifact_paths.{manifest_key}", "expected_path": expected_path}))
    task_correctness_path = manifest_paths.get("task_correctness_batch_summary")
    if isinstance(task_correctness_path, str) and _is_absolute_path(task_correctness_path):
        issues.append(_issue("error", "manifest_absolute_path_leak", "Workflow manifest contains an absolute artifact path.", artifact_type="workflow_run_manifest", artifact_path=artifact_path, metadata={"field_path": "artifact_paths.task_correctness_batch_summary", "redacted_value": "<absolute_path>"}))

    if manifest.get("config_used") is True:
        config_display = manifest.get("config_display_path")
        if isinstance(config_display, str) and _is_absolute_path(config_display):
            issues.append(_issue("error", "manifest_config_path_absolute", "Workflow manifest config_display_path is absolute.", artifact_type="workflow_run_manifest", artifact_path=artifact_path, metadata={"field_path": "config_display_path"}))
        if len(_list_value(manifest.get("tags"))) > 20 or len(_list_value(manifest.get("notes"))) > 20:
            issues.append(_issue("warning", "manifest_config_provenance_unbounded", "Workflow manifest config provenance lists are unexpectedly large.", artifact_type="workflow_run_manifest", artifact_path=artifact_path))

    required_missing = [
        artifact_type
        for artifact_type in REQUIRED_WORKFLOW_OUTPUT_ARTIFACTS
        if artifacts.get(artifact_type) is None or artifacts[artifact_type].status != "ok"
    ]
    if manifest.get("status") == "ok" and required_missing:
        issues.append(_issue("error", "manifest_status_ok_with_missing_required_artifacts", "Workflow manifest status is ok while required artifacts are missing or invalid.", artifact_type="workflow_run_manifest", artifact_path=artifact_path, metadata={"missing_required_count": len(required_missing)}))
    if manifest.get("status") == "ok":
        optional_missing = [
            artifact_type
            for artifact_type in OPTIONAL_WORKFLOW_OUTPUT_ARTIFACTS
            if artifacts.get(artifact_type) is None or artifacts[artifact_type].status != "ok"
        ]
        if optional_missing:
            issues.append(_issue("warning", "manifest_status_ok_with_missing_optional_artifacts", "Workflow manifest status is ok while optional artifacts are missing.", artifact_type="workflow_run_manifest", artifact_path=artifact_path, metadata={"missing_optional_count": len(optional_missing)}))


def _cross_link_artifacts(payloads: dict[WorkflowArtifactType, dict[str, Any]], issues: list[ModelEvaluationArtifactIssue]) -> None:
    plan = payloads.get("model_comparison_plan")
    readiness = payloads.get("readiness_report")
    scorecard = payloads.get("model_evaluation_scorecard")
    normality = payloads.get("normality_comparison_summary")
    resource = payloads.get("model_resource_summary")
    task_correctness = payloads.get("task_correctness_batch_summary")
    bundle = payloads.get("workflow_bundle")

    if plan is not None and readiness is not None:
        if _text(plan.get("plan_id")) and _text(readiness.get("plan_id")) and _text(plan.get("plan_id")) != _text(readiness.get("plan_id")):
            issues.append(_issue("error", "plan_readiness_plan_id_mismatch", "Plan id does not match readiness plan_id."))
        _count_match(len(_dict_rows(plan.get("candidate_pairs"))), readiness.get("candidate_pair_count"), "plan_readiness_candidate_pair_count_mismatch", "Plan candidate count does not match readiness.", None, None, issues)
        _count_match(len(_dict_rows(plan.get("trials"))), readiness.get("trial_count"), "plan_readiness_trial_count_mismatch", "Plan trial count does not match readiness.", None, None, issues)

    if scorecard is not None:
        scorecard_pair_ids = _scorecard_pair_ids(scorecard)
        if resource is not None:
            for pair_id in sorted(_resource_pair_ids(resource) - scorecard_pair_ids):
                issues.append(_issue("warning", "resource_pair_missing_from_scorecard", "Resource by_pair entry is not represented in scorecard.", metadata={"pair_id": pair_id}))
        if normality is not None:
            for pair_id in sorted(_normality_pair_ids(normality) - scorecard_pair_ids):
                issues.append(_issue("warning", "normality_pair_missing_from_scorecard", "Normality model pair is not represented in scorecard.", metadata={"pair_id": pair_id}))
        if task_correctness is not None:
            for pair_id in sorted(_task_correctness_pair_ids(task_correctness) - scorecard_pair_ids):
                issues.append(_issue("warning", "task_correctness_pair_missing_from_scorecard", "Task correctness pair is not represented in scorecard.", metadata={"pair_id": pair_id}))

    if bundle is not None and plan is not None:
        summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
        _count_match(len(_dict_rows(plan.get("candidate_pairs"))), summary.get("candidate_pair_count"), "bundle_plan_candidate_pair_count_mismatch", "Bundle candidate_pair_count contradicts plan.", "workflow_bundle", None, issues)
        _count_match(len(_dict_rows(plan.get("trials"))), summary.get("trial_count"), "bundle_plan_trial_count_mismatch", "Bundle trial_count contradicts plan.", "workflow_bundle", None, issues)


def _report(
    *,
    validation_id: str,
    artifacts: dict[WorkflowArtifactType, LoadedWorkflowArtifact],
    issues: list[ModelEvaluationArtifactIssue],
    cross_link_summary: dict[str, Any],
) -> ModelEvaluationArtifactValidationReport:
    sorted_issues = sorted(issues, key=lambda item: ({"error": 0, "warning": 1, "info": 2}[item.severity], item.code))
    error_count = sum(1 for issue in sorted_issues if issue.severity == "error")
    warning_count = sum(1 for issue in sorted_issues if issue.severity == "warning")
    status: ArtifactValidationStatus = "invalid" if error_count else ("valid_with_warnings" if warning_count else "valid")
    return ModelEvaluationArtifactValidationReport(
        status=status,
        validation_id=validation_id,
        artifact_count=len(artifacts),
        checked_artifacts={
            artifact_type: {
                "path": artifact.path,
                "present": artifact.present,
                "status": artifact.status,
            }
            for artifact_type, artifact in artifacts.items()
        },
        issue_count=len(sorted_issues),
        warning_count=warning_count,
        error_count=error_count,
        cross_link_summary=_safe_value(cross_link_summary),
        issues=sorted_issues,
    )


def _cross_link_summary(
    payloads: dict[WorkflowArtifactType, dict[str, Any]],
    artifacts: dict[WorkflowArtifactType, LoadedWorkflowArtifact],
) -> dict[str, Any]:
    plan = payloads.get("model_comparison_plan") or {}
    readiness = payloads.get("readiness_report") or {}
    scorecard = payloads.get("model_evaluation_scorecard") or {}
    normality = payloads.get("normality_comparison_summary") or {}
    resource = payloads.get("model_resource_summary") or {}
    task_correctness = payloads.get("task_correctness_batch_summary") or {}
    bundle = payloads.get("workflow_bundle") or {}
    manifest = payloads.get("workflow_run_manifest") or {}
    return {
        "plan_pair_count": len(_dict_rows(plan.get("candidate_pairs"))),
        "plan_trial_count": len(_dict_rows(plan.get("trials"))),
        "readiness_candidate_pair_count": _safe_int(readiness.get("candidate_pair_count")),
        "readiness_trial_count": _safe_int(readiness.get("trial_count")),
        "scorecard_pair_count": len(_dict_rows(scorecard.get("model_pairs"))),
        "normality_pair_count": len(_normality_pair_ids(normality)),
        "resource_pair_count": len(_resource_pair_ids(resource)),
        "task_correctness_pair_count": len(_task_correctness_pair_ids(task_correctness)),
        "bundle_status": _safe_optional(bundle.get("status")),
        "manifest_status": _safe_optional(manifest.get("status")),
        "ok_artifact_count": sum(1 for artifact in artifacts.values() if artifact.status == "ok"),
    }


def _count_match(
    left_value: int,
    right_value: Any,
    code: str,
    message: str,
    artifact_type: str | None,
    artifact_path: str | None,
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    if isinstance(right_value, int) and right_value != left_value:
        issues.append(_issue("error", code, message, artifact_type=artifact_type, artifact_path=artifact_path, metadata={"expected_count": left_value, "actual_count": right_value}))


def _duplicate_errors(
    values: list[str],
    code: str,
    message: str,
    artifact_type: str,
    artifact_path: str | None,
    issues: list[ModelEvaluationArtifactIssue],
) -> None:
    counts = Counter(values)
    for value, count in sorted(counts.items()):
        if count > 1:
            issues.append(_issue("error", code, message, artifact_type=artifact_type, artifact_path=artifact_path, metadata={"id": _safe_text(value), "count": count}))


def _expected_bundle_status(bundle_artifacts: dict[str, Any]) -> str | None:
    required = ("model_catalog", "model_comparison_plan", "readiness_report")
    optional = ("normality_comparison_summary", "model_resource_summary", "model_evaluation_scorecard")
    supplemental = ("task_correctness_batch_summary",)
    if any(_bundle_artifact_status(bundle_artifacts, item) != "ok" for item in required):
        return "invalid"
    if any(_bundle_artifact_status(bundle_artifacts, item) != "ok" for item in optional):
        return "partial"
    if any(_bundle_artifact_status(bundle_artifacts, item) in {"missing", "invalid_input"} for item in supplemental):
        return "partial"
    return "complete"


def _bundle_artifact_status(bundle_artifacts: dict[str, Any], artifact_type: str) -> str | None:
    row = bundle_artifacts.get(artifact_type)
    return row.get("status") if isinstance(row, dict) else None


def _manifest_expected_paths() -> dict[str, str]:
    return {
        "model_comparison_plan": KNOWN_WORKFLOW_ARTIFACT_LOCATIONS["model_comparison_plan"],
        "readiness_report": KNOWN_WORKFLOW_ARTIFACT_LOCATIONS["readiness_report"],
        "normality_comparison_summary": KNOWN_WORKFLOW_ARTIFACT_LOCATIONS["normality_comparison_summary"],
        "model_resource_summary": KNOWN_WORKFLOW_ARTIFACT_LOCATIONS["model_resource_summary"],
        "model_evaluation_scorecard": KNOWN_WORKFLOW_ARTIFACT_LOCATIONS["model_evaluation_scorecard"],
        "workflow_bundle": KNOWN_WORKFLOW_ARTIFACT_LOCATIONS["workflow_bundle"],
        "workflow_run_manifest": KNOWN_WORKFLOW_ARTIFACT_LOCATIONS["workflow_run_manifest"],
    }


def _scan_value_safety(
    value: Any,
    *,
    artifact_type: WorkflowArtifactType,
    artifact_path: str | None,
    issues: list[ModelEvaluationArtifactIssue],
    field_path: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_path = f"{field_path}.{key_text}" if field_path != "$" else key_text
            normalized_key = key_text.strip().lower()
            if normalized_key in _SUSPICIOUS_KEY_NAMES:
                issues.append(_issue("error", "suspicious_secret_or_raw_field", "Artifact contains a suspicious secret/raw field name.", artifact_type=artifact_type, artifact_path=artifact_path, metadata={"field_path": _safe_text(key_path)}))
            _scan_value_safety(child, artifact_type=artifact_type, artifact_path=artifact_path, issues=issues, field_path=key_path)
    elif isinstance(value, list):
        if field_path.split(".")[-1] in {"issues", "findings", "top_findings", "event_preview"} and len(value) > _MAX_SCAN_LIST_ITEMS:
            issues.append(_issue("warning", "unbounded_list_detected", "Artifact contains a very large issue/finding list.", artifact_type=artifact_type, artifact_path=artifact_path, metadata={"field_path": _safe_text(field_path), "item_count": len(value)}))
        for index, child in enumerate(value[:_MAX_SCAN_LIST_ITEMS]):
            _scan_value_safety(child, artifact_type=artifact_type, artifact_path=artifact_path, issues=issues, field_path=f"{field_path}[{index}]")
    elif isinstance(value, str):
        if _is_absolute_path(value):
            code = "absolute_path_leak_detected"
            if ".gguf" in value.lower():
                code = "absolute_gguf_path_leak_detected"
            issues.append(_issue("error", code, "Artifact contains an absolute local path string.", artifact_type=artifact_type, artifact_path=artifact_path, metadata={"field_path": _safe_text(field_path), "redacted_value": "<absolute_path>"}))
        if _RAW_MARKER_RE.search(value):
            issues.append(_issue("warning", "raw_content_marker_detected", "Artifact contains a suspicious raw content marker.", artifact_type=artifact_type, artifact_path=artifact_path, metadata={"field_path": _safe_text(field_path)}))


def _raw_collection_present(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in {"observations", "resource_observations", "events", "event_preview", "entries", "results"}:
                return True
            if _raw_collection_present(child):
                return True
    if isinstance(value, list):
        return any(_raw_collection_present(item) for item in value)
    return False


def _pair_ids_from_plan(plan: dict[str, Any]) -> set[str]:
    return {_safe_text(pair_id) for pair_id in (_text(pair.get("pair_id")) for pair in _dict_rows(plan.get("candidate_pairs"))) if pair_id}


def _scorecard_pair_ids(scorecard: dict[str, Any]) -> set[str]:
    ids = {_text(pair.get("pair_id")) for pair in _dict_rows(scorecard.get("model_pairs")) if _text(pair.get("pair_id"))}
    if ids:
        return {_safe_text(pair_id) for pair_id in ids}
    labels = {_text(pair.get("pair_label")) for pair in _dict_rows(scorecard.get("model_pairs")) if _text(pair.get("pair_label"))}
    return {_pair_label_to_pair_id(label) for label in labels if _pair_label_to_pair_id(label)}


def _resource_pair_ids(resource: dict[str, Any]) -> set[str]:
    groups = resource.get("groups") if isinstance(resource.get("groups"), dict) else {}
    by_pair = groups.get("by_pair") if isinstance(groups.get("by_pair"), dict) else {}
    return {_safe_text(str(key)) for key in by_pair}


def _normality_pair_ids(normality: dict[str, Any]) -> set[str]:
    groups = normality.get("groups") if isinstance(normality.get("groups"), dict) else {}
    by_model_pair = groups.get("by_model_pair") if isinstance(groups.get("by_model_pair"), dict) else {}
    result: set[str] = set()
    for label, group in by_model_pair.items():
        if isinstance(group, dict):
            key = group.get("group_key") if isinstance(group.get("group_key"), dict) else {}
            orchestrator = _text(key.get("orchestrator"))
            executor = _text(key.get("executor"))
            if orchestrator and executor:
                result.add(f"{_safe_text(orchestrator)}__to__{_safe_text(executor)}")
                continue
        pair_id = _pair_label_to_pair_id(str(label))
        if pair_id:
            result.add(pair_id)
    return result


def _task_correctness_pair_ids(task_correctness: dict[str, Any]) -> set[str]:
    by_pair = task_correctness.get("by_pair") if isinstance(task_correctness.get("by_pair"), dict) else {}
    result: set[str] = set()
    for label, group in by_pair.items():
        pair_id = None
        if isinstance(group, dict):
            pair_id = _text(group.get("pair_id"))
        pair_id = pair_id or _text(label)
        if pair_id:
            result.add(_safe_text(pair_id))
    return result


def _pair_label_to_pair_id(label: str) -> str | None:
    if "->" in label:
        left, right = label.split("->", 1)
        if left.strip() and right.strip():
            return f"{_safe_text(left.strip())}__to__{_safe_text(right.strip())}"
    if "__to__" in label:
        return _safe_text(label)
    return None


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _safe_optional(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, int | float | bool):
        return value
    return _safe_text(str(value))


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        return {_safe_text(str(key)): _safe_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_safe_value(child) for child in value[:100]]
    return value


def _issue(
    severity: ArtifactIssueSeverity,
    code: str,
    message: str,
    *,
    artifact_type: str | None = None,
    artifact_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ModelEvaluationArtifactIssue:
    return ModelEvaluationArtifactIssue(
        severity=severity,
        code=code,
        message=message,
        artifact_type=artifact_type,
        artifact_path=artifact_path,
        metadata=_safe_value(metadata or {}),
    )


def _display_path(path: str | Path | None, *, base_dir: str | Path | None = None) -> str | None:
    if path is None:
        return None
    path_obj = Path(path)
    path_text = str(path)
    if base_dir is not None:
        base = Path(base_dir)
        try:
            rel = path_obj.resolve(strict=False).relative_to(base.resolve(strict=False))
        except (OSError, ValueError):
            rel = None
        if rel is not None:
            return _safe_text(rel.as_posix())
    if not _is_absolute_path(path_text):
        return _safe_text(path_text.replace("\\", "/"))
    name = path_obj.name or PureWindowsPath(path_text).name or PurePosixPath(path_text).name or "artifact.json"
    return f"<absolute_path>/{_safe_text(name)}"


def _is_absolute_path(path: str) -> bool:
    return (
        PureWindowsPath(path).is_absolute()
        or PurePosixPath(path).is_absolute()
        or _WINDOWS_ABSOLUTE_RE.search(path) is not None
        or _POSIX_ABSOLUTE_RE.search(path) is not None
        or _UNC_ABSOLUTE_RE.search(path) is not None
    )


def _safe_text(value: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    text = _WINDOWS_ABSOLUTE_RE.sub("<absolute_path>", value)
    text = _POSIX_ABSOLUTE_RE.sub("<absolute_path>", text)
    text = _UNC_ABSOLUTE_RE.sub("<absolute_path>", text)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _markdown_preview(report: ModelEvaluationArtifactValidationReport) -> str:
    lines = [
        "# Model Evaluation Artifact Validation",
        "",
        f"- status: `{report.status}`",
        f"- validation_id: `{report.validation_id}`",
        f"- checked artifacts: `{report.artifact_count}`",
        f"- errors: `{report.error_count}`",
        f"- warnings: `{report.warning_count}`",
        f"- no runtime execution: `{str(report.no_runtime_execution).lower()}`",
        "",
        "## Artifacts",
        "",
    ]
    for artifact_type, row in report.checked_artifacts.items():
        lines.append(f"- `{artifact_type}`: `{row.get('status')}` ({row.get('path') or 'not provided'})")
    if report.issues:
        lines.extend(["", "## Issues", ""])
        for issue in report.issues:
            artifact = f" `{issue.artifact_type}`" if issue.artifact_type else ""
            lines.append(f"- `{issue.severity}` `{issue.code}`{artifact}: {issue.message}")
    return "\n".join(lines) + "\n"
