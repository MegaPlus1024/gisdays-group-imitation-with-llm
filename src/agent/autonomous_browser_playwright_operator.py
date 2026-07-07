from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .autonomous_browser_scenario_suite import (
    AutonomousBrowserScenarioSuiteValidationError,
    load_autonomous_browser_scenario_suite,
)
from .autonomous_runtime_scenarios import (
    AutonomousRuntimeScenarioValidationError,
    load_autonomous_runtime_scenario,
)


CONFIG_SCHEMA_VERSION = "playwright_operator_config_v1"
READINESS_SCHEMA_VERSION = "playwright_operator_readiness_v1"
PACKET_SCHEMA_VERSION = "playwright_operator_packet_v1"
REQUIRED_ALLOW_FLAG = "--allow-real-browser"
REQUIRED_CONFIRM_FLAG = "--confirm-real-browser"
REQUIRED_CONFIRM_VALUE = "BROWSER_RUNTIME_OPT_IN"
SUPPORTED_EXECUTION_SCOPE_MODES = frozenset({"first_scenario_only", "scenario_id", "suite"})
SUPPORTED_PLAYWRIGHT_ACTIONS = frozenset(
    {
        "browser_open_url",
        "browser_click",
        "browser_extract_text",
        "browser_fill",
        "browser_submit",
        "browser_wait",
        "browser_search",
        "browser_snapshot",
    }
)


class PlaywrightOperatorConfigError(ValueError):
    """Raised for expected Playwright operator config validation failures."""


@dataclass(frozen=True)
class PlaywrightOperatorGuard:
    allow_flag: str = REQUIRED_ALLOW_FLAG
    confirm_flag: str = REQUIRED_CONFIRM_FLAG
    confirm_value: str = REQUIRED_CONFIRM_VALUE

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PlaywrightOperatorGuard:
        return cls(
            allow_flag=str(payload.get("allow_flag", "")).strip(),
            confirm_flag=str(payload.get("confirm_flag", "")).strip(),
            confirm_value=str(payload.get("confirm_value", "")).strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "allow_flag": self.allow_flag,
            "confirm_flag": self.confirm_flag,
            "confirm_value": self.confirm_value,
        }

    def is_exact(self) -> bool:
        return (
            self.allow_flag == REQUIRED_ALLOW_FLAG
            and self.confirm_flag == REQUIRED_CONFIRM_FLAG
            and self.confirm_value == REQUIRED_CONFIRM_VALUE
        )


@dataclass(frozen=True)
class PlaywrightOperatorConfig:
    schema_version: str
    operator_id: str
    scenario_suite_path: str | None = None
    scenario_path: str | None = None
    fixture_server: dict[str, Any] = field(default_factory=dict)
    browser_backend: dict[str, Any] = field(default_factory=dict)
    output_dir: str = "artifacts/autonomous_runtime_summaries/playwright_operator"
    execution_scope: dict[str, Any] = field(default_factory=dict)
    required_guards: PlaywrightOperatorGuard = field(default_factory=PlaywrightOperatorGuard)
    no_secrets: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PlaywrightOperatorConfig:
        guards_payload = payload.get("required_guards")
        if not isinstance(guards_payload, dict):
            raise PlaywrightOperatorConfigError("required_guards must be present.")
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            operator_id=_required_id(payload.get("operator_id"), "operator_id"),
            scenario_suite_path=_optional_safe_path(payload.get("scenario_suite_path"), "scenario_suite_path"),
            scenario_path=_optional_safe_path(payload.get("scenario_path"), "scenario_path"),
            fixture_server=_dict(payload.get("fixture_server", {}), "fixture_server"),
            browser_backend=_dict(payload.get("browser_backend", {}), "browser_backend"),
            output_dir=_safe_relative_path(str(payload.get("output_dir", "")), "output_dir"),
            execution_scope=_dict(payload.get("execution_scope", {}), "execution_scope"),
            required_guards=PlaywrightOperatorGuard.from_dict(guards_payload),
            no_secrets=_bool(payload.get("no_secrets", False), "no_secrets"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operator_id": self.operator_id,
            "scenario_suite_path": self.scenario_suite_path,
            "scenario_path": self.scenario_path,
            "fixture_server": dict(self.fixture_server),
            "browser_backend": dict(self.browser_backend),
            "output_dir": self.output_dir,
            "execution_scope": dict(self.execution_scope),
            "required_guards": self.required_guards.to_dict(),
            "no_secrets": self.no_secrets,
        }


@dataclass(frozen=True)
class PlaywrightOperatorReadiness:
    ready: bool
    checks: tuple[dict[str, Any], ...]
    required_operator_guards: tuple[str, ...] = (
        REQUIRED_ALLOW_FLAG,
        f"{REQUIRED_CONFIRM_FLAG} {REQUIRED_CONFIRM_VALUE}",
    )
    no_runtime_execution: bool = True
    schema_version: str = READINESS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ready": self.ready,
            "checks": list(self.checks),
            "required_operator_guards": list(self.required_operator_guards),
            "no_runtime_execution": self.no_runtime_execution,
        }


