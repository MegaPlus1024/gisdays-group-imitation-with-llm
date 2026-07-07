from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping


OFFICE_EXECUTION_CORRECTNESS_SUMMARY_SCHEMA_VERSION = "office_execution_correctness_summary_v1"
OFFICE_EXECUTION_CORRECTNESS_SUMMARY_FILENAME = "office_execution_correctness_summary.json"


class OfficeExecutionCorrectnessSummaryError(ValueError):
    """Controlled office execution correctness error safe to expose through CLI JSON."""


def load_json_object(path: str | Path, *, label: str) -> dict[str, Any]:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OfficeExecutionCorrectnessSummaryError(f"{label}_file_missing") from exc
    except OSError as exc:
        raise OfficeExecutionCorrectnessSummaryError(f"{label}_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise OfficeExecutionCorrectnessSummaryError(f"{label}_json_malformed") from exc
    if not isinstance(payload, dict):
        raise OfficeExecutionCorrectnessSummaryError(f"{label}_payload_not_object")
    return payload


def score_office_execution_correctness(
    trial_result: Mapping[str, Any],
    office_artifact_summary: Mapping[str, Any],
) -> dict[str, Any]:
    group_history = [row for row in _list_value(trial_result.get("group_history")) if isinstance(row, Mapping)]
    executable_rows = [
        row
        for row in group_history
        if _row_metadata(row).get("action_execution_enabled") is True
        or "execution_attempted" in _row_metadata(row)
        or "execution_success" in _row_metadata(row)
    ]
    artifacts = [row for row in _list_value(office_artifact_summary.get("artifacts")) if isinstance(row, Mapping)]
    artifact_count = _safe_int(office_artifact_summary.get("artifact_count"), fallback=len(artifacts))
    readable_artifact_count = _safe_int(office_artifact_summary.get("readable_count"))
    missing_artifact_count = _safe_int(office_artifact_summary.get("missing_count"))
    criteria = {
        "trial_succeeded": _trial_succeeded(trial_result),
        "all_steps_validated": bool(group_history)
        and all(_row_metadata(row).get("validation_accepted") is True for row in group_history),
        "all_execution_attempted": bool(executable_rows)
        and all(_row_metadata(row).get("execution_attempted") is True for row in executable_rows),
        "all_execution_succeeded": bool(executable_rows)
        and all(_row_metadata(row).get("execution_success") is True for row in executable_rows),
        "all_office_artifacts_exist": _all_office_artifacts_exist(
            artifacts,
            artifact_count=artifact_count,
            missing_artifact_count=missing_artifact_count,
        ),
        "all_office_artifacts_readable": _all_office_artifacts_readable(
            artifacts,
            artifact_count=artifact_count,
            readable_artifact_count=readable_artifact_count,
        ),
    }
    score = round(sum(1.0 if passed else 0.0 for passed in criteria.values()) / len(criteria), 6)
    execution_correctness_pass = all(
        criteria[key]
        for key in (
            "trial_succeeded",
            "all_steps_validated",
            "all_execution_attempted",
            "all_execution_succeeded",
        )
    )
    artifact_correctness_pass = all(
        criteria[key]
        for key in (
            "all_office_artifacts_exist",
            "all_office_artifacts_readable",
        )
    )
    return _drop_none_values(
        {
            "schema_version": OFFICE_EXECUTION_CORRECTNESS_SUMMARY_SCHEMA_VERSION,
            "run_id": _run_id(trial_result, office_artifact_summary),
            "trial_id": _optional_text(trial_result.get("trial_id") or office_artifact_summary.get("trial_id")),
            "scenario_id": _optional_text(trial_result.get("scenario_id") or office_artifact_summary.get("scenario_id")),
            "pair_id": _optional_text(trial_result.get("pair_id") or office_artifact_summary.get("pair_id")),
            "correctness_score": score,
            "criteria": criteria,
            "execution_correctness_pass": execution_correctness_pass,
            "artifact_correctness_pass": artifact_correctness_pass,
            "artifact_count": artifact_count,
            "readable_artifact_count": readable_artifact_count,
            "missing_artifact_count": missing_artifact_count,
            "artifact_paths": _artifact_paths(artifacts),
            "notes": [
                "execution_correctness_only",
                "semantic_document_quality_not_scored",
            ],
            "warnings": sorted(
                set(
                    [
                        *_string_list(trial_result.get("warnings")),
                        *_string_list(office_artifact_summary.get("warnings")),
                    ]
                )
            ),
            "no_runtime_execution": True,
        }
    )


def write_office_execution_correctness_summary(
    summary: Mapping[str, Any],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _trial_succeeded(trial_result: Mapping[str, Any]) -> bool:
    status = _optional_text(trial_result.get("status"))
    if status not in {"succeeded", "success", "completed", "passed"}:
        return False
    return trial_result.get("task_success") is not False


def _all_office_artifacts_exist(
    artifacts: list[Mapping[str, Any]],
    *,
    artifact_count: int,
    missing_artifact_count: int,
) -> bool:
    if artifact_count < 1:
        return False
    if artifacts:
        return all(row.get("exists") is True for row in artifacts)
    return missing_artifact_count == 0


def _all_office_artifacts_readable(
    artifacts: list[Mapping[str, Any]],
    *,
    artifact_count: int,
    readable_artifact_count: int,
) -> bool:
    if artifact_count < 1:
        return False
    if artifacts:
        return all(row.get("readable") is True for row in artifacts)
    return readable_artifact_count == artifact_count


def _artifact_paths(artifacts: list[Mapping[str, Any]]) -> list[str]:
    paths: list[str] = []
    for artifact in artifacts:
        path = _safe_relative_path(artifact.get("path"))
        if path:
            paths.append(path)
    return list(dict.fromkeys(paths))


def _run_id(*sources: Mapping[str, Any]) -> str | None:
    for source in sources:
        explicit = _optional_text(source.get("run_id"))
        if explicit:
            return explicit
        metadata = source.get("metadata")
        if isinstance(metadata, Mapping):
            text = _optional_text(metadata.get("run_id"))
            if text:
                return text
        for ref in _string_list(source.get("artifact_refs")):
            normalized = ref.replace("\\", "/")
            parts = PurePosixPath(normalized).parts
            if "single_trial_runs" in parts:
                index = parts.index("single_trial_runs")
                if index + 1 < len(parts):
                    return parts[index + 1]
    return None


def _row_metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _safe_relative_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("\\", "/")
    if not text:
        return None
    if _is_absolute_path(text):
        return "<absolute_path>"
    if ".." in PurePosixPath(text).parts:
        return None
    return _bounded_text(text, 500)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("\\", "/")
    if not text or _is_absolute_path(text):
        return None
    return _bounded_text(text, 500)


def _safe_int(value: Any, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value >= 0 else 0
    return fallback if fallback >= 0 else 0


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )


def _bounded_text(value: str, max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    if max_chars < 1:
        return ""
    if len(clean) > max_chars:
        return clean[:max_chars] + "...[truncated]"
    return clean


def _drop_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
