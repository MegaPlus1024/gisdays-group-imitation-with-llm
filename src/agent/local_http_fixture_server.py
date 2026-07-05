from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import ClassVar
from urllib.parse import unquote, urlsplit


class LocalHttpFixtureServerError(ValueError):
    """Raised when the local fixture server is configured unsafely."""


class LocalHttpFixtureRequestError(ValueError):
    """Raised when an HTTP fixture request is unsafe or unsupported."""


@dataclass(frozen=True, slots=True)
class LocalHttpFixtureServerConfig:
    fixture_root: Path
    host: str = "127.0.0.1"
    port: int = 0
    allow_directory_listing: bool = False
    allowed_extensions: tuple[str, ...] = (".html", ".css", ".js", ".json", ".txt")
    max_file_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if self.host != "127.0.0.1":
            raise LocalHttpFixtureServerError("Fixture server may bind only to 127.0.0.1.")
        if self.port < 0 or self.port > 65535:
            raise LocalHttpFixtureServerError("Fixture server port must be between 0 and 65535.")
        if self.allow_directory_listing:
            raise LocalHttpFixtureServerError("Directory listing is not supported.")
        if self.max_file_bytes <= 0:
            raise LocalHttpFixtureServerError("max_file_bytes must be > 0.")
        if not self.allowed_extensions:
            raise LocalHttpFixtureServerError("allowed_extensions must not be empty.")
        for extension in self.allowed_extensions:
            if not extension.startswith(".") or "/" in extension or "\\" in extension:
                raise LocalHttpFixtureServerError("allowed_extensions must be simple suffixes.")


class LocalHttpFixtureServer:
    """Tiny local-only HTTP server for repository fixture pages.

    This utility is intended for controlled tests and future local browser automation.
    It binds only to 127.0.0.1 and serves static files from one fixture root.
    """

    def __init__(self, config: LocalHttpFixtureServerConfig) -> None:
        self.config = config
        self._httpd: _FixtureThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._base_url: str | None = None

    @property
    def base_url(self) -> str:
        if self._base_url is None:
            raise LocalHttpFixtureServerError("Fixture server is not started.")
        return self._base_url

    @property
    def is_running(self) -> bool:
        return self._httpd is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> LocalHttpFixtureServer:
        if self._httpd is not None:
            return self
        fixture_root = self.config.fixture_root.resolve()
        if not fixture_root.is_dir():
            raise LocalHttpFixtureServerError("fixture_root must be an existing directory.")

        handler_cls = _make_handler(
            fixture_root=fixture_root,
            allowed_extensions=self.config.allowed_extensions,
            max_file_bytes=self.config.max_file_bytes,
        )
        httpd = _FixtureThreadingHTTPServer((self.config.host, self.config.port), handler_cls)
        host, port = httpd.server_address[:2]
        self._httpd = httpd
        self._base_url = f"http://{host}:{port}"
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            name="local-http-fixture-server",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        httpd = self._httpd
        thread = self._thread
        self._httpd = None
        self._thread = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if thread is not None:
            thread.join(timeout=5)

    def url_for(self, path: str) -> str:
        if not isinstance(path, str) or not path.strip():
            raise LocalHttpFixtureServerError("path must be a non-empty string.")
        normalized = path.strip().replace("\\", "/")
        if "://" in normalized or "\x00" in normalized:
            raise LocalHttpFixtureServerError("path must be a local URL path.")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return f"{self.base_url}{normalized}"

    def __enter__(self) -> LocalHttpFixtureServer:
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()


class _FixtureThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads: ClassVar[bool] = True
    allow_reuse_address: ClassVar[bool] = True


def _make_handler(
    *,
    fixture_root: Path,
    allowed_extensions: tuple[str, ...],
    max_file_bytes: int,
) -> type[BaseHTTPRequestHandler]:
    class FixtureRequestHandler(BaseHTTPRequestHandler):
        server_version = "LocalHttpFixtureServer/1"
        sys_version = ""

        def do_GET(self) -> None:
            self._serve(send_body=True)

        def do_HEAD(self) -> None:
            self._serve(send_body=False)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _serve(self, *, send_body: bool) -> None:
            try:
                path = _resolve_request_path(
                    self.path,
                    fixture_root=fixture_root,
                    allowed_extensions=allowed_extensions,
                    max_file_bytes=max_file_bytes,
                )
            except FileNotFoundError:
                self._send_plain(HTTPStatus.NOT_FOUND, "not found", send_body=send_body)
                return
            except LocalHttpFixtureRequestError:
                self._send_plain(HTTPStatus.FORBIDDEN, "forbidden", send_body=send_body)
                return

            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", _content_type(path.suffix.lower()))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if send_body:
                self.wfile.write(data)

        def _send_plain(self, status: HTTPStatus, message: str, *, send_body: bool) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if send_body:
                self.wfile.write(body)

    return FixtureRequestHandler


def _resolve_request_path(
    raw_path: str,
    *,
    fixture_root: Path,
    allowed_extensions: tuple[str, ...],
    max_file_bytes: int,
) -> Path:
    parsed = urlsplit(raw_path)
    if parsed.scheme or parsed.netloc:
        raise LocalHttpFixtureRequestError("Absolute request URLs are not supported.")

    decoded_path = unquote(parsed.path or "/")
    if "\x00" in decoded_path or "\\" in decoded_path:
        raise LocalHttpFixtureRequestError("Unsafe request path.")
    if not decoded_path.startswith("/"):
        raise LocalHttpFixtureRequestError("Request path must be absolute.")

    relative = decoded_path.lstrip("/")
    if not relative:
        raise LocalHttpFixtureRequestError("Directory listing is not supported.")
    posix_path = PurePosixPath(relative)
    parts = posix_path.parts
    if any(part in {"", ".", ".."} for part in parts):
        raise LocalHttpFixtureRequestError("Request path must not contain traversal.")
    if any(part.startswith(".") for part in parts):
        raise LocalHttpFixtureRequestError("Hidden fixture files are not served.")

    resolved = (fixture_root / Path(*parts)).resolve()
    try:
        resolved.relative_to(fixture_root)
    except ValueError as exc:
        raise LocalHttpFixtureRequestError("Request path escapes fixture root.") from exc

    if not resolved.exists():
        raise FileNotFoundError("Fixture route not found.")
    if resolved.is_dir():
        raise LocalHttpFixtureRequestError("Directory listing is not supported.")
    if resolved.suffix.lower() not in allowed_extensions:
        raise LocalHttpFixtureRequestError("Unsupported fixture extension.")
    if resolved.stat().st_size > max_file_bytes:
        raise LocalHttpFixtureRequestError("Fixture file exceeds max_file_bytes.")
    return resolved


def _content_type(extension: str) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }.get(extension, "application/octet-stream")


@contextlib.contextmanager
def local_http_fixture_server(
    config: LocalHttpFixtureServerConfig,
) -> LocalHttpFixtureServer:
    server = LocalHttpFixtureServer(config)
    try:
        yield server.start()
    finally:
        server.stop()
