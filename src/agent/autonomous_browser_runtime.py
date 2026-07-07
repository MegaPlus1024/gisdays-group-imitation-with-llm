from __future__ import annotations

import json
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlparse

from .autonomous_multi_agent_runtime import (
    RuntimeActionDecision,
    RuntimeActionResult,
    RuntimeSharedState,
)
from .browser_fixture_resolver import (
    BrowserFixtureResolverError,
    resolve_browser_fixture_url,
)
from .scripts.browser_playwright_activity import (
    PlaywrightBrowserActivityConfig,
    run_playwright_browser_activity,
)


BROWSER_RUNTIME_ACTION_NAMES = frozenset(
    {
        "browser_open_url",
        "browser_search",
        "browser_click",
        "browser_extract_text",
        "browser_fill",
        "browser_submit",
        "browser_wait",
        "browser_snapshot",
    }
)

DEFAULT_FIXTURE_DOMAINS = (
    "localhost",
    "127.0.0.1",
    "local-intranet.test",
    "local.intranet",
    "docs.local",
    "portal.local",
)


@dataclass(frozen=True)
class BrowserRuntimePolicy:
    allowed_action_names: tuple[str, ...] = tuple(sorted(BROWSER_RUNTIME_ACTION_NAMES))
    allowed_schemes: tuple[str, ...] = ("http", "https")
    allow_file_urls: bool = False
    allow_javascript_urls: bool = False
    allow_data_urls: bool = False
    fixture_mode: bool = True
    max_text_chars: int = 2_000
    max_search_results: int = 5
    max_snapshot_count: int = 50
    require_browser_namespace: bool = True
    playwright_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_action_names:
            raise ValueError("allowed_action_names must not be empty.")
        if not self.allowed_schemes:
            raise ValueError("allowed_schemes must not be empty.")
        for field_name in ("max_text_chars", "max_search_results", "max_snapshot_count"):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be > 0.")

    def to_flags(self) -> dict[str, Any]:
        return {
            "allowed_action_names": list(self.allowed_action_names),
            "allowed_schemes": list(self.allowed_schemes),
            "allow_file_urls": self.allow_file_urls,
            "allow_javascript_urls": self.allow_javascript_urls,
            "allow_data_urls": self.allow_data_urls,
            "fixture_mode": self.fixture_mode,
            "max_text_chars": self.max_text_chars,
            "max_search_results": self.max_search_results,
            "max_snapshot_count": self.max_snapshot_count,
            "require_browser_namespace": self.require_browser_namespace,
            "playwright_enabled": self.playwright_enabled,
        }


@dataclass
class BrowserRuntimeObservation:
    action_name: str
    current_url: str | None = None
    title: str | None = None
    text_preview: str = ""
    snapshot_id: str | None = None
    artifact_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "current_url": self.current_url,
            "title": self.title,
            "text_preview": self.text_preview,
            "snapshot_id": self.snapshot_id,
            "artifact_refs": list(self.artifact_refs),
            "metadata": _jsonable(self.metadata),
        }


@dataclass
class BrowserRuntimeSession:
    session_id: str
    agent_id: str
    workspace_id: str
    environment_id: str
    allowed_domains: tuple[str, ...] = DEFAULT_FIXTURE_DOMAINS
    start_url: str | None = None
    current_url: str | None = None
    visited_urls: list[str] = field(default_factory=list)
    snapshots: list[BrowserRuntimeObservation] = field(default_factory=list)
    last_observation: BrowserRuntimeObservation | None = None
    policy_flags: dict[str, Any] = field(default_factory=dict)
    form_state: dict[str, dict[str, str]] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    actions_attempted: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0
    policy_denials: int = 0

    def __post_init__(self) -> None:
        self.session_id = _safe_id(self.session_id, "session_id")
        self.agent_id = _safe_id(self.agent_id, "agent_id")
        self.workspace_id = _safe_id(self.workspace_id, "workspace_id")
        self.environment_id = _safe_id(self.environment_id, "environment_id")
        self.allowed_domains = tuple(_safe_domain(domain) for domain in self.allowed_domains)
        if self.start_url and self.current_url is None:
            self.current_url = self.start_url.strip()
        if self.current_url and not self.visited_urls:
            self.visited_urls.append(self.current_url)

    def record_observation(self, observation: BrowserRuntimeObservation, *, snapshot: bool = False) -> None:
        self.last_observation = observation
        if observation.current_url:
            self.current_url = observation.current_url
            if observation.current_url not in self.visited_urls:
                self.visited_urls.append(observation.current_url)
        for ref in observation.artifact_refs:
            if ref not in self.artifacts:
                self.artifacts.append(ref)
        if snapshot:
            self.snapshots.append(observation)

    def to_summary(self) -> dict[str, Any]:
        return {
            "schema_version": "autonomous_browser_runtime_summary_v1",
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "environment_id": self.environment_id,
            "allowed_domains": list(self.allowed_domains),
            "start_url": self.start_url,
            "current_url": self.current_url,
            "visited_url_count": len(self.visited_urls),
            "visited_urls": list(self.visited_urls),
            "snapshot_count": len(self.snapshots),
            "last_observation": self.last_observation.to_dict() if self.last_observation else None,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "policy_denials": self.policy_denials,
            "artifacts": list(self.artifacts),
            "policy_flags": _jsonable(self.policy_flags),
        }


