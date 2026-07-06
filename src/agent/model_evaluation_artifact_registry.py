from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MODEL_CATALOG = "model_catalog"
MODEL_COMPARISON_PLAN = "model_comparison_plan"
MODEL_PAIR_MATRIX_RUN_SUMMARY = "model_pair_matrix_run_summary"
MATRIX_RUN_ADAPTER_SUMMARY = "matrix_run_adapter_summary"
MODEL_PAIR_EXECUTION_READINESS_SUMMARY = "model_pair_execution_readiness_summary"
PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SUMMARY = "prepared_normality_judge_prompt_pack_summary"
TASK_CORRECTNESS_EVALUATION_RESULT = "task_correctness_evaluation_result"
TASK_CORRECTNESS_BATCH_SUMMARY = "task_correctness_batch_summary"
READINESS_REPORT = "readiness_report"
NORMALITY_COMPARISON_SUMMARY = "normality_comparison_summary"
MODEL_RESOURCE_SUMMARY = "model_resource_summary"
MODEL_EVALUATION_SCORECARD = "model_evaluation_scorecard"
WORKFLOW_BUNDLE = "workflow_bundle"
WORKFLOW_RUN_MANIFEST = "workflow_run_manifest"
ARTIFACT_VALIDATION_REPORT = "artifact_validation_report"
WORKFLOW_CONFIG = "workflow_config"
MODEL_EVALUATION_COMPATIBILITY_REPORT = "model_evaluation_compatibility_report"

ArtifactType = Literal[
    "model_catalog",
    "model_comparison_plan",
    "model_pair_matrix_run_summary",
    "matrix_run_adapter_summary",
    "model_pair_execution_readiness_summary",
    "prepared_normality_judge_prompt_pack_summary",
    "task_correctness_evaluation_result",
    "task_correctness_batch_summary",
    "readiness_report",
    "normality_comparison_summary",
    "model_resource_summary",
    "model_evaluation_scorecard",
    "workflow_bundle",
    "workflow_run_manifest",
    "artifact_validation_report",
    "workflow_config",
    "model_evaluation_compatibility_report",
]
WorkflowBundleArtifactType = Literal[
    "model_catalog",
    "model_comparison_plan",
    "readiness_report",
    "normality_comparison_summary",
    "model_resource_summary",
    "model_evaluation_scorecard",
]
WorkflowOutputArtifactType = Literal[
    "model_comparison_plan",
    "readiness_report",
    "normality_comparison_summary",
    "model_resource_summary",
    "model_evaluation_scorecard",
    "workflow_bundle",
    "workflow_run_manifest",
]

CLI_TOOL_NAME = "offline_model_evaluation_cli"
SUPPORTED_CLI_SUBCOMMANDS = ("run", "validate", "compatibility", "check", "schema", "version")


@dataclass(frozen=True)
class ArtifactSchemaInfo:
    artifact_type: ArtifactType
    schema_version: str
    default_filename: str
    workflow_relative_path: str | None = None
    required_for_workflow_bundle: bool = False
    optional_for_workflow_bundle: bool = False
    required_for_workflow_output: bool = False
    optional_for_workflow_output: bool = False
    description: str = ""
    status_field: str | None = None
    expected_top_level_type: str = "object"