@dataclass(frozen=True)
class PlaywrightOperatorCommand:
    name: str
    argv: str
    no_runtime_execution: bool
    requires_operator: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argv": self.argv,
            "no_runtime_execution": self.no_runtime_execution,
            "requires_operator": self.requires_operator,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class PlaywrightOperatorRunPlan:
    operator_id: str
    config_path: str
    commands: tuple[PlaywrightOperatorCommand, ...]
    no_runtime_execution: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "config_path": self.config_path,
            "commands": [command.to_dict() for command in self.commands],
            "no_runtime_execution": self.no_runtime_execution,
        }


@dataclass(frozen=True)
class PlaywrightOperatorPacket:
    packet_dir: str | None
    readiness: PlaywrightOperatorReadiness
    commands: tuple[PlaywrightOperatorCommand, ...]
    files: tuple[str, ...] = ()
    no_runtime_execution: bool = True
    schema_version: str = PACKET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_dir": self.packet_dir,
            "readiness": self.readiness.to_dict(),
            "commands": [command.to_dict() for command in self.commands],
            "files": list(self.files),
            "no_runtime_execution": self.no_runtime_execution,
        }


def load_playwright_operator_config(path: str | Path) -> PlaywrightOperatorConfig:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlaywrightOperatorConfigError("Playwright operator config JSON is malformed.") from exc
    except OSError as exc:
        raise PlaywrightOperatorConfigError("Playwright operator config could not be read.") from exc
    if not isinstance(payload, dict):
        raise PlaywrightOperatorConfigError("Playwright operator config root must be an object.")
    return PlaywrightOperatorConfig.from_dict(payload)


def validate_playwright_operator_config(
    config: PlaywrightOperatorConfig,
    *,
    repo_root: str | Path | None = None,
) -> PlaywrightOperatorReadiness:
    root = Path(repo_root) if repo_root is not None else Path(".")
    checks: list[dict[str, Any]] = []

    _add_check(checks, "schema_version", config.schema_version == CONFIG_SCHEMA_VERSION, config.schema_version)
    _add_check(checks, "no_secrets", config.no_secrets is True, "no_secrets must be true.")
    _add_check(checks, "operator_guards", config.required_guards.is_exact(), config.required_guards.to_dict())
    _validate_fixture_server(config.fixture_server, root, checks)
    _validate_browser_backend(config.browser_backend, checks)
    _add_check(checks, "output_dir_safe", _path_safe(config.output_dir), config.output_dir)
    _validate_execution_scope(config.execution_scope, checks)
    _validate_scenario_reference(config, root, checks)

    return PlaywrightOperatorReadiness(ready=all(item["passed"] for item in checks), checks=tuple(checks))


def build_playwright_operator_commands(
    config: PlaywrightOperatorConfig,
    *,
    config_path: str = "configs/autonomous_runtime/playwright_operator.example.json",
) -> list[PlaywrightOperatorCommand]:
    safe_config_path = _safe_relative_path(config_path, "config_path")
    suite_config_path = "configs/autonomous_runtime/playwright_suite_operator.example.json"
    dry_run = (
        ".\\.venv\\Scripts\\python.exe scripts/run_autonomous_browser_playwright_operator.py "
        f"--config {safe_config_path} --dry-run"
    )
    guarded = (
        ".\\.venv\\Scripts\\python.exe scripts/run_autonomous_browser_playwright_operator.py "
        f"--config {safe_config_path} {config.required_guards.allow_flag} "
        f"{config.required_guards.confirm_flag} {config.required_guards.confirm_value}"
    )
    guarded_suite = (
        ".\\.venv\\Scripts\\python.exe scripts/run_autonomous_browser_playwright_operator.py "
        f"--config {suite_config_path} {config.required_guards.allow_flag} "
        f"{config.required_guards.confirm_flag} {config.required_guards.confirm_value}"
    )
    return [
        PlaywrightOperatorCommand(
            name="readiness_dry_run",
            argv=dry_run,
            no_runtime_execution=True,
            notes=("Readiness only; no browser, server, model or Playwright import.",),
        ),
        PlaywrightOperatorCommand(
            name="operator_guarded_real_browser",
            argv=guarded,
            no_runtime_execution=False,
            requires_operator=True,
            notes=(
                "Codex must not run this command.",
                "Operator must install Playwright/Chromium separately if missing; Codex must not install dependencies.",
                "Requires explicit operator approval and local fixture server/browser readiness.",
            ),
        ),
        PlaywrightOperatorCommand(
            name="operator_guarded_suite_real_browser",
            argv=guarded_suite,
            no_runtime_execution=False,
            requires_operator=True,
            notes=(
                "Codex must not run this command.",
                "Runs bounded suite mode over local fixture-backed scenarios only.",
                "Requires explicit operator approval and local Playwright/Chromium readiness.",
            ),
        ),
    ]


