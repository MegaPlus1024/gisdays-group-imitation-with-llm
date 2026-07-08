from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_plan_validation import ALLOWED_BROWSER_HOSTS, validate_autonomous_browser_plan
from .autonomous_browser_runtime import (
    BrowserRuntimeAction,
    BrowserRuntimeSession,
    BrowserRuntimeVerifier,
    FixtureBackedBrowserRuntimeExecutor,
)


CONFIG_SCHEMA_VERSION = "autonomous_browser_plan_playwright_replay_operator_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_plan_playwright_replay_operator_summary_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_operator"
DEFAULT_REPLAY_PLAN_PATH = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_packet/playwright_replay_plan.json"
DEFAULT_FIXTURE_MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
REQUIRED_ALLOW_FLAG = "--allow-real-browser"
REQUIRED_CONFIRM_FLAG = "--confirm-real-browser"
REQUIRED_CONFIRM_VALUE = "BROWSER_RUNTIME_OPT_IN"
FIXTURE_SCOPE_LOCAL_ONLY = "local_only"


@dataclass(frozen=True)
class AutonomousBrowserPlanPlaywrightReplayOperatorConfig:
    schema_version: str
    replay_plan_path: str
    output_dir: str
    allowed_hosts: tuple[str, ...]
    fixture_scope: str
    headless: bool
    timeout_ms: int
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "replay_plan_path": self.replay_plan_path,
            "output_dir": self.output_dir,
            "allowed_hosts": list(self.allowed_hosts),
            "fixture_scope": self.fixture_scope,
            "headless": self.headless,
            "timeout_ms": self.timeout_ms,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class AutonomousBrowserPlanPlaywrightReplayOperatorSummary:
    schema_version: str
    status: str
    error_code: str | None
    guard_status: str
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    replay_backend: str | None
    fixture_replay_execution: bool
    playwright_execution: bool
    browser_opened: bool
    real_network_traffic: bool
    replay_plan_path: str | None
    plan_id: str | None
    actions_total: int
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    expected_results_passed: int
    expected_results_failed: int
    expected_results_total: int
    output_files: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "guard_status": self.guard_status,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "replay_backend": self.replay_backend,
            "fixture_replay_execution": self.fixture_replay_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "replay_plan_path": self.replay_plan_path,
            "plan_id": self.plan_id,
            "actions_total": self.actions_total,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "expected_results_total": self.expected_results_total,
            "output_files": list(self.output_files),
            "limitations": list(self.limitations),
            "diagnostics": _jsonable(self.diagnostics),
        }


def load_autonomous_browser_plan_playwright_replay_operator_config(
    config_artifact: str | Path | Mapping[str, Any],
) -> AutonomousBrowserPlanPlaywrightReplayOperatorConfig:
    payload = _load_json_payload(config_artifact)
    if not isinstance(payload, dict):
        raise AutonomousBrowserPlanPlaywrightReplayOperatorConfigError("operator config root must be an object.")
    return _config_from_mapping(payload)


