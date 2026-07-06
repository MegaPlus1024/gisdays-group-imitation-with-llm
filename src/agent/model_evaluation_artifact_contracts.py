from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .model_evaluation_artifact_registry import (
    ARTIFACT_VALIDATION_REPORT,
    MODEL_CATALOG,
    MODEL_COMPARISON_PLAN,
    MODEL_EVALUATION_COMPATIBILITY_REPORT,
    MODEL_EVALUATION_SCORECARD,
    MODEL_PAIR_MATRIX_RUN_SUMMARY,
    MODEL_RESOURCE_SUMMARY,
    NORMALITY_COMPARISON_SUMMARY,
    READINESS_REPORT,
    TASK_CORRECTNESS_BATCH_SUMMARY,
    TASK_CORRECTNESS_EVALUATION_RESULT,
    WORKFLOW_BUNDLE,
    WORKFLOW_CONFIG,
    WORKFLOW_RUN_MANIFEST,
    ArtifactType,
    get_artifact_schema_info,
    list_artifact_schema_infos,
)


ARTIFACT_CONTRACT_VERSION = "artifact_contract_v1"

JSONTypeName = Literal[
    "object",
    "array",
    "string",
    "number",
    "integer",
    "boolean",
    "null",
    "any",
]
ContractIssueSeverity = Literal["warning", "error"]


