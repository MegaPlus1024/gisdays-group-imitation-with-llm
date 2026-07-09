from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_plan_playwright_replay_operator import (
    CONFIG_SCHEMA_VERSION as OPERATOR_CONFIG_SCHEMA_VERSION,
    REQUIRED_CONFIRM_VALUE,
    run_autonomous_browser_plan_playwright_replay_operator,
)
from .autonomous_browser_plan_playwright_replay_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    build_autonomous_browser_plan_playwright_replay_packet,
)
from .autonomous_browser_plan_validation import ALLOWED_BROWSER_HOSTS


CONFIG_SCHEMA_VERSION = "autonomous_browser_plan_playwright_replay_suite_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_plan_playwright_replay_suite_summary_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_suite"
DEFAULT_REPLAY_BACKEND = "fixture"
SUPPORTED_REPLAY_BACKENDS = ("fixture", "playwright")
FIXTURE_SCOPE_LOCAL_ONLY = "local_only"


@dataclass(frozen=True)
class AutonomousBrowserPlanPlaywrightReplaySuiteConfig:
    schema_version: str
    suite_id: str
    captured_outputs: tuple[str, ...]
    output_dir: str
    replay_backend: str
    allowed_hosts: tuple[str, ...]
    fixture_scope: str
    headless: bool
    timeout_ms: int
    expected_min_succeeded: int
    expected_max_failed: int
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "captured_outputs": list(self.captured_outputs),
            "output_dir": self.output_dir,
            "replay_backend": self.replay_backend,
            "allowed_hosts": list(self.allowed_hosts),
            "fixture_scope": self.fixture_scope,
            "headless": self.headless,
            "timeout_ms": self.timeout_ms,
            "expected_min_succeeded": self.expected_min_succeeded,
            "expected_max_failed": self.expected_max_failed,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class AutonomousBrowserPlanPlaywrightReplaySuiteSummary:
    schema_version: str
    status: str
    error_code: str | None
    suite_id: str | None
    replay_backend: str | None
    guard_status: str
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    real_network_traffic: bool
    outputs_total: int
    outputs_succeeded: int
    outputs_failed: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_passed: int
    expected_results_failed: int
    expected_results_total: int
    output_summaries: tuple[dict[str, Any], ...] = ()
    thresholds: dict[str, int] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "suite_id": self.suite_id,
            "replay_backend": self.replay_backend,
            "guard_status": self.guard_status,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "outputs_total": self.outputs_total,
            "outputs_succeeded": self.outputs_succeeded,
            "outputs_failed": self.outputs_failed,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "expected_results_total": self.expected_results_total,
            "output_summaries": [_jsonable(item) for item in self.output_summaries],
            "thresholds": dict(self.thresholds),
            "limitations": list(self.limitations),
        }


