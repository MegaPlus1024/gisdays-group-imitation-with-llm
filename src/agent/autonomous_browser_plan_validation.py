from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse


PLAN_SCHEMA_VERSION = "autonomous_browser_plan_v1"
VALIDATION_RESULT_SCHEMA_VERSION = "autonomous_browser_plan_validation_result_v1"

ALLOWED_BROWSER_ACTION_NAMES = (
    "browser_open_url",
    "browser_click",
    "browser_extract_text",
    "browser_fill",
    "browser_submit",
    "browser_wait",
    "browser_search",
    "browser_snapshot",
)

ALLOWED_BROWSER_HOSTS = (
    "local.intranet",
    "local-intranet.test",
    "docs.local",
    "portal.local",
)

MAX_TEXT_LENGTH = 2_000
MAX_PARAMETER_TEXT_LENGTH = 2_000
MAX_PLAN_ID_LENGTH = 120
MAX_GOAL_LENGTH = 500
MAX_STEP_ID_LENGTH = 120
MAX_EXPECTED_TEXT_LENGTH = 500
MAX_ACTIONS_TOTAL = 128

SECRET_KEY_TOKENS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "auth",
)

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\b\s*[:=]\s*['\"]?[^,\s'\"}]+"
)


class AutonomousBrowserPlanValidationError(ValueError):
    """Raised when a browser plan cannot be loaded or validated."""


@dataclass(frozen=True)
class AutonomousBrowserPlanValidationResult:
    schema_version: str
    status: str
    error_code: str | None
    plan_id: str | None
    actions_total: int
    allowed_actions: tuple[str, ...] = ()
    normalized_plan: dict[str, Any] | None = None
    limitations: tuple[str, ...] = ()
    diagnostics: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "plan_id": self.plan_id,
            "actions_total": self.actions_total,
            "allowed_actions": list(self.allowed_actions),
            "limitations": list(self.limitations),
            "diagnostics": [dict(item) for item in self.diagnostics],
        }
        if self.normalized_plan is not None:
            payload["normalized_plan"] = self.normalized_plan
        return payload