@dataclass(frozen=True)
class BrowserRuntimeAction:
    agent_id: str
    action_type: str
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserRuntimeResult:
    success: bool
    output: Any | None = None
    observation: BrowserRuntimeObservation | None = None
    error_type: str | None = None
    error_message: str | None = None
    artifact_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": _jsonable(self.output),
            "observation": self.observation.to_dict() if self.observation else None,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "artifact_refs": list(self.artifact_refs),
            "metadata": _jsonable(self.metadata),
        }


@dataclass(frozen=True)
class BrowserRuntimeVerification:
    passed: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "metadata": _jsonable(self.metadata),
        }


class BrowserRuntimeVerifier:
    def verify(
        self,
        result: BrowserRuntimeResult,
        *,
        expected_text: str | None = None,
        expected_url: str | None = None,
        required_artifact: str | None = None,
    ) -> BrowserRuntimeVerification:
        if not result.success:
            return BrowserRuntimeVerification(False, result.error_type or "browser_action_failed")
        observation = result.observation
        text = observation.text_preview if observation else ""
        current_url = observation.current_url if observation else None
        artifacts = set(result.artifact_refs)

        if expected_text is not None and expected_text not in text:
            return BrowserRuntimeVerification(
                False,
                "expected_text_missing",
                {"expected_text": expected_text},
            )
        if expected_url is not None and current_url != expected_url:
            return BrowserRuntimeVerification(
                False,
                "expected_url_mismatch",
                {"expected_url": expected_url, "current_url": current_url},
            )
        if required_artifact is not None and required_artifact not in artifacts:
            return BrowserRuntimeVerification(
                False,
                "required_artifact_missing",
                {"required_artifact": required_artifact},
            )
        return BrowserRuntimeVerification(True, "browser_expectations_met")


class BrowserRuntimeAdapter:
    def __init__(self, policy: BrowserRuntimePolicy | None = None) -> None:
        self.policy = policy or BrowserRuntimePolicy()

    def from_decision(self, decision: RuntimeActionDecision) -> BrowserRuntimeAction:
        params = dict(decision.parameters)
        raw_session_id = params.pop("session_id", None) or decision.metadata.get("browser_session_id")
        session_id = str(raw_session_id).strip() if raw_session_id is not None else None
        return BrowserRuntimeAction(
            agent_id=decision.agent_id,
            action_type=decision.action_type,
            action_name=decision.action_name,
            parameters=params,
            session_id=session_id,
            task_id=decision.task_id,
            metadata=dict(decision.metadata),
        )

    def validate_namespace(self, namespaces: tuple[str, ...] | list[str] | set[str]) -> BrowserRuntimeResult | None:
        if self.policy.require_browser_namespace and "browser" not in set(namespaces):
            return _failure(
                "browser_namespace_disabled",
                "Browser runtime namespace is not enabled for this virtual environment.",
            )
        return None