def run_autonomous_browser_plan_playwright_replay_operator(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    allow_real_browser: bool = False,
    confirm_real_browser: str | None = None,
    dry_run: bool = False,
    replay_executor: Callable[
        [Mapping[str, Any], AutonomousBrowserPlanPlaywrightReplayOperatorConfig, Path],
        dict[str, Any],
    ]
    | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    try:
        config = load_autonomous_browser_plan_playwright_replay_operator_config(config_artifact)
    except AutonomousBrowserPlanPlaywrightReplayOperatorConfigError as exc:
        return _write_summary(
            _failure_summary(
                status="failed",
                error_code="config_validation_failed",
                guard_status="config_validation_failed",
                replay_plan_path=None,
                plan_id=None,
                actions_total=0,
                output_dir=None,
                limitations=tuple(),
                replay_backend=None,
                fixture_replay_execution=False,
                playwright_execution=False,
                browser_opened=False,
                real_network_traffic=False,
                diagnostics={"config_error": str(exc)},
            ),
            repo,
        )

    config_error = _validate_config(config)
    if config_error is not None:
        return _write_summary(_config_failure_summary(config, config_error), repo)

    output_dir = repo / config.output_dir
    summary_path = output_dir / "autonomous_browser_plan_playwright_replay_operator_summary.json"
    output_files = (f"{config.output_dir}/autonomous_browser_plan_playwright_replay_operator_summary.json",)

    if dry_run:
        replay_plan_payload = _load_replay_plan(repo / config.replay_plan_path)
        if isinstance(replay_plan_payload, dict) and "normalized_plan" in replay_plan_payload and isinstance(
            replay_plan_payload["normalized_plan"], Mapping
        ):
            replay_plan = dict(replay_plan_payload["normalized_plan"])
        elif isinstance(replay_plan_payload, Mapping):
            replay_plan = dict(replay_plan_payload)
        else:
            summary = _failure_summary(
                status="failed",
                error_code="replay_plan_validation_failed",
                guard_status="dry_run",
                replay_plan_path=config.replay_plan_path,
                plan_id=None,
                actions_total=0,
                output_dir=config.output_dir,
                limitations=_limitations(config),
                output_files=output_files,
                diagnostics={"replay_plan_error": "replay plan root must be an object."},
            )
            return _write_summary(summary, repo, summary_path=summary_path)

        validation_result = validate_autonomous_browser_plan(replay_plan)
        validation_status = str(validation_result.get("status") or "rejected")
        if validation_status != "accepted":
            summary = _failure_summary(
                status="rejected",
                error_code=str(validation_result.get("error_code") or "replay_plan_validation_failed"),
                guard_status="dry_run",
                replay_plan_path=config.replay_plan_path,
                plan_id=str(validation_result.get("plan_id")) if validation_result.get("plan_id") else None,
                actions_total=_int(validation_result.get("actions_total")),
                output_dir=config.output_dir,
                limitations=_limitations(config),
                output_files=output_files,
                diagnostics={"validation": _validation_diagnostics(validation_result)},
            )
            return _write_summary(summary, repo, summary_path=summary_path)

        normalized_plan = validation_result.get("normalized_plan")
        if not isinstance(normalized_plan, Mapping):
            summary = _failure_summary(
                status="failed",
                error_code="normalized_plan_missing",
                guard_status="dry_run",
                replay_plan_path=config.replay_plan_path,
                plan_id=str(validation_result.get("plan_id")) if validation_result.get("plan_id") else None,
                actions_total=_int(validation_result.get("actions_total")),
                output_dir=config.output_dir,
                limitations=_limitations(config),
                output_files=output_files,
                diagnostics={"validation": _validation_diagnostics(validation_result)},
            )
            return _write_summary(summary, repo, summary_path=summary_path)

        summary = _dry_run_summary(
            config=config,
            replay_plan_path=config.replay_plan_path,
            validation_result=validation_result,
            output_files=output_files,
        )
        return _write_summary(summary, repo, summary_path=summary_path)

    if not allow_real_browser or confirm_real_browser != REQUIRED_CONFIRM_VALUE:
        summary = _failure_summary(
            status="refused",
            error_code="allow_real_browser_required",
            guard_status="refused",
            replay_plan_path=config.replay_plan_path,
            plan_id=None,
            actions_total=0,
            output_dir=config.output_dir,
            limitations=_limitations(config),
            output_files=output_files,
            replay_backend=None,
            fixture_replay_execution=False,
            playwright_execution=False,
            browser_opened=False,
            real_network_traffic=False,
        )
        return _write_summary(summary, repo, summary_path=summary_path)

    replay_plan_payload = _load_replay_plan(repo / config.replay_plan_path)
    if isinstance(replay_plan_payload, dict) and "normalized_plan" in replay_plan_payload and isinstance(
        replay_plan_payload["normalized_plan"], Mapping
    ):
        replay_plan = dict(replay_plan_payload["normalized_plan"])
    elif isinstance(replay_plan_payload, Mapping):
        replay_plan = dict(replay_plan_payload)
    else:
        summary = _failure_summary(
            status="failed",
            error_code="replay_plan_validation_failed",
            guard_status="guarded_replay",
            replay_plan_path=config.replay_plan_path,
            plan_id=None,
            actions_total=0,
            output_dir=config.output_dir,
            limitations=_limitations(config),
            output_files=output_files,
            diagnostics={"replay_plan_error": "replay plan root must be an object."},
        )
        return _write_summary(summary, repo, summary_path=summary_path)

    validation_result = validate_autonomous_browser_plan(replay_plan)
    validation_status = str(validation_result.get("status") or "rejected")
    if validation_status != "accepted":
        summary = _failure_summary(
            status="rejected",
            error_code=str(validation_result.get("error_code") or "replay_plan_validation_failed"),
            guard_status="guarded_replay",
            replay_plan_path=config.replay_plan_path,
            plan_id=str(validation_result.get("plan_id")) if validation_result.get("plan_id") else None,
            actions_total=_int(validation_result.get("actions_total")),
            output_dir=config.output_dir,
            limitations=_limitations(config),
            output_files=output_files,
            diagnostics={"validation": _validation_diagnostics(validation_result)},
        )
        return _write_summary(summary, repo, summary_path=summary_path)

    normalized_plan = validation_result.get("normalized_plan")
    if not isinstance(normalized_plan, Mapping):
        summary = _failure_summary(
            status="failed",
            error_code="normalized_plan_missing",
            guard_status="guarded_replay",
            replay_plan_path=config.replay_plan_path,
            plan_id=str(validation_result.get("plan_id")) if validation_result.get("plan_id") else None,
            actions_total=_int(validation_result.get("actions_total")),
            output_dir=config.output_dir,
            limitations=_limitations(config),
            output_files=output_files,
            diagnostics={"validation": _validation_diagnostics(validation_result)},
        )
        return _write_summary(summary, repo, summary_path=summary_path)

    executor = replay_executor or _default_replay_executor
    replay_result = executor(normalized_plan, config, repo)
    summary = AutonomousBrowserPlanPlaywrightReplayOperatorSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=str(replay_result.get("status") or "succeeded"),
        error_code=replay_result.get("error_code"),
        guard_status="guarded_replay",
        no_runtime_execution=bool(replay_result.get("no_runtime_execution", False)),
        model_execution=False,
        real_browser_execution=False,
        replay_backend=str(replay_result.get("replay_backend") or "fixture"),
        fixture_replay_execution=bool(replay_result.get("fixture_replay_execution", True)),
        playwright_execution=bool(replay_result.get("playwright_execution", False)),
        browser_opened=bool(replay_result.get("browser_opened", False)),
        real_network_traffic=bool(replay_result.get("real_network_traffic", False)),
        replay_plan_path=config.replay_plan_path,
        plan_id=str(validation_result.get("plan_id")) if validation_result.get("plan_id") else None,
        actions_total=_int(validation_result.get("actions_total")),
        actions_attempted=_int(replay_result.get("actions_attempted")),
        actions_succeeded=_int(replay_result.get("actions_succeeded")),
        actions_failed=_int(replay_result.get("actions_failed")),
        expected_results_passed=_int(replay_result.get("expected_results_passed")),
        expected_results_failed=_int(replay_result.get("expected_results_failed")),
        expected_results_total=_int(replay_result.get("expected_results_total")),
        output_files=output_files,
        limitations=_limitations(config),
        diagnostics=_jsonable(replay_result.get("diagnostics", {})),
    )
    return _write_summary(summary, repo, summary_path=summary_path)