def validate_autonomous_browser_plan(plan: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    try:
        payload = _load_plan_payload(plan)
    except AutonomousBrowserPlanValidationError as exc:
        return AutonomousBrowserPlanValidationResult(
            schema_version=VALIDATION_RESULT_SCHEMA_VERSION,
            status="rejected",
            error_code="plan_load_failed",
            plan_id=None,
            actions_total=0,
            allowed_actions=ALLOWED_BROWSER_ACTION_NAMES,
            limitations=_limitations(),
            diagnostics=({"finding_type": "plan_load_failed", "message": str(exc)},),
        ).to_dict()

    result = _validate_plan_payload(payload)
    return result.to_dict()


def _validate_plan_payload(payload: Mapping[str, Any]) -> AutonomousBrowserPlanValidationResult:
    diagnostics: list[dict[str, Any]] = []
    plan_id = _safe_text(payload.get("plan_id"), "plan_id", diagnostics, max_length=MAX_PLAN_ID_LENGTH)
    goal = _safe_text(payload.get("goal"), "goal", diagnostics, max_length=MAX_GOAL_LENGTH)
    scenario_id = _safe_text(payload.get("scenario_id"), "scenario_id", diagnostics, max_length=MAX_STEP_ID_LENGTH)

    if str(payload.get("schema_version", "")) != PLAN_SCHEMA_VERSION:
        return _reject(
            "invalid_schema_version",
            plan_id=plan_id,
            diagnostics=diagnostics,
            extra={"expected_schema_version": PLAN_SCHEMA_VERSION},
        )
    if plan_id is None or goal is None or scenario_id is None:
        return _reject(
            "missing_required_field",
            plan_id=plan_id,
            diagnostics=diagnostics,
        )

    max_actions = payload.get("max_actions")
    if not isinstance(max_actions, int) or isinstance(max_actions, bool) or max_actions < 1:
        return _reject("invalid_max_actions", plan_id=plan_id, diagnostics=diagnostics)

    actions = payload.get("actions")
    if not isinstance(actions, list):
        return _reject("invalid_actions_collection", plan_id=plan_id, diagnostics=diagnostics)
    if len(actions) > max_actions:
        diagnostics.append(
            {
                "finding_type": "plan_exceeds_max_actions",
                "max_actions": max_actions,
                "actions_total": len(actions),
            }
        )
        return _reject("max_actions_exceeded", plan_id=plan_id, diagnostics=diagnostics)
    if len(actions) > MAX_ACTIONS_TOTAL:
        diagnostics.append(
            {
                "finding_type": "plan_too_large",
                "actions_total": len(actions),
                "limit": MAX_ACTIONS_TOTAL,
            }
        )
        return _reject("plan_too_large", plan_id=plan_id, diagnostics=diagnostics)

    normalized_actions: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            diagnostics.append({"finding_type": "invalid_action", "path": f"actions[{index}]"})
            return _reject("invalid_action_shape", plan_id=plan_id, diagnostics=diagnostics)
        step_id = _safe_text(action.get("step_id"), f"actions[{index}].step_id", diagnostics, max_length=MAX_STEP_ID_LENGTH)
        if step_id is None:
            return _reject("missing_step_id", plan_id=plan_id, diagnostics=diagnostics)
        if step_id in seen_step_ids:
            diagnostics.append({"finding_type": "duplicate_step_id", "path": f"actions[{index}].step_id"})
            return _reject("duplicate_step_id", plan_id=plan_id, diagnostics=diagnostics)
        seen_step_ids.add(step_id)

        action_name = _safe_text(action.get("action_name"), f"actions[{index}].action_name", diagnostics, max_length=MAX_STEP_ID_LENGTH)
        if action_name is None:
            return _reject("missing_action_name", plan_id=plan_id, diagnostics=diagnostics)
        if action_name not in ALLOWED_BROWSER_ACTION_NAMES:
            diagnostics.append({"finding_type": "unknown_browser_action", "path": f"actions[{index}].action_name", "action_name": action_name})
            return _reject("unknown_browser_action", plan_id=plan_id, diagnostics=diagnostics)

        parameters = action.get("parameters")
        if not isinstance(parameters, Mapping):
            diagnostics.append({"finding_type": "invalid_parameters_shape", "path": f"actions[{index}].parameters"})
            return _reject("invalid_parameters_shape", plan_id=plan_id, diagnostics=diagnostics)

        normalized_parameters, parameter_issues = _validate_parameters(parameters, f"actions[{index}].parameters")
        if parameter_issues:
            diagnostics.extend(parameter_issues)
            return _reject(parameter_issues[0]["finding_type"], plan_id=plan_id, diagnostics=diagnostics)

        expected_text = _optional_text(action.get("expected_text"), f"actions[{index}].expected_text", diagnostics, max_length=MAX_EXPECTED_TEXT_LENGTH)
        if expected_text is False:
            return _reject("expected_text_too_long", plan_id=plan_id, diagnostics=diagnostics)

        normalized_action = {
            "step_id": step_id,
            "action_name": action_name,
            "parameters": normalized_parameters,
        }
        if expected_text is not None:
            normalized_action["expected_text"] = expected_text
        normalized_actions.append(normalized_action)

    normalized_plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": plan_id,
        "goal": goal,
        "scenario_id": scenario_id,
        "max_actions": max_actions,
        "actions": normalized_actions,
    }
    return AutonomousBrowserPlanValidationResult(
        schema_version=VALIDATION_RESULT_SCHEMA_VERSION,
        status="accepted",
        error_code=None,
        plan_id=plan_id,
        actions_total=len(normalized_actions),
        allowed_actions=ALLOWED_BROWSER_ACTION_NAMES,
        normalized_plan=normalized_plan,
        limitations=_limitations(),
        diagnostics=(),
    )


