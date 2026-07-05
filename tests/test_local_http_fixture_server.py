from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from src.agent.local_http_fixture_server import (
    LocalHttpFixtureServer,
    LocalHttpFixtureServerConfig,
    LocalHttpFixtureServerError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures/local_intranet/office_site_v1"


def _read(url: str) -> tuple[int, str]:
    with urlopen(url, timeout=3) as response:
        return response.status, response.read().decode("utf-8")


def _status(url: str) -> int:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def _server(root: Path = FIXTURE_ROOT) -> LocalHttpFixtureServer:
    return LocalHttpFixtureServer(LocalHttpFixtureServerConfig(fixture_root=root))


def test_server_starts_on_loopback_with_random_port() -> None:
    with _server() as server:
        assert server.is_running is True
        assert server.base_url.startswith("http://127.0.0.1:")

    assert server.is_running is False


def test_known_index_fixture_returns_local_intranet_text() -> None:
    with _server() as server:
        status, body = _read(server.url_for("/index.html"))

    assert status == 200
    assert "Office Intranet" in body
    assert "simulated browser actions only" in body


def test_known_ticket_fixture_returns_200() -> None:
    with _server() as server:
        status, body = _read(server.url_for("/tickets/1.html"))

    assert status == 200
    assert "Quarterly Access Review" in body


def test_directory_listing_is_rejected() -> None:
    with _server() as server:
        assert _status(server.url_for("/tickets/")) == 403


def test_path_traversal_is_rejected() -> None:
    with _server() as server:
        assert _status(f"{server.base_url}/%2e%2e/outside.html") == 403


def test_hidden_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".hidden.html").write_text("hidden", encoding="utf-8")

    with _server(tmp_path) as server:
        assert _status(server.url_for("/.hidden.html")) == 403


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "image.png").write_bytes(b"png")

    with _server(tmp_path) as server:
        assert _status(server.url_for("/image.png")) == 403


def test_unknown_route_returns_404() -> None:
    with _server() as server:
        assert _status(server.url_for("/missing.html")) == 404


def test_url_for_returns_local_url() -> None:
    with _server() as server:
        url = server.url_for("/tickets/1.html")

    assert url.startswith("http://127.0.0.1:")
    assert url.endswith("/tickets/1.html")


def test_non_local_bind_host_is_rejected() -> None:
    with pytest.raises(LocalHttpFixtureServerError):
        LocalHttpFixtureServerConfig(fixture_root=FIXTURE_ROOT, host="0.0.0.0")

    with pytest.raises(LocalHttpFixtureServerError):
        LocalHttpFixtureServerConfig(fixture_root=FIXTURE_ROOT, host="localhost")


def test_server_stop_is_idempotent() -> None:
    server = _server().start()

    server.stop()
    server.stop()

    assert server.is_running is False
