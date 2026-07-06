from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .model_evaluation_artifact_contracts import (
    ArtifactContractIssue,
    get_artifact_schema_contract,
    validate_artifact_against_contract,
)
from .model_evaluation_artifact_registry import (
    ARTIFACT_VALIDATION_REPORT,
    MODEL_CATALOG,
    MODEL_COMPARISON_PLAN,
    MODEL_EVALUATION_COMPATIBILITY_REPORT,
    MODEL_EVALUATION_SCORECARD,
    MODEL_RESOURCE_SUMMARY,
    NORMALITY_COMPARISON_SUMMARY,
    READINESS_REPORT,
    WORKFLOW_BUNDLE,
    WORKFLOW_RUN_MANIFEST,
    get_all_workflow_output_artifact_types,
    get_artifact_schema_info,
    get_default_artifact_filename,
    get_optional_workflow_output_artifact_types,
    get_required_workflow_output_artifact_types,
    get_workflow_known_relative_paths,
)
from .model_evaluation_artifact_validator import (
    ModelEvaluationArtifactValidationReport,
    validate_model_evaluation_workflow_output_dir,
)


MODEL_EVALUATION_COMPATIBILITY_REPORT_SCHEMA_VERSION = get_artifact_schema_info(
    MODEL_EVALUATION_COMPATIBILITY_REPORT
).schema_version
MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME = get_default_artifact_filename(
    MODEL_EVALUATION_COMPATIBILITY_REPORT
)
MODEL_EVALUATION_COMPATIBILITY_PREVIEW_FILENAME = "model_evaluation_compatibility_preview.md"

CompatibilityIssueSeverity = Literal["info", "warning", "error"]
CompatibilityIssueScope = Literal[
    "golden_fixture",
    "registry",
    "contract",
    "validator",
    "workflow_output",
    "cli",
]
CompatibilityStatus = Literal["compatible", "compatible_with_warnings", "incompatible"]

MAX_GOLDEN_FIXTURE_PACK_BYTES = 100_000
_MAX_INPUT_BYTES = 1_000_000
_MAX_TEXT_CHARS = 300

COMPATIBILITY_NOTES = [
    "Offline compatibility validation only; no model execution performed.",
    "Compatibility report only; not a production recommendation.",
]

GOLDEN_FIXTURE_ARTIFACT_PATHS: dict[str, str] = {
    MODEL_CATALOG: "model_catalog.json",
    MODEL_COMPARISON_PLAN: "plan/model_comparison_plan.json",
    READINESS_REPORT: "readiness/model_comparison_readiness_report.json",
    NORMALITY_COMPARISON_SUMMARY: "normality/normality_comparison_summary.json",
    MODEL_RESOURCE_SUMMARY: "resource/model_resource_summary.json",
    MODEL_EVALUATION_SCORECARD: "scorecard/model_evaluation_scorecard.json",
    WORKFLOW_BUNDLE: "bundle/model_evaluation_workflow_bundle.json",
    WORKFLOW_RUN_MANIFEST: "workflow_run_manifest.json",
    ARTIFACT_VALIDATION_REPORT: "validation/model_evaluation_artifact_validation_report.json",
}
WORKFLOW_OUTPUT_ARTIFACT_TYPES = get_all_workflow_output_artifact_types()
REQUIRED_WORKFLOW_OUTPUT_ARTIFACT_TYPES = get_required_workflow_output_artifact_types()
OPTIONAL_WORKFLOW_OUTPUT_ARTIFACT_TYPES = get_optional_workflow_output_artifact_types()
WORKFLOW_KNOWN_RELATIVE_PATHS = get_workflow_known_relative_paths()

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
    "observations",
    "resource_observations",
    "raw_observations",
    "events",
    "event_preview",
}
_SECRET_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9]|ghp_[A-Za-z0-9]|hf_[A-Za-z0-9]|bearer\s+|authorization\s*:|"
    r"access_token|refresh_token|id_token|password|secret)",
    re.I,
)
_RAW_MARKER_RE = re.compile(r"(RAW_FULL|raw_response|full_prompt|BEGIN\s+PROMPT)", re.I)
_WINDOWS_ABSOLUTE_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_POSIX_ABSOLUTE_RE = re.compile(r"(?<![:\w])/(?:[^\s\"']+/)+[^\s\"']+")
_UNC_ABSOLUTE_RE = re.compile(r"\\\\[^\s\"']+")
_BAD_PRODUCTION_PHRASES = (
    "production-ready",
    "production ready",
    "recommended for production",
    "production deployment recommendation",
    "final deployment recommendation",
)