def load_autonomous_browser_plan_playwright_replay_suite_config(
    config_artifact: str | Path | Mapping[str, Any],
) -> AutonomousBrowserPlanPlaywrightReplaySuiteConfig:
    try:
        payload = _load_json_payload(config_artifact)
    except OSError as exc:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("suite config could not be read.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("suite config could not be parsed.") from exc
    if not isinstance(payload, dict):
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("suite config root must be an object.")
    return _config_from_mapping(payload)


def run_autonomous_browser_plan_playwright_replay_suite(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    allow_real_browser: bool = False,
    confirm_real_browser: str | None = None,
    dry_run: bool = False,
    replay_backend: str | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    try:
        config = load_autonomous_browser_plan_playwright_replay_suite_config(config_artifact)
    except AutonomousBrowserPlanPlaywrightReplaySuiteConfigError as exc:
        return _suite_failure(
            status="failed",
            error_code="config_validation_failed",
            guard_status="config_validation_failed",
            suite_id=None,
            replay_backend=_safe_backend_value(replay_backend),
            outputs_total=0,
            limitations=tuple(),
            diagnostics={"config_error": str(exc)},
        )

    requested_backend = _resolve_replay_backend(config.replay_backend, replay_backend)
    if requested_backend is None:
        return _suite_failure(
            status="failed",
            error_code="unknown_replay_backend",
            guard_status="config_validation_failed",
            suite_id=config.suite_id,
            replay_backend=_safe_backend_value(replay_backend) or config.replay_backend,
            outputs_total=0,
            limitations=_limitations(config),
            diagnostics={"config": _jsonable(config.to_dict())},
        )

    config_error = _validate_config(config, replay_backend=requested_backend)
    if config_error is not None:
        return _suite_failure(
            status="failed",
            error_code="config_validation_failed",
            guard_status="config_validation_failed",
            suite_id=config.suite_id,
            replay_backend=requested_backend,
            outputs_total=0,
            limitations=_limitations(config),
            diagnostics={"config": _jsonable(config.to_dict())},
        )

    if not dry_run and (not allow_real_browser or confirm_real_browser != REQUIRED_CONFIRM_VALUE):
        return _suite_failure(
            status="refused",
            error_code="allow_real_browser_required",
            guard_status="refused",
            suite_id=config.suite_id,
            replay_backend=requested_backend,
            outputs_total=len(config.captured_outputs),
            limitations=_limitations(config),
        )

    output_summaries: list[dict[str, Any]] = []
    outputs_succeeded = 0
    outputs_failed = 0
    actions_attempted_total = 0
    actions_succeeded_total = 0
    actions_failed_total = 0
    expected_results_passed = 0
    expected_results_failed = 0
    expected_results_total = 0
    any_real_browser_execution = False
    any_playwright_execution = False
    any_browser_opened = False
    any_real_network_traffic = False
    no_runtime_execution = True
    first_issue_code: str | None = None

    for index, captured_output in enumerate(config.captured_outputs):
        output_summary = _replay_captured_output(
            captured_output,
            repo_root=repo,
            suite=config,
            replay_backend=requested_backend,
            dry_run=dry_run,
            allow_real_browser=allow_real_browser,
            confirm_real_browser=confirm_real_browser,
            output_index=index,
        )
        output_summary = _normalize_error_code_payload(output_summary)
        output_summaries.append(output_summary)

        if str(output_summary.get("status")) == "succeeded":
            outputs_succeeded += 1
        else:
            outputs_failed += 1
            if first_issue_code is None:
                first_issue_code = str(output_summary.get("error_code") or "captured_output_failed")

        actions_attempted_total += _int(output_summary.get("actions_attempted"))
        actions_succeeded_total += _int(output_summary.get("actions_succeeded"))
        actions_failed_total += _int(output_summary.get("actions_failed"))
        expected_results_passed += _int(output_summary.get("expected_results_passed"))
        expected_results_failed += _int(output_summary.get("expected_results_failed"))
        expected_results_total += _int(output_summary.get("expected_results_total"))

        no_runtime_execution = no_runtime_execution and bool(output_summary.get("no_runtime_execution", False))
        any_real_browser_execution = any_real_browser_execution or bool(output_summary.get("real_browser_execution", False))
        any_playwright_execution = any_playwright_execution or bool(output_summary.get("playwright_execution", False))
        any_browser_opened = any_browser_opened or bool(output_summary.get("browser_opened", False))
        any_real_network_traffic = any_real_network_traffic or bool(output_summary.get("real_network_traffic", False))

    if not output_summaries:
        return _suite_failure(
            status="failed",
            error_code="no_captured_outputs_provided",
            guard_status="dry_run" if dry_run else "guarded_replay",
            suite_id=config.suite_id,
            replay_backend=requested_backend,
            outputs_total=0,
            limitations=_limitations(config),
            thresholds={
                "expected_min_succeeded": config.expected_min_succeeded,
                "expected_max_failed": config.expected_max_failed,
            },
        )

    thresholds_met = outputs_succeeded >= config.expected_min_succeeded and outputs_failed <= config.expected_max_failed
    if outputs_failed == 0 and thresholds_met:
        status = "succeeded"
        error_code = None
    elif thresholds_met:
        status = "completed_with_failures"
        error_code = first_issue_code or "suite_completed_with_failures"
    else:
        status = "failed"
        error_code = first_issue_code or "suite_thresholds_not_met"

    summary = AutonomousBrowserPlanPlaywrightReplaySuiteSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        suite_id=config.suite_id,
        replay_backend=requested_backend,
        guard_status="dry_run" if dry_run else "guarded_replay",
        no_runtime_execution=no_runtime_execution,
        model_execution=False,
        real_browser_execution=any_real_browser_execution,
        playwright_execution=any_playwright_execution,
        browser_opened=any_browser_opened,
        real_network_traffic=any_real_network_traffic,
        outputs_total=len(output_summaries),
        outputs_succeeded=outputs_succeeded,
        outputs_failed=outputs_failed,
        actions_attempted_total=actions_attempted_total,
        actions_succeeded_total=actions_succeeded_total,
        actions_failed_total=actions_failed_total,
        expected_results_passed=expected_results_passed,
        expected_results_failed=expected_results_failed,
        expected_results_total=expected_results_total,
        output_summaries=tuple(output_summaries),
        thresholds={
            "expected_min_succeeded": config.expected_min_succeeded,
            "expected_max_failed": config.expected_max_failed,
        },
        limitations=_limitations(config),
    )
    return summary.to_dict()


def write_autonomous_browser_plan_playwright_replay_suite_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_plan_playwright_replay_suite_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _replay_captured_output(
    captured_output: str,
    *,
    repo_root: Path,
    suite: AutonomousBrowserPlanPlaywrightReplaySuiteConfig,
    replay_backend: str,
    dry_run: bool,
    allow_real_browser: bool,
    confirm_real_browser: str | None,
    output_index: int,
) -> dict[str, Any]:
    captured_output_path = _safe_relative_path(captured_output, "captured_output")
    if captured_output_path is None:
        return {
            "captured_output_path": captured_output,
            "status": "failed",
            "error_code": "unsafe_captured_output_path",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "real_network_traffic": False,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "expected_results_total": 0,
            "packet_summary": {},
            "operator_summary": {},
        }

    packet_output_dir = f"{suite.output_dir}/captured_outputs/output_{output_index + 1:02d}/packet"
    operator_output_dir = f"{suite.output_dir}/captured_outputs/output_{output_index + 1:02d}/operator"
    packet_config = {
        "schema_version": PACKET_CONFIG_SCHEMA_VERSION,
        "packet_id": f"{suite.suite_id}_packet_{output_index + 1:02d}",
        "source_output_path": captured_output_path,
        "output_dir": packet_output_dir,
        "no_runtime_execution": True,
        "limitations": list(suite.limitations),
    }
    packet_summary = build_autonomous_browser_plan_playwright_replay_packet(packet_config, repo_root=repo_root)
    packet_summary = _normalize_error_code_payload(packet_summary)
    if str(packet_summary.get("status")) != "succeeded":
        return {
            "captured_output_path": captured_output_path,
            "packet_output_dir": packet_output_dir,
            "operator_output_dir": operator_output_dir,
            "status": str(packet_summary.get("status") or "failed"),
            "error_code": packet_summary.get("error_code"),
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "real_network_traffic": False,
            "actions_attempted": _int(packet_summary.get("actions_attempted")),
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "expected_results_total": 0,
            "packet_summary": packet_summary,
            "operator_summary": {},
        }

    operator_config = {
        "schema_version": OPERATOR_CONFIG_SCHEMA_VERSION,
        "replay_backend": replay_backend,
        "replay_plan_path": f"{packet_output_dir}/playwright_replay_plan.json",
        "output_dir": operator_output_dir,
        "allowed_hosts": list(suite.allowed_hosts),
        "fixture_scope": suite.fixture_scope,
        "headless": suite.headless,
        "timeout_ms": suite.timeout_ms,
        "limitations": list(suite.limitations),
    }
    operator_summary = run_autonomous_browser_plan_playwright_replay_operator(
        operator_config,
        repo_root=repo_root,
        allow_real_browser=allow_real_browser,
        confirm_real_browser=confirm_real_browser,
        dry_run=dry_run,
        replay_backend=replay_backend,
    )
    operator_summary = _normalize_error_code_payload(operator_summary)
    return {
        "captured_output_path": captured_output_path,
        "packet_output_dir": packet_output_dir,
        "operator_output_dir": operator_output_dir,
        "status": operator_summary.get("status"),
        "error_code": operator_summary.get("error_code"),
        "no_runtime_execution": bool(operator_summary.get("no_runtime_execution", False)),
        "model_execution": False,
        "real_browser_execution": bool(operator_summary.get("real_browser_execution", False)),
        "playwright_execution": bool(operator_summary.get("playwright_execution", False)),
        "browser_opened": bool(operator_summary.get("browser_opened", False)),
        "real_network_traffic": bool(operator_summary.get("real_network_traffic", False)),
        "actions_attempted": _int(operator_summary.get("actions_attempted")),
        "actions_succeeded": _int(operator_summary.get("actions_succeeded")),
        "actions_failed": _int(operator_summary.get("actions_failed")),
        "expected_results_passed": _int(operator_summary.get("expected_results_passed")),
        "expected_results_failed": _int(operator_summary.get("expected_results_failed")),
        "expected_results_total": _int(operator_summary.get("expected_results_total")),
        "packet_summary": packet_summary,
        "operator_summary": operator_summary,
    }


def _load_json_payload(config_artifact: str | Path | Mapping[str, Any]) -> Any:
    if isinstance(config_artifact, Mapping):
        return dict(config_artifact)
    return json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))


