from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from statistics import mean
from typing import Any, Mapping, Sequence


MINI_MATRIX_AGGREGATE_SUMMARY_SCHEMA_VERSION = "controlled_mini_matrix_aggregate_summary_v1"
MINI_MATRIX_AGGREGATE_SUMMARY_FILENAME = "mini_matrix_aggregate_summary.json"


class MiniMatrixAggregationError(ValueError):
    """Controlled mini-matrix aggregation error safe to expose through CLI JSON."""


def aggregate_mini_matrix_results(
    run_output_dirs: Sequence[str | Path],
    *,
    summary_id: str | None = None,
) -> dict[str, Any]:
    if not run_output_dirs:
        raise MiniMatrixAggregationError("run_output_dirs_required")
    repeat_summaries = [_repeat_summary(Path(path)) for path in run_output_dirs]
    scores = [
        row["correctness_score"]
        for row in repeat_summaries
        if isinstance(row.get("correctness_score"), int | float)
    ]
    warnings = sorted({warning for row in repeat_summaries for warning in _string_list(row.get("warnings"))})
    return _drop_none_values(
        {
            "schema_version": MINI_MATRIX_AGGREGATE_SUMMARY_SCHEMA_VERSION,
            "summary_id": summary_id or "controlled_mini_matrix_aggregate",
            "repeat_count": len(repeat_summaries),
            "succeeded_count": sum(1 for row in repeat_summaries if row.get("status") == "succeeded"),
            "failed_count": sum(1 for row in repeat_summaries if row.get("status") == "failed"),
            "task_success_count": sum(1 for row in repeat_summaries if row.get("task_success") is True),
            "task_failure_count": sum(1 for row in repeat_summaries if row.get("task_success") is False),
            "execution_attempted_count": sum(_safe_int(row.get("execution_attempted_count")) for row in repeat_summaries),
            "execution_success_count": sum(_safe_int(row.get("execution_success_count")) for row in repeat_summaries),
            "office_artifact_count": sum(_safe_int(row.get("office_artifact_count")) for row in repeat_summaries),
            "office_artifact_readable_count": sum(
                _safe_int(row.get("office_artifact_readable_count")) for row in repeat_summaries
            ),
            "normality_input_count": sum(_safe_int(row.get("normality_input_count")) for row in repeat_summaries),
            "resource_observation_count": sum(
                _safe_int(row.get("resource_observation_count")) for row in repeat_summaries
            ),
            "correctness_score_count": len(scores),
            "mean_correctness_score": round(mean(scores), 6) if scores else None,
            "execution_correctness_pass_count": sum(
                1 for row in repeat_summaries if row.get("execution_correctness_pass") is True
            ),
            "artifact_correctness_pass_count": sum(
                1 for row in repeat_summaries if row.get("artifact_correctness_pass") is True
            ),
            "repeats": repeat_summaries,
            "warnings": warnings,
            "no_runtime_execution": True,
        }
    )


