from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from .results import ScriptExecutionResult


SUPPORTED_PLAYWRIGHT_BROWSER_ACTIONS = frozenset(
    {
        "open_url_real",
        "extract_text_real",
        "take_snapshot_real",
    }
)


class PlaywrightBrowserActionError(Exception):
    """Base error for controlled Playwright browser scaffold failures."""


class PlaywrightDependencyMissingError(PlaywrightBrowserActionError, ImportError):
    """Raised when Playwright is requested but not installed."""


class PlaywrightBrowserActivityConfig(BaseModel):
    enabled: bool = False
    headless: bool = True
    timeout_ms: int = 15_000
    allowed_url_prefixes: list[str] = Field(default_factory=list)
    artifact_root: str | None = None
    project_root: Path = Path(".")
    text_preview_chars: int = 500
    text_snapshot_chars: int = 10_000

    @field_validator("timeout_ms")
    @classmethod
    def validate_timeout_ms(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout_ms must be > 0.")
        return value

    @field_validator("text_preview_chars", "text_snapshot_chars")
    @classmethod
    def validate_text_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("text limits must be > 0.")
        return value

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("artifact_root")
    @classmethod
    def validate_artifact_root(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("artifact_root must be non-empty when provided.")
        if value is None:
            return None
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/") or Path(value).is_absolute():
            raise ValueError("artifact_root must be a safe relative path.")
        return normalized

    @model_validator(mode="after")
    def validate_unique_prefixes(self) -> PlaywrightBrowserActivityConfig:
        if len(self.allowed_url_prefixes) != len(set(self.allowed_url_prefixes)):
            raise ValueError("allowed_url_prefixes must not contain duplicates.")
        for prefix in self.allowed_url_prefixes:
            _validate_allowed_prefix(prefix)
        return self


class PlaywrightBrowserActionResult(ScriptExecutionResult):
    """Script result shape for the optional Playwright browser scaffold."""


def run_playwright_browser_activity(
    action: str,
    parameters: dict[str, Any] | None = None,
    config: PlaywrightBrowserActivityConfig | None = None,
    *,
    dependency_loader: Callable[[], Any] | None = None,
) -> PlaywrightBrowserActionResult:
    """Run a tightly bounded optional Playwright backend.

    The default path is still a controlled denial. Real browser work is available only
    when enabled=True and only for local/allowlisted HTTP URLs.
    """

    cfg = config or PlaywrightBrowserActivityConfig()
    params = parameters or {}
    normalized_action = action if isinstance(action, str) and action.strip() else "unknown"
    if normalized_action not in SUPPORTED_PLAYWRIGHT_BROWSER_ACTIONS:
        return _error(
            normalized_action,
            "unknown_playwright_browser_action",
            f"Unknown Playwright browser action: {action}",
            cfg,
        )

    if not cfg.enabled:
        return _error(
            normalized_action,
            "real_browser_automation_disabled",
            "Real browser automation is disabled by default.",
            cfg,
        )

    url_result = _target_url(params)
    if not url_result.success:
        return _error(
            normalized_action,
            url_result.error_type or "invalid_parameter",
            url_result.error_message or "Invalid browser action parameters.",
            cfg,
            **url_result.metadata,
        )
    url = str(url_result.metadata["url"])
    url_decision = _validate_url_for_real_browser(url, cfg)
    if not url_decision["allowed"]:
        return _error(
            normalized_action,
            str(url_decision["error_type"]),
            str(url_decision["error_message"]),
            cfg,
            **url_decision["metadata"],
        )

    loader = dependency_loader or _load_sync_playwright
    try:
        sync_playwright_factory = loader()
    except ImportError as exc:
        return _error(
            normalized_action,
            "playwright_dependency_missing",
            "Playwright is not installed. Install optional browser dependencies explicitly.",
            cfg,
            dependency_error_type=exc.__class__.__name__,
        )
    except Exception as exc:
        return _error(
            normalized_action,
            "playwright_browser_unavailable",
            "Playwright backend is unavailable.",
            cfg,
            backend_error_type=exc.__class__.__name__,
        )

    return _run_real_playwright_action(
        normalized_action,
        url,
        cfg,
        sync_playwright_factory,
    )


def _load_sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightDependencyMissingError(str(exc)) from exc
    return sync_playwright


def _target_url(parameters: dict[str, Any]) -> PlaywrightBrowserActionResult:
    raw = parameters.get("url", parameters.get("target_url"))
    if not isinstance(raw, str) or not raw.strip():
        return PlaywrightBrowserActionResult(
            action="validate_url",
            success=False,
            error_type="missing_parameter",
            error_message="Missing required parameter: url",
            metadata={},
        )
    return PlaywrightBrowserActionResult(
        action="validate_url",
        success=True,
        metadata={"url": raw.strip()},
    )


def _run_real_playwright_action(
    action: str,
    url: str,
    config: PlaywrightBrowserActivityConfig,
    sync_playwright_factory: Any,
) -> PlaywrightBrowserActionResult:
    blocked_request_count = 0
    browser = None
    context = None
    manager = None
    try:
        manager = (
            sync_playwright_factory()
            if callable(sync_playwright_factory)
            else sync_playwright_factory
        )
        with manager as playwright:
            try:
                browser = playwright.chromium.launch(headless=config.headless)
            except Exception as exc:
                return _error(
                    action,
                    "playwright_browser_unavailable",
                    "Playwright browser runtime is unavailable.",
                    config,
                    backend_error_type=exc.__class__.__name__,
                )

            try:
                context = browser.new_context()
                context.set_default_timeout(config.timeout_ms)
                page = context.new_page()

                def route_guard(route: Any) -> None:
                    nonlocal blocked_request_count
                    request_url = str(route.request.url)
                    decision = _validate_url_for_real_browser(request_url, config)
                    if decision["allowed"]:
                        route.continue_()
                        return
                    blocked_request_count += 1
                    route.abort()

                page.route("**/*", route_guard)
                page.goto(url, wait_until="domcontentloaded", timeout=config.timeout_ms)

                final_url = str(page.url)
                final_decision = _validate_url_for_real_browser(final_url, config)
                if not final_decision["allowed"]:
                    return _error(
                        action,
                        "post_navigation_url_denied",
                        "Browser navigation left the local allowlist.",
                        config,
                        browser_launched=True,
                        real_browser_automation=True,
                        blocked_request_count=blocked_request_count,
                        **final_decision["metadata"],
                    )

                title = _safe_page_title(page)
                text = _safe_page_text(page, config)
                metadata = {
                    "real_browser_automation": True,
                    "real_external_network_traffic": False,
                    "browser_launched": True,
                    "playwright_enabled": config.enabled,
                    "headless": config.headless,
                    "timeout_ms": config.timeout_ms,
                    "allowed_url_prefix_count": len(config.allowed_url_prefixes),
                    "artifact_root_configured": config.artifact_root is not None,
                    "current_url": final_url,
                    "page_title": title,
                    "text_preview": _preview(text, config.text_preview_chars),
                    "blocked_request_count": blocked_request_count,
                }

                if action == "take_snapshot_real":
                    artifact_result = _write_snapshot_artifacts(
                        page=page,
                        action=action,
                        url=final_url,
                        title=title,
                        text=text,
                        blocked_request_count=blocked_request_count,
                        config=config,
                    )
                    if not artifact_result.success:
                        return artifact_result
                    metadata.update(artifact_result.metadata)

                return PlaywrightBrowserActionResult(
                    action=action,
                    success=True,
                    output=_success_output(action, text),
                    metadata=metadata,
                )
            except Exception as exc:
                return _error(
                    action,
                    "playwright_navigation_failed",
                    "Playwright navigation or page extraction failed.",
                    config,
                    browser_launched=True,
                    real_browser_automation=True,
                    blocked_request_count=blocked_request_count,
                    backend_error_type=exc.__class__.__name__,
                )
            finally:
                _close_quietly(context)
                _close_quietly(browser)
    except Exception as exc:
        return _error(
            action,
            "playwright_browser_unavailable",
            "Playwright backend is unavailable.",
            config,
            backend_error_type=exc.__class__.__name__,
        )


def _safe_page_title(page: Any) -> str:
    try:
        title = page.title()
    except Exception:
        return ""
    return str(title)


def _safe_page_text(page: Any, config: PlaywrightBrowserActivityConfig) -> str:
    try:
        text = page.inner_text("body", timeout=config.timeout_ms)
    except Exception:
        try:
            text = page.text_content("body", timeout=config.timeout_ms)
        except Exception:
            text = ""
    return str(text or "")


def _success_output(action: str, text: str) -> str:
    if action == "open_url_real":
        return "Opened a local allowlisted URL with the optional Playwright backend."
    if action == "extract_text_real":
        return text
    if action == "take_snapshot_real":
        return "Captured local browser snapshot artifacts."
    return "Completed optional Playwright browser action."


def _write_snapshot_artifacts(
    *,
    page: Any,
    action: str,
    url: str,
    title: str,
    text: str,
    blocked_request_count: int,
    config: PlaywrightBrowserActivityConfig,
) -> PlaywrightBrowserActionResult:
    artifact_root = _resolve_artifact_root(config)
    if artifact_root is None:
        return _error(
            action,
            "artifact_root_required",
            "take_snapshot_real requires a configured artifact_root.",
            config,
            browser_launched=True,
            real_browser_automation=True,
            blocked_request_count=blocked_request_count,
        )

    try:
        artifact_root.mkdir(parents=True, exist_ok=True)
        stem = _artifact_stem(action, url)
        screenshot_path = artifact_root / f"{stem}.png"
        text_path = artifact_root / f"{stem}.txt"
        metadata_path = artifact_root / f"{stem}.json"

        page.screenshot(
            path=str(screenshot_path),
            full_page=True,
            timeout=config.timeout_ms,
        )
        text_path.write_text(text[: config.text_snapshot_chars], encoding="utf-8")
        metadata_path.write_text(
            json.dumps(
                {
                    "action": action,
                    "page_title": title,
                    "current_url": url,
                    "real_external_network_traffic": False,
                    "blocked_request_count": blocked_request_count,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        return _error(
            action,
            "artifact_write_failed",
            "Failed to write Playwright browser snapshot artifacts.",
            config,
            browser_launched=True,
            real_browser_automation=True,
            backend_error_type=exc.__class__.__name__,
            blocked_request_count=blocked_request_count,
        )

    return PlaywrightBrowserActionResult(
        action=action,
        success=True,
        metadata={
            "screenshot_path_relative": _relative_to_project(screenshot_path, config),
            "text_snapshot_path_relative": _relative_to_project(text_path, config),
            "metadata_path_relative": _relative_to_project(metadata_path, config),
        },
    )


def _resolve_artifact_root(config: PlaywrightBrowserActivityConfig) -> Path | None:
    if config.artifact_root is None:
        return None
    project_root = config.project_root.resolve()
    artifact_root = (project_root / config.artifact_root).resolve()
    try:
        artifact_root.relative_to(project_root)
    except ValueError as exc:  # pragma: no cover - protected by config validation
        raise ValueError("artifact_root must stay under project_root.") from exc
    return artifact_root


def _relative_to_project(path: Path, config: PlaywrightBrowserActivityConfig) -> str:
    return path.resolve().relative_to(config.project_root.resolve()).as_posix()


def _artifact_stem(action: str, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{_safe_slug(action)}_{digest}"


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._") or "browser"


def _preview(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _close_quietly(value: Any) -> None:
    if value is None:
        return
    try:
        value.close()
    except Exception:
        return


def _validate_allowed_prefix(prefix: str) -> None:
    if not isinstance(prefix, str) or not prefix.strip():
        raise ValueError("allowed_url_prefixes entries must be non-empty strings.")
    parsed = urlparse(prefix.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("allowed_url_prefixes must be http/https URLs.")
    if not parsed.hostname:
        raise ValueError("allowed_url_prefixes must include a host.")
    if parsed.username or parsed.password:
        raise ValueError("allowed_url_prefixes must not include credentials.")
    if not _is_loopback_url(parsed):
        raise ValueError("allowed_url_prefixes must be loopback-only.")


def _validate_url_for_real_browser(
    url: str,
    config: PlaywrightBrowserActivityConfig,
) -> dict[str, Any]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return _url_denied("unsafe_url", "URL could not be parsed.")

    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        port = None

    metadata = {
        "denied_scheme": scheme,
        "denied_host": host or None,
        "denied_port_present": port is not None,
    }
    if scheme == "file":
        return _url_denied("file_url_denied", "file:// URLs are not allowed.", metadata)
    if parsed.username or parsed.password:
        return _url_denied(
            "credential_url_denied",
            "Credential URLs are not allowed.",
            metadata,
        )
    if scheme not in {"http", "https"}:
        return _url_denied("unsafe_url", "Only http/https URLs are allowed.", metadata)
    if not _is_loopback_url(parsed):
        return _url_denied(
            "external_url_denied",
            "Only loopback local fixture URLs are allowed.",
            metadata,
        )
    if not _matches_allowed_prefix(parsed, config.allowed_url_prefixes):
        if not (scheme == "http" and host == "127.0.0.1" and port is not None):
            return _url_denied(
                "url_not_allowlisted",
                "URL is not in allowed_url_prefixes.",
                metadata,
            )
    return {"allowed": True, "metadata": {}}


def _is_loopback_url(parsed: Any) -> bool:
    return (parsed.hostname or "").lower() == "127.0.0.1"


def _matches_allowed_prefix(parsed: Any, prefixes: list[str]) -> bool:
    for prefix in prefixes:
        prefix_parsed = urlparse(prefix.strip())
        if parsed.scheme.lower() != prefix_parsed.scheme.lower():
            continue
        if (parsed.hostname or "").lower() != (prefix_parsed.hostname or "").lower():
            continue
        if parsed.port != prefix_parsed.port:
            continue
        prefix_path = prefix_parsed.path.rstrip("/")
        if not prefix_path:
            return True
        path = parsed.path.rstrip("/")
        if path == prefix_path or path.startswith(f"{prefix_path}/"):
            return True
    return False


def _url_denied(
    error_type: str,
    error_message: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "allowed": False,
        "error_type": error_type,
        "error_message": error_message,
        "metadata": metadata or {},
    }


def _error(
    action: str,
    error_type: str,
    error_message: str,
    config: PlaywrightBrowserActivityConfig,
    *,
    browser_launched: bool = False,
    real_browser_automation: bool = False,
    **metadata: Any,
) -> PlaywrightBrowserActionResult:
    return PlaywrightBrowserActionResult(
        action=action,
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata={
            "real_browser_automation": real_browser_automation,
            "real_external_network_traffic": False,
            "browser_launched": browser_launched,
            "playwright_enabled": config.enabled,
            "headless": config.headless,
            "timeout_ms": config.timeout_ms,
            "allowed_url_prefix_count": len(config.allowed_url_prefixes),
            "artifact_root_configured": config.artifact_root is not None,
            **metadata,
        },
    )