class ModelEvaluationCompatibilityIssue(BaseModel):
    severity: CompatibilityIssueSeverity
    code: str
    scope: CompatibilityIssueScope | None = None
    artifact_type: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("compatibility issue code and message must be non-empty.")
        return _safe_text(cleaned)

    @field_validator("artifact_type")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return _safe_text(value) if value is not None else None


class ModelEvaluationCompatibilityReport(BaseModel):
    schema_version: str = MODEL_EVALUATION_COMPATIBILITY_REPORT_SCHEMA_VERSION
    status: CompatibilityStatus
    compatibility_id: str
    golden_fixture_dir_display: str
    workflow_output_dir_display: str | None = None
    checked_artifact_count: int
    issue_count: int
    warning_count: int
    error_count: int
    checks: dict[str, Any] = Field(default_factory=dict)
    issues: list[ModelEvaluationCompatibilityIssue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=lambda: list(COMPATIBILITY_NOTES))
    no_runtime_execution: bool = True
    report_path_relative: str | None = None
    markdown_preview_path_relative: str | None = None

    @field_validator("compatibility_id", "golden_fixture_dir_display", "workflow_output_dir_display")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("compatibility report text fields must be non-empty.")
        return _safe_text(cleaned)


def run_model_evaluation_compatibility_gate(
    *,
    golden_fixture_dir: str | Path,
    workflow_output_dir: str | Path | None = None,
    compatibility_id: str = "model_evaluation_compatibility",
    max_fixture_pack_bytes: int = MAX_GOLDEN_FIXTURE_PACK_BYTES,
) -> ModelEvaluationCompatibilityReport:
    golden_root = Path(golden_fixture_dir)
    workflow_root = Path(workflow_output_dir) if workflow_output_dir is not None else None
    golden_issues, golden_checks, golden_count, golden_payloads = _golden_fixture_checks(
        golden_root,
        max_fixture_pack_bytes=max_fixture_pack_bytes,
    )
    issues = list(golden_issues)
    checks: dict[str, Any] = {"golden_fixture": golden_checks}
    checked_count = golden_count

    if workflow_root is not None:
        workflow_issues, workflow_checks, workflow_count = _workflow_output_checks(
            workflow_root,
            golden_root,
            golden_payloads=golden_payloads,
        )
        issues.extend(workflow_issues)
        checks["workflow_output"] = workflow_checks
        checked_count += workflow_count

    return _report(
        compatibility_id=compatibility_id,
        golden_fixture_dir=golden_root,
        workflow_output_dir=workflow_root,
        checked_artifact_count=checked_count,
        checks=checks,
        issues=issues,
    )


def validate_golden_fixture_pack(
    golden_fixture_dir: str | Path,
    *,
    compatibility_id: str = "golden_fixture_compatibility",
    max_fixture_pack_bytes: int = MAX_GOLDEN_FIXTURE_PACK_BYTES,
) -> ModelEvaluationCompatibilityReport:
    golden_root = Path(golden_fixture_dir)
    issues, checks, checked_count, _ = _golden_fixture_checks(
        golden_root,
        max_fixture_pack_bytes=max_fixture_pack_bytes,
    )
    return _report(
        compatibility_id=compatibility_id,
        golden_fixture_dir=golden_root,
        workflow_output_dir=None,
        checked_artifact_count=checked_count,
        checks={"golden_fixture": checks},
        issues=issues,
    )