def write_mini_matrix_aggregate_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MINI_MATRIX_AGGREGATE_SUMMARY_FILENAME
    path.write_text(
        json.dumps(dict(summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _repeat_summary(run_dir: Path) -> dict[str, Any]:
    trial_result_path = run_dir / "model_pair_single_trial_result.json"
    matrix_summary_path = run_dir / "model_pair_single_trial_matrix_summary.json"
    office_summary_path = run_dir / "office_execution_artifact_summary.json"
    correctness_summary_path = run_dir / "office_execution_correctness_summary.json"
    adapter_summary_path = run_dir / "matrix_adapters" / "matrix_run_adapter_summary.json"

    trial_result = _load_json_or_empty(trial_result_path)
    matrix_summary = _load_json_or_empty(matrix_summary_path)
    office_summary = _load_json_or_empty(office_summary_path)
    correctness_summary = _load_json_or_empty(correctness_summary_path)
    adapter_summary = _load_json_or_empty(adapter_summary_path)
    warnings = [
        *_string_list(trial_result.get("warnings")),
        *_string_list(matrix_summary.get("warnings")),
        *_string_list(office_summary.get("warnings")),
        *_string_list(correctness_summary.get("warnings")),
        *_string_list(adapter_summary.get("warnings")),
    ]
    if not trial_result_path.is_file():
        warnings.append("trial_result_missing")
    if not matrix_summary_path.is_file():
        warnings.append("matrix_summary_missing")
    if not office_summary_path.is_file():
        warnings.append("office_execution_artifact_summary_missing")

    execution_counts = _execution_counts(trial_result)
    correctness_score = _correctness_score(trial_result, correctness_summary)
    return _drop_none_values(
        {
            "run_id": _run_id(run_dir, trial_result, matrix_summary, office_summary),
            "run_output_dir": _safe_relative_path(run_dir),
            "trial_id": _optional_text(trial_result.get("trial_id")),
            "scenario_id": _optional_text(trial_result.get("scenario_id")),
            "pair_id": _optional_text(trial_result.get("pair_id")),
            "status": _optional_text(trial_result.get("status")) or "missing",
            "task_success": trial_result.get("task_success") if isinstance(trial_result.get("task_success"), bool) else None,
            "correctness_score": correctness_score,
            "correctness_summary_path": (
                _safe_relative_path(correctness_summary_path) if correctness_summary_path.is_file() else None
            ),
            "correctness_criteria": (
                correctness_summary.get("criteria") if isinstance(correctness_summary.get("criteria"), Mapping) else None
            ),
            "execution_correctness_pass": correctness_summary.get("execution_correctness_pass")
            if isinstance(correctness_summary.get("execution_correctness_pass"), bool)
            else None,
            "artifact_correctness_pass": correctness_summary.get("artifact_correctness_pass")
            if isinstance(correctness_summary.get("artifact_correctness_pass"), bool)
            else None,
            "normality_input_ref": _optional_text(trial_result.get("normality_input_ref")),
            "error_code": _optional_text(trial_result.get("error_code")),
            "execution_attempted_count": execution_counts["attempted"],
            "execution_success_count": execution_counts["success"],
            "office_artifact_summary_path": _safe_relative_path(office_summary_path) if office_summary_path.is_file() else None,
            "office_artifact_count": _safe_int(office_summary.get("artifact_count")),
            "office_artifact_readable_count": _safe_int(office_summary.get("readable_count")),
            "adapter_summary_path": _safe_relative_path(adapter_summary_path) if adapter_summary_path.is_file() else None,
            "normality_input_count": _safe_int(adapter_summary.get("normality_input_count")),
            "resource_observation_count": _safe_int(adapter_summary.get("resource_observation_count")),
            "warnings": sorted(set(warnings)),
        }
    )


def _correctness_score(trial_result: Mapping[str, Any], correctness_summary: Mapping[str, Any]) -> float | None:
    summary_score = _optional_score(correctness_summary.get("correctness_score"))
    if summary_score is not None:
        return summary_score
    return _optional_score(trial_result.get("correctness_score"))


def _load_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"warnings": [f"{path.name}_unreadable"]}
    return payload if isinstance(payload, dict) else {"warnings": [f"{path.name}_not_object"]}


def _execution_counts(trial_result: Mapping[str, Any]) -> dict[str, int]:
    attempted = 0
    success = 0
    rows = trial_result.get("group_history")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        metadata = row.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if metadata.get("execution_attempted") is True:
            attempted += 1
        if metadata.get("execution_success") is True:
            success += 1
    return {"attempted": attempted, "success": success}


def _run_id(run_dir: Path, *sources: Mapping[str, Any]) -> str:
    for source in sources:
        text = _optional_text(source.get("run_id"))
        if text:
            return text
    return run_dir.name


def _safe_relative_path(path: Path) -> str:
    text = str(path).replace("\\", "/")
    if _is_absolute_path(text):
        try:
            text = path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
        except (OSError, ValueError):
            return "<absolute_path>"
    return text


def _is_absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("\\", "/")
    if not text or _is_absolute_path(text):
        return None
    return text


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value >= 0 else 0
    return 0


def _optional_score(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 1 else None


def _drop_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
