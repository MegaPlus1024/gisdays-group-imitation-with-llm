from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Literal, Mapping, Protocol

from pydantic import BaseModel, Field, field_validator

from .model_pair_matrix_runner import ModelPairMatrixRunSummary, ModelPairTrialExecutionResult


TASK_CORRECTNESS_EVALUATION_RESULT_SCHEMA_VERSION = "task_correctness_evaluation_result_v1"
TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION = "task_correctness_batch_summary_v1"
TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME = "task_correctness_batch_summary.json"
DEFAULT_TASK_CORRECTNESS_SUMMARY_ID = "task_correctness_batch_summary"

TaskCorrectnessCheckStatus = Literal["passed", "failed", "skipped", "warning"]
TaskCorrectnessStatus = Literal["passed", "failed", "partial", "skipped", "invalid_input"]


class TaskCorrectnessInputLoadError(ValueError):
    """Controlled input-loading error safe to expose through CLI JSON."""


class TaskCorrectnessCheckResult(BaseModel):
    check_id: str
    status: TaskCorrectnessCheckStatus
    score: float | None = None
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("check_id", "status", "message")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("correctness check text fields must be non-empty.")
        return cleaned

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("check score must be between 0 and 1 when provided.")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class TaskCorrectnessEvaluationInput(BaseModel):
    trial_id: str
    scenario_id: str
    pair_id: str
    orchestrator_model_id: str
    executor_model_id: str
    task_summary: str | None = None
    expected_outputs: list[Any] | dict[str, Any] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    trial_status: str | None = None
    trial_result: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("trial_id", "scenario_id", "pair_id", "orchestrator_model_id", "executor_model_id")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("correctness input identity fields must be non-empty.")
        return cleaned

    @field_validator("task_summary", "trial_status")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("optional correctness input text fields must be non-empty when provided.")
        return cleaned

    @field_validator("artifact_refs", "tags")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class TaskCorrectnessEvaluationResult(BaseModel):
    schema_version: str = TASK_CORRECTNESS_EVALUATION_RESULT_SCHEMA_VERSION
    trial_id: str
    scenario_id: str
    pair_id: str
    status: TaskCorrectnessStatus
    task_success: bool | None = None
    correctness_score: float | None = None
    check_results: list[TaskCorrectnessCheckResult] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    no_runtime_execution: bool = True

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != TASK_CORRECTNESS_EVALUATION_RESULT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TASK_CORRECTNESS_EVALUATION_RESULT_SCHEMA_VERSION}.")
        return value

    @field_validator("trial_id", "scenario_id", "pair_id", "status")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("correctness result text fields must be non-empty.")
        return cleaned

    @field_validator("correctness_score")
    @classmethod
    def validate_score(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("correctness_score must be between 0 and 1 when provided.")
        return value

    @field_validator("failure_reasons", "warnings", "notes")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class TaskCorrectnessBatchSummary(BaseModel):
    schema_version: str = TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION
    summary_id: str
    input_count: int
    evaluated_count: int
    invalid_count: int
    passed_count: int
    failed_count: int
    partial_count: int
    skipped_count: int
    mean_correctness_score: float | None = None
    by_pair: dict[str, dict[str, Any]] = Field(default_factory=dict)
    by_scenario: dict[str, dict[str, Any]] = Field(default_factory=dict)
    results: list[TaskCorrectnessEvaluationResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    no_runtime_execution: bool = True

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION}.")
        return value

    @field_validator("summary_id")
    @classmethod
    def validate_summary_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("summary_id must be non-empty.")
        return cleaned

    @field_validator("warnings", "notes")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _clean_text_list(value)


class TaskCorrectnessEvaluator(Protocol):
    def evaluate(self, input: TaskCorrectnessEvaluationInput) -> TaskCorrectnessEvaluationResult:
        ...


class StaticTaskCorrectnessEvaluator:
    def __init__(
        self,
        results_by_trial_or_pair: Mapping[str, TaskCorrectnessEvaluationResult | dict[str, Any]],
    ) -> None:
        self.results_by_trial_or_pair = dict(results_by_trial_or_pair)

    def evaluate(self, input: TaskCorrectnessEvaluationInput) -> TaskCorrectnessEvaluationResult:
        payload = self.results_by_trial_or_pair.get(input.trial_id)
        if payload is None:
            payload = self.results_by_trial_or_pair.get(input.pair_id)
        if payload is None:
            return _skipped_result(
                input,
                warnings=["static_correctness_result_missing"],
                notes=["static_evaluator_defaulted_to_skipped"],
            )
        return _static_result_from_payload(payload, input)


class RuleBasedTaskCorrectnessEvaluator:
    def evaluate(self, input: TaskCorrectnessEvaluationInput) -> TaskCorrectnessEvaluationResult:
        checks = _check_definitions(input.expected_outputs)
        if not checks:
            office_result = _result_from_office_execution_artifacts(input)
            if office_result is not None:
                return office_result
            return _result_from_existing_trial_fields(input)

        check_results = [_evaluate_check(check, input, index=index) for index, check in enumerate(checks, start=1)]
        status = _status_from_check_results(check_results)
        scores = [result.score for result in check_results if result.score is not None]
        score = round(mean(scores), 6) if scores else _optional_score(input.trial_result.get("correctness_score"))
        failure_reasons = [result.message for result in check_results if result.status == "failed"]
        return TaskCorrectnessEvaluationResult(
            trial_id=input.trial_id,
            scenario_id=input.scenario_id,
            pair_id=input.pair_id,
            status=status,
            task_success=_task_success_from_status(status),
            correctness_score=score,
            check_results=check_results,
            failure_reasons=failure_reasons,
            warnings=[result.message for result in check_results if result.status == "warning"],
            notes=["rule_based_offline_evaluation"],
            no_runtime_execution=True,
        )


class DisabledTaskCorrectnessEvaluator:
    def evaluate(self, input: TaskCorrectnessEvaluationInput) -> TaskCorrectnessEvaluationResult:
        return _skipped_result(
            input,
            warnings=["task_correctness_evaluator_disabled"],
            notes=["disabled_evaluator_no_runtime_execution"],
        )


def build_correctness_input_from_trial_result(
    trial_result: ModelPairTrialExecutionResult | Mapping[str, Any],
    scenario_metadata: Mapping[str, Any] | None = None,
) -> TaskCorrectnessEvaluationInput:
    payload = _record_dict(trial_result)
    metadata = dict(scenario_metadata or {})
    trial_status = _optional_text(payload.get("status"))
    artifact_refs = _artifact_refs_from_trial_result(payload)
    artifact_refs.extend(_string_list(metadata.get("artifact_refs")))
    return TaskCorrectnessEvaluationInput(
        trial_id=_required_text(payload.get("trial_id"), "trial_id_missing"),
        scenario_id=_required_text(payload.get("scenario_id"), "scenario_id_missing"),
        pair_id=_required_text(payload.get("pair_id"), "pair_id_missing"),
        orchestrator_model_id=_required_text(payload.get("orchestrator_model_id"), "orchestrator_model_id_missing"),
        executor_model_id=_required_text(payload.get("executor_model_id"), "executor_model_id_missing"),
        task_summary=_task_summary(payload, metadata),
        expected_outputs=_expected_outputs(payload, metadata),
        artifact_refs=list(dict.fromkeys(artifact_refs)),
        trial_status=trial_status,
        trial_result=payload,
        tags=sorted(set([*_string_list(payload.get("tags")), *_string_list(metadata.get("tags"))])),
    )


def build_correctness_inputs_from_matrix_run_summary(
    matrix_summary: ModelPairMatrixRunSummary | Mapping[str, Any] | str | Path,
    scenario_metadata_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[TaskCorrectnessEvaluationInput]:
    payload = _coerce_matrix_summary_payload(matrix_summary)
    trial_results = payload.get("trial_results")
    if not isinstance(trial_results, list):
        raise TaskCorrectnessInputLoadError("matrix_trial_results_missing")
    metadata_by_id = dict(scenario_metadata_by_id or {})
    inputs: list[TaskCorrectnessEvaluationInput] = []
    for row in trial_results:
        if not isinstance(row, dict):
            raise TaskCorrectnessInputLoadError("matrix_trial_result_not_object")
        scenario_id = _optional_text(row.get("scenario_id"))
        scenario_metadata = metadata_by_id.get(scenario_id or "", {})
        inputs.append(build_correctness_input_from_trial_result(row, scenario_metadata=scenario_metadata))
    return inputs


def evaluate_task_correctness_batch(
    inputs: list[TaskCorrectnessEvaluationInput | Mapping[str, Any]],
    evaluator: TaskCorrectnessEvaluator | None = None,
    *,
    summary_id: str | None = None,
    tags: list[str] | None = None,
) -> TaskCorrectnessBatchSummary:
    correctness_evaluator = evaluator or RuleBasedTaskCorrectnessEvaluator()
    results: list[TaskCorrectnessEvaluationResult] = []
    warnings: list[str] = []
    for index, item in enumerate(inputs, start=1):
        try:
            input_obj = _coerce_input(item)
            result = correctness_evaluator.evaluate(input_obj)
            results.append(result)
        except Exception:
            results.append(_invalid_input_result(index))
            warnings.append(f"input_invalid:{index}")

    status_counts = Counter(result.status for result in results)
    scores = [result.correctness_score for result in results if result.correctness_score is not None]
    summary_notes = ["Offline task correctness evaluation only; no runtime execution performed."]
    if tags:
        summary_notes.append(f"tags:{','.join(_clean_text_list(tags))}")
    return TaskCorrectnessBatchSummary(
        summary_id=summary_id or DEFAULT_TASK_CORRECTNESS_SUMMARY_ID,
        input_count=len(inputs),
        evaluated_count=sum(1 for result in results if result.status != "invalid_input"),
        invalid_count=status_counts["invalid_input"],
        passed_count=status_counts["passed"],
        failed_count=status_counts["failed"],
        partial_count=status_counts["partial"],
        skipped_count=status_counts["skipped"],
        mean_correctness_score=round(mean(scores), 6) if scores else None,
        by_pair=_group_results(results, group_key="pair_id"),
        by_scenario=_group_results(results, group_key="scenario_id"),
        results=results,
        warnings=sorted({*warnings, *(warning for result in results for warning in result.warnings)}),
        notes=summary_notes,
        no_runtime_execution=all(result.no_runtime_execution for result in results),
    )


def write_task_correctness_batch_summary(
    summary: TaskCorrectnessBatchSummary,
    output_dir: str | Path,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME
    path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_task_correctness_inputs_from_file(path: str | Path) -> list[TaskCorrectnessEvaluationInput]:
    candidate = Path(path)
    try:
        text = candidate.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TaskCorrectnessInputLoadError("input_file_missing") from exc
    except OSError as exc:
        raise TaskCorrectnessInputLoadError("input_file_unreadable") from exc
    if candidate.suffix.lower() == ".jsonl":
        return _load_jsonl_inputs(text)
    return _load_json_inputs(text)


def _load_json_inputs(text: str) -> list[TaskCorrectnessEvaluationInput]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TaskCorrectnessInputLoadError("input_json_malformed") from exc
    rows = _input_rows(payload)
    return [TaskCorrectnessEvaluationInput.model_validate(row) for row in rows]


def _load_jsonl_inputs(text: str) -> list[TaskCorrectnessEvaluationInput]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TaskCorrectnessInputLoadError(f"input_jsonl_malformed:{line_number}") from exc
        if not isinstance(payload, dict):
            raise TaskCorrectnessInputLoadError(f"input_jsonl_row_not_object:{line_number}")
        rows.append(payload)
    if not rows:
        raise TaskCorrectnessInputLoadError("input_rows_missing")
    return [TaskCorrectnessEvaluationInput.model_validate(row) for row in rows]


def _input_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("inputs"), list):
            rows = payload["inputs"]
        elif isinstance(payload.get("correctness_inputs"), list):
            rows = payload["correctness_inputs"]
        else:
            rows = [payload]
    else:
        raise TaskCorrectnessInputLoadError("input_payload_not_object_or_list")
    if not rows:
        raise TaskCorrectnessInputLoadError("input_rows_missing")
    if not all(isinstance(row, dict) for row in rows):
        raise TaskCorrectnessInputLoadError("input_row_not_object")
    return rows


def _coerce_matrix_summary_payload(matrix_summary: ModelPairMatrixRunSummary | Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(matrix_summary, ModelPairMatrixRunSummary):
        return matrix_summary.model_dump(mode="json")
    if isinstance(matrix_summary, Mapping):
        return dict(matrix_summary)
    path = Path(matrix_summary)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskCorrectnessInputLoadError("matrix_summary_file_missing") from exc
    except OSError as exc:
        raise TaskCorrectnessInputLoadError("matrix_summary_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise TaskCorrectnessInputLoadError("matrix_summary_json_malformed") from exc
    if not isinstance(payload, dict):
        raise TaskCorrectnessInputLoadError("matrix_summary_payload_not_object")
    return payload


def _static_result_from_payload(
    payload: TaskCorrectnessEvaluationResult | dict[str, Any],
    input: TaskCorrectnessEvaluationInput,
) -> TaskCorrectnessEvaluationResult:
    raw = payload.model_dump(mode="json") if isinstance(payload, TaskCorrectnessEvaluationResult) else dict(payload)
    raw.setdefault("trial_id", input.trial_id)
    raw.setdefault("scenario_id", input.scenario_id)
    raw.setdefault("pair_id", input.pair_id)
    raw.setdefault("status", "skipped")
    raw.setdefault("check_results", [])
    raw.setdefault("failure_reasons", [])
    raw.setdefault("warnings", [])
    raw.setdefault("notes", ["static_task_correctness_result"])
    raw["no_runtime_execution"] = True
    return TaskCorrectnessEvaluationResult.model_validate(raw)


def _result_from_existing_trial_fields(input: TaskCorrectnessEvaluationInput) -> TaskCorrectnessEvaluationResult:
    task_success = input.trial_result.get("task_success")
    correctness_score = _optional_score(input.trial_result.get("correctness_score"))
    if isinstance(task_success, bool):
        status: TaskCorrectnessStatus = "passed" if task_success else "failed"
        score = correctness_score if correctness_score is not None else (1.0 if task_success else 0.0)
        return TaskCorrectnessEvaluationResult(
            trial_id=input.trial_id,
            scenario_id=input.scenario_id,
            pair_id=input.pair_id,
            status=status,
            task_success=task_success,
            correctness_score=score,
            notes=["used_existing_trial_correctness_fields"],
        )
    if correctness_score is not None:
        status = "passed" if correctness_score >= 0.8 else "partial" if correctness_score > 0 else "failed"
        return TaskCorrectnessEvaluationResult(
            trial_id=input.trial_id,
            scenario_id=input.scenario_id,
            pair_id=input.pair_id,
            status=status,
            task_success=_task_success_from_status(status),
            correctness_score=correctness_score,
            notes=["used_existing_trial_correctness_score"],
        )
    return _skipped_result(
        input,
        warnings=["no_correctness_checks_available"],
        notes=["rule_based_evaluator_skipped_empty_checks"],
    )


def _result_from_office_execution_artifacts(
    input: TaskCorrectnessEvaluationInput,
) -> TaskCorrectnessEvaluationResult | None:
    artifact_summary = _office_execution_artifact_summary(input.trial_result)
    if artifact_summary is None:
        return None

    group_history = [row for row in _list_value(input.trial_result.get("group_history")) if isinstance(row, dict)]
    executable_rows = [
        row
        for row in group_history
        if _row_metadata(row).get("action_execution_enabled") is True
        or "execution_attempted" in _row_metadata(row)
        or "execution_success" in _row_metadata(row)
    ]
    artifacts = [row for row in _list_value(artifact_summary.get("artifacts")) if isinstance(row, dict)]
    criteria = {
        "trial_succeeded": _trial_succeeded(input),
        "all_validated": bool(group_history) and all(_row_metadata(row).get("validation_accepted") is True for row in group_history),
        "all_executed": bool(executable_rows)
        and all(
            _row_metadata(row).get("execution_attempted") is True
            and _row_metadata(row).get("execution_success") is True
            for row in executable_rows
        ),
        "all_output_artifacts_exist": bool(artifacts)
        and all(row.get("exists") is True and row.get("readable") is True for row in artifacts),
    }
    check_results = [
        _office_execution_check_result("trial_succeeded", criteria["trial_succeeded"], "trial status succeeded"),
        _office_execution_check_result("all_validated", criteria["all_validated"], "all group steps validated"),
        _office_execution_check_result("all_executed", criteria["all_executed"], "all executable group steps ran successfully"),
        _office_execution_check_result(
            "all_output_artifacts_exist",
            criteria["all_output_artifacts_exist"],
            "all harvested office artifacts exist and are readable",
            evidence_refs=[row["path"] for row in artifacts if isinstance(row.get("path"), str)],
            metadata={
                "artifact_count": artifact_summary.get("artifact_count", len(artifacts)),
                "readable_count": artifact_summary.get("readable_count"),
            },
        ),
    ]
    score = round(sum(1.0 if value else 0.0 for value in criteria.values()) / len(criteria), 6)
    status: TaskCorrectnessStatus
    if all(criteria.values()):
        status = "passed"
    elif any(criteria.values()):
        status = "partial"
    else:
        status = "failed"
    return TaskCorrectnessEvaluationResult(
        trial_id=input.trial_id,
        scenario_id=input.scenario_id,
        pair_id=input.pair_id,
        status=status,
        task_success=_task_success_from_status(status),
        correctness_score=score,
        check_results=check_results,
        failure_reasons=[result.message for result in check_results if result.status == "failed"],
        notes=[
            "office_execution_correctness_only",
            "semantic_content_quality_not_evaluated",
        ],
        no_runtime_execution=True,
    )


def _office_execution_check_result(
    check_id: str,
    passed: bool,
    message: str,
    *,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> TaskCorrectnessCheckResult:
    return TaskCorrectnessCheckResult(
        check_id=check_id,
        status="passed" if passed else "failed",
        score=1.0 if passed else 0.0,
        message=message if passed else f"{message} failed",
        evidence_refs=evidence_refs or [],
        metadata={"check_type": "office_execution_artifact_summary", **(metadata or {})},
    )


def _office_execution_artifact_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    for source in (payload, payload.get("metadata")):
        if not isinstance(source, dict):
            continue
        summary = source.get("office_execution_artifact_summary")
        if isinstance(summary, dict):
            return summary
    return None


def _trial_succeeded(input: TaskCorrectnessEvaluationInput) -> bool:
    status = input.trial_status or _optional_text(input.trial_result.get("status"))
    return status in {"succeeded", "success", "completed", "passed"}


def _row_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _evaluate_check(
    check: dict[str, Any],
    input: TaskCorrectnessEvaluationInput,
    *,
    index: int,
) -> TaskCorrectnessCheckResult:
    check_type = _check_type(check)
    check_id = _optional_text(check.get("check_id")) or f"{check_type}_{index:03d}"
    if check_type == "required_key":
        key = _required_text(_first_value(check, "key", "field", "required_key"), "required_key_check_key_missing")
        passed = _has_nested_key(input.trial_result, key)
        return TaskCorrectnessCheckResult(
            check_id=check_id,
            status="passed" if passed else "failed",
            score=1.0 if passed else 0.0,
            message=f"required key present: {key}" if passed else f"required key missing: {key}",
            evidence_refs=[f"trial_result:{key}"],
            metadata={"check_type": check_type, "key": key},
        )
    if check_type == "status_equals":
        expected = _required_text(_first_value(check, "expected", "status", "status_equals"), "status_equals_expected_missing")
        field = _optional_text(_first_value(check, "key", "field"))
        actual = _optional_text(_get_nested_value(input.trial_result, field)) if field else input.trial_status
        actual = actual or _optional_text(input.trial_result.get("status"))
        passed = actual == expected
        return TaskCorrectnessCheckResult(
            check_id=check_id,
            status="passed" if passed else "failed",
            score=1.0 if passed else 0.0,
            message=f"status matched: {expected}" if passed else f"status mismatch: expected {expected}, got {actual}",
            evidence_refs=["trial_status" if not field else f"trial_result:{field}"],
            metadata={"check_type": check_type, "expected": expected, "actual": actual},
        )
    if check_type == "artifact_ref_listed":
        artifact_ref = _required_text(
            _first_value(check, "artifact_ref", "ref", "path", "artifact_ref_listed"),
            "artifact_ref_check_ref_missing",
        )
        passed = artifact_ref in input.artifact_refs
        return TaskCorrectnessCheckResult(
            check_id=check_id,
            status="passed" if passed else "failed",
            score=1.0 if passed else 0.0,
            message=f"artifact ref listed: {artifact_ref}" if passed else f"artifact ref missing: {artifact_ref}",
            evidence_refs=[artifact_ref] if passed else [],
            metadata={"check_type": check_type, "artifact_ref": artifact_ref},
        )
    if check_type == "numeric_score_threshold":
        key = _required_text(_first_value(check, "key", "field", "score_key"), "numeric_threshold_key_missing")
        threshold = _optional_score(_first_value(check, "min_score", "threshold", "minimum"))
        if threshold is None:
            threshold = 0.0
        value = _optional_score(_get_nested_value(input.trial_result, key))
        passed = value is not None and value >= threshold
        return TaskCorrectnessCheckResult(
            check_id=check_id,
            status="passed" if passed else "failed",
            score=1.0 if passed else 0.0,
            message=(
                f"numeric score threshold met: {key}>={threshold}"
                if passed
                else f"numeric score threshold failed: {key}>={threshold}, got {value}"
            ),
            evidence_refs=[f"trial_result:{key}"],
            metadata={"check_type": check_type, "key": key, "threshold": threshold, "actual": value},
        )
    return TaskCorrectnessCheckResult(
        check_id=check_id,
        status="warning",
        score=None,
        message=f"unsupported check type: {check_type}",
        metadata={"check_type": check_type},
    )


def _check_definitions(expected_outputs: list[Any] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(expected_outputs, dict):
        if isinstance(expected_outputs.get("checks"), list):
            return [row for row in expected_outputs["checks"] if isinstance(row, dict)]
        if isinstance(expected_outputs.get("correctness_checks"), list):
            return [row for row in expected_outputs["correctness_checks"] if isinstance(row, dict)]
        if _looks_like_check(expected_outputs):
            return [dict(expected_outputs)]
        return []
    checks: list[dict[str, Any]] = []
    for item in expected_outputs:
        if isinstance(item, dict):
            checks.append(item)
    return checks


def _looks_like_check(value: dict[str, Any]) -> bool:
    return bool(
        {"type", "check_type", "required_key", "status_equals", "artifact_ref_listed", "artifact_ref", "score_key"}
        & set(value)
    )


def _check_type(check: dict[str, Any]) -> str:
    explicit = _optional_text(_first_value(check, "type", "check_type"))
    if explicit:
        return explicit
    if "required_key" in check:
        return "required_key"
    if "status_equals" in check:
        return "status_equals"
    if "artifact_ref_listed" in check or "artifact_ref" in check:
        return "artifact_ref_listed"
    if "score_key" in check:
        return "numeric_score_threshold"
    return "unsupported"


def _status_from_check_results(check_results: list[TaskCorrectnessCheckResult]) -> TaskCorrectnessStatus:
    if not check_results:
        return "skipped"
    passed = sum(1 for result in check_results if result.status == "passed")
    failed = sum(1 for result in check_results if result.status == "failed")
    skipped = sum(1 for result in check_results if result.status == "skipped")
    warnings = sum(1 for result in check_results if result.status == "warning")
    if failed == 0 and passed > 0:
        return "passed"
    if failed > 0 and passed > 0:
        return "partial"
    if failed > 0:
        return "failed"
    if skipped == len(check_results):
        return "skipped"
    if warnings:
        return "partial"
    return "skipped"


def _task_success_from_status(status: TaskCorrectnessStatus) -> bool | None:
    if status == "passed":
        return True
    if status == "failed":
        return False
    return None


def _skipped_result(
    input: TaskCorrectnessEvaluationInput,
    *,
    warnings: list[str] | None = None,
    notes: list[str] | None = None,
) -> TaskCorrectnessEvaluationResult:
    return TaskCorrectnessEvaluationResult(
        trial_id=input.trial_id,
        scenario_id=input.scenario_id,
        pair_id=input.pair_id,
        status="skipped",
        task_success=None,
        correctness_score=None,
        warnings=warnings or [],
        notes=notes or [],
        no_runtime_execution=True,
    )


def _invalid_input_result(index: int) -> TaskCorrectnessEvaluationResult:
    return TaskCorrectnessEvaluationResult(
        trial_id=f"invalid_input_{index:03d}",
        scenario_id="unknown_scenario",
        pair_id="unknown_pair",
        status="invalid_input",
        failure_reasons=["input_validation_failed"],
        warnings=["input_validation_failed"],
        notes=["invalid correctness input suppressed"],
        no_runtime_execution=True,
    )


def _group_results(
    results: list[TaskCorrectnessEvaluationResult],
    *,
    group_key: Literal["pair_id", "scenario_id"],
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[TaskCorrectnessEvaluationResult]] = {}
    for result in results:
        key = result.pair_id if group_key == "pair_id" else result.scenario_id
        buckets.setdefault(key, []).append(result)
    groups: dict[str, dict[str, Any]] = {}
    for key, rows in sorted(buckets.items()):
        counts = Counter(row.status for row in rows)
        scores = [row.correctness_score for row in rows if row.correctness_score is not None]
        groups[key] = {
            group_key: key,
            "input_count": len(rows),
            "evaluated_count": sum(1 for row in rows if row.status != "invalid_input"),
            "invalid_count": counts["invalid_input"],
            "passed_count": counts["passed"],
            "failed_count": counts["failed"],
            "partial_count": counts["partial"],
            "skipped_count": counts["skipped"],
            "mean_correctness_score": round(mean(scores), 6) if scores else None,
            "trial_ids": sorted(row.trial_id for row in rows),
            "failure_reasons": sorted({reason for row in rows for reason in row.failure_reasons}),
            "warnings": sorted({warning for row in rows for warning in row.warnings}),
        }
    return groups


def _coerce_input(item: TaskCorrectnessEvaluationInput | Mapping[str, Any]) -> TaskCorrectnessEvaluationInput:
    if isinstance(item, TaskCorrectnessEvaluationInput):
        return item
    return TaskCorrectnessEvaluationInput.model_validate(dict(item))


def _artifact_refs_from_trial_result(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    refs.extend(_string_list(payload.get("artifact_refs")))
    refs.extend(_string_list(payload.get("artifacts")))
    refs.extend(_office_execution_artifact_summary_refs(payload))
    normality_ref = _optional_text(payload.get("normality_input_ref"))
    if normality_ref:
        refs.append(normality_ref)
    return refs


def _office_execution_artifact_summary_refs(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for source in (payload, payload.get("metadata")):
        if not isinstance(source, dict):
            continue
        for key in (
            "office_execution_artifact_summary_path",
            "office_execution_artifact_summary_ref",
        ):
            text = _optional_text(source.get(key))
            if text:
                refs.append(text)
    return refs


def _task_summary(payload: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    return (
        _optional_text(payload.get("task_summary"))
        or _optional_text(metadata.get("task_summary"))
        or _optional_text(metadata.get("expected_group_behavior"))
        or _optional_text(metadata.get("description"))
    )


def _expected_outputs(payload: dict[str, Any], metadata: dict[str, Any]) -> list[Any] | dict[str, Any]:
    for source in (payload, metadata):
        value = source.get("expected_outputs")
        if isinstance(value, list | dict) and value:
            return value
        value = source.get("correctness_checks")
        if isinstance(value, list):
            return {"checks": value}
    return []


def _record_dict(value: ModelPairTrialExecutionResult | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, ModelPairTrialExecutionResult):
        return value.model_dump(mode="json")
    return dict(value)


def _required_text(value: Any, error_code: str) -> str:
    text = _optional_text(value)
    if not text:
        raise TaskCorrectnessInputLoadError(error_code)
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text_list(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value]
    if any(not item for item in cleaned):
        raise ValueError("text lists must not contain empty values.")
    return cleaned


def _optional_score(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 1.0 else None


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _has_nested_key(payload: dict[str, Any], key: str) -> bool:
    current: Any = payload
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _get_nested_value(payload: dict[str, Any], key: str | None) -> Any:
    if key is None:
        return None
    current: Any = payload
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
