from __future__ import annotations

import importlib

from src.agent.scripts.browser_playwright_activity import (
    PlaywrightBrowserActivityConfig,
    run_playwright_browser_activity,
)


def test_module_imports_without_importing_playwright_dependency() -> None:
    module = importlib.import_module("src.agent.scripts.browser_playwright_activity")

    assert hasattr(module, "PlaywrightBrowserActivityConfig")
    assert hasattr(module, "run_playwright_browser_activity")


def test_disabled_by_default_returns_controlled_denial() -> None:
    result = run_playwright_browser_activity(
        "open_url_real",
        {"url": "http://localhost:8088/tickets/1"},
        PlaywrightBrowserActivityConfig(),
    )

    assert result.success is False
    assert result.error_type == "real_browser_automation_disabled"
    assert result.metadata["real_browser_automation"] is False
    assert result.metadata["real_external_network_traffic"] is False
    assert result.metadata["browser_launched"] is False
    assert result.metadata["playwright_enabled"] is False


def test_disabled_behavior_does_not_call_dependency_loader() -> None:
    def fail_loader() -> object:
        raise AssertionError("disabled scaffold must not import Playwright")

    result = run_playwright_browser_activity(
        "extract_text_real",
        {"url": "http://localhost:8088/tickets/1"},
        PlaywrightBrowserActivityConfig(enabled=False),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == "real_browser_automation_disabled"
    assert result.metadata["browser_launched"] is False


def test_enabled_with_missing_dependency_returns_controlled_error() -> None:
    def missing_loader() -> object:
        raise ImportError("playwright missing for test")

    result = run_playwright_browser_activity(
        "open_url_real",
        {"url": "http://localhost:8088/tickets/1"},
        PlaywrightBrowserActivityConfig(enabled=True),
        dependency_loader=missing_loader,
    )

    assert result.success is False
    assert result.error_type == "playwright_dependency_missing"
    assert result.metadata["real_browser_automation"] is False
    assert result.metadata["real_external_network_traffic"] is False
    assert result.metadata["browser_launched"] is False
    assert result.metadata["playwright_enabled"] is True


def test_enabled_with_available_dependency_still_does_not_launch_browser() -> None:
    result = run_playwright_browser_activity(
        "take_snapshot_real",
        {"url": "http://localhost:8088/tickets/1"},
        PlaywrightBrowserActivityConfig(enabled=True),
        dependency_loader=lambda: object(),
    )

    assert result.success is False
    assert result.error_type == "playwright_backend_not_implemented"
    assert result.metadata["real_browser_automation"] is False
    assert result.metadata["real_external_network_traffic"] is False
    assert result.metadata["browser_launched"] is False


def test_unsupported_action_returns_controlled_error_without_browser_runtime() -> None:
    result = run_playwright_browser_activity(
        "click_real",
        {"selector": "#submit"},
        PlaywrightBrowserActivityConfig(enabled=True),
        dependency_loader=lambda: object(),
    )

    assert result.success is False
    assert result.error_type == "unknown_playwright_browser_action"
    assert result.metadata["real_browser_automation"] is False
    assert result.metadata["real_external_network_traffic"] is False
    assert result.metadata["browser_launched"] is False