def _validate_parameters(parameters: Mapping[str, Any], path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []
    for key, value in parameters.items():
        if not isinstance(key, str) or not key.strip():
            issues.append({"finding_type": "invalid_parameter_key", "path": f"{path}.[key]"})
            return {}, issues
        clean_key = key.strip()
        if _secret_like_key(clean_key):
            issues.append({"finding_type": "secret_like_parameter_key", "path": f"{path}.{clean_key}"})
            return {}, issues
        clean_value, issue = _normalize_value(value, f"{path}.{clean_key}")
        if issue is not None:
            issues.append(issue)
            return {}, issues
        normalized[clean_key] = clean_value
    return normalized, issues


def _normalize_value(value: Any, path: str) -> tuple[Any, dict[str, Any] | None]:
    if value is None or isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value, None
    if isinstance(value, str):
        text = value.strip()
        if len(text) > MAX_PARAMETER_TEXT_LENGTH:
            return None, {"finding_type": "text_too_long", "path": path, "limit": MAX_PARAMETER_TEXT_LENGTH}
        if _secret_like_text(text):
            return None, {"finding_type": "secret_like_parameter_value", "path": path}
        path_issue = _reject_path_or_url(text, path)
        if path_issue is not None:
            return None, path_issue
        return text, None
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                return None, {"finding_type": "invalid_parameter_key", "path": f"{path}.[key]"}
            clean_key = key.strip()
            if _secret_like_key(clean_key):
                return None, {"finding_type": "secret_like_parameter_key", "path": f"{path}.{clean_key}"}
            normalized_item, issue = _normalize_value(item, f"{path}.{clean_key}")
            if issue is not None:
                return None, issue
            normalized[clean_key] = normalized_item
        return normalized, None
    if isinstance(value, list):
        normalized_items: list[Any] = []
        for index, item in enumerate(value):
            normalized_item, issue = _normalize_value(item, f"{path}[{index}]")
            if issue is not None:
                return None, issue
            normalized_items.append(normalized_item)
        return normalized_items, None
    return None, {"finding_type": "unsupported_parameter_type", "path": path, "type": type(value).__name__}


def _reject_path_or_url(text: str, path: str) -> dict[str, Any] | None:
    if _is_windows_absolute_path(text) or _is_posix_absolute_path(text):
        return {"finding_type": "absolute_path_not_allowed", "path": path}
    if text.startswith("file://"):
        return {"finding_type": "file_url_not_allowed", "path": path}
    if "://" not in text:
        return None
    parsed = urlparse(text)
    if parsed.username or parsed.password:
        return {"finding_type": "url_credentials_not_allowed", "path": path}
    if parsed.scheme not in {"http", "https"}:
        return {"finding_type": "external_url_not_allowed", "path": path}
    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_BROWSER_HOSTS:
        if hostname in {"localhost", "127.0.0.1"}:
            return {"finding_type": "loopback_url_not_allowed", "path": path}
        return {"finding_type": "external_url_not_allowed", "path": path}
    return None


def _optional_text(value: Any, path: str, diagnostics: list[dict[str, Any]], *, max_length: int) -> str | None | bool:
    if value is None:
        return None
    if not isinstance(value, str):
        diagnostics.append({"finding_type": "invalid_text_field", "path": path})
        return False
    text = value.strip()
    if len(text) > max_length:
        diagnostics.append({"finding_type": "text_too_long", "path": path, "limit": max_length})
        return False
    if _secret_like_text(text):
        diagnostics.append({"finding_type": "secret_like_value_detected", "path": path})
        return False
    issue = _reject_path_or_url(text, path)
    if issue is not None:
        diagnostics.append(issue)
        return False
    return text


def _safe_text(value: Any, path: str, diagnostics: list[dict[str, Any]], *, max_length: int) -> str | None:
    if not isinstance(value, str):
        diagnostics.append({"finding_type": "missing_or_invalid_text", "path": path})
        return None
    text = value.strip()
    if not text:
        diagnostics.append({"finding_type": "missing_or_invalid_text", "path": path})
        return None
    if len(text) > max_length:
        diagnostics.append({"finding_type": "text_too_long", "path": path, "limit": max_length})
        return None
    if _secret_like_text(text):
        diagnostics.append({"finding_type": "secret_like_value_detected", "path": path})
        return None
    return text


def _reject(error_code: str, *, plan_id: str | None, diagnostics: list[dict[str, Any]], extra: Mapping[str, Any] | None = None) -> AutonomousBrowserPlanValidationResult:
    if extra:
        diagnostics.append({"finding_type": error_code, **dict(extra)})
    return AutonomousBrowserPlanValidationResult(
        schema_version=VALIDATION_RESULT_SCHEMA_VERSION,
        status="rejected",
        error_code=error_code,
        plan_id=plan_id,
        actions_total=0,
        allowed_actions=ALLOWED_BROWSER_ACTION_NAMES,
        limitations=_limitations(),
        diagnostics=tuple(diagnostics),
    )


def _load_plan_payload(plan: str | Path | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(plan, Mapping):
        return plan
    path = Path(plan)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AutonomousBrowserPlanValidationError("plan JSON is malformed.") from exc
    except OSError as exc:
        raise AutonomousBrowserPlanValidationError("plan file could not be read.") from exc
    if not isinstance(payload, dict):
        raise AutonomousBrowserPlanValidationError("plan root must be a JSON object.")
    return payload


def _limitations() -> tuple[str, ...]:
    return (
        "offline validation only",
        "no LLM planning",
        "no browser execution",
        "no Playwright import",
        "no model runtime",
        "no production readiness claim",
    )


def _secret_like_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in SECRET_KEY_TOKENS)


def _secret_like_text(value: str) -> bool:
    return bool(_SECRET_ASSIGNMENT_RE.search(value))


def _is_windows_absolute_path(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z]:[\\/].*", value)) or value.startswith("\\\\")


def _is_posix_absolute_path(value: str) -> bool:
    return value.startswith("/") and "://" not in value