def _config_from_mapping(payload: Mapping[str, Any]) -> AutonomousBrowserPlanPlaywrightReplaySuiteConfig:
    schema_version = str(payload.get("schema_version", "")).strip()
    suite_id = _safe_text(payload.get("suite_id"))
    replay_backend = str(payload.get("replay_backend", DEFAULT_REPLAY_BACKEND)).strip().lower() or DEFAULT_REPLAY_BACKEND
    captured_outputs_value = payload.get("captured_outputs")
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
    allowed_hosts = _safe_host_list(payload.get("allowed_hosts"))
    fixture_scope = str(payload.get("fixture_scope", "")).strip()
    headless = payload.get("headless")
    timeout_ms = payload.get("timeout_ms")
    expected_min_succeeded = payload.get("expected_min_succeeded")
    expected_max_failed = payload.get("expected_max_failed")
    limitations = tuple(
        str(item).strip()
        for item in payload.get("limitations", [])
        if isinstance(item, str) and item.strip()
    )

    if not schema_version or suite_id is None or output_dir is None or not allowed_hosts:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("suite config validation failed.")
    if schema_version != CONFIG_SCHEMA_VERSION:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("suite config schema_version must match.")
    if replay_backend not in SUPPORTED_REPLAY_BACKENDS:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("replay_backend must be fixture or playwright.")
    if fixture_scope != FIXTURE_SCOPE_LOCAL_ONLY:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("fixture_scope must be local_only.")
    if not isinstance(headless, bool) or headless is not True:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("headless must be true.")
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("timeout_ms must be a positive integer.")
    if not isinstance(expected_min_succeeded, int) or isinstance(expected_min_succeeded, bool) or expected_min_succeeded < 0:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("expected_min_succeeded must be non-negative.")
    if not isinstance(expected_max_failed, int) or isinstance(expected_max_failed, bool) or expected_max_failed < 0:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("expected_max_failed must be non-negative.")
    if not isinstance(captured_outputs_value, list) or not captured_outputs_value:
        raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError("captured_outputs must be a non-empty list.")

    captured_outputs: list[str] = []
    for index, candidate in enumerate(captured_outputs_value):
        captured_output = _safe_relative_path(candidate, f"captured_outputs[{index}]")
        if captured_output is None:
            raise AutonomousBrowserPlanPlaywrightReplaySuiteConfigError(
                f"captured_outputs[{index}] must be a safe relative path."
            )
        captured_outputs.append(captured_output)

    return AutonomousBrowserPlanPlaywrightReplaySuiteConfig(
        schema_version=schema_version,
        suite_id=suite_id,
        captured_outputs=tuple(captured_outputs),
        output_dir=output_dir,
        replay_backend=replay_backend,
        allowed_hosts=allowed_hosts,
        fixture_scope=fixture_scope,
        headless=headless,
        timeout_ms=timeout_ms,
        expected_min_succeeded=expected_min_succeeded,
        expected_max_failed=expected_max_failed,
        limitations=limitations,
    )


