from __future__ import annotations

import importlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping


OFFICE_EXECUTION_ARTIFACT_SUMMARY_SCHEMA_VERSION = "office_execution_artifact_summary_v1"
OFFICE_EXECUTION_ARTIFACT_SUMMARY_FILENAME = "office_execution_artifact_summary.json"

_MAX_TEXT_CHARS = 240
_MAX_ARTIFACTS = 100
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "auth",
)


class OfficeExecutionArtifactSummaryError(ValueError):
    """Controlled office artifact summary error safe to expose through CLI JSON."""


def load_trial_result(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OfficeExecutionArtifactSummaryError("trial_result_file_missing") from exc
    except OSError as exc:
        raise OfficeExecutionArtifactSummaryError("trial_result_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise OfficeExecutionArtifactSummaryError("trial_result_json_malformed") from exc
    if not isinstance(payload, dict):
        raise OfficeExecutionArtifactSummaryError("trial_result_payload_not_object")
    return payload


def write_office_execution_artifact_summary(
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


def summarize_office_execution_artifacts(
    trial_result: Mapping[str, Any],
    *,
    project_root: str | Path = ".",
    max_text_chars: int = _MAX_TEXT_CHARS,
    strict: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    payload = dict(trial_result)
    warnings: list[str] = []
    artifacts: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for candidate in _artifact_candidates(payload):
        if candidate["path"] in seen_paths:
            continue
        seen_paths.add(candidate["path"])
        artifact = _summarize_candidate(
            candidate,
            project_root=root,
            max_text_chars=max_text_chars,
        )
        if strict and not artifact.get("exists"):
            raise OfficeExecutionArtifactSummaryError("office_execution_artifact_missing")
        warnings.extend(_string_list(artifact.pop("_warning_codes", [])))
        artifacts.append(artifact)
        if len(artifacts) >= _MAX_ARTIFACTS:
            warnings.append("office_execution_artifact_limit_reached")
            break

    readable_count = sum(1 for artifact in artifacts if artifact.get("readable") is True)
    missing_count = sum(1 for artifact in artifacts if artifact.get("exists") is False)
    return _drop_none_values(
        {
            "schema_version": OFFICE_EXECUTION_ARTIFACT_SUMMARY_SCHEMA_VERSION,
            "run_id": _run_id(payload),
            "trial_id": _optional_text(payload.get("trial_id")),
            "scenario_id": _optional_text(payload.get("scenario_id")),
            "pair_id": _optional_text(payload.get("pair_id")),
            "artifact_count": len(artifacts),
            "readable_count": readable_count,
            "missing_count": missing_count,
            "artifacts": artifacts,
            "warnings": sorted(set(warnings)),
            "no_runtime_execution": True,
        }
    )


def _artifact_candidates(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in _list_value(payload.get("group_history")):
        if not isinstance(row, Mapping):
            continue
        metadata = row.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        for source_key in ("precreate_metadata", "office_execution_artifact", "office_execution_output"):
            source = metadata.get(source_key)
            if not isinstance(source, Mapping):
                continue
            path = _optional_text(source.get("path") or source.get("path_relative") or source.get("output_path"))
            if path:
                candidates.append(_candidate_from_row(row, path, source_key=source_key))
        for key in ("path", "path_relative", "output_path"):
            path = _optional_text(metadata.get(key))
            if path:
                candidates.append(_candidate_from_row(row, path, source_key=key))
    for path in _string_list(payload.get("artifact_refs")):
        if PurePosixPath(path.replace("\\", "/")).suffix.lower() == ".docx":
            candidates.append(
                {
                    "task_id": None,
                    "agent_id": None,
                    "action": None,
                    "path": path,
                    "source": "artifact_refs",
                }
            )
    return candidates


def _candidate_from_row(row: Mapping[str, Any], path: str, *, source_key: str) -> dict[str, Any]:
    return {
        "task_id": _optional_text(row.get("task_id")),
        "agent_id": _optional_text(row.get("agent_id")),
        "action": _optional_text(row.get("action")),
        "path": path,
        "source": f"group_history.{source_key}",
    }


def _summarize_candidate(
    candidate: Mapping[str, Any],
    *,
    project_root: Path,
    max_text_chars: int,
) -> dict[str, Any]:
    raw_path = _optional_text(candidate.get("path")) or ""
    path = _safe_relative_path(raw_path)
    extension = PurePosixPath(path).suffix.lower() if path != "<absolute_path>" else None
    artifact: dict[str, Any] = {
        "task_id": _optional_text(candidate.get("task_id")),
        "agent_id": _optional_text(candidate.get("agent_id")),
        "action": _optional_text(candidate.get("action")),
        "path": path,
        "extension": extension,
        "exists": False,
        "size_bytes": None,
        "readable": False,
        "paragraph_count": None,
        "safe_text_excerpt": None,
        "source": _optional_text(candidate.get("source")),
    }
    warnings: list[str] = []
    if path == "<absolute_path>":
        warnings.append("absolute_artifact_path_suppressed")
        artifact["_warning_codes"] = warnings
        return _drop_none_values(artifact)
    if not _is_safe_relative_path(path):
        warnings.append("unsafe_artifact_path_suppressed")
        artifact["_warning_codes"] = warnings
        return _drop_none_values(artifact)
    if extension != ".docx":
        warnings.append("office_artifact_extension_unsupported")
        artifact["_warning_codes"] = warnings
        return _drop_none_values(artifact)

    resolved = (project_root / path).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError:
        warnings.append("office_artifact_outside_project_root")
        artifact["_warning_codes"] = warnings
        return _drop_none_values(artifact)

    artifact["exists"] = resolved.is_file()
    if not resolved.is_file():
        warnings.append("office_artifact_missing")
        artifact["_warning_codes"] = warnings
        return _drop_none_values(artifact)
    artifact["size_bytes"] = resolved.stat().st_size
    if artifact["size_bytes"] <= 0:
        warnings.append("office_artifact_empty")
        artifact["_warning_codes"] = warnings
        return _drop_none_values(artifact)

    docx_metadata = _read_docx_metadata(resolved, max_text_chars=max_text_chars)
    artifact.update(docx_metadata)
    if docx_metadata.get("dependency_missing"):
        warnings.append("office_artifact_docx_dependency_missing")
    if docx_metadata.get("readable") is not True:
        warnings.append("office_artifact_unreadable")
    artifact["_warning_codes"] = warnings
    return _drop_none_values(artifact)


def _read_docx_metadata(path: Path, *, max_text_chars: int) -> dict[str, Any]:
    try:
        docx_module = importlib.import_module("docx")
    except Exception:
        return {
            "readable": False,
            "dependency_missing": "python-docx",
        }
    try:
        document = docx_module.Document(str(path))
        paragraphs = list(getattr(document, "paragraphs", []))
        texts = [str(getattr(paragraph, "text", "")) for paragraph in paragraphs]
        safe_excerpt = _bounded_text(" ".join(text for text in texts if text), max_text_chars)
    except Exception as exc:
        return {
            "readable": False,
            "read_error": _safe_error_code(exc),
        }
    return {
        "readable": True,
        "paragraph_count": len(paragraphs),
        "safe_text_excerpt": safe_excerpt,
    }


def _run_id(payload: Mapping[str, Any]) -> str | None:
    explicit = _optional_text(payload.get("run_id"))
    if explicit:
        return explicit
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        text = _optional_text(metadata.get("run_id"))
        if text:
            return text
    for ref in _string_list(payload.get("artifact_refs")):
        normalized = ref.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        if "single_trial_runs" in parts:
            index = parts.index("single_trial_runs")
            if index + 1 < len(parts):
                return parts[index + 1]
    return None


def _safe_relative_path(value: str) -> str:
    text = value.strip().replace("\\", "/")
    if _is_absolute_path(text):
        return "<absolute_path>"
    return _bounded_text(_redact_secret_text(text), 500)


def _is_safe_relative_path(value: str) -> bool:
    if not value or _is_absolute_path(value):
        return False
    path = PurePosixPath(value)
    return ".." not in path.parts


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )


def _bounded_text(value: str, max_chars: int) -> str:
    clean = _redact_secret_text(value).replace("\r", " ").replace("\n", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    if max_chars < 1:
        return ""
    if len(clean) > max_chars:
        return clean[:max_chars] + "...[truncated]"
    return clean


def _safe_error_code(exc: Exception) -> str:
    text = str(exc).strip()
    if not text or _is_absolute_path(text) or _secret_like_text(text):
        return exc.__class__.__name__
    return _bounded_text(text, 120)


def _redact_secret_text(value: str) -> str:
    return re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\s*[:=]\s*['\"]?[^,\s'\"]+",
        lambda match: f"{match.group(1)}=<redacted_secret>",
        value,
    )


def _secret_like_text(value: str) -> bool:
    return bool(re.search(r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\b", value))


def _secret_like_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def _drop_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _redact_secret_text(str(value)).strip()
    if not text or _secret_like_key(text):
        return None
    return text


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