class FixtureBackedBrowserRuntimeExecutor:
    def __init__(
        self,
        *,
        fixture_manifest_path: str | Path,
        project_root: str | Path = ".",
        policy: BrowserRuntimePolicy | None = None,
        allowed_url_prefixes: tuple[str, ...] | list[str] = (),
    ) -> None:
        self.fixture_manifest_path = fixture_manifest_path
        self.project_root = Path(project_root).resolve()
        self.policy = policy or BrowserRuntimePolicy()
        self.allowed_url_prefixes = tuple(str(prefix) for prefix in allowed_url_prefixes)

    def execute(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        session.actions_attempted += 1
        validation_error = self._validate_action(action, session)
        if validation_error is not None:
            return self._record_failure(session, validation_error, policy_denial=True)

        try:
            if action.action_name == "browser_open_url":
                result = self._open_url(action, session)
            elif action.action_name == "browser_extract_text":
                result = self._extract_text(action, session)
            elif action.action_name == "browser_click":
                result = self._click(action, session)
            elif action.action_name == "browser_search":
                result = self._search(action, session)
            elif action.action_name == "browser_snapshot":
                result = self._snapshot(action, session)
            elif action.action_name == "browser_fill":
                result = self._fill(action, session)
            elif action.action_name == "browser_submit":
                result = self._submit(action, session)
            elif action.action_name == "browser_wait":
                result = self._wait(action, session)
            else:
                result = _failure(
                    "unknown_browser_action",
                    f"Unknown browser runtime action: {action.action_name}",
                )
        except BrowserFixtureResolverError as exc:
            result = _failure("fixture_resolution_failed", str(exc))
        except Exception as exc:  # noqa: BLE001 - executor failures are runtime data.
            result = _failure("browser_runtime_executor_error", exc.__class__.__name__)

        if result.success:
            session.actions_succeeded += 1
            if result.observation:
                session.record_observation(
                    result.observation,
                    snapshot=action.action_name == "browser_snapshot",
                )
            return result
        return self._record_failure(session, result, policy_denial=False)

    def _record_failure(
        self,
        session: BrowserRuntimeSession,
        result: BrowserRuntimeResult,
        *,
        policy_denial: bool,
    ) -> BrowserRuntimeResult:
        session.actions_failed += 1
        if policy_denial:
            session.policy_denials += 1
        return result

    def _validate_action(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult | None:
        if action.action_type != "browser":
            return _failure("invalid_browser_action_type", "Browser runtime actions require action_type='browser'.")
        if action.action_name not in self.policy.allowed_action_names:
            return _failure("unknown_browser_action", f"Browser action is not allowlisted: {action.action_name}")
        missing = _missing_required_parameter(action)
        if missing:
            return _failure("missing_required_parameter", f"Missing required parameter: {missing}")
        url = _action_url(action, session)
        if url is not None:
            return self._validate_url(url, session)
        return None

    def _validate_url(self, url: str, session: BrowserRuntimeSession) -> BrowserRuntimeResult | None:
        parsed = urlparse(url.strip()) if isinstance(url, str) else urlparse("")
        scheme = (parsed.scheme or "").lower()
        if not scheme:
            return _failure("browser_url_scheme_required", "Browser URL scheme is required.")
        if scheme == "file" and not self.policy.allow_file_urls:
            return _failure("browser_url_denied", "file:// URLs are not allowed.")
        if scheme == "javascript" and not self.policy.allow_javascript_urls:
            return _failure("browser_url_denied", "javascript: URLs are not allowed.")
        if scheme == "data" and not self.policy.allow_data_urls:
            return _failure("browser_url_denied", "data: URLs are not allowed.")
        if scheme not in self.policy.allowed_schemes:
            return _failure("browser_url_denied", f"Browser URL scheme is not allowed: {scheme}")
        if parsed.username or parsed.password:
            return _failure("browser_url_denied", "Credential URLs are not allowed.")
        host = (parsed.hostname or "").lower()
        if not host:
            return _failure("browser_domain_denied", "Browser URL host is required.")
        if not _host_allowed(host, session.allowed_domains):
            return _failure("browser_domain_denied", "Browser URL domain is outside the session policy.")
        if not self.policy.fixture_mode:
            return _failure("browser_fixture_mode_required", "Fixture-backed executor requires fixture_mode=True.")
        return None

    def _open_url(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        url = str(action.parameters["url"]).strip()
        observation = self._observation_from_url(action.action_name, url, session)
        return BrowserRuntimeResult(
            success=True,
            output=observation.to_dict(),
            observation=observation,
            artifact_refs=observation.artifact_refs,
            metadata={"network_used": False, "browser_opened": False, "fixture_mode": True},
        )

    def _extract_text(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        url = str(action.parameters.get("url") or session.current_url or "").strip()
        observation = self._observation_from_url(action.action_name, url, session)
        return BrowserRuntimeResult(
            success=True,
            output=observation.text_preview,
            observation=observation,
            artifact_refs=observation.artifact_refs,
            metadata={"text_char_count": len(observation.text_preview), "network_used": False},
        )

    def _click(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        current_url = str(action.parameters.get("url") or session.current_url or "").strip()
        if not current_url:
            return _failure("browser_current_url_required", "browser_click requires a current URL or url parameter.")
        resolution = self._resolve(current_url, session)
        links = _extract_links(resolution.fixture_path.read_text(encoding="utf-8"))
        target_url = self._click_target_url(action, current_url, links)
        if target_url is None:
            return _failure("browser_click_target_not_found", "Fixture click target was not found.")
        denial = self._validate_url(target_url, session)
        if denial is not None:
            return denial
        observation = self._observation_from_url(action.action_name, target_url, session)
        return BrowserRuntimeResult(
            success=True,
            output=observation.to_dict(),
            observation=observation,
            artifact_refs=observation.artifact_refs,
            metadata={"clicked_url": target_url, "network_used": False},
        )

    def _search(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        query = str(action.parameters["query"]).strip()
        results = self._search_fixture_pages(query, session)
        observation = BrowserRuntimeObservation(
            action_name=action.action_name,
            current_url=session.current_url,
            title="Fixture search results",
            text_preview=f"{len(results)} fixture-backed result(s) for: {query}",
            metadata={"query": query, "results": results, "network_used": False},
        )
        return BrowserRuntimeResult(
            success=True,
            output={"query": query, "results": results},
            observation=observation,
            metadata={"network_used": False, "result_count": len(results)},
        )

    def _snapshot(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        url = str(action.parameters.get("url") or session.current_url or "").strip()
        if not url:
            return _failure("browser_current_url_required", "browser_snapshot requires a current URL or url parameter.")
        base = self._observation_from_url(action.action_name, url, session)
        snapshot_id = f"{session.session_id}-snapshot-{len(session.snapshots) + 1}"
        artifact_ref = f"browser/{session.session_id}/{snapshot_id}.json"
        observation = BrowserRuntimeObservation(
            action_name=action.action_name,
            current_url=base.current_url,
            title=base.title,
            text_preview=base.text_preview,
            snapshot_id=snapshot_id,
            artifact_refs=(artifact_ref,),
            metadata={**base.metadata, "snapshot_index": len(session.snapshots) + 1},
        )
        return BrowserRuntimeResult(
            success=True,
            output=observation.to_dict(),
            observation=observation,
            artifact_refs=observation.artifact_refs,
            metadata={"network_used": False, "snapshot_id": snapshot_id},
        )

    def _fill(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        fields = action.parameters["fields"]
        target = str(action.parameters.get("form_id") or session.current_url or "default_form")
        if not isinstance(fields, Mapping):
            return _failure("invalid_parameter", "browser_fill fields must be an object.")
        normalized_fields: dict[str, str] = {}
        for key, value in fields.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return _failure("invalid_parameter", "browser_fill field names and values must be strings.")
            normalized_fields[key] = value
        session.form_state.setdefault(target, {}).update(normalized_fields)
        observation = BrowserRuntimeObservation(
            action_name=action.action_name,
            current_url=session.current_url,
            title="Synthetic form state updated",
            text_preview=f"Updated {len(normalized_fields)} fixture form field(s).",
            metadata={"form_id": target, "field_names": sorted(normalized_fields), "submitted": False},
        )
        return BrowserRuntimeResult(
            success=True,
            output={"form_id": target, "field_count": len(normalized_fields)},
            observation=observation,
            metadata={"network_used": False, "submitted": False},
        )

    def _submit(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        target = str(action.parameters.get("form_id") or session.current_url or "default_form")
        form = session.form_state.setdefault(target, {})
        form["_submitted"] = "true"
        observation = BrowserRuntimeObservation(
            action_name=action.action_name,
            current_url=session.current_url,
            title="Synthetic form submitted",
            text_preview="Fixture form submission recorded locally.",
            metadata={"form_id": target, "submitted": True, "field_count": len(form)},
        )
        return BrowserRuntimeResult(
            success=True,
            output={"form_id": target, "submitted": True},
            observation=observation,
            metadata={"network_used": False, "submitted": True},
        )

    def _wait(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        milliseconds = action.parameters.get("milliseconds", action.parameters.get("ms", 0))
        observation = BrowserRuntimeObservation(
            action_name=action.action_name,
            current_url=session.current_url,
            title="Synthetic wait",
            text_preview="Fixture browser wait completed without sleeping or launching a browser.",
            metadata={"milliseconds": milliseconds, "slept": False},
        )
        return BrowserRuntimeResult(success=True, output=observation.to_dict(), observation=observation)

    def _observation_from_url(
        self,
        action_name: str,
        url: str,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeObservation:
        resolution = self._resolve(url, session)
        text_preview = _compact_text(resolution.extracted_text)[: self.policy.max_text_chars]
        return BrowserRuntimeObservation(
            action_name=action_name,
            current_url=resolution.url,
            title=resolution.title,
            text_preview=text_preview,
            metadata={
                "fixture_source": True,
                "fixture_site_id": resolution.site_id,
                "fixture_route": resolution.route,
                "fixture_path_relative": resolution.fixture_path_relative,
                "real_network_traffic": False,
                "browser_opened": False,
            },
        )

    def _resolve(self, url: str, session: BrowserRuntimeSession) -> Any:
        return resolve_browser_fixture_url(
            url,
            self.fixture_manifest_path,
            project_root=self.project_root,
            allowed_url_prefixes=[
                *self.allowed_url_prefixes,
                *_prefixes_for_domains(session.allowed_domains),
            ],
            preview_chars=self.policy.max_text_chars,
        )

    def _click_target_url(
        self,
        action: BrowserRuntimeAction,
        current_url: str,
        links: list[dict[str, str]],
    ) -> str | None:
        explicit = action.parameters.get("target_url") or action.parameters.get("href")
        if isinstance(explicit, str) and explicit.strip():
            return urljoin(current_url, explicit.strip())
        target_text = action.parameters.get("target_text") or action.parameters.get("text")
        selector = action.parameters.get("selector")
        for link in links:
            if isinstance(target_text, str) and target_text.strip().lower() in link["text"].lower():
                return urljoin(current_url, link["href"])
            if isinstance(selector, str) and selector.strip() and selector.strip() == link.get("id"):
                return urljoin(current_url, link["href"])
        return None

    def _search_fixture_pages(
        self,
        query: str,
        session: BrowserRuntimeSession,
    ) -> list[dict[str, Any]]:
        manifest = self._load_manifest()
        prefixes = _string_list(manifest.get("base_url_prefixes", []))
        base_url = prefixes[0] if prefixes else f"http://{session.allowed_domains[0]}"
        query_terms = [term.lower() for term in re.findall(r"[a-zA-Z0-9]+", query)]
        scored_results: list[tuple[int, dict[str, Any]]] = []
        routes = manifest.get("routes", {})
        if not isinstance(routes, dict):
            return []
        for route in sorted(routes):
            url = urljoin(base_url.rstrip("/") + "/", str(route).lstrip("/"))
            denial = self._validate_url(url, session)
            if denial is not None:
                continue
            try:
                resolution = self._resolve(url, session)
            except BrowserFixtureResolverError:
                continue
            haystack = resolution.extracted_text.lower()
            if query_terms and not all(term in haystack for term in query_terms):
                continue
            title = resolution.title or ""
            query_lower = query.lower()
            score = 1
            if query_lower in title.lower():
                score += 10
            if query_lower in haystack:
                score += 5
            if str(route).strip("/").replace("/", " ") in query_lower:
                score += 3
            scored_results.append(
                (
                    score,
                    {
                        "url": resolution.url,
                        "title": title,
                        "fixture_route": resolution.route,
                        "text_preview": _compact_text(resolution.extracted_text)[: self.policy.max_text_chars],
                    },
                )
            )
        ranked = sorted(scored_results, key=lambda item: (-item[0], item[1]["fixture_route"]))
        return [item for _, item in ranked[: self.policy.max_search_results]]

    def _load_manifest(self) -> dict[str, Any]:
        path = Path(self.fixture_manifest_path)
        if not path.is_absolute():
            path = self.project_root / path
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}


class PlaywrightBrowserRuntimeExecutor:
    def __init__(
        self,
        *,
        config: PlaywrightBrowserActivityConfig | None = None,
        dependency_loader: Any | None = None,
    ) -> None:
        self.config = config or PlaywrightBrowserActivityConfig(enabled=False)
        self.dependency_loader = dependency_loader

    def execute(
        self,
        action: BrowserRuntimeAction,
        session: BrowserRuntimeSession,
    ) -> BrowserRuntimeResult:
        del session
        action_map = {
            "browser_open_url": "open_url_real",
            "browser_extract_text": "extract_text_real",
            "browser_snapshot": "take_snapshot_real",
        }
        mapped = action_map.get(action.action_name)
        if mapped is None:
            return _failure(
                "unsupported_playwright_browser_action",
                "Playwright browser runtime interface supports open/extract/snapshot only.",
                metadata={"browser_launched": False, "real_browser_automation": False},
            )
        result = run_playwright_browser_activity(
            mapped,
            action.parameters,
            self.config,
            dependency_loader=self.dependency_loader,
        )
        return BrowserRuntimeResult(
            success=result.success,
            output=result.output,
            error_type=result.error_type,
            error_message=result.error_message,
            metadata=dict(result.metadata),
        )


def make_browser_runtime_action_executor(
    browser_executor: FixtureBackedBrowserRuntimeExecutor | PlaywrightBrowserRuntimeExecutor,
    session_store: MutableMapping[str, BrowserRuntimeSession],
    *,
    allowed_resource_namespaces: tuple[str, ...] | list[str] | set[str] = ("browser",),
    default_workspace_id: str = "browser_workspace",
    default_environment_id: str = "browser_environment",
    adapter: BrowserRuntimeAdapter | None = None,
) -> Any:
    runtime_adapter = adapter or BrowserRuntimeAdapter()

    def execute(decision: RuntimeActionDecision, state: RuntimeSharedState) -> RuntimeActionResult:
        namespace_error = runtime_adapter.validate_namespace(allowed_resource_namespaces)
        if namespace_error is not None:
            _record_browser_event(decision, state, namespace_error)
            return _to_runtime_result(namespace_error, None)

        action = runtime_adapter.from_decision(decision)
        session = _session_for_action(
            action,
            session_store,
            default_workspace_id=default_workspace_id,
            default_environment_id=default_environment_id,
            policy=runtime_adapter.policy,
        )
        result = browser_executor.execute(action, session)
        _record_browser_event(decision, state, result, session=session)
        return _to_runtime_result(result, session)

    return execute


def browser_session_resource_lock(session_id: str) -> str:
    return f"browser:{_safe_id(session_id, 'session_id')}"


def _session_for_action(
    action: BrowserRuntimeAction,
    store: MutableMapping[str, BrowserRuntimeSession],
    *,
    default_workspace_id: str,
    default_environment_id: str,
    policy: BrowserRuntimePolicy,
) -> BrowserRuntimeSession:
    session_id = action.session_id or f"{action.agent_id}_browser"
    if session_id in store:
        return store[session_id]
    allowed_domains = action.parameters.get("allowed_domains", DEFAULT_FIXTURE_DOMAINS)
    if not isinstance(allowed_domains, (list, tuple)):
        allowed_domains = DEFAULT_FIXTURE_DOMAINS
    session = BrowserRuntimeSession(
        session_id=session_id,
        agent_id=action.agent_id,
        workspace_id=str(action.parameters.get("workspace_id") or default_workspace_id),
        environment_id=str(action.parameters.get("environment_id") or default_environment_id),
        allowed_domains=tuple(str(domain) for domain in allowed_domains),
        start_url=action.parameters.get("url") if isinstance(action.parameters.get("url"), str) else None,
        policy_flags=policy.to_flags(),
    )
    store[session_id] = session
    return session


def _to_runtime_result(
    result: BrowserRuntimeResult,
    session: BrowserRuntimeSession | None,
) -> RuntimeActionResult:
    metadata = {"browser_result": result.to_dict()}
    if session is not None:
        metadata["browser_session"] = session.to_summary()
    return RuntimeActionResult(
        success=result.success,
        output=result.output if result.output is not None else result.to_dict(),
        error_type=result.error_type,
        error_message=result.error_message,
        artifact_refs=result.artifact_refs,
        metadata=metadata,
    )


def _record_browser_event(
    decision: RuntimeActionDecision,
    state: RuntimeSharedState,
    result: BrowserRuntimeResult,
    *,
    session: BrowserRuntimeSession | None = None,
) -> None:
    event_type = "browser_action_observed" if result.success else "browser_policy_denied"
    severity = "info" if result.success else "warning"
    metadata: dict[str, Any] = {"browser_result": result.to_dict()}
    if session is not None:
        metadata["browser_session_id"] = session.session_id
        metadata["browser_session_summary"] = session.to_summary()
    state.record_event(
        event_type,
        "Browser runtime action completed." if result.success else (result.error_message or "Browser action denied."),
        agent_id=decision.agent_id,
        task_id=decision.task_id,
        severity=severity,
        metadata=metadata,
    )
    if result.success and result.observation and session is not None:
        state.add_fact(
            f"browser:{session.session_id}:last_observation",
            result.observation.to_dict(),
            decision.agent_id,
        )
        for artifact_ref in result.artifact_refs:
            if artifact_ref not in state.produced_artifacts:
                state.produced_artifacts.append(artifact_ref)


def _missing_required_parameter(action: BrowserRuntimeAction) -> str | None:
    params = action.parameters
    if action.action_name == "browser_open_url" and not _non_empty_string(params.get("url")):
        return "url"
    if action.action_name == "browser_search" and not _non_empty_string(params.get("query")):
        return "query"
    if action.action_name == "browser_fill" and "fields" not in params:
        return "fields"
    if action.action_name == "browser_click":
        has_current = _non_empty_string(params.get("url"))
        has_target = any(
            _non_empty_string(params.get(name))
            for name in ("target_text", "text", "target_url", "href", "selector")
        )
        if not has_current and not has_target:
            return "target_text"
    return None


def _action_url(action: BrowserRuntimeAction, session: BrowserRuntimeSession) -> str | None:
    if _non_empty_string(action.parameters.get("url")):
        return str(action.parameters["url"]).strip()
    if action.action_name in {"browser_extract_text", "browser_snapshot", "browser_click"}:
        return session.current_url
    if _non_empty_string(action.parameters.get("target_url")):
        return str(action.parameters["target_url"]).strip()
    if _non_empty_string(action.parameters.get("href")):
        current = session.current_url or ""
        return urljoin(current, str(action.parameters["href"]).strip())
    return None


def _failure(
    error_type: str,
    error_message: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> BrowserRuntimeResult:
    return BrowserRuntimeResult(
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata=metadata or {},
    )


def _safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    stripped = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", stripped):
        raise ValueError(f"{label} contains unsafe characters.")
    return stripped


def _safe_domain(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("allowed_domains entries must be non-empty strings.")
    host = value.strip().lower()
    if "://" in host or "/" in host or "\\" in host or ".." in PurePosixPath(host).parts:
        raise ValueError("allowed_domains entries must be bare host names.")
    return host


def _host_allowed(host: str, allowed_domains: tuple[str, ...]) -> bool:
    host_lower = host.lower()
    for domain in allowed_domains:
        domain_lower = domain.lower()
        if host_lower == domain_lower or host_lower.endswith(f".{domain_lower}"):
            return True
    return False


def _prefixes_for_domains(domains: tuple[str, ...]) -> list[str]:
    prefixes: list[str] = []
    for domain in domains:
        prefixes.append(f"http://{domain}")
        prefixes.append(f"https://{domain}")
    return prefixes


def _extract_links(html: str) -> list[dict[str, str]]:
    parser = _LinkParser()
    parser.feed(html)
    return parser.links


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        href = attr_map.get("href")
        if not href:
            return
        self._current = {"href": href, "id": attr_map.get("id", "")}
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return
        self._current["text"] = _compact_text(" ".join(self._text_parts))
        self.links.append(self._current)
        self._current = None
        self._text_parts = []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