_REGISTRY: tuple[ArtifactSchemaInfo, ...] = (
    ArtifactSchemaInfo(
        artifact_type=MODEL_CATALOG,
        schema_version="model_catalog_v1",
        default_filename="model_catalog.json",
        required_for_workflow_bundle=True,
        description="Offline model catalog metadata.",
    ),
    ArtifactSchemaInfo(
        artifact_type=MODEL_COMPARISON_PLAN,
        schema_version="model_comparison_plan_v1",
        default_filename="model_comparison_plan.json",
        workflow_relative_path="plan/model_comparison_plan.json",
        required_for_workflow_bundle=True,
        required_for_workflow_output=True,
        description="Offline model comparison plan.",
    ),
    ArtifactSchemaInfo(
        artifact_type=MODEL_PAIR_MATRIX_RUN_SUMMARY,
        schema_version="model_pair_matrix_run_summary_v1",
        default_filename="model_pair_matrix_run_summary.json",
        description="Offline model-pair matrix run summary.",
    ),
    ArtifactSchemaInfo(
        artifact_type=MATRIX_RUN_ADAPTER_SUMMARY,
        schema_version="matrix_run_adapter_summary_v1",
        default_filename="matrix_run_adapter_summary.json",
        description="Offline model-pair matrix adapter output summary.",
    ),
    ArtifactSchemaInfo(
        artifact_type=MODEL_PAIR_EXECUTION_READINESS_SUMMARY,
        schema_version="model_pair_execution_readiness_v1",
        default_filename="model_pair_execution_readiness_summary.json",
        description="Offline model-pair execution readiness validation summary.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SUMMARY,
        schema_version="prepared_normality_judge_prompt_pack_v1",
        default_filename="normality_judge_prompt_pack_summary.json",
        description="Offline prepared normality judge prompt pack summary.",
    ),
    ArtifactSchemaInfo(
        artifact_type=TASK_CORRECTNESS_EVALUATION_RESULT,
        schema_version="task_correctness_evaluation_result_v1",
        default_filename="task_correctness_evaluation_result.json",
        description="Offline task correctness evaluation result.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=TASK_CORRECTNESS_BATCH_SUMMARY,
        schema_version="task_correctness_batch_summary_v1",
        default_filename="task_correctness_batch_summary.json",
        description="Offline task correctness batch summary.",
    ),
    ArtifactSchemaInfo(
        artifact_type=READINESS_REPORT,
        schema_version="model_comparison_readiness_v1",
        default_filename="model_comparison_readiness_report.json",
        workflow_relative_path="readiness/model_comparison_readiness_report.json",
        required_for_workflow_bundle=True,
        required_for_workflow_output=True,
        description="Offline model comparison readiness report.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=NORMALITY_COMPARISON_SUMMARY,
        schema_version="normality_comparison_v1",
        default_filename="normality_comparison_summary.json",
        workflow_relative_path="normality/normality_comparison_summary.json",
        optional_for_workflow_bundle=True,
        optional_for_workflow_output=True,
        description="Offline normality comparison summary.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=MODEL_RESOURCE_SUMMARY,
        schema_version="model_resource_summary_v1",
        default_filename="model_resource_summary.json",
        workflow_relative_path="resource/model_resource_summary.json",
        optional_for_workflow_bundle=True,
        optional_for_workflow_output=True,
        description="Offline model resource summary.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=MODEL_EVALUATION_SCORECARD,
        schema_version="model_evaluation_scorecard_v1",
        default_filename="model_evaluation_scorecard.json",
        workflow_relative_path="scorecard/model_evaluation_scorecard.json",
        optional_for_workflow_bundle=True,
        required_for_workflow_output=True,
        description="Offline model evaluation scorecard.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=WORKFLOW_BUNDLE,
        schema_version="model_evaluation_workflow_bundle_v1",
        default_filename="model_evaluation_workflow_bundle.json",
        workflow_relative_path="bundle/model_evaluation_workflow_bundle.json",
        required_for_workflow_output=True,
        description="Offline model evaluation workflow bundle.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=WORKFLOW_RUN_MANIFEST,
        schema_version="model_evaluation_workflow_run_v1",
        default_filename="workflow_run_manifest.json",
        workflow_relative_path="workflow_run_manifest.json",
        required_for_workflow_output=True,
        description="Offline workflow run manifest.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=ARTIFACT_VALIDATION_REPORT,
        schema_version="model_evaluation_artifact_validation_v1",
        default_filename="model_evaluation_artifact_validation_report.json",
        description="Offline workflow artifact validation report.",
        status_field="status",
    ),
    ArtifactSchemaInfo(
        artifact_type=WORKFLOW_CONFIG,
        schema_version="model_evaluation_workflow_config_v1",
        default_filename="model_evaluation_workflow.example.json",
        description="Offline model evaluation workflow config.",
    ),
    ArtifactSchemaInfo(
        artifact_type=MODEL_EVALUATION_COMPATIBILITY_REPORT,
        schema_version="model_evaluation_compatibility_report_v1",
        default_filename="model_evaluation_compatibility_report.json",
        description="Offline model evaluation compatibility report.",
        status_field="status",
    ),
)