def _dry_run_summary(
    *,
    config: AutonomousBrowserPlanPlaywrightReplayOperatorConfig,
    replay_plan_path: str,
    validation_result: Mapping[str, Any],
    output_files: tuple[str, ...],
) -> AutonomousBrowserPlanPlaywrightReplayOperatorSummary:
    normalized_plan = validation_result.get("normalized_plan")
    expected_total = _expected_results_total(normalized_plan if isinstance(normalized_plan, Mapping) else {})
    return AutonomousBrowserPlanPlaywrightReplayOperatorSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        guard_status="dry_run",
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        replay_backend=None,
        fixture_replay_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        replay_plan_path=replay_plan_path,
        plan_id=str(validation_result.get("plan_id")) if validation_result.get("plan_id") else None,
        actions_total=_int(validation_result.get("actions_total")),
        actions_attempted=0,
        actions_succeeded=0,
        actions_failed=0,
        expected_results_passed=0,
        expected_results_failed=0,
        expected_results_total=expected_total,
        output_files=output_files,
        limitations=_limitations(config),
        diagnostics={
            "validation": _validation_diagnostics(validation_result),
            "dry_run": True,
        },
    )


def _default_replay_executor(
    normalized_plan: Mapping[str, Any],
    config: AutonomousBrowserPlanPlaywrightReplayOperatorConfig,
    repo_root: Path,
) -> dict[str, Any]:
    manifest_path = repo_root / DEFAULT_FIXTURE_MANIFEST_PATH
    executor = FixtureBackedBrowserRuntimeExecutor(
        fixture_manifest_path=manifest_path,
        project_root=repo_root,
        allowed_url_prefixes=tuple(),
    )
    session = BrowserRuntimeSession(
        session_id="browser_plan_replay_session",
        agent_id="browser_plan_replay_operator",
        workspace_id="browser_plan_replay_workspace",
        environment_id="browser_plan_replay_environment",
        allowed_domains=tuple(config.allowed_hosts),
    )
    verifier = BrowserRuntimeVerifier()
    actions_attempted = 0
    actions_succeeded = 0
    actions_failed = 0
    expected_passed = 0
    expected_failed = 0
    expected_total = 0
    action_summaries: list[dict[str, Any]] = []

    for action in _normalized_actions(normalized_plan):
        actions_attempted += 1
        browser_action = BrowserRuntimeAction(
            agent_id="browser_plan_replay_operator",
            action_type="browser",
            action_name=str(action.get("action_name", "")),
            parameters=dict(action.get("parameters", {})) if isinstance(action.get("parameters"), Mapping) else {},
        )
        result = executor.execute(browser_action, session)
        action_summary = {
            "action_name": browser_action.action_name,
            "success": result.success,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "output": _jsonable(result.output),
        }
        if result.success:
            actions_succeeded += 1
        else:
            actions_failed += 1
        expected_text = action.get("expected_text")
        if isinstance(expected_text, str):
            expected_total += 1
            verification = verifier.verify(result, expected_text=expected_text)
            action_summary["expected_text"] = expected_text
            action_summary["verification"] = verification.to_dict()
            if verification.passed:
                expected_passed += 1
            else:
                expected_failed += 1
        action_summaries.append(action_summary)

    status = "succeeded" if actions_failed == 0 and expected_failed == 0 else "failed"
    error_code = None
    if actions_failed > 0:
        error_code = "browser_action_failed"
    elif expected_failed > 0:
        error_code = "expected_result_failed"
    return {
        "status": status,
        "error_code": error_code,
        "no_runtime_execution": False,
        "replay_backend": "fixture",
        "fixture_replay_execution": True,
        "playwright_execution": False,
        "browser_opened": False,
        "real_network_traffic": False,
        "actions_attempted": actions_attempted,
        "actions_succeeded": actions_succeeded,
        "actions_failed": actions_failed,
        "expected_results_passed": expected_passed,
        "expected_results_failed": expected_failed,
        "expected_results_total": expected_total,
        "diagnostics": {
            "replayed_actions": action_summaries,
            "fixture_manifest_path": DEFAULT_FIXTURE_MANIFEST_PATH,
            "allowed_hosts": list(config.allowed_hosts),
        },
    }


