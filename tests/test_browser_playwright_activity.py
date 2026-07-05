from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.agent.local_http_fixture_server import (
    LocalHttpFixtureServer,
    LocalHttpFixtureServerConfig,
)
from src.agent.scripts.browser_playwright_activity import (
    PlaywrightBrowserActivityConfig,
    run_playwright_browser_activity,
)


pytestmark = [
    pytest.mark.browser,
    pytest.mark.playwright,
    pytest.mark.optional_browser,
]

if os.environ.get("RUN_BROWSER_TESTS") != "1":
    pytestmark.append(pytest.mark.skip(reason="RUN_BROWSER_TESTS=1 is not set"))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures/local_intranet/office_site_v1"


def _server(root: Path = FIXTURE_ROOT) -> LocalHttpFixtureServer:
    return LocalHttpFixtureServer(LocalHttpFixtureServerConfig(fixture_root=root))


def _config(
    *,
    server: LocalHttpFixtureServer,
    artifact_root: str | None = None,
    project_root: Path | None = None,
) -> PlaywrightBrowserActivityConfig:
    return PlaywrightBrowserActivityConfig(
        enabled=True,
        headless=True,
        timeout_ms=5_000,
        allowed_url_prefixes=[server.base_url],
        artifact_root=artifact_root,
        project_root=project_root or PROJECT_ROOT,
    )


def _run_or_skip_browser(
    action: str,
    parameters: dict[str, str],
    config: PlaywrightBrowserActivityConfig,
):
    pytest.importorskip("playwright.sync_api")
    result = run_playwright_browser_activity(action, parameters, config)
    if not result.success and result.error_type == "playwright_browser_unavailable":
        pytest.skip("Playwright browser binary is unavailable")
    return result


def test_allowed_local_url_opens_fixture_page() -> None:
    with _server() as server:
        result = _run_or_skip_browser(
            "open_url_real",
            {"url": server.url_for("/index.html")},
            _config(server=server),
        )

    assert result.success is True
    assert result.metadata["real_browser_automation"] is True
    assert result.metadata["real_external_network_traffic"] is False
    assert result.metadata["browser_launched"] is True
    assert result.metadata["page_title"] == "Office Intranet Home"
    assert "Office Intranet" in result.metadata["text_preview"]


def test_extract_text_real_returns_fixture_text() -> None:
    with _server() as server:
        result = _run_or_skip_browser(
            "extract_text_real",
            {"url": server.url_for("/tickets/1.html")},
            _config(server=server),
        )

    assert result.success is True
    assert "Quarterly Access Review" in (result.output or "")
    assert result.metadata["real_external_network_traffic"] is False
    assert result.metadata["page_title"] == "Ticket 1 - Quarterly Access Review"


def test_external_url_is_denied_before_navigation() -> None:
    result = run_playwright_browser_activity(
        "open_url_real",
        {"url": "https://example.com/"},
        PlaywrightBrowserActivityConfig(enabled=True),
        dependency_loader=lambda: pytest.fail(
            "unsafe URL should be denied before import"
        ),
    )

    assert result.success is False
    assert result.error_type == "external_url_denied"
    assert result.metadata["browser_launched"] is False


def test_file_url_is_denied_before_navigation() -> None:
    result = run_playwright_browser_activity(
        "open_url_real",
        {"url": "file:///tmp/fixture.html"},
        PlaywrightBrowserActivityConfig(enabled=True),
        dependency_loader=lambda: pytest.fail("file URL should be denied before import"),
    )

    assert result.success is False
    assert result.error_type == "file_url_denied"
    assert result.metadata["browser_launched"] is False


def test_credential_url_is_denied_before_navigation() -> None:
    result = run_playwright_browser_activity(
        "open_url_real",
        {"url": "http://user:pass@127.0.0.1:8088/tickets/1"},
        PlaywrightBrowserActivityConfig(enabled=True),
        dependency_loader=lambda: pytest.fail(
            "credential URL should be denied before import"
        ),
    )

    assert result.success is False
    assert result.error_type == "credential_url_denied"
    assert result.metadata["browser_launched"] is False


def test_take_snapshot_real_writes_relative_artifacts(tmp_path: Path) -> None:
    with _server() as server:
        result = _run_or_skip_browser(
            "take_snapshot_real",
            {"url": server.url_for("/index.html")},
            _config(server=server, artifact_root="browser_artifacts", project_root=tmp_path),
        )

    assert result.success is True
    screenshot = result.metadata["screenshot_path_relative"]
    text_snapshot = result.metadata["text_snapshot_path_relative"]
    assert not Path(screenshot).is_absolute()
    assert not Path(text_snapshot).is_absolute()
    assert (tmp_path / screenshot).is_file()
    assert (tmp_path / text_snapshot).is_file()
    assert "Office Intranet" in (tmp_path / text_snapshot).read_text(encoding="utf-8")


def test_route_interception_blocks_external_subresource(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>External Subresource Probe</title></head>
<body>
  <h1>Local page</h1>
  <img src="https://example.com/pixel.png" alt="blocked external image">
</body>
</html>
""",
        encoding="utf-8",
    )

    with _server(site) as server:
        result = _run_or_skip_browser(
            "open_url_real",
            {"url": server.url_for("/index.html")},
            _config(server=server),
        )

    assert result.success is True
    assert result.metadata["real_external_network_traffic"] is False
    assert result.metadata["blocked_request_count"] >= 1
