from __future__ import annotations

from pathlib import Path

from src.agent.scripts.browser_activity import BrowserActivityConfig, run_browser_activity


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"


def test_browser_open_url_uses_fixture_backed_content_without_network() -> None:
    result = run_browser_activity(
        "open_url",
        {"url": "http://localhost:8088/tickets/1"},
        BrowserActivityConfig(
            project_root=PROJECT_ROOT,
            fixture_manifest_path=MANIFEST_PATH,
        ),
    )

    assert result.success is True
    assert result.metadata["simulated"] is True
    assert result.metadata["browser_opened"] is False
    assert result.metadata["network_used"] is False
    assert result.metadata["real_network_traffic"] is False
    assert result.metadata["fixture_source"] is True
    assert result.metadata["fixture_site_id"] == "office_site_v1"
    assert result.metadata["fixture_route"] == "/tickets/1"
    assert result.metadata["fixture_path_relative"] == "tickets/1.html"
    assert result.metadata["title"] == "Ticket 1 - Quarterly Access Review"
    assert "Quarterly Access Review" in result.metadata["extracted_text_preview"]


def test_browser_open_url_without_fixture_keeps_original_simulated_shape() -> None:
    result = run_browser_activity(
        "open_url",
        {"url": "http://localhost:8088/tickets/1"},
        BrowserActivityConfig(project_root=PROJECT_ROOT),
    )

    assert result.success is True
    assert result.metadata["simulated"] is True
    assert result.metadata["browser_opened"] is False
    assert "fixture_source" not in result.metadata


def test_browser_open_url_fixture_rejects_unknown_route_without_network() -> None:
    result = run_browser_activity(
        "open_url",
        {"url": "http://localhost:8088/private/missing"},
        BrowserActivityConfig(
            project_root=PROJECT_ROOT,
            fixture_manifest_path=MANIFEST_PATH,
        ),
    )

    assert result.success is False
    assert result.error_type == "fixture_resolution_failed"
