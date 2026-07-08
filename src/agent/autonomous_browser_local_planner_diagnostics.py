from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


CONFIG_SCHEMA_VERSION = "autonomous_browser_local_planner_diagnostic_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_local_planner_diagnostic_summary_v1"
DEFAULT_DIAGNOSTIC_ID = "browser_local_planner_diagnostic_v1"
DEFAULT_ENDPOINT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_MODEL = "second_model"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/local_planner_diagnostics"
DEFAULT_HEALTH_TIMEOUT_SEC = 3.0
DEFAULT_MODELS_TIMEOUT_SEC = 3.0
DEFAULT_TINY_COMPLETION_TIMEOUT_SEC = 6.0
DEFAULT_MICRO_PLANNER_TIMEOUT_SEC = 8.0
DEFAULT_TINY_MAX_TOKENS = 16
DEFAULT_MICRO_PLANNER_MAX_TOKENS = 96
SUMMARY_FILENAME = "autonomous_browser_local_planner_diagnostic_summary.json"
ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost"}
_MAX_PREVIEW_CHARS = 240


TransportFn = Callable[[str, str, bytes | None, float], "DiagnosticHttpResponse"]


@dataclass(frozen=True)
class DiagnosticHttpResponse:
    status_code: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DiagnosticStepSummary:
    name: str
    status: str
    error_code: str | None
    latency_ms: int | None
    response_preview: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "error_code": self.error_code,
            "latency_ms": self.latency_ms,
            "response_preview": self.response_preview,
        }


@dataclass(frozen=True)
class AutonomousBrowserLocalPlannerDiagnosticSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution_attempted: bool
    model_execution_completed: bool
    endpoint_base_url: str | None
    model: str | None
    steps: tuple[dict[str, Any], ...] = ()
    health_status: str = "skipped"
    models_status: str = "skipped"
    tiny_completion_status: str = "skipped"
    micro_planner_status: str = "skipped"
    tiny_latency_ms: int | None = None
    micro_planner_latency_ms: int | None = None
    timeout_step: str | None = None
    output_path: str | None = None
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution_attempted": self.model_execution_attempted,
            "model_execution_completed": self.model_execution_completed,
            "endpoint_base_url": self.endpoint_base_url,
            "model": self.model,
            "steps": [dict(step) for step in self.steps],
            "health_status": self.health_status,
            "models_status": self.models_status,
            "tiny_completion_status": self.tiny_completion_status,
            "micro_planner_status": self.micro_planner_status,
            "tiny_latency_ms": self.tiny_latency_ms,
            "micro_planner_latency_ms": self.micro_planner_latency_ms,
            "timeout_step": self.timeout_step,
            "output_path": self.output_path,
            "limitations": list(self.limitations),
        }


