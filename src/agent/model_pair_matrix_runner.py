from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol

from pydantic import BaseModel, Field, field_validator

from .model_comparison_plan import (
    MODEL_COMPARISON_PLAN_SCHEMA_VERSION,
    ModelComparisonPlan,
)


MODEL_PAIR_MATRIX_RUN_SUMMARY_SCHEMA_VERSION = "model_pair_matrix_run_summary_v1"
MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME = "model_pair_matrix_run_summary.json"
MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME = "model_pair_trial_results.jsonl"
DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE = "dry_run"

ModelPairTrialStatus = Literal["succeeded", "failed", "skipped", "dry_run"]


class ModelPairMatrixPlanError(ValueError):
    """Controlled plan validation error safe to expose through CLI JSON."""


class ModelPairTrialExecutionRequest(BaseModel):
    trial_id: str
    scenario_id: str
    scenario_path: str
    pair_id: str
    orchestrator_model_id: str
    executor_model_id: str
    repeat_index: int
    tags: list[str] = Field(default_factory=list)
    task_summary: str | None = None
    expected_outputs: list[Any] | dict[str, Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    no_runtime_execution: bool = True
    execution_mode: str = DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE

    @field_validator(
        "trial_id",
        "scenario_id",
        "scenario_path",
        "pair_id",
        "orchestrator_model_id",
        "executor_model_id",
        "execution_mode",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("trial execution request text fields must be non-empty.")
        return cleaned

    @field_validator("repeat_index")
    @classmethod
    def validate_repeat_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("repeat_index must be >= 1.")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)

    @field_validator("task_summary")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("task_summary must be non-empty when provided.")
        return cleaned


class ModelPairTrialExecutionResult(BaseModel):
    trial_id: str
    scenario_id: str
    pair_id: str
    orchestrator_model_id: str
    executor_model_id: str
    status: ModelPairTrialStatus
    task_success: bool | None = None
    correctness_score: float | None = None
    normality_input_ref: str | None = None
    resource_observation: dict[str, Any] | None = None
    group_history: list[dict[str, Any]] = Field(default_factory=list)
    event_history: list[dict[str, Any]] = Field(default_factory=list)
    activity_trace: list[dict[str, Any]] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    task_summary: str | None = None
    expected_outputs: list[Any] | dict[str, Any] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    no_runtime_execution: bool = True
    execution_mode: str = DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE

    @field_validator(
        "trial_id",
        "scenario_id",
        "pair_id",
        "orchestrator_model_id",
        "executor_model_id",
        "status",
        "execution_mode",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("trial execution result text fields must be non-empty.")
        return cleaned

    @field_validator("correctness_score")
    @classmethod
    def validate_score(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("correctness_score must be between 0 and 1 when provided.")
        return value

    @field_validator("normality_input_ref", "task_summary", "error_code")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("optional trial result text fields must be non-empty when provided.")
        return cleaned

    @field_validator("artifact_refs", "tags", "warnings", "notes")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class ModelPairMatrixRunSummary(BaseModel):
    schema_version: str = MODEL_PAIR_MATRIX_RUN_SUMMARY_SCHEMA_VERSION
    run_id: str
    plan_id: str
    execution_mode: str
    trial_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    dry_run_count: int
    pair_summaries: list[dict[str, Any]] = Field(default_factory=list)
    scenario_summaries: list[dict[str, Any]] = Field(default_factory=list)
    trial_results: list[ModelPairTrialExecutionResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    no_runtime_execution: bool = True

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != MODEL_PAIR_MATRIX_RUN_SUMMARY_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {MODEL_PAIR_MATRIX_RUN_SUMMARY_SCHEMA_VERSION}.")
        return value

    @field_validator("run_id", "plan_id", "execution_mode")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("matrix run summary text fields must be non-empty.")
        return cleaned

    @field_validator("warnings", "notes")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class ModelPairTrialExecutor(Protocol):
    def execute_trial(self, request: ModelPairTrialExecutionRequest) -> ModelPairTrialExecutionResult:
        ...


class DryRunModelPairTrialExecutor:
    def execute_trial(self, request: ModelPairTrialExecutionRequest) -> ModelPairTrialExecutionResult:
        return ModelPairTrialExecutionResult(
            trial_id=request.trial_id,
            scenario_id=request.scenario_id,
            pair_id=request.pair_id,
            orchestrator_model_id=request.orchestrator_model_id,
            executor_model_id=request.executor_model_id,
            status="dry_run",
            task_success=None,
            correctness_score=None,
            warnings=[],
            notes=["dry_run_no_runtime_execution"],
            no_runtime_execution=True,
            execution_mode=request.execution_mode,
        )


class StaticModelPairTrialExecutor:
    def __init__(
        self,
        results_by_trial_or_pair: Mapping[str, ModelPairTrialExecutionResult | dict[str, Any]],
    ) -> None:
        self.results_by_trial_or_pair = dict(results_by_trial_or_pair)

    def execute_trial(self, request: ModelPairTrialExecutionRequest) -> ModelPairTrialExecutionResult:
        payload = self.results_by_trial_or_pair.get(request.trial_id)
        if payload is None:
            payload = self.results_by_trial_or_pair.get(request.pair_id)
        if payload is None:
            return ModelPairTrialExecutionResult(
                trial_id=request.trial_id,
                scenario_id=request.scenario_id,
                pair_id=request.pair_id,
                orchestrator_model_id=request.orchestrator_model_id,
                executor_model_id=request.executor_model_id,
                status="dry_run",
                task_success=None,
                correctness_score=None,
                warnings=["static_result_missing"],
                notes=["static_executor_defaulted_to_dry_run"],
                no_runtime_execution=True,
                execution_mode=request.execution_mode,
            )
        return _static_result_from_payload(payload, request)


def build_trial_execution_requests_from_plan(
    plan: ModelComparisonPlan | Mapping[str, Any] | str | Path,
    *,
    execution_mode: str = DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE,
) -> list[ModelPairTrialExecutionRequest]:
    payload = _validated_plan_payload(plan)
    return _trial_execution_requests(payload, execution_mode=execution_mode)


def run_model_pair_matrix(
    plan: ModelComparisonPlan | Mapping[str, Any] | str | Path,
    executor: ModelPairTrialExecutor | None = None,
    *,
    run_id: str | None = None,
    output_dir: str | Path | None = None,
    execution_mode: str = DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE,
    write_trial_results_jsonl: bool = False,
    notes: list[str] | None = None,
) -> ModelPairMatrixRunSummary:
    payload = _validated_plan_payload(plan)
    requests = _trial_execution_requests(payload, execution_mode=execution_mode)
    trial_executor = executor or DryRunModelPairTrialExecutor()
    results: list[ModelPairTrialExecutionResult] = []
    for request in requests:
        try:
            result = trial_executor.execute_trial(request)
            results.append(_coerce_executor_result(result, request))
        except Exception:
            results.append(_executor_failed_result(request))

    summary = _build_summary(
        payload,
        requests,
        results,
        run_id=run_id or "model_pair_matrix_run",
        execution_mode=execution_mode,
        notes=notes,
    )
    if output_dir is not None:
        write_model_pair_matrix_run_summary(
            summary,
            output_dir,
            write_trial_results_jsonl=write_trial_results_jsonl,
        )
    return summary


def write_model_pair_matrix_run_summary(
    summary: ModelPairMatrixRunSummary,
    output_dir: str | Path,
    *,
    write_trial_results_jsonl: bool = False,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if write_trial_results_jsonl:
        jsonl_path = out_dir / MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME
        jsonl_path.write_text(
            "".join(
                json.dumps(result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")) + "\n"
                for result in summary.trial_results
            ),
            encoding="utf-8",
        )
    return summary_path


def _validated_plan_payload(plan: ModelComparisonPlan | Mapping[str, Any] | str | Path) -> dict[str, Any]:
    payload = _coerce_plan_payload(plan)
    _validate_plan_payload(payload)
    return payload


def _coerce_plan_payload(plan: ModelComparisonPlan | Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(plan, ModelComparisonPlan):
        return plan.model_dump(mode="json")
    if isinstance(plan, Mapping):
        return dict(plan)
    path = Path(plan)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ModelPairMatrixPlanError("plan_file_missing") from exc
    except OSError as exc:
        raise ModelPairMatrixPlanError("plan_file_unreadable") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelPairMatrixPlanError("plan_json_malformed") from exc
    if not isinstance(payload, dict):
        raise ModelPairMatrixPlanError("plan_payload_not_object")
    return payload


def _validate_plan_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != MODEL_COMPARISON_PLAN_SCHEMA_VERSION:
        raise ModelPairMatrixPlanError("plan_schema_version_unsupported")
    if not _non_empty_text(payload.get("plan_id")):
        raise ModelPairMatrixPlanError("plan_id_missing")
    pairs = _object_rows(payload.get("candidate_pairs"), "plan_candidate_pairs_missing")
    scenarios = _object_rows(payload.get("scenarios"), "plan_scenarios_missing")
    trials = _object_rows(payload.get("trials"), "plan_trials_missing")
    pair_ids = {_required_text(pair.get("pair_id"), "candidate_pair_id_missing") for pair in pairs}
    scenario_ids = {_required_text(scenario.get("scenario_id"), "scenario_id_missing") for scenario in scenarios}
    for trial in trials:
        trial_id = _required_text(trial.get("trial_id"), "trial_id_missing")
        pair_id = _required_text(trial.get("pair_id"), f"trial_pair_id_missing:{trial_id}")
        scenario_id = _required_text(trial.get("scenario_id"), f"trial_scenario_id_missing:{trial_id}")
        if pair_id not in pair_ids:
            raise ModelPairMatrixPlanError(f"trial_pair_ref_missing:{trial_id}")
        if scenario_id not in scenario_ids:
            raise ModelPairMatrixPlanError(f"trial_scenario_ref_missing:{trial_id}")


def _trial_execution_requests(
    payload: dict[str, Any],
    *,
    execution_mode: str,
) -> list[ModelPairTrialExecutionRequest]:
    pairs = {
        _required_text(pair.get("pair_id"), "candidate_pair_id_missing"): pair
        for pair in _object_rows(payload.get("candidate_pairs"), "plan_candidate_pairs_missing")
    }
    scenarios = {
        _required_text(scenario.get("scenario_id"), "scenario_id_missing"): scenario
        for scenario in _object_rows(payload.get("scenarios"), "plan_scenarios_missing")
    }
    requests: list[ModelPairTrialExecutionRequest] = []
    for trial in _object_rows(payload.get("trials"), "plan_trials_missing"):
        trial_id = _required_text(trial.get("trial_id"), "trial_id_missing")
        pair_id = _required_text(trial.get("pair_id"), f"trial_pair_id_missing:{trial_id}")
        scenario_id = _required_text(trial.get("scenario_id"), f"trial_scenario_id_missing:{trial_id}")
        pair = pairs[pair_id]
        scenario = scenarios[scenario_id]
        orchestrator_model_id = _optional_text(trial.get("orchestrator_model_id")) or _optional_text(
            pair.get("orchestrator_model_id")
        )
        executor_model_id = _optional_text(trial.get("executor_model_id")) or _optional_text(pair.get("executor_model_id"))
        if not orchestrator_model_id or not executor_model_id:
            raise ModelPairMatrixPlanError(f"trial_model_refs_missing:{trial_id}")
        scenario_path = _optional_text(trial.get("scenario_path")) or _optional_text(scenario.get("scenario_path"))
        if not scenario_path:
            raise ModelPairMatrixPlanError(f"trial_scenario_path_missing:{trial_id}")
        requests.append(
            ModelPairTrialExecutionRequest(
                trial_id=trial_id,
                scenario_id=scenario_id,
                scenario_path=scenario_path,
                pair_id=pair_id,
                orchestrator_model_id=orchestrator_model_id,
                executor_model_id=executor_model_id,
                repeat_index=_positive_int(trial.get("repeat_index"), f"trial_repeat_index_invalid:{trial_id}"),
                tags=_string_list(trial.get("tags")),
                task_summary=_task_summary(trial, scenario),
                expected_outputs=_expected_outputs(trial, scenario),
                metadata=_request_metadata(payload, trial, pair, scenario),
                no_runtime_execution=bool(trial.get("no_runtime_execution", payload.get("no_runtime_execution", True))),
                execution_mode=execution_mode,
            )
        )
    return requests


def _static_result_from_payload(
    payload: ModelPairTrialExecutionResult | dict[str, Any],
    request: ModelPairTrialExecutionRequest,
) -> ModelPairTrialExecutionResult:
    if isinstance(payload, ModelPairTrialExecutionResult):
        raw = payload.model_dump(mode="json")
    else:
        raw = dict(payload)
    raw.setdefault("trial_id", request.trial_id)
    raw.setdefault("scenario_id", request.scenario_id)
    raw.setdefault("pair_id", request.pair_id)
    raw.setdefault("orchestrator_model_id", request.orchestrator_model_id)
    raw.setdefault("executor_model_id", request.executor_model_id)
    raw.setdefault("status", "dry_run")
    raw.setdefault("task_summary", request.task_summary)
    raw.setdefault("expected_outputs", request.expected_outputs)
    raw.setdefault("tags", request.tags)
    raw.setdefault("metadata", request.metadata)
    raw.setdefault("warnings", [])
    raw.setdefault("notes", [])
    raw["no_runtime_execution"] = True
    raw["execution_mode"] = request.execution_mode
    return ModelPairTrialExecutionResult.model_validate(raw)


def _coerce_executor_result(
    result: ModelPairTrialExecutionResult | dict[str, Any],
    request: ModelPairTrialExecutionRequest,
) -> ModelPairTrialExecutionResult:
    if isinstance(result, ModelPairTrialExecutionResult):
        return result
    return _static_result_from_payload(result, request)


def _executor_failed_result(request: ModelPairTrialExecutionRequest) -> ModelPairTrialExecutionResult:
    return ModelPairTrialExecutionResult(
        trial_id=request.trial_id,
        scenario_id=request.scenario_id,
        pair_id=request.pair_id,
        orchestrator_model_id=request.orchestrator_model_id,
        executor_model_id=request.executor_model_id,
        status="failed",
        task_success=False,
        correctness_score=None,
        error_code="trial_executor_failed",
        warnings=["trial_executor_failed"],
        notes=["executor_exception_suppressed"],
        no_runtime_execution=True,
        execution_mode=request.execution_mode,
    )


def _build_summary(
    payload: dict[str, Any],
    requests: list[ModelPairTrialExecutionRequest],
    results: list[ModelPairTrialExecutionResult],
    *,
    run_id: str,
    execution_mode: str,
    notes: list[str] | None,
) -> ModelPairMatrixRunSummary:
    status_counts = Counter(result.status for result in results)
    warnings = sorted(
        {
            *_string_list(payload.get("warnings")),
            *(warning for result in results for warning in result.warnings),
        }
    )
    summary_notes = [
        "Model pair matrix scaffold only; no runtime execution performed.",
        *(_string_list(payload.get("notes"))),
        *(_string_list(notes)),
    ]
    return ModelPairMatrixRunSummary(
        run_id=run_id,
        plan_id=_required_text(payload.get("plan_id"), "plan_id_missing"),
        execution_mode=execution_mode,
        trial_count=len(results),
        succeeded_count=status_counts["succeeded"],
        failed_count=status_counts["failed"],
        skipped_count=status_counts["skipped"],
        dry_run_count=status_counts["dry_run"],
        pair_summaries=_group_summaries(results, requests, group_key="pair_id"),
        scenario_summaries=_group_summaries(results, requests, group_key="scenario_id"),
        trial_results=results,
        warnings=warnings,
        notes=list(dict.fromkeys(summary_notes)),
        no_runtime_execution=all(request.no_runtime_execution for request in requests)
        and all(result.no_runtime_execution for result in results),
    )


def _group_summaries(
    results: list[ModelPairTrialExecutionResult],
    requests: list[ModelPairTrialExecutionRequest],
    *,
    group_key: Literal["pair_id", "scenario_id"],
) -> list[dict[str, Any]]:
    request_by_trial_id = {request.trial_id: request for request in requests}
    buckets: dict[str, list[ModelPairTrialExecutionResult]] = {}
    for result in results:
        key = result.pair_id if group_key == "pair_id" else result.scenario_id
        buckets.setdefault(key, []).append(result)
    rows: list[dict[str, Any]] = []
    for key, items in sorted(buckets.items()):
        status_counts = Counter(item.status for item in items)
        scores = [item.correctness_score for item in items if item.correctness_score is not None]
        requests_for_items = [
            request_by_trial_id[item.trial_id]
            for item in items
            if item.trial_id in request_by_trial_id
        ]
        row: dict[str, Any] = {
            group_key: key,
            "trial_count": len(items),
            "succeeded_count": status_counts["succeeded"],
            "failed_count": status_counts["failed"],
            "skipped_count": status_counts["skipped"],
            "dry_run_count": status_counts["dry_run"],
            "task_success_count": sum(1 for item in items if item.task_success is True),
            "task_failure_count": sum(1 for item in items if item.task_success is False),
            "mean_correctness_score": round(sum(scores) / len(scores), 6) if scores else None,
            "normality_input_ref_count": sum(1 for item in items if item.normality_input_ref),
            "resource_observation_count": sum(1 for item in items if item.resource_observation is not None),
            "trial_ids": sorted(item.trial_id for item in items),
            "warnings": sorted({warning for item in items for warning in item.warnings}),
        }
        row.update(_action_execution_summary_from_results(items))
        if group_key == "pair_id":
            first = items[0]
            row.update(
                {
                    "orchestrator_model_id": first.orchestrator_model_id,
                    "executor_model_id": first.executor_model_id,
                    "scenario_ids": sorted({item.scenario_id for item in items}),
                }
            )
        else:
            row.update(
                {
                    "scenario_path": requests_for_items[0].scenario_path if requests_for_items else None,
                    "pair_ids": sorted({item.pair_id for item in items}),
                }
            )
        rows.append(row)
    return rows


def _action_execution_summary_from_results(items: list[ModelPairTrialExecutionResult]) -> dict[str, Any]:
    rows = [
        item.metadata
        for item in items
        if any(
            key in item.metadata
            for key in (
                "validation_only",
                "validation_success_count",
                "execution_attempted_count",
                "execution_success_count",
                "action_execution_enabled",
            )
        )
    ]
    if not rows:
        return {}
    validation_only_count = sum(1 for row in rows if row.get("validation_only") is True)
    return {
        "validation_only": validation_only_count == len(rows),
        "validation_only_count": validation_only_count,
        "validation_success_count": sum(_safe_int(row.get("validation_success_count")) for row in rows),
        "execution_attempted_count": sum(_safe_int(row.get("execution_attempted_count")) for row in rows),
        "execution_success_count": sum(_safe_int(row.get("execution_success_count")) for row in rows),
        "action_execution_enabled": any(row.get("action_execution_enabled") is True for row in rows),
    }


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _object_rows(value: Any, missing_code: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ModelPairMatrixPlanError(missing_code)
    rows = [item for item in value if isinstance(item, dict)]
    if len(rows) != len(value):
        raise ModelPairMatrixPlanError(f"{missing_code}_invalid")
    return rows


def _required_text(value: Any, error_code: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ModelPairMatrixPlanError(error_code)
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _non_empty_text(value: Any) -> bool:
    return _optional_text(value) is not None


def _positive_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool):
        raise ModelPairMatrixPlanError(error_code)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ModelPairMatrixPlanError(error_code) from exc
    if parsed < 1:
        raise ModelPairMatrixPlanError(error_code)
    return parsed


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _clean_text_list(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value]
    if any(not item for item in cleaned):
        raise ValueError("text lists must not contain empty values.")
    return cleaned


def _task_summary(trial: dict[str, Any], scenario: dict[str, Any]) -> str | None:
    for source in (trial, scenario):
        for key in ("task_summary", "expected_group_behavior", "description"):
            text = _optional_text(source.get(key))
            if text:
                return text
    return None


def _expected_outputs(trial: dict[str, Any], scenario: dict[str, Any]) -> list[Any] | dict[str, Any]:
    for source in (trial, scenario):
        value = source.get("expected_outputs")
        if isinstance(value, list | dict):
            return value
        value = source.get("correctness_checks")
        if isinstance(value, list):
            return {"checks": value}
    return []


def _request_metadata(
    payload: dict[str, Any],
    trial: dict[str, Any],
    pair: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "plan_id": _optional_text(payload.get("plan_id")),
        "trial_notes": _string_list(trial.get("notes")),
        "trial_warnings": _string_list(trial.get("warnings")),
        "pair_tags": _string_list(pair.get("tags")),
        "scenario_tags": _string_list(scenario.get("tags")),
        "no_runtime_execution": bool(trial.get("no_runtime_execution", payload.get("no_runtime_execution", True))),
    }
    local_pipeline_config = _first_mapping(
        trial.get("local_pipeline_config"),
        scenario.get("local_pipeline_config"),
        payload.get("local_pipeline_config"),
    )
    if local_pipeline_config is not None:
        metadata["local_pipeline_config"] = dict(local_pipeline_config)
    return metadata


def _first_mapping(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict):
            return value
    return None