def _validate_config(
    config: AutonomousBrowserPlanPlaywrightReplaySuiteConfig,
    *,
    replay_backend: str,
) -> str | None:
    if replay_backend not in SUPPORTED_REPLAY_BACKENDS:
        return "unknown_replay_backend"
    if config.schema_version != CONFIG_SCHEMA_VERSION:
        return "config_validation_failed"
    if config.fixture_scope != FIXTURE_SCOPE_LOCAL_ONLY:
        return "config_validation_failed"
    if not config.headless:
        return "config_validation_failed"
    if config.timeout_ms <= 0:
        return "config_validation_failed"
    if not config.allowed_hosts:
        return "config_validation_failed"
    if not config.captured_outputs:
        return "config_validation_failed"
    if not all(host in ALLOWED_BROWSER_HOSTS for host in config.allowed_hosts):
        return "config_validation_failed"
    return None


def _resolve_replay_backend(config_backend: str, override_backend: str | None) -> str | None:
    if override_backend is not None:
        backend = _safe_backend_value(override_backend)
        if backend not in SUPPORTED_REPLAY_BACKENDS:
            return None
        return backend
    backend = _safe_backend_value(config_backend)
    if backend is None:
        return None
    if backend not in SUPPORTED_REPLAY_BACKENDS:
        return None
    return backend


