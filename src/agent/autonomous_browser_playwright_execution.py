from __future__ import annotations

import json
import mimetypes
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlparse

from .autonomous_browser_scenario_suite import load_autonomous_browser_scenario_suite
from .autonomous_runtime_scenarios import (
    AutonomousRuntimeScenario,
    AutonomousRuntimeScriptedStep,
    load_autonomous_runtime_scenario,
)
from .browser_fixture_resolver import (
    BrowserFixtureResolverError,
    BrowserFixtureRouteNotFound,
    BrowserFixtureUrlDenied,
    resolve_browser_fixture_url,
)


SMOKE_SUMMARY_SCHEMA_VERSION = "autonomous_browser_playwright_smoke_summary_v1"


class PlaywrightExecutionError(ValueError):
    """Raised for static guarded Playwright execution configuration errors."""


@dataclass(frozen=True)
class PlaywrightExecutionConfig:
    operator_id: str
    scenario_suite_path: str | None
    scenario_path: str | None
    fixture_server: dict[str, Any]
    browser_backend: dict[str, Any]
    output_dir: str
    execution_scope: dict[str, Any] = field(default_factory=dict)
    repo_root: Path = Path(".")

    @classmethod
    def from_operator_config(cls, operator_config: Any, *, repo_root: str | Path | None = None) -> PlaywrightExecutionConfig:
        return cls(
            operator_id=str(operator_config.operator_id),
            scenario_suite_path=operator_config.scenario_suite_path,
            scenario_path=operator_config.scenario_path,
            fixture_server=dict(operator_config.fixture_server),
            browser_backend=dict(operator_config.browser_backend),
            output_dir=str(operator_config.output_dir),
            execution_scope=dict(getattr(operator_config, "execution_scope", {}) or {}),
            repo_root=Path(repo_root) if repo_root is not None else Path("."),
        )


@dataclass(frozen=True)
class PlaywrightExecutionResult:
    action_name: str
    logical_url: str
    served_url: str
    success: bool
    text_preview: str = ""
    artifact_ref: str | None = None
    error_code: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "logical_url": self.logical_url,
            "served_url": self.served_url,
            "success": self.success,
            "text_preview": self.text_preview,
            "artifact_ref": self.artifact_ref,
            "error_code": self.error_code,
            "diagnostics": _jsonable(self.diagnostics),
        }


@dataclass(frozen=True)
class PlaywrightExecutionSummary:
    operator_id: str
    status: str
    error_code: str | None
    fixture_server: dict[str, Any]
    browser_backend: dict[str, Any]
    scenario_scope: dict[str, Any]
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    logical_urls_visited: tuple[str, ...]
    snapshots: tuple[str, ...]
    expected_results: tuple[dict[str, Any], ...]
    duration_ms: int
    diagnostics: dict[str, Any] = field(default_factory=dict)
    no_runtime_execution: bool = False
    schema_version: str = SMOKE_SUMMARY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operator_id": self.operator_id,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "fixture_server": _jsonable(self.fixture_server),
            "browser_backend": _jsonable(self.browser_backend),
            "scenario_scope": _jsonable(self.scenario_scope),
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "logical_urls_visited": list(self.logical_urls_visited),
            "snapshots": list(self.snapshots),
            "expected_results": list(self.expected_results),
            "duration_ms": self.duration_ms,
            "diagnostics": _jsonable(self.diagnostics),
        }


class PlaywrightBackend(Protocol):
    def run_action(
        self,
        action_name: str,
        served_url: str,
        *,
        logical_url: str = "",
        expected_text: str | None = None,
    ) -> PlaywrightExecutionResult:
        ...