def diagnose_autonomous_browser_local_planner(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    allow_local_model_endpoint: bool = False,
    transport: TransportFn | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            diagnostic_id=config_result.get("diagnostic_id"),
            endpoint_base_url=config_result.get("endpoint_base_url"),
            model=config_result.get("model"),
            output_path=config_result.get("output_path"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    diagnostic_id = str(config_result["diagnostic_id"])
    endpoint_base_url = str(config_result["endpoint_base_url"])
    model = str(config_result["model"])
    output_path = str(config_result["output_path"])
    limitations = tuple(config_result.get("limitations") or _limitations())
    timeouts = config_result["timeouts"]
    max_tokens = config_result["max_tokens"]

    output_dir = repo / output_path
    output_dir.mkdir(parents=True, exist_ok=True)

    if not allow_local_model_endpoint:
        summary = _failure_summary(
            diagnostic_id=diagnostic_id,
            endpoint_base_url=endpoint_base_url,
            model=model,
            output_path=output_path,
            error_code="allow_local_model_endpoint_required",
            limitations=limitations,
        )
        _write_summary(summary, output_dir)
        return summary

    parsed = urllib.parse.urlparse(endpoint_base_url)
    if not _is_local_endpoint(parsed):
        summary = _failure_summary(
            diagnostic_id=diagnostic_id,
            endpoint_base_url=endpoint_base_url,
            model=model,
            output_path=output_path,
            error_code="endpoint_host_not_allowed",
            limitations=limitations,
        )
        _write_summary(summary, output_dir)
        return summary

    transport_fn = transport or _urllib_transport
    model_execution_attempted = True
    steps: list[DiagnosticStepSummary] = []
    health_status = "skipped"
    models_status = "skipped"
    tiny_completion_status = "skipped"
    micro_planner_status = "skipped"
    tiny_latency_ms: int | None = None
    micro_planner_latency_ms: int | None = None
    timeout_step: str | None = None
    error_code: str | None = None

    step = _run_get_step(
        name="health_check",
        url=_join_endpoint(endpoint_base_url, "/health"),
        timeout_sec=float(timeouts["health_timeout_sec"]),
        transport=transport_fn,
    )
    steps.append(step)
    health_status = step.status
    if step.status == "timed_out":
        timeout_step = step.name
        error_code = "local_planner_timeout"
    elif step.status != "succeeded":
        error_code = step.error_code or "health_check_failed"

    if error_code is None:
        step = _run_get_step(
            name="models_check",
            url=_join_endpoint(endpoint_base_url, "/v1/models"),
            timeout_sec=float(timeouts["models_timeout_sec"]),
            transport=transport_fn,
            expect_json=True,
        )
        steps.append(step)
        models_status = step.status
        if step.status == "timed_out":
            timeout_step = step.name
            error_code = "local_planner_timeout"
        elif step.status != "succeeded":
            error_code = step.error_code or "models_check_failed"

    if error_code is None:
        tiny_prompt = 'Return only this JSON: {"ok": true}'
        step = _run_chat_step(
            name="tiny_completion",
            url=_join_endpoint(endpoint_base_url, "/v1/chat/completions"),
            timeout_sec=float(timeouts["tiny_completion_timeout_sec"]),
            transport=transport_fn,
            model=model,
            prompt=tiny_prompt,
            max_tokens=int(max_tokens["tiny_max_tokens"]),
            require_json_content=True,
        )
        steps.append(step)
        tiny_completion_status = step.status
        tiny_latency_ms = step.latency_ms
        if step.status == "timed_out":
            timeout_step = step.name
            error_code = "local_planner_timeout"
        elif step.status != "succeeded":
            error_code = step.error_code or "tiny_completion_failed"

    if error_code is None:
        micro_prompt = _micro_planner_prompt()
        step = _run_chat_step(
            name="micro_planner_completion",
            url=_join_endpoint(endpoint_base_url, "/v1/chat/completions"),
            timeout_sec=float(timeouts["micro_planner_timeout_sec"]),
            transport=transport_fn,
            model=model,
            prompt=micro_prompt,
            max_tokens=int(max_tokens["micro_planner_max_tokens"]),
            require_json_content=False,
        )
        steps.append(step)
        micro_planner_status = step.status
        micro_planner_latency_ms = step.latency_ms
        if step.status == "timed_out":
            timeout_step = step.name
            error_code = "local_planner_timeout"
        elif step.status != "succeeded":
            error_code = step.error_code or "micro_planner_failed"

    model_execution_completed = error_code is None
    status = "succeeded" if model_execution_completed else "failed"
    summary = AutonomousBrowserLocalPlannerDiagnosticSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        model_execution_attempted=model_execution_attempted,
        model_execution_completed=model_execution_completed,
        endpoint_base_url=endpoint_base_url,
        model=model,
        steps=tuple(step.to_dict() for step in steps) + tuple(
            _skipped_step(name)
            for name in _remaining_step_names(steps)
        ),
        health_status=health_status,
        models_status=models_status,
        tiny_completion_status=tiny_completion_status,
        micro_planner_status=micro_planner_status,
        tiny_latency_ms=tiny_latency_ms,
        micro_planner_latency_ms=micro_planner_latency_ms,
        timeout_step=timeout_step,
        output_path=output_path,
        limitations=limitations,
    )
    summary_payload = summary.to_dict()
    _write_summary(summary_payload, output_dir)
    return summary_payload


def write_autonomous_browser_local_planner_diagnostic_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _load_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except OSError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "diagnostic_id": None,
                "endpoint_base_url": None,
                "model": None,
                "output_path": None,
                "limitations": _limitations(),
            }
        except json.JSONDecodeError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "diagnostic_id": None,
                "endpoint_base_url": None,
                "model": None,
                "output_path": None,
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostic_id": None,
            "endpoint_base_url": None,
            "model": None,
            "output_path": None,
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostic_id": _safe_text(payload.get("diagnostic_id")),
            "endpoint_base_url": _safe_text(payload.get("endpoint_base_url")),
            "model": _safe_text(payload.get("model")),
            "output_path": _safe_relative_path(payload.get("output_dir")),
            "limitations": _limitations(),
        }

    diagnostic_id = _safe_identifier(payload.get("diagnostic_id", DEFAULT_DIAGNOSTIC_ID), "diagnostic_id")
    endpoint_base_url = _safe_endpoint_base_url(payload.get("endpoint_base_url", DEFAULT_ENDPOINT_BASE_URL))
    model = _safe_identifier(payload.get("model", DEFAULT_MODEL), "model")
    output_path = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR))
    if diagnostic_id is None or endpoint_base_url is None or model is None or output_path is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostic_id": diagnostic_id,
            "endpoint_base_url": endpoint_base_url,
            "model": model,
            "output_path": output_path,
            "limitations": _limitations(),
        }

    health_timeout_sec = _safe_timeout(payload.get("health_timeout_sec", DEFAULT_HEALTH_TIMEOUT_SEC))
    models_timeout_sec = _safe_timeout(payload.get("models_timeout_sec", DEFAULT_MODELS_TIMEOUT_SEC))
    tiny_completion_timeout_sec = _safe_timeout(payload.get("tiny_completion_timeout_sec", DEFAULT_TINY_COMPLETION_TIMEOUT_SEC))
    micro_planner_timeout_sec = _safe_timeout(payload.get("micro_planner_timeout_sec", DEFAULT_MICRO_PLANNER_TIMEOUT_SEC))
    tiny_max_tokens = _safe_int(payload.get("tiny_max_tokens", DEFAULT_TINY_MAX_TOKENS))
    micro_planner_max_tokens = _safe_int(payload.get("micro_planner_max_tokens", DEFAULT_MICRO_PLANNER_MAX_TOKENS))
    if None in {health_timeout_sec, models_timeout_sec, tiny_completion_timeout_sec, micro_planner_timeout_sec}:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostic_id": diagnostic_id,
            "endpoint_base_url": endpoint_base_url,
            "model": model,
            "output_path": output_path,
            "limitations": _limitations(),
        }
    if tiny_max_tokens is None or micro_planner_max_tokens is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostic_id": diagnostic_id,
            "endpoint_base_url": endpoint_base_url,
            "model": model,
            "output_path": output_path,
            "limitations": _limitations(),
        }

    parsed = urllib.parse.urlparse(endpoint_base_url)
    if not _is_local_endpoint(parsed):
        return {
            "status": "failed",
            "error_code": "endpoint_host_not_allowed",
            "diagnostic_id": diagnostic_id,
            "endpoint_base_url": endpoint_base_url,
            "model": model,
            "output_path": output_path,
            "limitations": _limitations(),
        }

    return {
        "status": "ok",
        "diagnostic_id": diagnostic_id,
        "endpoint_base_url": endpoint_base_url,
        "model": model,
        "output_path": output_path,
        "timeouts": {
            "health_timeout_sec": health_timeout_sec,
            "models_timeout_sec": models_timeout_sec,
            "tiny_completion_timeout_sec": tiny_completion_timeout_sec,
            "micro_planner_timeout_sec": micro_planner_timeout_sec,
        },
        "max_tokens": {
            "tiny_max_tokens": tiny_max_tokens,
            "micro_planner_max_tokens": micro_planner_max_tokens,
        },
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _run_get_step(
    *,
    name: str,
    url: str,
    timeout_sec: float,
    transport: TransportFn,
    expect_json: bool = False,
) -> DiagnosticStepSummary:
    start = time.perf_counter()
    try:
        response = transport("GET", url, None, timeout_sec)
    except TimeoutError:
        return DiagnosticStepSummary(name=name, status="timed_out", error_code="local_planner_timeout", latency_ms=_latency_ms(start), response_preview="")
    except urllib.error.URLError as exc:
        if _is_timeout_exc(exc):
            return DiagnosticStepSummary(name=name, status="timed_out", error_code="local_planner_timeout", latency_ms=_latency_ms(start), response_preview="")
        return DiagnosticStepSummary(name=name, status="failed", error_code="endpoint_request_failed", latency_ms=_latency_ms(start), response_preview=_preview(str(exc)))
    except OSError as exc:
        return DiagnosticStepSummary(name=name, status="failed", error_code="endpoint_request_failed", latency_ms=_latency_ms(start), response_preview=_preview(str(exc)))

    latency_ms = _latency_ms(start)
    body_text = _decode_body(response.body)
    if response.status_code >= 400:
        return DiagnosticStepSummary(
            name=name,
            status="failed",
            error_code="endpoint_request_failed",
            latency_ms=latency_ms,
            response_preview=_preview(body_text or f"HTTP {response.status_code}"),
        )
    if expect_json:
        if not body_text.strip():
            return DiagnosticStepSummary(name=name, status="failed", error_code="response_parse_failed", latency_ms=latency_ms, response_preview="")
        try:
            parsed = json.loads(body_text or "{}")
        except json.JSONDecodeError:
            return DiagnosticStepSummary(name=name, status="failed", error_code="response_parse_failed", latency_ms=latency_ms, response_preview=_preview(body_text))
        return DiagnosticStepSummary(name=name, status="succeeded", error_code=None, latency_ms=latency_ms, response_preview=_preview(json.dumps(parsed, ensure_ascii=False, sort_keys=True)))
    return DiagnosticStepSummary(name=name, status="succeeded", error_code=None, latency_ms=latency_ms, response_preview=_preview(body_text))


def _run_chat_step(
    *,
    name: str,
    url: str,
    timeout_sec: float,
    transport: TransportFn,
    model: str,
    prompt: str,
    max_tokens: int,
    require_json_content: bool,
) -> DiagnosticStepSummary:
    start = time.perf_counter()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a local diagnostics probe."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        response = transport("POST", url, body, timeout_sec)
    except TimeoutError:
        return DiagnosticStepSummary(name=name, status="timed_out", error_code="local_planner_timeout", latency_ms=_latency_ms(start), response_preview="")
    except urllib.error.URLError as exc:
        if _is_timeout_exc(exc):
            return DiagnosticStepSummary(name=name, status="timed_out", error_code="local_planner_timeout", latency_ms=_latency_ms(start), response_preview="")
        return DiagnosticStepSummary(name=name, status="failed", error_code="endpoint_request_failed", latency_ms=_latency_ms(start), response_preview=_preview(str(exc)))
    except OSError as exc:
        return DiagnosticStepSummary(name=name, status="failed", error_code="endpoint_request_failed", latency_ms=_latency_ms(start), response_preview=_preview(str(exc)))

    latency_ms = _latency_ms(start)
    body_text = _decode_body(response.body)
    if response.status_code >= 400:
        return DiagnosticStepSummary(
            name=name,
            status="failed",
            error_code="endpoint_request_failed",
            latency_ms=latency_ms,
            response_preview=_preview(body_text or f"HTTP {response.status_code}"),
        )
    try:
        response_json = json.loads(body_text or "{}")
    except json.JSONDecodeError:
        return DiagnosticStepSummary(name=name, status="failed", error_code="response_parse_failed", latency_ms=latency_ms, response_preview=_preview(body_text))

    preview = _assistant_content_preview(response_json)
    if require_json_content and not preview.strip():
        return DiagnosticStepSummary(name=name, status="failed", error_code="response_parse_failed", latency_ms=latency_ms, response_preview="")
    if require_json_content:
        try:
            json.loads(preview)
        except json.JSONDecodeError:
            return DiagnosticStepSummary(name=name, status="failed", error_code="response_parse_failed", latency_ms=latency_ms, response_preview=_preview(preview))
    return DiagnosticStepSummary(name=name, status="succeeded", error_code=None, latency_ms=latency_ms, response_preview=_preview(preview))


def _assistant_content_preview(response_json: Mapping[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if not isinstance(content, str):
        return ""
    return content


def _urllib_transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> DiagnosticHttpResponse:
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return DiagnosticHttpResponse(
                status_code=int(getattr(response, "status", 200)),
                body=response.read(),
                headers=dict(response.headers.items()),
            )
    except urllib.error.HTTPError as exc:
        return DiagnosticHttpResponse(
            status_code=int(getattr(exc, "code", 500)),
            body=exc.read() if hasattr(exc, "read") else b"",
            headers=dict(getattr(exc, "headers", {}).items()) if getattr(exc, "headers", None) else {},
        )


def _write_summary(summary: Mapping[str, Any], output_dir: Path) -> Path:
    return write_autonomous_browser_local_planner_diagnostic_summary(summary, output_dir)


def _failure_summary(
    *,
    diagnostic_id: str | None,
    endpoint_base_url: str | None,
    model: str | None,
    output_path: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserLocalPlannerDiagnosticSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution_attempted=False,
        model_execution_completed=False,
        endpoint_base_url=endpoint_base_url,
        model=model,
        steps=(
            _skipped_step("health_check"),
            _skipped_step("models_check"),
            _skipped_step("tiny_completion"),
            _skipped_step("micro_planner_completion"),
        ),
        health_status="skipped",
        models_status="skipped",
        tiny_completion_status="skipped",
        micro_planner_status="skipped",
        output_path=output_path,
        limitations=limitations,
    )
    return summary.to_dict()


def _skipped_step(name: str) -> dict[str, Any]:
    return DiagnosticStepSummary(name=name, status="skipped", error_code=None, latency_ms=None, response_preview="").to_dict()


def _remaining_step_names(steps: list[DiagnosticStepSummary]) -> list[str]:
    seen = [step.name for step in steps]
    ordered = ["health_check", "models_check", "tiny_completion", "micro_planner_completion"]
    return [name for name in ordered if name not in seen]


def _micro_planner_prompt() -> str:
    return (
        "Return JSON only for autonomous_browser_plan_v1. "
        "Use one local fixture-backed browser action plan with short fields."
    )


def _limitations() -> tuple[str, ...]:
    return (
        "guarded local endpoint diagnostics only",
        "no model launch",
        "no browser execution",
        "no Playwright import",
        "strict per-step timeout only",
        "not production readiness",
    )


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


def _safe_endpoint_base_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        return None
    return normalized


def _safe_timeout(value: Any) -> float | None:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return None
    return timeout if timeout > 0 else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    return integer if integer > 0 else None


def _join_endpoint(base_url: str, suffix: str) -> str:
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def _decode_body(body: bytes) -> str:
    return body.decode("utf-8", errors="replace") if body else ""


def _latency_ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


def _preview(text: str) -> str:
    sanitized = _sanitize_text(text)
    if len(sanitized) <= _MAX_PREVIEW_CHARS:
        return sanitized
    return sanitized[: _MAX_PREVIEW_CHARS - 1] + "…"


def _sanitize_text(text: str) -> str:
    collapsed = " ".join(text.split())
    replaced = collapsed.replace("supersecret", "[redacted]").replace("api_key", "[redacted]")
    replaced = _redact_windows_paths(replaced)
    return replaced


def _redact_windows_paths(text: str) -> str:
    result = []
    i = 0
    while i < len(text):
        if i + 2 < len(text) and text[i + 1] == ":" and text[i].isalpha() and text[i + 2] in {"\\", "/"}:
            j = i + 3
            while j < len(text) and text[j] not in {" ", '"', "'", ",", "}", "]", ")", ">", "<"}:
                j += 1
            result.append("[path]")
            i = j
            continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _is_local_endpoint(parsed: urllib.parse.ParseResult) -> bool:
    return parsed.scheme in {"http", "https"} and parsed.hostname in ALLOWED_LOCAL_HOSTS


def _is_timeout_exc(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout))
    return isinstance(exc, socket.timeout)