def compare_workflow_output_to_golden_expectations(
    workflow_output_dir: str | Path,
    golden_fixture_dir: str | Path,
    *,
    compatibility_id: str = "workflow_output_golden_compatibility",
) -> ModelEvaluationCompatibilityReport:
    golden_root = Path(golden_fixture_dir)
    workflow_root = Path(workflow_output_dir)
    golden_issues, _, _, golden_payloads = _golden_fixture_checks(golden_root)
    workflow_issues, checks, checked_count = _workflow_output_checks(
        workflow_root,
        golden_root,
        golden_payloads=golden_payloads,
    )
    return _report(
        compatibility_id=compatibility_id,
        golden_fixture_dir=golden_root,
        workflow_output_dir=workflow_root,
        checked_artifact_count=checked_count,
        checks={"workflow_output": checks},
        issues=[*golden_issues, *workflow_issues],
    )


def write_model_evaluation_compatibility_report(
    report: ModelEvaluationCompatibilityReport,
    output_dir: str | Path,
    *,
    write_markdown_preview: bool = False,
) -> tuple[Path, Path | None]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME
    preview_path = out_dir / MODEL_EVALUATION_COMPATIBILITY_PREVIEW_FILENAME
    report_to_write = report.model_copy(
        update={
            "report_path_relative": MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME,
            "markdown_preview_path_relative": (
                MODEL_EVALUATION_COMPATIBILITY_PREVIEW_FILENAME
                if write_markdown_preview
                else None
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


def _golden_fixture_checks(
    golden_root: Path,
    *,
    max_fixture_pack_bytes: int = MAX_GOLDEN_FIXTURE_PACK_BYTES,
) -> tuple[list[ModelEvaluationCompatibilityIssue], dict[str, Any], int, dict[str, dict[str, Any]]]:
    issues: list[ModelEvaluationCompatibilityIssue] = []
    payloads: dict[str, dict[str, Any]] = {}
    paths = {artifact_type: golden_root / relative_path for artifact_type, relative_path in GOLDEN_FIXTURE_ARTIFACT_PATHS.items()}
    existing_files = [path for path in paths.values() if path.is_file()]
    total_size = sum(_file_size(path) for path in existing_files)
    if total_size > max_fixture_pack_bytes:
        issues.append(
            _issue(
                "error",
                "golden_fixture_pack_too_large",
                "Golden fixture pack exceeds the compatibility size threshold.",
                scope="golden_fixture",
                metadata={"max_bytes": max_fixture_pack_bytes, "actual_bytes": total_size},
            )
        )

    for artifact_type, path in paths.items():
        relative_path = GOLDEN_FIXTURE_ARTIFACT_PATHS[artifact_type]
        try:
            get_artifact_schema_info(artifact_type)
        except ValueError:
            issues.append(
                _issue(
                    "error",
                    "registry_artifact_type_unknown",
                    "Golden fixture artifact type is not registered.",
                    scope="registry",
                    artifact_type=artifact_type,
                )
            )
            continue

        loaded = _load_json_object(
            path,
            artifact_type=artifact_type,
            scope="golden_fixture",
            required=True,
            base_dir=golden_root,
        )
        issues.extend(loaded["issues"])
        text = loaded.get("text")
        if isinstance(text, str):
            _scan_text_safety(text, issues, artifact_type=artifact_type, scope="golden_fixture", artifact_path=relative_path)
        payload = loaded.get("payload")
        if not isinstance(payload, dict):
            continue
        payloads[artifact_type] = payload
        _scan_value_safety(payload, issues, artifact_type=artifact_type, scope="golden_fixture")
        issues.extend(_contract_issues(payload, artifact_type, scope="contract"))

    if _workflow_fixture_files_present(golden_root):
        validation_report = validate_model_evaluation_workflow_output_dir(
            golden_root,
            validation_id="golden_fixture_compatibility_validation",
        )
        _append_validator_report_issues(validation_report, issues, artifact_type=None)

    checks = {
        "expected_artifact_count": len(GOLDEN_FIXTURE_ARTIFACT_PATHS),
        "loaded_artifact_count": len(payloads),
        "total_size_bytes": total_size,
        "max_size_bytes": max_fixture_pack_bytes,
        "workflow_validator_status": (
            validate_model_evaluation_workflow_output_dir(golden_root).status
            if _workflow_fixture_files_present(golden_root)
            else "not_run"
        ),
        "no_runtime_execution": True,
    }
    return issues, _safe_value(checks), len(GOLDEN_FIXTURE_ARTIFACT_PATHS), payloads


def _workflow_output_checks(
    workflow_root: Path,
    golden_root: Path,
    *,
    golden_payloads: dict[str, dict[str, Any]],
) -> tuple[list[ModelEvaluationCompatibilityIssue], dict[str, Any], int]:
    issues: list[ModelEvaluationCompatibilityIssue] = []
    loaded_count = 0
    for artifact_type, relative_path in WORKFLOW_KNOWN_RELATIVE_PATHS.items():
        path = workflow_root / relative_path
        required = artifact_type in REQUIRED_WORKFLOW_OUTPUT_ARTIFACT_TYPES
        if not path.is_file():
            issues.append(
                _issue(
                    "error" if required else "warning",
                    "workflow_required_artifact_missing" if required else "workflow_optional_artifact_missing",
                    "Workflow output artifact is missing.",
                    scope="workflow_output",
                    artifact_type=artifact_type,
                    metadata={"artifact_path": relative_path},
                )
            )
            continue
        loaded_count += 1
        if path.name != Path(relative_path).name:
            issues.append(
                _issue(
                    "warning",
                    "workflow_artifact_filename_unexpected",
                    "Workflow output artifact filename differs from the registry location.",
                    scope="workflow_output",
                    artifact_type=artifact_type,
                    metadata={"expected_path": relative_path},
                )
            )
        loaded = _load_json_object(
            path,
            artifact_type=artifact_type,
            scope="workflow_output",
            required=required,
            base_dir=workflow_root,
        )
        issues.extend(loaded["issues"])
        payload = loaded.get("payload")
        if not isinstance(payload, dict):
            continue
        _compare_artifact_to_stable_expectations(
            payload,
            artifact_type=artifact_type,
            relative_path=relative_path,
            golden_payload=golden_payloads.get(artifact_type),
            issues=issues,
        )
        if artifact_type == WORKFLOW_RUN_MANIFEST:
            _compare_manifest_paths(payload, issues)

    try:
        validation_report = validate_model_evaluation_workflow_output_dir(
            workflow_root,
            validation_id="workflow_output_compatibility_validation",
        )
        _append_validator_report_issues(validation_report, issues, artifact_type=None)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues.append(
            _issue(
                "error",
                "workflow_validator_failed",
                "Workflow output validator could not complete.",
                scope="validator",
                metadata={"error": exc.__class__.__name__},
            )
        )

    checks = {
        "workflow_output_dir_display": _display_path(workflow_root, base_dir=Path.cwd()),
        "golden_fixture_dir_display": _display_path(golden_root, base_dir=Path.cwd()),
        "expected_artifact_count": len(WORKFLOW_OUTPUT_ARTIFACT_TYPES),
        "loaded_artifact_count": loaded_count,
        "required_artifact_types": list(REQUIRED_WORKFLOW_OUTPUT_ARTIFACT_TYPES),
        "optional_artifact_types": list(OPTIONAL_WORKFLOW_OUTPUT_ARTIFACT_TYPES),
        "known_relative_paths": WORKFLOW_KNOWN_RELATIVE_PATHS,
        "no_runtime_execution": True,
    }
    return issues, _safe_value(checks), len(WORKFLOW_OUTPUT_ARTIFACT_TYPES)


def _compare_artifact_to_stable_expectations(
    payload: dict[str, Any],
    *,
    artifact_type: str,
    relative_path: str,
    golden_payload: dict[str, Any] | None,
    issues: list[ModelEvaluationCompatibilityIssue],
) -> None:
    schema_info = get_artifact_schema_info(artifact_type)
    expected_schema = (
        golden_payload.get("schema_version")
        if isinstance(golden_payload, dict)
        else schema_info.schema_version
    )
    if payload.get("schema_version") != expected_schema:
        issues.append(
            _issue(
                "error",
                "workflow_schema_version_mismatch",
                "Workflow artifact schema_version differs from golden stable expectations.",
                scope="workflow_output",
                artifact_type=artifact_type,
                metadata={
                    "expected_schema_version": expected_schema,
                    "actual_schema_version": _safe_optional(payload.get("schema_version")),
                    "artifact_path": relative_path,
                },
            )
        )

    contract = get_artifact_schema_contract(artifact_type)
    required_fields = {field.name for field in contract.required_fields}
    missing_required_fields = sorted(field for field in required_fields if field not in payload)
    if missing_required_fields:
        issues.append(
            _issue(
                "error",
                "workflow_required_contract_keys_missing",
                "Workflow artifact is missing required contract keys.",
                scope="workflow_output",
                artifact_type=artifact_type,
                metadata={"missing_fields": missing_required_fields, "artifact_path": relative_path},
            )
        )

    issues.extend(_contract_issues(payload, artifact_type, scope="contract"))
    if _expects_no_runtime_execution(payload, golden_payload, contract) and payload.get("no_runtime_execution") is not True:
        issues.append(
            _issue(
                "error",
                "workflow_no_runtime_execution_missing",
                "Workflow artifact must declare no_runtime_execution=true.",
                scope="workflow_output",
                artifact_type=artifact_type,
                metadata={"artifact_path": relative_path},
            )
        )

    if contract.status_allowed_values:
        status = payload.get("status")
        if status not in contract.status_allowed_values:
            issues.append(
                _issue(
                    "error",
                    "workflow_status_not_allowed",
                    "Workflow artifact status is outside the compatibility contract.",
                    scope="workflow_output",
                    artifact_type=artifact_type,
                    metadata={"allowed_values": list(contract.status_allowed_values), "status": _safe_optional(status)},
                )
            )


def _compare_manifest_paths(
    manifest: dict[str, Any],
    issues: list[ModelEvaluationCompatibilityIssue],
) -> None:
    artifact_paths = manifest.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        issues.append(
            _issue(
                "error",
                "workflow_manifest_artifact_paths_missing",
                "Workflow manifest artifact_paths must be an object.",
                scope="workflow_output",
                artifact_type=WORKFLOW_RUN_MANIFEST,
            )
        )
        return
    for artifact_type, expected_path in WORKFLOW_KNOWN_RELATIVE_PATHS.items():
        value = artifact_paths.get(artifact_type)
        required = artifact_type in REQUIRED_WORKFLOW_OUTPUT_ARTIFACT_TYPES
        if value is None:
            issues.append(
                _issue(
                    "error" if required else "warning",
                    "workflow_manifest_required_path_missing" if required else "workflow_manifest_optional_path_missing",
                    "Workflow manifest does not reference an expected artifact path.",
                    scope="workflow_output",
                    artifact_type=WORKFLOW_RUN_MANIFEST,
                    metadata={"referenced_artifact_type": artifact_type},
                )
            )
            continue
        if not isinstance(value, str):
            issues.append(
                _issue(
                    "error",
                    "workflow_manifest_path_not_string",
                    "Workflow manifest artifact path must be a string when present.",
                    scope="workflow_output",
                    artifact_type=WORKFLOW_RUN_MANIFEST,
                    metadata={"referenced_artifact_type": artifact_type},
                )
            )
            continue
        if _is_absolute_path(value):
            issues.append(
                _issue(
                    "error",
                    "workflow_manifest_absolute_path_leak",
                    "Workflow manifest contains an absolute artifact path.",
                    scope="workflow_output",
                    artifact_type=WORKFLOW_RUN_MANIFEST,
                    metadata={"referenced_artifact_type": artifact_type, "redacted_value": "<absolute_path>"},
                )
            )
            continue
        if value.replace("\\", "/") != expected_path:
            issues.append(
                _issue(
                    "warning",
                    "workflow_manifest_path_unexpected",
                    "Workflow manifest artifact path differs from the registry location.",
                    scope="workflow_output",
                    artifact_type=WORKFLOW_RUN_MANIFEST,
                    metadata={"referenced_artifact_type": artifact_type, "expected_path": expected_path},
                )
            )


def _load_json_object(
    path: Path,
    *,
    artifact_type: str,
    scope: CompatibilityIssueScope,
    required: bool,
    base_dir: Path,
) -> dict[str, Any]:
    display_path = _display_path(path, base_dir=base_dir)
    if not path.is_file():
        return {
            "issues": [
                _issue(
                    "error" if required else "warning",
                    "artifact_missing",
                    "Expected artifact file is missing.",
                    scope=scope,
                    artifact_type=artifact_type,
                    metadata={"artifact_path": display_path},
                )
            ]
        }
    try:
        if path.stat().st_size > _MAX_INPUT_BYTES:
            return {
                "issues": [
                    _issue(
                        "error",
                        "artifact_too_large",
                        "Artifact file is larger than the compatibility input limit.",
                        scope=scope,
                        artifact_type=artifact_type,
                        metadata={"artifact_path": display_path},
                    )
                ]
            }
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {
            "issues": [
                _issue(
                    "error",
                    "artifact_unreadable",
                    "Artifact file could not be read.",
                    scope=scope,
                    artifact_type=artifact_type,
                    metadata={"artifact_path": display_path},
                )
            ]
        }
    except UnicodeDecodeError:
        return {
            "issues": [
                _issue(
                    "error",
                    "artifact_not_utf8_text",
                    "Artifact file is not UTF-8 text.",
                    scope=scope,
                    artifact_type=artifact_type,
                    metadata={"artifact_path": display_path},
                )
            ]
        }
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "text": text,
            "issues": [
                _issue(
                    "error",
                    "artifact_json_decode_error",
                    "Artifact file is not valid JSON.",
                    scope=scope,
                    artifact_type=artifact_type,
                    metadata={"artifact_path": display_path},
                )
            ],
        }
    if not isinstance(payload, dict):
        return {
            "text": text,
            "issues": [
                _issue(
                    "error",
                    "artifact_payload_not_object",
                    "Artifact JSON must be an object.",
                    scope=scope,
                    artifact_type=artifact_type,
                    metadata={"artifact_path": display_path},
                )
            ],
        }
    return {"payload": payload, "text": text, "issues": []}


def _contract_issues(
    payload: dict[str, Any],
    artifact_type: str,
    *,
    scope: CompatibilityIssueScope,
) -> list[ModelEvaluationCompatibilityIssue]:
    result: list[ModelEvaluationCompatibilityIssue] = []
    for issue in validate_artifact_against_contract(payload, artifact_type):
        result.append(_contract_issue_to_compatibility_issue(issue, scope=scope))
    return result


def _contract_issue_to_compatibility_issue(
    issue: ArtifactContractIssue,
    *,
    scope: CompatibilityIssueScope,
) -> ModelEvaluationCompatibilityIssue:
    return _issue(
        issue.severity,
        issue.code,
        issue.message,
        scope=scope,
        artifact_type=issue.artifact_type,
        metadata={"field": issue.field, **(issue.metadata or {})},
    )


def _append_validator_report_issues(
    validation_report: ModelEvaluationArtifactValidationReport,
    issues: list[ModelEvaluationCompatibilityIssue],
    *,
    artifact_type: str | None,
) -> None:
    if validation_report.status == "invalid":
        issues.append(
            _issue(
                "error",
                "artifact_validator_incompatible",
                "Artifact validator reported incompatible workflow artifacts.",
                scope="validator",
                artifact_type=artifact_type,
                metadata={
                    "validator_status": validation_report.status,
                    "validator_error_count": validation_report.error_count,
                    "validator_warning_count": validation_report.warning_count,
                },
            )
        )
    elif validation_report.status == "valid_with_warnings":
        issues.append(
            _issue(
                "warning",
                "artifact_validator_warning",
                "Artifact validator reported workflow artifact warnings.",
                scope="validator",
                artifact_type=artifact_type,
                metadata={
                    "validator_status": validation_report.status,
                    "validator_warning_count": validation_report.warning_count,
                },
            )
        )
    for validator_issue in validation_report.issues:
        issues.append(
            _issue(
                validator_issue.severity,
                validator_issue.code,
                validator_issue.message,
                scope="validator",
                artifact_type=validator_issue.artifact_type,
                metadata=validator_issue.metadata,
            )
        )


def _scan_text_safety(
    text: str,
    issues: list[ModelEvaluationCompatibilityIssue],
    *,
    artifact_type: str,
    scope: CompatibilityIssueScope,
    artifact_path: str,
) -> None:
    if _is_absolute_path(text):
        issues.append(
            _issue(
                "error",
                "absolute_path_leak_detected",
                "Artifact text contains an absolute local path string.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"artifact_path": artifact_path, "redacted_value": "<absolute_path>"},
            )
        )
    if ".gguf" in text.lower():
        issues.append(
            _issue(
                "error",
                "gguf_reference_detected",
                "Artifact text contains a GGUF reference.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"artifact_path": artifact_path},
            )
        )
    if _RAW_MARKER_RE.search(text):
        issues.append(
            _issue(
                "warning",
                "raw_content_marker_detected",
                "Artifact text contains a suspicious raw content marker.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"artifact_path": artifact_path},
            )
        )


def _scan_value_safety(
    value: Any,
    issues: list[ModelEvaluationCompatibilityIssue],
    *,
    artifact_type: str,
    scope: CompatibilityIssueScope,
    field_path: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_path = f"{field_path}.{key_text}" if field_path != "$" else key_text
            normalized_key = key_text.strip().lower()
            if normalized_key in _SUSPICIOUS_KEY_NAMES:
                issues.append(
                    _issue(
                        "error",
                        "suspicious_secret_or_raw_field",
                        "Artifact contains a suspicious secret/raw field name.",
                        scope=scope,
                        artifact_type=artifact_type,
                        metadata={"field_path": key_path},
                    )
                )
            _scan_value_safety(child, issues, artifact_type=artifact_type, scope=scope, field_path=key_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value[:500]):
            _scan_value_safety(child, issues, artifact_type=artifact_type, scope=scope, field_path=f"{field_path}[{index}]")
        return
    if not isinstance(value, str):
        return

    lower = value.lower()
    if _is_absolute_path(value):
        code = "absolute_gguf_path_leak_detected" if ".gguf" in lower else "absolute_path_leak_detected"
        issues.append(
            _issue(
                "error",
                code,
                "Artifact contains an absolute local path string.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"field_path": field_path, "redacted_value": "<absolute_path>"},
            )
        )
    if _SECRET_VALUE_RE.search(value):
        issues.append(
            _issue(
                "error",
                "secret_like_value_detected",
                "Artifact contains a secret-like value.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"field_path": field_path, "redacted_value": "<secret_like_value>"},
            )
        )
    if ".gguf" in lower:
        issues.append(
            _issue(
                "error",
                "gguf_reference_detected",
                "Artifact contains a GGUF reference.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"field_path": field_path},
            )
        )
    if _RAW_MARKER_RE.search(value):
        issues.append(
            _issue(
                "warning",
                "raw_content_marker_detected",
                "Artifact contains a suspicious raw content marker.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"field_path": field_path},
            )
        )
    if _contains_bad_production_wording(lower):
        issues.append(
            _issue(
                "error",
                "production_recommendation_wording_detected",
                "Artifact contains production recommendation wording.",
                scope=scope,
                artifact_type=artifact_type,
                metadata={"field_path": field_path},
            )
        )


def _contains_bad_production_wording(lower_value: str) -> bool:
    if any(phrase in lower_value for phrase in _BAD_PRODUCTION_PHRASES):
        return True
    return "production recommendation" in lower_value and "not a production recommendation" not in lower_value


def _expects_no_runtime_execution(
    payload: dict[str, Any],
    golden_payload: dict[str, Any] | None,
    contract: Any,
) -> bool:
    contract_fields = {field.name for field in (*contract.required_fields, *contract.optional_fields)}
    return (
        "no_runtime_execution" in contract_fields
        or "no_runtime_execution" in payload
        or (isinstance(golden_payload, dict) and "no_runtime_execution" in golden_payload)
    )


def _workflow_fixture_files_present(golden_root: Path) -> bool:
    return all((golden_root / relative_path).is_file() for relative_path in WORKFLOW_KNOWN_RELATIVE_PATHS.values())


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _report(
    *,
    compatibility_id: str,
    golden_fixture_dir: Path,
    workflow_output_dir: Path | None,
    checked_artifact_count: int,
    checks: dict[str, Any],
    issues: list[ModelEvaluationCompatibilityIssue],
) -> ModelEvaluationCompatibilityReport:
    sorted_issues = sorted(issues, key=lambda item: ({"error": 0, "warning": 1, "info": 2}[item.severity], item.code))
    error_count = sum(1 for issue in sorted_issues if issue.severity == "error")
    warning_count = sum(1 for issue in sorted_issues if issue.severity == "warning")
    status: CompatibilityStatus = (
        "incompatible"
        if error_count
        else ("compatible_with_warnings" if warning_count else "compatible")
    )
    return ModelEvaluationCompatibilityReport(
        status=status,
        compatibility_id=_safe_text(compatibility_id),
        golden_fixture_dir_display=_display_path(golden_fixture_dir, base_dir=Path.cwd()) or "golden_fixture",
        workflow_output_dir_display=(
            _display_path(workflow_output_dir, base_dir=Path.cwd())
            if workflow_output_dir is not None
            else None
        ),
        checked_artifact_count=checked_artifact_count,
        issue_count=len(sorted_issues),
        warning_count=warning_count,
        error_count=error_count,
        checks=_safe_value(checks),
        issues=sorted_issues,
    )


def _issue(
    severity: CompatibilityIssueSeverity,
    code: str,
    message: str,
    *,
    scope: CompatibilityIssueScope | None = None,
    artifact_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ModelEvaluationCompatibilityIssue:
    return ModelEvaluationCompatibilityIssue(
        severity=severity,
        code=code,
        scope=scope,
        artifact_type=artifact_type,
        message=message,
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
    name = path_obj.name or PureWindowsPath(path_text).name or PurePosixPath(path_text).name or "path"
    return f"<absolute_path>/{_safe_text(name)}"


def _is_absolute_path(path: str) -> bool:
    return (
        PureWindowsPath(path).is_absolute()
        or PurePosixPath(path).is_absolute()
        or _WINDOWS_ABSOLUTE_RE.search(path) is not None
        or _POSIX_ABSOLUTE_RE.search(path) is not None
        or _UNC_ABSOLUTE_RE.search(path) is not None
    )


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


def _safe_text(value: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    text = _WINDOWS_ABSOLUTE_RE.sub("<absolute_path>", value)
    text = _POSIX_ABSOLUTE_RE.sub("<absolute_path>", text)
    text = _UNC_ABSOLUTE_RE.sub("<absolute_path>", text)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _markdown_preview(report: ModelEvaluationCompatibilityReport) -> str:
    lines = [
        "# Model Evaluation Compatibility",
        "",
        f"- status: `{report.status}`",
        f"- compatibility_id: `{report.compatibility_id}`",
        f"- checked artifacts: `{report.checked_artifact_count}`",
        f"- errors: `{report.error_count}`",
        f"- warnings: `{report.warning_count}`",
        f"- no runtime execution: `{str(report.no_runtime_execution).lower()}`",
        "",
        "## Issues",
        "",
    ]
    if report.issues:
        for issue in report.issues:
            artifact = f" `{issue.artifact_type}`" if issue.artifact_type else ""
            lines.append(f"- `{issue.severity}` `{issue.code}`{artifact}: {issue.message}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"