def _normalized_actions(normalized_plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    actions = normalized_plan.get("actions")
    if isinstance(actions, list):
        return [item for item in actions if isinstance(item, Mapping)]
    return []


def _expected_results_total(normalized_plan: Mapping[str, Any]) -> int:
    return sum(1 for action in _normalized_actions(normalized_plan) if isinstance(action.get("expected_text"), str))


def _validation_diagnostics(validation_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": validation_result.get("status"),
        "error_code": validation_result.get("error_code"),
        "plan_id": validation_result.get("plan_id"),
        "actions_total": validation_result.get("actions_total"),
        "diagnostics": [_safe_validation_diagnostic(item) for item in validation_result.get("diagnostics", []) if isinstance(item, Mapping)],
    }


def _safe_validation_diagnostic(item: Mapping[str, Any]) -> dict[str, Any]:
    safe_keys = ("finding_type", "path", "json_path", "key", "parameter_key", "error_code", "limit", "actions_total", "type", "status")
    return {key: _jsonable(item[key]) for key in safe_keys if key in item and item[key] is not None}


def _load_replay_plan(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError:
        return None
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, Mapping) else None


def _validate_config(config: AutonomousBrowserPlanPlaywrightReplayOperatorConfig) -> str | None:
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
    if not config.replay_plan_path or not config.output_dir:
        return "config_validation_failed"
    if not all(host in ALLOWED_BROWSER_HOSTS for host in config.allowed_hosts):
        return "config_validation_failed"
    return None


def _config_from_mapping(payload: Mapping[str, Any]) -> AutonomousBrowserPlanPlaywrightReplayOperatorConfig:
    schema_version = str(payload.get("schema_version", "")).strip()
    replay_plan_path = _safe_relative_path(payload.get("replay_plan_path"), "replay_plan_path")
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
    allowed_hosts = _safe_host_list(payload.get("allowed_hosts"))
    fixture_scope = str(payload.get("fixture_scope", "")).strip()
    headless = payload.get("headless")
    timeout_ms = payload.get("timeout_ms")
    limitations = tuple(
        str(item).strip()
        for item in payload.get("limitations", [])
        if isinstance(item, str) and item.strip()
    )

    if not schema_version or replay_plan_path is None or output_dir is None or not allowed_hosts:
        raise AutonomousBrowserPlanPlaywrightReplayOperatorConfigError("operator config validation failed.")
    if fixture_scope != FIXTURE_SCOPE_LOCAL_ONLY:
        raise AutonomousBrowserPlanPlaywrightReplayOperatorConfigError("fixture_scope must be local_only.")
    if not isinstance(headless, bool) or headless is not True:
        raise AutonomousBrowserPlanPlaywrightReplayOperatorConfigError("headless must be true.")
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
        raise AutonomousBrowserPlanPlaywrightReplayOperatorConfigError("timeout_ms must be a positive integer.")
    return AutonomousBrowserPlanPlaywrightReplayOperatorConfig(
        schema_version=schema_version,
        replay_plan_path=replay_plan_path,
        output_dir=output_dir,
        allowed_hosts=allowed_hosts,
        fixture_scope=fixture_scope,
        headless=headless,
        timeout_ms=timeout_ms,
        limitations=limitations,
    )


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


def _failure_summary(
    *,
    status: str,
    error_code: str | None,
    guard_status: str,
    replay_plan_path: str | None,
    plan_id: str | None,
    actions_total: int,
    output_dir: str | None,
    limitations: tuple[str, ...],
    output_files: tuple[str, ...] = (),
    diagnostics: Mapping[str, Any] | None = None,
    replay_backend: str | None = None,
    fixture_replay_execution: bool = False,
    playwright_execution: bool = False,
    browser_opened: bool = False,
    real_network_traffic: bool = False,
) -> AutonomousBrowserPlanPlaywrightReplayOperatorSummary:
    return AutonomousBrowserPlanPlaywrightReplayOperatorSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        guard_status=guard_status,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        replay_backend=replay_backend,
        fixture_replay_execution=fixture_replay_execution,
        playwright_execution=playwright_execution,
        browser_opened=browser_opened,
        real_network_traffic=real_network_traffic,
        replay_plan_path=replay_plan_path,
        plan_id=plan_id,
        actions_total=actions_total,
        actions_attempted=0,
        actions_succeeded=0,
        actions_failed=0,
        expected_results_passed=0,
        expected_results_failed=0,
        expected_results_total=0,
        output_files=output_files if output_files else _summary_output_files(output_dir),
        limitations=limitations,
        diagnostics=dict(diagnostics or {}),
    )