_REGISTRY_BY_TYPE: dict[ArtifactType, ArtifactSchemaInfo] = {
    info.artifact_type: info for info in _REGISTRY
}


def get_artifact_schema_info(artifact_type: str) -> ArtifactSchemaInfo:
    try:
        return _REGISTRY_BY_TYPE[artifact_type]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"unknown artifact type: {artifact_type}") from exc


def list_artifact_schema_infos() -> tuple[ArtifactSchemaInfo, ...]:
    return _REGISTRY


def get_supported_schema_versions() -> tuple[str, ...]:
    return tuple(info.schema_version for info in _REGISTRY)


def get_workflow_known_relative_paths() -> dict[WorkflowOutputArtifactType, str]:
    return {
        info.artifact_type: info.workflow_relative_path
        for info in _REGISTRY
        if info.workflow_relative_path is not None
    }  # type: ignore[return-value]


def get_required_workflow_artifact_types() -> tuple[WorkflowBundleArtifactType, ...]:
    return tuple(
        info.artifact_type
        for info in _REGISTRY
        if info.required_for_workflow_bundle
    )  # type: ignore[return-value]


def get_optional_workflow_artifact_types() -> tuple[WorkflowBundleArtifactType, ...]:
    return tuple(
        info.artifact_type
        for info in _REGISTRY
        if info.optional_for_workflow_bundle
    )  # type: ignore[return-value]


def get_all_workflow_bundle_artifact_types() -> tuple[WorkflowBundleArtifactType, ...]:
    return (
        *get_required_workflow_artifact_types(),
        *get_optional_workflow_artifact_types(),
    )


def get_required_workflow_output_artifact_types() -> tuple[WorkflowOutputArtifactType, ...]:
    return tuple(
        info.artifact_type
        for info in _REGISTRY
        if info.required_for_workflow_output
    )  # type: ignore[return-value]


def get_optional_workflow_output_artifact_types() -> tuple[WorkflowOutputArtifactType, ...]:
    return tuple(
        info.artifact_type
        for info in _REGISTRY
        if info.optional_for_workflow_output
    )  # type: ignore[return-value]


def get_all_workflow_output_artifact_types() -> tuple[WorkflowOutputArtifactType, ...]:
    return (
        *get_required_workflow_output_artifact_types(),
        *get_optional_workflow_output_artifact_types(),
    )


def get_default_artifact_filename(artifact_type: str) -> str:
    return get_artifact_schema_info(artifact_type).default_filename


def get_artifact_contract_supported_types() -> tuple[ArtifactType, ...]:
    return tuple(info.artifact_type for info in _REGISTRY)


def artifact_type_from_workflow_relative_path(path: str) -> WorkflowOutputArtifactType | None:
    normalized = path.replace("\\", "/").strip()
    for artifact_type, relative_path in get_workflow_known_relative_paths().items():
        if normalized == relative_path:
            return artifact_type
    return None


def get_expected_schema_versions_for_workflow_outputs() -> dict[WorkflowOutputArtifactType, str]:
    return {
        artifact_type: get_artifact_schema_info(artifact_type).schema_version
        for artifact_type in get_all_workflow_output_artifact_types()
    }


def build_version_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "tool": CLI_TOOL_NAME,
        "supported_subcommands": list(SUPPORTED_CLI_SUBCOMMANDS),
        "supported_schema_versions": list(get_supported_schema_versions()),
        "supported_artifact_types": [
            info.artifact_type for info in list_artifact_schema_infos()
        ],
        "workflow_known_relative_paths": get_workflow_known_relative_paths(),
        "required_workflow_artifact_types": list(get_required_workflow_artifact_types()),
        "optional_workflow_artifact_types": list(get_optional_workflow_artifact_types()),
        "artifact_contract_version": "artifact_contract_v1",
        "artifact_contract_supported_types": list(get_artifact_contract_supported_types()),
        "no_runtime_execution": True,
    }