def build_playwright_operator_packet(
    config: PlaywrightOperatorConfig,
    *,
    config_path: str = "configs/autonomous_runtime/playwright_operator.example.json",
    packet_output_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> PlaywrightOperatorPacket:
    readiness = validate_playwright_operator_config(config, repo_root=repo_root)
    commands = tuple(build_playwright_operator_commands(config, config_path=config_path))
    if packet_output_dir is None:
        return PlaywrightOperatorPacket(packet_dir=None, readiness=readiness, commands=commands)

    packet_dir = _validated_output_dir(packet_output_dir)
    packet_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    payloads = {
        "readiness_summary.json": readiness.to_dict(),
        "commands.json": {
            "schema_version": "playwright_operator_commands_v1",
            "operator_id": config.operator_id,
            "commands": [command.to_dict() for command in commands],
            "no_runtime_execution": True,
        },
        "operator_config.example.json": config.to_dict(),
    }
    for name, payload in payloads.items():
        path = packet_dir / name
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
        files.append(_relative_path(path))
    readme = packet_dir / "README.md"
    readme.write_text(_packet_readme(config, commands), encoding="utf-8")
    files.append(_relative_path(readme))
    return PlaywrightOperatorPacket(
        packet_dir=_relative_path(packet_dir),
        readiness=readiness,
        commands=commands,
        files=tuple(sorted(files)),
    )


def _validate_fixture_server(payload: Mapping[str, Any], root: Path, checks: list[dict[str, Any]]) -> None:
    host = str(payload.get("host", "")).strip()
    port = payload.get("port")
    fixture_root = str(payload.get("fixture_root", "")).strip()
    base_url = str(payload.get("base_url", "")).strip()
    _add_check(checks, "fixture_server_host_loopback", host == "127.0.0.1", host)
    _add_check(checks, "fixture_server_port", isinstance(port, int) and 1 <= port <= 65535, port)
    _add_check(checks, "fixture_root_safe", _path_safe(fixture_root), fixture_root)
    _add_check(checks, "fixture_root_exists", (root / fixture_root).is_dir() if _path_safe(fixture_root) else False, fixture_root)
    parsed = urlparse(base_url)
    _add_check(
        checks,
        "fixture_base_url_loopback",
        parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == port,
        base_url,
    )


def _validate_browser_backend(payload: Mapping[str, Any], checks: list[dict[str, Any]]) -> None:
    _add_check(checks, "browser_backend_type", payload.get("type") == "playwright", payload.get("type"))
    _add_check(checks, "browser_backend_name", payload.get("browser_name") == "chromium", payload.get("browser_name"))
    _add_check(checks, "browser_headless", isinstance(payload.get("headless"), bool), payload.get("headless"))
    timeout = payload.get("launch_timeout_seconds")
    _add_check(checks, "browser_timeout", isinstance(timeout, int) and timeout > 0, timeout)


def _validate_execution_scope(payload: Mapping[str, Any], checks: list[dict[str, Any]]) -> None:
    mode = payload.get("mode", "first_scenario_only")
    _add_check(checks, "execution_scope_mode", isinstance(mode, str) and mode in SUPPORTED_EXECUTION_SCOPE_MODES, mode)
    if mode == "suite":
        max_scenarios = payload.get("max_scenarios")
        max_actions = payload.get("max_browser_actions_per_scenario")
        required_actions = payload.get("required_actions")
        _add_check(checks, "execution_scope_max_scenarios", isinstance(max_scenarios, int) and 1 <= max_scenarios <= 20, max_scenarios)
        _add_check(
            checks,
            "execution_scope_max_actions_per_scenario",
            isinstance(max_actions, int) and 1 <= max_actions <= 100,
            max_actions,
        )
        _add_check(checks, "execution_scope_required_actions", _valid_required_actions(required_actions), required_actions)
        return
    if mode == "scenario_id":
        scenario_id = payload.get("scenario_id")
        _add_check(
            checks,
            "execution_scope_scenario_id",
            isinstance(scenario_id, str) and bool(scenario_id.strip()) and _safe_identifier_text(scenario_id),
            scenario_id,
        )
    max_actions = payload.get("max_browser_actions", payload.get("max_browser_actions_per_scenario", 8))
    _add_check(checks, "execution_scope_max_actions", isinstance(max_actions, int) and 1 <= max_actions <= 100, max_actions)


def _validate_scenario_reference(config: PlaywrightOperatorConfig, root: Path, checks: list[dict[str, Any]]) -> None:
    has_suite = bool(config.scenario_suite_path)
    has_scenario = bool(config.scenario_path)
    _add_check(checks, "scenario_reference_present", has_suite ^ has_scenario, "exactly one scenario_suite_path or scenario_path is required")
    if has_suite and config.scenario_suite_path:
        _add_check(checks, "scenario_suite_path_safe", _path_safe(config.scenario_suite_path), config.scenario_suite_path)
        _add_check(checks, "scenario_suite_path_exists", (root / config.scenario_suite_path).is_file(), config.scenario_suite_path)
        try:
            suite = load_autonomous_browser_scenario_suite(root / config.scenario_suite_path)
            _add_check(checks, "scenario_suite_loads", True, suite.suite_id)
            for scenario_path in suite.scenario_paths:
                _validate_browser_namespace(root / scenario_path, checks)
        except AutonomousBrowserScenarioSuiteValidationError as exc:
            _add_check(checks, "scenario_suite_loads", False, str(exc))
    if has_scenario and config.scenario_path:
        _add_check(checks, "scenario_path_safe", _path_safe(config.scenario_path), config.scenario_path)
        _add_check(checks, "scenario_path_exists", (root / config.scenario_path).is_file(), config.scenario_path)
        _validate_browser_namespace(root / config.scenario_path, checks)


def _validate_browser_namespace(path: Path, checks: list[dict[str, Any]]) -> None:
    try:
        scenario = load_autonomous_runtime_scenario(path)
    except AutonomousRuntimeScenarioValidationError as exc:
        _add_check(checks, f"scenario_loads:{path.as_posix()}", False, str(exc))
        return
    namespaces = scenario.virtual_environment.get("allowed_resource_namespaces", [])
    _add_check(
        checks,
        f"browser_namespace:{scenario.scenario_id}",
        isinstance(namespaces, list) and "browser" in namespaces,
        scenario.scenario_id,
    )


def _add_check(checks: list[dict[str, Any]], name: str, passed: bool, details: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "details": _jsonable(details)})