def _config_failure_summary(
    config: AutonomousBrowserPlanPlaywrightReplayOperatorConfig,
    error_code: str,
) -> AutonomousBrowserPlanPlaywrightReplayOperatorSummary:
    return _failure_summary(
        status="failed",
        error_code=error_code,
        guard_status="config_validation_failed",
        replay_plan_path=config.replay_plan_path,
        plan_id=None,
        actions_total=0,
        output_dir=config.output_dir,
        limitations=_limitations(config),
        output_files=_summary_output_files(config.output_dir),
        replay_backend=None,
        fixture_replay_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        diagnostics={"config": _jsonable(config.to_dict())},
    )


def _limitations(config: AutonomousBrowserPlanPlaywrightReplayOperatorConfig) -> tuple[str, ...]:
    base = [
        "guarded operator runner only",
        "dry-run validates without browser",
        "real browser execution is operator-only",
        "no Playwright import in dry-run or refusal",
        "local fixture-only replay scope",
        "not production browser automation",
    ]
    for item in config.limitations:
        if item and item not in base:
            base.append(item)
    return tuple(base)


def _summary_output_files(output_dir: str | None) -> tuple[str, ...]:
    if not output_dir:
        return ()
    return (f"{output_dir}/autonomous_browser_plan_playwright_replay_operator_summary.json",)


def _write_summary(
    summary: AutonomousBrowserPlanPlaywrightReplayOperatorSummary,
    repo_root: Path,
    *,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    payload = summary.to_dict()
    if summary_path is None and summary.output_files:
        summary_path = repo_root / summary.output_files[0]
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _load_json_payload(config_artifact: str | Path | Mapping[str, Any]) -> Any:
    if isinstance(config_artifact, Mapping):
        return dict(config_artifact)
    try:
        return json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise AutonomousBrowserPlanPlaywrightReplayOperatorConfigError("operator config could not be read.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomousBrowserPlanPlaywrightReplayOperatorConfigError("operator config JSON is malformed.") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


class AutonomousBrowserPlanPlaywrightReplayOperatorConfigError(ValueError):
    """Raised for operator replay config validation failures."""