@dataclass(frozen=True)
class ArtifactFieldContract:
    name: str
    required: bool
    expected_type: JSONTypeName
    allowed_values: tuple[Any, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class ArtifactSchemaContract:
    artifact_type: ArtifactType
    schema_version: str
    required_fields: tuple[ArtifactFieldContract, ...]
    optional_fields: tuple[ArtifactFieldContract, ...] = ()
    status_allowed_values: tuple[str, ...] = ()
    description: str = ""
    contract_version: str = ARTIFACT_CONTRACT_VERSION


@dataclass(frozen=True)
class ArtifactContractIssue:
    severity: ContractIssueSeverity
    code: str
    artifact_type: str
    field: str | None
    message: str
    metadata: dict[str, Any] | None = None


def get_artifact_schema_contract(artifact_type: str) -> ArtifactSchemaContract:
    try:
        return _CONTRACTS_BY_TYPE[artifact_type]
    except KeyError as exc:
        raise ValueError(f"unknown artifact contract type: {artifact_type}") from exc


def list_artifact_schema_contracts() -> tuple[ArtifactSchemaContract, ...]:
    return tuple(_CONTRACTS_BY_TYPE[info.artifact_type] for info in list_artifact_schema_infos())


def export_artifact_schema_contracts() -> dict[str, Any]:
    contracts = [_contract_to_json(contract, full=True) for contract in list_artifact_schema_contracts()]
    return {
        "status": "ok",
        "contract_version": ARTIFACT_CONTRACT_VERSION,
        "artifact_count": len(contracts),
        "artifacts": contracts,
        "no_runtime_execution": True,
    }


def export_artifact_schema_contract_summaries() -> dict[str, Any]:
    contracts = [_contract_to_json(contract, full=False) for contract in list_artifact_schema_contracts()]
    return {
        "status": "ok",
        "contract_version": ARTIFACT_CONTRACT_VERSION,
        "artifact_count": len(contracts),
        "artifacts": contracts,
        "no_runtime_execution": True,
    }


def validate_artifact_against_contract(
    artifact: dict[str, Any],
    artifact_type: str,
) -> list[ArtifactContractIssue]:
    contract = get_artifact_schema_contract(artifact_type)
    issues: list[ArtifactContractIssue] = []
    if not isinstance(artifact, dict):
        return [
            ArtifactContractIssue(
                severity="error",
                code="contract_payload_not_object",
                artifact_type=artifact_type,
                field=None,
                message="Artifact payload must be a JSON object.",
            )
        ]

    issues.extend(validate_artifact_schema_version(artifact, artifact_type))
    field_contracts = [*contract.required_fields, *contract.optional_fields]
    field_contract_by_name = {field.name: field for field in field_contracts}

    for field in contract.required_fields:
        if field.name not in artifact:
            issues.append(
                ArtifactContractIssue(
                    severity="error",
                    code="contract_required_field_missing",
                    artifact_type=artifact_type,
                    field=field.name,
                    message="Required artifact field is missing.",
                    metadata={"expected_type": field.expected_type},
                )
            )

    for field_name, field in field_contract_by_name.items():
        if field_name not in artifact:
            continue
        value = artifact[field_name]
        if value is None and not field.required:
            continue
        if not _json_type_matches(value, field.expected_type):
            issues.append(
                ArtifactContractIssue(
                    severity="error",
                    code="contract_field_type_mismatch",
                    artifact_type=artifact_type,
                    field=field_name,
                    message="Artifact field has an unexpected JSON type.",
                    metadata={
                        "expected_type": field.expected_type,
                        "actual_type": _json_type_name(value),
                    },
                )
            )
            continue
        if field.allowed_values and value not in field.allowed_values:
            issues.append(
                ArtifactContractIssue(
                    severity="error",
                    code="contract_field_value_not_allowed",
                    artifact_type=artifact_type,
                    field=field_name,
                    message="Artifact field value is not allowed by the contract.",
                    metadata={"allowed_values": list(field.allowed_values)},
                )
            )

    status = artifact.get("status")
    if contract.status_allowed_values and status not in contract.status_allowed_values:
        issues.append(
            ArtifactContractIssue(
                severity="error",
                code="contract_status_not_allowed",
                artifact_type=artifact_type,
                field="status",
                message="Artifact status is not allowed by the contract.",
                metadata={"allowed_values": list(contract.status_allowed_values)},
            )
        )
    return issues


def validate_artifact_schema_version(
    artifact: dict[str, Any],
    artifact_type: str,
) -> list[ArtifactContractIssue]:
    contract = get_artifact_schema_contract(artifact_type)
    schema_version = artifact.get("schema_version") if isinstance(artifact, dict) else None
    if schema_version == contract.schema_version:
        return []
    return [
        ArtifactContractIssue(
            severity="error",
            code="contract_schema_version_mismatch",
            artifact_type=artifact_type,
            field="schema_version",
            message="Artifact schema_version does not match the registry contract.",
            metadata={"expected_schema_version": contract.schema_version},
        )
    ]


def _contract_to_json(contract: ArtifactSchemaContract, *, full: bool) -> dict[str, Any]:
    if full:
        return asdict(contract)
    return {
        "artifact_type": contract.artifact_type,
        "schema_version": contract.schema_version,
        "required_field_count": len(contract.required_fields),
        "optional_field_count": len(contract.optional_fields),
        "status_allowed_values": list(contract.status_allowed_values),
        "description": contract.description,
        "contract_version": contract.contract_version,
    }


def _contract(
    artifact_type: ArtifactType,
    *,
    required: tuple[ArtifactFieldContract, ...],
    optional: tuple[ArtifactFieldContract, ...] = (),
    statuses: tuple[str, ...] = (),
) -> ArtifactSchemaContract:
    info = get_artifact_schema_info(artifact_type)
    required = _attach_status_allowed_values(required, statuses)
    optional = _attach_status_allowed_values(optional, statuses)
    return ArtifactSchemaContract(
        artifact_type=info.artifact_type,
        schema_version=info.schema_version,
        required_fields=required,
        optional_fields=optional,
        status_allowed_values=statuses,
        description=info.description,
    )


def _attach_status_allowed_values(
    fields: tuple[ArtifactFieldContract, ...],
    statuses: tuple[str, ...],
) -> tuple[ArtifactFieldContract, ...]:
    if not statuses:
        return fields
    return tuple(
        ArtifactFieldContract(
            name=field.name,
            required=field.required,
            expected_type=field.expected_type,
            allowed_values=statuses if field.name == "status" and not field.allowed_values else field.allowed_values,
            description=field.description,
        )
        for field in fields
    )


def _field(
    name: str,
    expected_type: JSONTypeName,
    *,
    required: bool = True,
    allowed_values: tuple[Any, ...] = (),
    description: str = "",
) -> ArtifactFieldContract:
    return ArtifactFieldContract(
        name=name,
        required=required,
        expected_type=expected_type,
        allowed_values=allowed_values,
        description=description,
    )


def _optional(name: str, expected_type: JSONTypeName, **kwargs: Any) -> ArtifactFieldContract:
    return _field(name, expected_type, required=False, **kwargs)


def _json_type_matches(value: Any, expected_type: JSONTypeName) -> bool:
    if expected_type == "any":
        return True
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return False


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


_CONTRACTS_BY_TYPE: dict[str, ArtifactSchemaContract] = {
    MODEL_CATALOG: _contract(
        MODEL_CATALOG,
        required=(
            _field("schema_version", "string"),
            _field("models", "array"),
        ),
    ),
    MODEL_COMPARISON_PLAN: _contract(
        MODEL_COMPARISON_PLAN,
        required=(
            _field("schema_version", "string"),
            _field("plan_id", "string"),
            _field("candidate_pairs", "array"),
            _field("scenarios", "array"),
            _field("trials", "array"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("model_catalog_summary", "object"),
            _optional("warnings", "array"),
            _optional("tags", "array"),
            _optional("notes", "array"),
            _optional("created_by", "string"),
        ),
    ),
    MODEL_PAIR_MATRIX_RUN_SUMMARY: _contract(
        MODEL_PAIR_MATRIX_RUN_SUMMARY,
        required=(
            _field("schema_version", "string"),
            _field("run_id", "string"),
            _field("plan_id", "string"),
            _field("execution_mode", "string"),
            _field("trial_count", "integer"),
            _field("trial_results", "array"),
            _field("warnings", "array"),
            _field("notes", "array"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("succeeded_count", "integer"),
            _optional("failed_count", "integer"),
            _optional("skipped_count", "integer"),
            _optional("dry_run_count", "integer"),
            _optional("pair_summaries", "array"),
            _optional("scenario_summaries", "array"),
        ),
    ),
    TASK_CORRECTNESS_EVALUATION_RESULT: _contract(
        TASK_CORRECTNESS_EVALUATION_RESULT,
        required=(
            _field("schema_version", "string"),
            _field("trial_id", "string"),
            _field("scenario_id", "string"),
            _field("pair_id", "string"),
            _field("status", "string"),
            _field("check_results", "array"),
            _field("failure_reasons", "array"),
            _field("warnings", "array"),
            _field("notes", "array"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("task_success", "boolean"),
            _optional("correctness_score", "number"),
        ),
        statuses=("passed", "failed", "partial", "skipped", "invalid_input"),
    ),
    TASK_CORRECTNESS_BATCH_SUMMARY: _contract(
        TASK_CORRECTNESS_BATCH_SUMMARY,
        required=(
            _field("schema_version", "string"),
            _field("summary_id", "string"),
            _field("input_count", "integer"),
            _field("evaluated_count", "integer"),
            _field("results", "array"),
            _field("warnings", "array"),
            _field("notes", "array"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("invalid_count", "integer"),
            _optional("passed_count", "integer"),
            _optional("failed_count", "integer"),
            _optional("partial_count", "integer"),
            _optional("skipped_count", "integer"),
            _optional("mean_correctness_score", "number"),
            _optional("by_pair", "object"),
            _optional("by_scenario", "object"),
        ),
    ),
    READINESS_REPORT: _contract(
        READINESS_REPORT,
        required=(
            _field("schema_version", "string"),
            _field("status", "string"),
            _field("plan_id", "string"),
            _field("trial_count", "integer"),
            _field("candidate_pair_count", "integer"),
            _field("issues", "array"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("scenario_count", "integer"),
            _optional("summary", "object"),
            _optional("report_path_relative", "string"),
            _optional("markdown_preview_path_relative", "string"),
        ),
        statuses=("ready", "ready_with_warnings", "not_ready"),
    ),
    NORMALITY_COMPARISON_SUMMARY: _contract(
        NORMALITY_COMPARISON_SUMMARY,
        required=(
            _field("schema_version", "string"),
            _field("status", "string"),
            _field("input_summary_count", "integer"),
            _field("total_entries", "integer"),
            _field("evaluated_entries", "integer"),
            _field("failed_entries", "integer"),
            _field("groups", "object"),
            _field("warnings", "array"),
        ),
        optional=(
            _optional("overall", "object"),
            _optional("leaderboard", "array"),
            _optional("model_catalog_used", "boolean"),
        ),
        statuses=("ok", "invalid_input"),
    ),
    MODEL_RESOURCE_SUMMARY: _contract(
        MODEL_RESOURCE_SUMMARY,
        required=(
            _field("schema_version", "string"),
            _field("status", "string"),
            _field("input_count", "integer"),
            _field("observation_count", "integer"),
            _field("invalid_count", "integer"),
            _field("groups", "object"),
            _field("warnings", "array"),
        ),
        optional=(
            _optional("summary_id", "string"),
            _optional("tags", "array"),
            _optional("catalog_metadata", "object"),
        ),
        statuses=("ok", "invalid_input"),
    ),
    MODEL_EVALUATION_SCORECARD: _contract(
        MODEL_EVALUATION_SCORECARD,
        required=(
            _field("schema_version", "string"),
            _field("status", "string"),
            _field("scorecard_id", "string"),
            _field("model_pairs", "array"),
            _field("models", "array"),
            _field("warnings", "array"),
            _field("notes", "array"),
        ),
        optional=(
            _optional("model_count", "integer"),
            _optional("model_pair_count", "integer"),
            _optional("overall", "object"),
            _optional("plan_used", "boolean"),
            _optional("normality_summary_used", "boolean"),
            _optional("resource_summary_used", "boolean"),
            _optional("task_correctness_summary_used", "boolean"),
            _optional("task_correctness_metrics", "object"),
            _optional("no_runtime_execution", "boolean"),
        ),
        statuses=("ok", "invalid_input"),
    ),
    WORKFLOW_BUNDLE: _contract(
        WORKFLOW_BUNDLE,
        required=(
            _field("schema_version", "string"),
            _field("status", "string"),
            _field("bundle_id", "string"),
            _field("artifacts", "object"),
            _field("summary", "object"),
            _field("warnings", "array"),
            _field("notes", "array"),
        ),
        optional=(
            _optional("no_runtime_execution", "boolean"),
            _optional("bundle_path_relative", "string"),
            _optional("markdown_preview_path_relative", "string"),
        ),
        statuses=("complete", "partial", "invalid"),
    ),
    WORKFLOW_RUN_MANIFEST: _contract(
        WORKFLOW_RUN_MANIFEST,
        required=(
            _field("schema_version", "string"),
            _field("workflow_id", "string"),
            _field("status", "string"),
            _field("artifact_paths", "object"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("warnings", "array"),
            _optional("tags", "array"),
            _optional("notes", "array"),
            _optional("config_used", "boolean"),
        ),
        statuses=("ok", "partial", "invalid", "write_failed"),
    ),
    ARTIFACT_VALIDATION_REPORT: _contract(
        ARTIFACT_VALIDATION_REPORT,
        required=(
            _field("schema_version", "string"),
            _field("status", "string"),
            _field("validation_id", "string"),
            _field("checked_artifacts", "object"),
            _field("issue_count", "integer"),
            _field("warning_count", "integer"),
            _field("error_count", "integer"),
            _field("issues", "array"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("artifact_count", "integer"),
            _optional("cross_link_summary", "object"),
            _optional("notes", "array"),
        ),
        statuses=("valid", "valid_with_warnings", "invalid"),
    ),
    WORKFLOW_CONFIG: _contract(
        WORKFLOW_CONFIG,
        required=(
            _field("schema_version", "string"),
            _field("model_catalog_path", "string"),
            _field("scenario_paths", "array"),
            _field("output_dir", "string"),
        ),
        optional=(
            _optional("workflow_id", "string"),
            _optional("repetitions_per_pair", "integer"),
            _optional("include_self_pairs", "boolean"),
            _optional("include_role_mismatch_pairs", "boolean"),
            _optional("task_correctness_summary_path", "string"),
            _optional("tags", "array"),
            _optional("notes", "array"),
            _optional("write_markdown_previews", "boolean"),
        ),
    ),
    MODEL_EVALUATION_COMPATIBILITY_REPORT: _contract(
        MODEL_EVALUATION_COMPATIBILITY_REPORT,
        required=(
            _field("schema_version", "string"),
            _field("status", "string"),
            _field("compatibility_id", "string"),
            _field("checked_artifact_count", "integer"),
            _field("issue_count", "integer"),
            _field("warning_count", "integer"),
            _field("error_count", "integer"),
            _field("issues", "array"),
            _field("notes", "array"),
            _field("no_runtime_execution", "boolean"),
        ),
        optional=(
            _optional("golden_fixture_dir_display", "string"),
            _optional("workflow_output_dir_display", "string"),
            _optional("checks", "object"),
            _optional("report_path_relative", "string"),
            _optional("markdown_preview_path_relative", "string"),
        ),
        statuses=("compatible", "compatible_with_warnings", "incompatible"),
    ),
}
