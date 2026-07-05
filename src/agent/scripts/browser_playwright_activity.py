from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

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

    @field_validator("timeout_ms")
    @classmethod
    def validate_timeout_ms(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout_ms must be > 0.")
        return value

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
    """Return controlled scaffold results without launching a browser.

    This module intentionally does not enforce VirtualNetworkPolicy itself. Callers must
    run the virtual-network action policy before any future real navigation and must
    deny external, file, and credential URLs before a browser can be launched.
    """

    del parameters
    cfg = config or PlaywrightBrowserActivityConfig()
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

    loader = dependency_loader or _load_sync_playwright
    try:
        loader()
    except ImportError as exc:
        return _error(
            normalized_action,
            "playwright_dependency_missing",
            "Playwright is not installed. Install optional browser dependencies explicitly.",
            cfg,
            dependency_error_type=exc.__class__.__name__,
        )

    return _error(
        normalized_action,
        "playwright_backend_not_implemented",
        "Playwright dependency is available, but real browser execution is not implemented in this scaffold.",
        cfg,
    )


def _load_sync_playwright() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightDependencyMissingError(str(exc)) from exc
    return sync_playwright


def _error(
    action: str,
    error_type: str,
    error_message: str,
    config: PlaywrightBrowserActivityConfig,
    **metadata: Any,
) -> PlaywrightBrowserActionResult:
    return PlaywrightBrowserActionResult(
        action=action,
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata={
            "real_browser_automation": False,
            "real_external_network_traffic": False,
            "browser_launched": False,
            "playwright_enabled": config.enabled,
            "headless": config.headless,
            "timeout_ms": config.timeout_ms,
            "allowed_url_prefix_count": len(config.allowed_url_prefixes),
            "artifact_root_configured": config.artifact_root is not None,
            **metadata,
        },
    )