def _packet_readme(config: PlaywrightOperatorConfig, commands: tuple[PlaywrightOperatorCommand, ...]) -> str:
    lines = [
        "# Guarded Playwright Browser Operator Packet",
        "",
        "Codex must not run the guarded real-browser command.",
        "",
        "This packet is a readiness/operator handoff only. It does not launch Playwright, Chromium, a local HTTP server, models, Office, or an LLM judge.",
        "If Playwright or Chromium is missing, the operator must install it manually outside Codex.",
        "",
        "Required guards:",
        f"- `{config.required_guards.allow_flag}`",
        f"- `{config.required_guards.confirm_flag} {config.required_guards.confirm_value}`",
        "",
        "Commands:",
    ]
    for command in commands:
        lines.append(f"- `{command.name}`: `{command.argv}`")
    lines.append("")
    return "\n".join(lines)


def _validated_output_dir(value: str | Path) -> Path:
    normalized = _safe_relative_path(str(value), "packet_output_dir")
    if not normalized.startswith("artifacts/first_run_packets/") and not normalized.startswith("packets/"):
        raise PlaywrightOperatorConfigError("packet_output_dir must be under artifacts/first_run_packets/ or packets/.")
    return Path(normalized)


def _path_safe(value: str) -> bool:
    try:
        _safe_relative_path(value, "path")
    except PlaywrightOperatorConfigError:
        return False
    return True


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise PlaywrightOperatorConfigError(f"{label} must be non-empty.")
    if "://" in normalized or Path(value).is_absolute() or PurePosixPath(normalized).is_absolute():
        raise PlaywrightOperatorConfigError(f"{label} must be a safe relative path.")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise PlaywrightOperatorConfigError(f"{label} must not contain traversal.")
    return PurePosixPath(normalized).as_posix()


def _optional_safe_path(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlaywrightOperatorConfigError(f"{label} must be a string.")
    return _safe_relative_path(value, label)


def _required_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlaywrightOperatorConfigError(f"{label} must be a non-empty string.")
    stripped = value.strip()
    if not _safe_identifier_text(stripped):
        raise PlaywrightOperatorConfigError(f"{label} must be a safe identifier.")
    return stripped


def _safe_identifier_text(value: str) -> bool:
    return bool(value.strip()) and not any(ch in value for ch in ("\\", "/", ":", "\0"))


def _valid_required_actions(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or item not in SUPPORTED_PLAYWRIGHT_ACTIONS or item in seen:
            return False
        seen.add(item)
    return True


def _dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlaywrightOperatorConfigError(f"{label} must be an object.")
    return dict(value)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise PlaywrightOperatorConfigError(f"{label} must be a bool.")
    return value


def _relative_path(path: Path) -> str:
    return path.as_posix()


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