class RealPlaywrightBackend:
    def __init__(self, *, headless: bool = True, browser_name: str = "chromium", timeout_ms: int = 30_000) -> None:
        self.headless = headless
        self.browser_name = browser_name
        self.timeout_ms = timeout_ms
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None
        self._manager: Any | None = None

    def __enter__(self) -> RealPlaywrightBackend:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PlaywrightExecutionError("playwright_dependency_missing") from exc
        try:
            self._manager = sync_playwright().start()
            browser_launcher = getattr(self._manager, self.browser_name)
            self._browser = browser_launcher.launch(headless=self.headless)
            self._context = self._browser.new_context()
            self._context.set_default_timeout(self.timeout_ms)
            self._page = self._context.new_page()
        except Exception as exc:
            self.close()
            raise PlaywrightExecutionError("playwright_launch_failed") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb
        self.close()

    def close(self) -> None:
        for value in (self._context, self._browser):
            try:
                if value is not None:
                    value.close()
            except Exception:
                pass
        try:
            if self._manager is not None:
                self._manager.stop()
        except Exception:
            pass
        self._context = None
        self._browser = None
        self._page = None
        self._manager = None

    def run_action(
        self,
        action_name: str,
        served_url: str,
        *,
        logical_url: str = "",
        expected_text: str | None = None,
    ) -> PlaywrightExecutionResult:
        del expected_text
        if self._page is None:
            return _action_failure(action_name, logical_url, served_url, "playwright_page_not_ready")
        try:
            response: Any | None = None
            requires_navigation = action_name in {"browser_open_url", "browser_click"}
            if action_name in {"browser_open_url", "browser_click"}:
                response = self._page.goto(served_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            elif action_name == "browser_wait":
                self._page.wait_for_timeout(100)
            elif action_name in {"browser_extract_text", "browser_snapshot", "browser_search"}:
                if str(self._page.url) != served_url:
                    requires_navigation = True
                    response = self._page.goto(served_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            else:
                return _action_failure(action_name, logical_url, served_url, "unsupported_playwright_smoke_action")
            if requires_navigation and response is None:
                return _action_failure(action_name, logical_url, served_url, "browser_navigation_no_response")
            if response is not None:
                status = int(response.status)
                if status >= 400:
                    return _action_failure(
                        action_name,
                        logical_url,
                        served_url,
                        "browser_http_error",
                        diagnostics={"http_status": status, "logical_url": logical_url},
                    )
            text = str(self._page.inner_text("body", timeout=self.timeout_ms) or "")
            artifact_ref = "playwright_snapshot_placeholder" if action_name == "browser_snapshot" else None
            return PlaywrightExecutionResult(
                action_name=action_name,
                logical_url=logical_url,
                served_url=served_url,
                success=True,
                text_preview=_preview(text),
                artifact_ref=artifact_ref,
            )
        except Exception as exc:
            return _action_failure(action_name, logical_url, served_url, "playwright_action_failed", exc)


class FakePlaywrightBackend:
    def __init__(self, *, fail_with: str | None = None, http_status: int | None = None) -> None:
        self.fail_with = fail_with
        self.http_status = http_status
        self.calls: list[tuple[str, str]] = []

    def __enter__(self) -> FakePlaywrightBackend:
        if self.fail_with in {"playwright_dependency_missing", "playwright_launch_failed"}:
            raise PlaywrightExecutionError(self.fail_with)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb

    def run_action(
        self,
        action_name: str,
        served_url: str,
        *,
        logical_url: str = "",
        expected_text: str | None = None,
    ) -> PlaywrightExecutionResult:
        self.calls.append((action_name, served_url))
        if self.fail_with:
            return _action_failure(action_name, logical_url, served_url, self.fail_with)
        if self.http_status is not None and self.http_status >= 400:
            return _action_failure(
                action_name,
                logical_url,
                served_url,
                "browser_http_error",
                diagnostics={"http_status": self.http_status, "logical_url": logical_url},
            )
        return PlaywrightExecutionResult(
            action_name=action_name,
            logical_url=logical_url,
            served_url=served_url,
            success=True,
            text_preview=expected_text or "fake browser text",
            artifact_ref="browser/fake/fake-snapshot-1.json" if action_name == "browser_snapshot" else None,
        )


class LocalFixtureHttpServer:
    def __init__(self, *, host: str, port: int, fixture_root: str, base_url: str, repo_root: str | Path | None = None) -> None:
        self.host = host
        self.port = port
        self.fixture_root = _safe_relative_path(fixture_root, "fixture_root")
        self.base_url = base_url.rstrip("/")
        self.repo_root = Path(repo_root) if repo_root is not None else Path(".")
        self._server: Any | None = None
        self._thread: Any | None = None
        _validate_loopback_host(host)
        _validate_base_url(base_url, host, port)
        root = (self.repo_root / self.fixture_root).resolve()
        try:
            root.relative_to(self.repo_root.resolve())
        except ValueError as exc:
            raise PlaywrightExecutionError("fixture_root_escapes_repo") from exc
        if not root.is_dir():
            raise PlaywrightExecutionError("fixture_root_missing")
        self._resolved_root = root

    def __enter__(self) -> LocalFixtureHttpServer:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb
        self.stop()

    def start(self) -> None:
        import functools
        import http.server
        import socketserver
        import threading

        handler = functools.partial(_SafeFixtureRequestHandler, directory=str(self._resolved_root))
        self._server = socketserver.ThreadingTCPServer((self.host, self.port), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "fixture_root": self.fixture_root,
        }


class _SafeFixtureRequestHandler:
    def __new__(cls, *args: Any, directory: str, **kwargs: Any) -> Any:
        import http.server
        from urllib.parse import unquote, urlparse

        root = Path(directory).resolve()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = unquote(parsed.path or "/").lstrip("/")
                if not path or path.endswith("/"):
                    path = f"{path}index.html".lstrip("/")
                target = (root / path).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    self.send_error(404)
                    return
                if not target.is_file():
                    self.send_error(404)
                    return
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if content_type not in {
                    "text/html",
                    "text/css",
                    "text/javascript",
                    "application/javascript",
                    "application/json",
                    "text/plain",
                }:
                    self.send_error(403)
                    return
                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

        return Handler(*args, **kwargs)


def run_guarded_playwright_smoke(
    config: PlaywrightExecutionConfig,
    *,
    backend: Any | None = None,
    server: Any | None = None,
) -> PlaywrightExecutionSummary:
    started = time.perf_counter()
    try:
        scenario = _select_scenario(config)
        steps = _selected_steps(scenario, config)
        if not steps:
            return _summary(config, "failed", "no_supported_browser_steps", started, [], [], scenario)
        server_obj = server or LocalFixtureHttpServer(repo_root=config.repo_root, **config.fixture_server)
        backend_obj = backend or _real_backend_from_config(config.browser_backend)
        with server_obj as running_server:
            mapper = FixtureUrlMapper(
                manifest_path=_fixture_manifest_path(scenario),
                server_base_url=running_server.to_summary()["base_url"],
                repo_root=config.repo_root,
            )
            with backend_obj as running_backend:
                results: list[PlaywrightExecutionResult] = []
                expected: list[dict[str, Any]] = []
                for step in steps:
                    logical_url = _logical_url_for_step(step, results)
                    try:
                        served_url = mapper.map_logical_url(logical_url)
                    except PlaywrightExecutionError as exc:
                        result = _action_failure(step.action_name, logical_url, "", _safe_error_code(str(exc)))
                        results.append(result)
                        expected.append({"step_id": step.step_id, "expected_text": step.expected_text, "passed": False})
                        break
                    result = running_backend.run_action(
                        step.action_name,
                        served_url,
                        logical_url=logical_url,
                        expected_text=step.expected_text,
                    )
                    result = PlaywrightExecutionResult(
                        action_name=result.action_name,
                        logical_url=logical_url,
                        served_url=served_url,
                        success=result.success,
                        text_preview=result.text_preview,
                        artifact_ref=result.artifact_ref,
                        error_code=result.error_code,
                        diagnostics=result.diagnostics,
                    )
                    results.append(result)
                    expected.append(
                        {
                            "step_id": step.step_id,
                            "expected_text": step.expected_text,
                            "passed": bool(result.success and (not step.expected_text or step.expected_text in result.text_preview)),
                        }
                    )
                    if not result.success:
                        break
        status = "succeeded" if results and all(result.success for result in results) and all(item["passed"] for item in expected) else "failed"
        error_code = None if status == "succeeded" else _first_error(results, expected)
        return _summary(config, status, error_code, started, results, expected, scenario)
    except PlaywrightExecutionError as exc:
        code = _safe_error_code(str(exc))
        return _summary(config, "failed", code, started, [], [], None, diagnostics={"exception_type": exc.__class__.__name__})


class FixtureUrlMapper:
    def __init__(self, *, manifest_path: str, server_base_url: str, repo_root: str | Path | None = None) -> None:
        self.manifest_path = manifest_path
        self.server_base_url = server_base_url.rstrip("/")
        self.repo_root = Path(repo_root) if repo_root is not None else Path(".")

    def map_logical_url(self, logical_url: str) -> str:
        parsed = urlparse(logical_url)
        if (parsed.hostname or "").lower() not in {"local.intranet", "docs.local", "portal.local", "local-intranet.test"}:
            raise PlaywrightExecutionError("unknown_logical_domain")
        route = _route_from_parsed_url(parsed)
        prefixed_route = _domain_prefixed_route(parsed.hostname or "", route)
        if prefixed_route != route:
            prefixed_path = self._fixture_path_from_manifest_route(prefixed_route)
            if prefixed_path is not None:
                return self._served_url_for_fixture_path(prefixed_path)
        try:
            resolution = resolve_browser_fixture_url(
                logical_url,
                self.manifest_path,
                project_root=self.repo_root,
            )
            return self._served_url_for_fixture_path(resolution.fixture_path_relative)
        except BrowserFixtureRouteNotFound:
            pass
        except BrowserFixtureUrlDenied as exc:
            raise PlaywrightExecutionError("logical_url_mapping_failed") from exc
        except BrowserFixtureResolverError as exc:
            raise PlaywrightExecutionError("logical_url_mapping_failed") from exc
        fallback = self._fallback_fixture_path(parsed)
        if fallback is None:
            raise PlaywrightExecutionError("fixture_mapping_not_found")
        return self._served_url_for_fixture_path(fallback)

    def _fallback_fixture_path(self, parsed_url: Any) -> str | None:
        route = _route_from_parsed_url(parsed_url)
        route_candidates = [route]
        prefixed = _domain_prefixed_route(parsed_url.hostname or "", route)
        if prefixed not in route_candidates:
            route_candidates.append(prefixed)
        for candidate_route in route_candidates:
            manifest_path = self._fixture_path_from_manifest_route(candidate_route)
            if manifest_path is not None:
                return manifest_path
        root = self._fixture_root()
        for candidate_route in route_candidates:
            for relative_path in _candidate_fixture_paths(candidate_route):
                if _safe_fixture_file_exists(root, relative_path):
                    return relative_path
        return None

    def _fixture_path_from_manifest_route(self, route: str) -> str | None:
        routes = self._manifest_payload().get("routes", {})
        if not isinstance(routes, dict):
            raise PlaywrightExecutionError("fixture_manifest_routes_invalid")
        route_path = routes.get(route)
        if not isinstance(route_path, str):
            return None
        relative_path = _safe_fixture_relative_path(route_path)
        if _safe_fixture_file_exists(self._fixture_root(), relative_path):
            return relative_path
        return None

    def _served_url_for_fixture_path(self, relative_path: str) -> str:
        safe_path = _safe_fixture_relative_path(relative_path)
        return f"{self.server_base_url}/{quote(safe_path, safe='/._~-')}"

    def _manifest_payload(self) -> dict[str, Any]:
        path = Path(self.manifest_path)
        if not path.is_absolute():
            path = self.repo_root / path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PlaywrightExecutionError("fixture_manifest_unreadable") from exc
        except json.JSONDecodeError as exc:
            raise PlaywrightExecutionError("fixture_manifest_malformed") from exc
        if not isinstance(payload, dict):
            raise PlaywrightExecutionError("fixture_manifest_invalid")
        return payload

    def _fixture_root(self) -> Path:
        path = Path(self.manifest_path)
        if not path.is_absolute():
            path = self.repo_root / path
        root_value = self._manifest_payload().get("fixture_root", ".")
        relative_root = _safe_fixture_relative_path(str(root_value))
        root = (path.parent / relative_root).resolve()
        try:
            root.relative_to(path.parent.resolve())
        except ValueError as exc:
            raise PlaywrightExecutionError("fixture_root_escapes_manifest") from exc
        return root


def _select_scenario(config: PlaywrightExecutionConfig) -> AutonomousRuntimeScenario:
    if config.scenario_path:
        return load_autonomous_runtime_scenario(config.repo_root / config.scenario_path)
    if not config.scenario_suite_path:
        raise PlaywrightExecutionError("scenario_reference_missing")
    suite = load_autonomous_browser_scenario_suite(config.repo_root / config.scenario_suite_path)
    if not suite.scenario_paths:
        raise PlaywrightExecutionError("scenario_suite_empty")
    return load_autonomous_runtime_scenario(config.repo_root / suite.scenario_paths[0])


def _selected_steps(scenario: AutonomousRuntimeScenario, config: PlaywrightExecutionConfig) -> tuple[AutonomousRuntimeScriptedStep, ...]:
    max_actions = int(config.execution_scope.get("max_browser_actions", 8))
    supported = {"browser_open_url", "browser_click", "browser_extract_text", "browser_wait", "browser_snapshot", "browser_search"}
    return tuple(step for step in scenario.scripted_steps if step.action_name in supported)[:max_actions]


def _logical_url_for_step(step: AutonomousRuntimeScriptedStep, previous: list[PlaywrightExecutionResult]) -> str:
    for key in ("url", "target_url", "href", "success_url"):
        value = step.parameters.get(key)
        if isinstance(value, str) and value.strip():
            if value.startswith("/"):
                base = previous[-1].logical_url if previous else "https://local.intranet/"
                parsed = urlparse(base)
                return f"{parsed.scheme}://{parsed.netloc}{value}"
            return value.strip()
    if previous:
        return previous[-1].logical_url
    return "https://local.intranet/"


def _fixture_manifest_path(scenario: AutonomousRuntimeScenario) -> str:
    if not scenario.browser_sessions:
        raise PlaywrightExecutionError("browser_session_missing")
    return scenario.browser_sessions[0].fixture_manifest_path


def _real_backend_from_config(payload: Mapping[str, Any]) -> RealPlaywrightBackend:
    timeout_seconds = int(payload.get("launch_timeout_seconds", 30))
    return RealPlaywrightBackend(
        headless=bool(payload.get("headless", True)),
        browser_name=str(payload.get("browser_name", "chromium")),
        timeout_ms=timeout_seconds * 1000,
    )


def _route_from_parsed_url(parsed_url: Any) -> str:
    decoded = unquote(parsed_url.path or "/")
    if not decoded.startswith("/"):
        decoded = f"/{decoded}"
    if "\\" in decoded:
        raise PlaywrightExecutionError("fixture_mapping_path_unsafe")
    parts = PurePosixPath(decoded).parts
    if any(part == ".." for part in parts):
        raise PlaywrightExecutionError("fixture_mapping_path_unsafe")
    route = PurePosixPath(decoded).as_posix()
    return "/" if route in {"", "."} else route


def _domain_prefixed_route(hostname: str, route: str) -> str:
    prefix_by_host = {
        "docs.local": "docs",
        "portal.local": "portal",
    }
    prefix = prefix_by_host.get(hostname.lower())
    if not prefix:
        return route
    clean = route.lstrip("/")
    if not clean:
        return f"/{prefix}"
    if clean == prefix or clean.startswith(f"{prefix}/"):
        return route
    return f"/{prefix}/{clean}"


def _candidate_fixture_paths(route: str) -> tuple[str, ...]:
    clean = route.lstrip("/")
    if not clean:
        return ("index.html",)
    candidates = [clean]
    if not clean.endswith(".html"):
        candidates.append(f"{clean}.html")
    candidates.append(f"{clean.rstrip('/')}/index.html")
    return tuple(dict.fromkeys(_safe_fixture_relative_path(candidate) for candidate in candidates))


def _safe_fixture_file_exists(root: Path, relative_path: str) -> bool:
    safe_path = _safe_fixture_relative_path(relative_path)
    resolved = (root / safe_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return False
    return resolved.is_file()


def _summary(
    config: PlaywrightExecutionConfig,
    status: str,
    error_code: str | None,
    started: float,
    results: list[PlaywrightExecutionResult],
    expected: list[dict[str, Any]],
    scenario: AutonomousRuntimeScenario | None,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> PlaywrightExecutionSummary:
    snapshots = tuple(ref for ref in (result.artifact_ref for result in results) if ref)
    actions_failed = sum(1 for result in results if not result.success)
    return PlaywrightExecutionSummary(
        operator_id=config.operator_id,
        status=status,
        error_code=error_code,
        fixture_server={
            "host": str(config.fixture_server.get("host", "")),
            "port": config.fixture_server.get("port"),
            "base_url": str(config.fixture_server.get("base_url", "")),
            "fixture_root": str(config.fixture_server.get("fixture_root", "")),
        },
        browser_backend={
            "type": str(config.browser_backend.get("type", "")),
            "browser_name": str(config.browser_backend.get("browser_name", "")),
            "headless": bool(config.browser_backend.get("headless", True)),
        },
        scenario_scope={
            "mode": str(config.execution_scope.get("mode", "first_scenario_only")),
            "max_browser_actions": int(config.execution_scope.get("max_browser_actions", 8)),
            "scenario_id": scenario.scenario_id if scenario else None,
        },
        actions_attempted=len(results),
        actions_succeeded=sum(1 for result in results if result.success),
        actions_failed=actions_failed,
        logical_urls_visited=tuple(dict.fromkeys(result.logical_url for result in results if result.logical_url)),
        snapshots=snapshots,
        expected_results=tuple(expected),
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        diagnostics=_sanitize_diagnostics(diagnostics or {"actions": [result.to_dict() for result in results]}),
    )


def _action_failure(
    action_name: str,
    logical_url: str,
    served_url: str,
    error_code: str,
    exc: Exception | None = None,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> PlaywrightExecutionResult:
    out_diagnostics = dict(diagnostics or {})
    if exc is not None:
        out_diagnostics["exception_type"] = exc.__class__.__name__
    if exc is not None:
        out_diagnostics["safe_message"] = _safe_error_code(str(exc))[:160]
    return PlaywrightExecutionResult(
        action_name=action_name,
        logical_url=logical_url,
        served_url=served_url,
        success=False,
        error_code=error_code,
        diagnostics=out_diagnostics,
    )


def _first_error(results: list[PlaywrightExecutionResult], expected: list[dict[str, Any]]) -> str:
    for result in results:
        if not result.success:
            return "browser_action_failed"
    for item in expected:
        if item.get("passed") is not True:
            return "expected_result_failed"
    return "playwright_smoke_failed"


def _validate_loopback_host(host: str) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise PlaywrightExecutionError("fixture_server_host_not_loopback")


def _validate_base_url(base_url: str, host: str, port: int) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname != host or parsed.port != port:
        raise PlaywrightExecutionError("fixture_server_base_url_mismatch")


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized or "://" in normalized or Path(value).is_absolute() or PurePosixPath(normalized).is_absolute():
        raise PlaywrightExecutionError(f"{label}_unsafe")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise PlaywrightExecutionError(f"{label}_unsafe")
    return PurePosixPath(normalized).as_posix()


def _safe_fixture_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized or "://" in normalized or Path(value).is_absolute() or PurePosixPath(normalized).is_absolute():
        raise PlaywrightExecutionError("fixture_path_unsafe")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise PlaywrightExecutionError("fixture_path_unsafe")
    return PurePosixPath(normalized).as_posix()


def _preview(text: str, limit: int = 500) -> str:
    normalized = " ".join(str(text).split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 3]}..."


def _safe_error_code(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip().lower())
    return safe.strip("_") or "playwright_execution_failed"


def _sanitize_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    import re

    def sanitize_item(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(key): sanitize_item(child) for key, child in item.items()}
        if isinstance(item, list):
            return [sanitize_item(child) for child in item]
        if isinstance(item, tuple):
            return [sanitize_item(child) for child in item]
        if isinstance(item, str):
            if item.startswith(("http://", "https://")):
                return item
            sanitized = re.sub(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", item)
            sanitized = re.sub(r"(?<!\w)/(?:Users|home|tmp|var|etc|mnt|private)/[^\s\"']+", "<absolute_path>", sanitized)
            return sanitized
        return item

    return json.loads(json.dumps(sanitize_item(value), ensure_ascii=True, default=str))


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
