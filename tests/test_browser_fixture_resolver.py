from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.browser_fixture_resolver import (
    BrowserFixtureRouteNotFound,
    BrowserFixtureUrlDenied,
    resolve_browser_fixture_url,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"


def test_resolve_fixture_url_returns_local_html_content() -> None:
    result = resolve_browser_fixture_url(
        "http://localhost:8088/tickets/1",
        MANIFEST_PATH,
        project_root=PROJECT_ROOT,
    )

    assert result.site_id == "office_site_v1"
    assert result.route == "/tickets/1"
    assert result.fixture_path_relative == "tickets/1.html"
    assert result.fixture_path.resolve().is_relative_to(
        (PROJECT_ROOT / "tests/fixtures/local_intranet/office_site_v1").resolve()
    )
    assert result.title == "Ticket 1 - Quarterly Access Review"
    assert "Quarterly Access Review" in result.extracted_text_preview
    assert result.real_network_traffic is False


def test_resolve_fixture_url_accepts_manifest_internal_test_host() -> None:
    result = resolve_browser_fixture_url(
        "http://local-intranet.test/docs/policy",
        MANIFEST_PATH,
        project_root=PROJECT_ROOT,
    )

    assert result.route == "/docs/policy"
    assert "external network services" in result.extracted_text_preview


def test_resolve_fixture_url_rejects_external_url() -> None:
    with pytest.raises(BrowserFixtureUrlDenied):
        resolve_browser_fixture_url(
            "https://example.com/tickets/1",
            MANIFEST_PATH,
            project_root=PROJECT_ROOT,
        )


def test_resolve_fixture_url_rejects_file_url() -> None:
    with pytest.raises(BrowserFixtureUrlDenied):
        resolve_browser_fixture_url(
            "file:///tmp/tickets/1.html",
            MANIFEST_PATH,
            project_root=PROJECT_ROOT,
        )


def test_resolve_fixture_url_rejects_credential_url() -> None:
    with pytest.raises(BrowserFixtureUrlDenied):
        resolve_browser_fixture_url(
            "http://user:pass@localhost:8088/tickets/1",
            MANIFEST_PATH,
            project_root=PROJECT_ROOT,
        )


def test_resolve_fixture_url_rejects_path_traversal() -> None:
    with pytest.raises(BrowserFixtureUrlDenied):
        resolve_browser_fixture_url(
            "http://localhost:8088/../outside",
            MANIFEST_PATH,
            project_root=PROJECT_ROOT,
        )


def test_resolve_fixture_url_rejects_unknown_local_route() -> None:
    with pytest.raises(BrowserFixtureRouteNotFound):
        resolve_browser_fixture_url(
            "http://localhost:8088/private/missing",
            MANIFEST_PATH,
            project_root=PROJECT_ROOT,
        )