def _safe_backend_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    backend = value.strip().lower()
    return backend or None


def _suite_failure(
    *,
    status: str,
    error_code: str,
    guard_status: str,
    suite_id: str | None,
    replay_backend: str | None,
    outputs_total: int,
    limitations: tuple[str, ...],
    diagnostics: Mapping[str, Any] | None = None,
    thresholds: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    summary = AutonomousBrowserPlanPlaywrightReplaySuiteSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        suite_id=suite_id,
        replay_backend=replay_backend,
        guard_status=guard_status,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        outputs_total=outputs_total,
        outputs_succeeded=0,
        outputs_failed=0,
        actions_attempted_total=0,
        actions_succeeded_total=0,
        actions_failed_total=0,
        expected_results_passed=0,
        expected_results_failed=0,
        expected_results_total=0,
        output_summaries=tuple(),
        thresholds=dict(thresholds or {"expected_min_succeeded": 0, "expected_max_failed": 0}),
        limitations=limitations,
    )
    payload = summary.to_dict()
    if diagnostics:
        payload["diagnostics"] = _jsonable(diagnostics)
    return payload


def _limitations(config: AutonomousBrowserPlanPlaywrightReplaySuiteConfig) -> tuple[str, ...]:
    base = [
        "guarded suite runner only",
        "dry-run validates without browser",
        "real browser execution is operator-only",
        "no Playwright import in dry-run or refusal",
        "local fixture-only replay scope",
        "not production browser automation",
        "validated model-plan replay only",
        "operator approval required for future real browser execution",
    ]
    for item in config.limitations:
        if item and item not in base:
            base.append(item)
    return tuple(base)


def _safe_host_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    hosts: list[str] = []
    for item in value:
        host = _safe_host(item)
        if host is None:
            return ()
        hosts.append(host)
    return tuple(hosts)


def _safe_host(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    host = value.strip().lower()
    if not host or "://" in host or "/" in host or "\\" in host or ":" in host or any(part == ".." for part in Path(host).parts):
        return None
    if host not in ALLOWED_BROWSER_HOSTS:
        return None
    return host


def _safe_relative_path(value: Any, label: str) -> str | None:
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


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _normalize_error_code_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "error_code" not in normalized and "error_d" in normalized:
        normalized["error_code"] = normalized["error_d"]
    normalized.pop("error_d", None)
    return normalized


def _load_json_payload(config_artifact: str | Path | Mapping[str, Any]) -> Any:
    if isinstance(config_artifact, Mapping):
        return dict(config_artifact)
    return json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))


class AutonomousBrowserPlanPlaywrightReplaySuiteConfigError(ValueError):
    pass
