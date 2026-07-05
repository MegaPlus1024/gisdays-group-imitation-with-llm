from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse


class BrowserFixtureResolverError(ValueError):
    """Raised when a simulated browser URL cannot be resolved to a local fixture."""


class BrowserFixtureUrlDenied(BrowserFixtureResolverError):
    """Raised when a URL is outside the configured fixture URL policy."""


class BrowserFixtureRouteNotFound(BrowserFixtureResolverError):
    """Raised when a safe URL is not present in the fixture route map."""


@dataclass(frozen=True)
class BrowserFixtureResolution:
    site_id: str
    url: str
    route: str
    fixture_path: Path
    fixture_path_relative: str
    title: str | None
    extracted_text: str
    extracted_text_preview: str
    real_network_traffic: bool = False

    def to_metadata(self) -> dict[str, Any]:
        return {
            "fixture_source": True,
            "fixture_site_id": self.site_id,
            "fixture_route": self.route,
            "fixture_path_relative": self.fixture_path_relative,
            "title": self.title,
            "extracted_text_preview": self.extracted_text_preview,
            "real_network_traffic": self.real_network_traffic,
        }


def resolve_browser_fixture_url(
    url: str,
    manifest_path: str | Path,
    *,
    project_root: Path | None = None,
    allowed_url_prefixes: list[str] | None = None,
    preview_chars: int = 500,
) -> BrowserFixtureResolution:
    if preview_chars <= 0:
        raise BrowserFixtureResolverError("preview_chars must be > 0.")

    manifest = _load_manifest(manifest_path, project_root=project_root)
    prefixes = list(allowed_url_prefixes or []) + _string_list(
        manifest.payload.get("base_url_prefixes", [])
    )
    normalized_url = _validate_url(url, prefixes)
    route = _route_from_url(normalized_url)
    routes = _route_map(manifest.payload.get("routes", {}))
    route_path = routes.get(route)
    if route_path is None and route.endswith("/"):
        route_path = routes.get(route.rstrip("/"))
        if route_path is not None:
            route = route.rstrip("/")
    if route_path is None:
        raise BrowserFixtureRouteNotFound("URL path is not present in the fixture manifest.")

    fixture_path = _safe_fixture_file(manifest.root, route_path)
    html = fixture_path.read_text(encoding="utf-8")
    title, extracted = _extract_visible_html_text(html)
    preview = _compact_text(extracted)[:preview_chars]
    return BrowserFixtureResolution(
        site_id=str(manifest.payload.get("site_id") or manifest.root.name),
        url=normalized_url,
        route=route,
        fixture_path=fixture_path,
        fixture_path_relative=PurePosixPath(route_path.replace("\\", "/")).as_posix(),
        title=title,
        extracted_text=extracted,
        extracted_text_preview=preview,
    )


@dataclass(frozen=True)
class _LoadedManifest:
    payload: dict[str, Any]
    path: Path
    root: Path


def _load_manifest(path: str | Path, *, project_root: Path | None) -> _LoadedManifest:
    manifest_path = Path(path)
    if not manifest_path.is_absolute():
        base = project_root if project_root is not None else Path(".")
        manifest_path = base / manifest_path
    resolved_manifest = manifest_path.resolve()
    payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BrowserFixtureResolverError("Fixture manifest root must be a JSON object.")
    root_value = payload.get("fixture_root")
    root = resolved_manifest.parent if root_value is None else _manifest_relative_path(
        resolved_manifest.parent, root_value
    )
    return _LoadedManifest(payload=payload, path=resolved_manifest, root=root.resolve())


def _manifest_relative_path(base: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BrowserFixtureResolverError("fixture_root must be a non-empty relative path.")
    normalized = value.strip().replace("\\", "/")
    if "://" in normalized or PurePosixPath(normalized).is_absolute() or Path(value).is_absolute():
        raise BrowserFixtureResolverError("fixture_root must be relative to the manifest.")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise BrowserFixtureResolverError("fixture_root must not contain path traversal.")
    return base / normalized


def _validate_url(url: str, allowed_prefixes: list[str]) -> str:
    if not isinstance(url, str) or not url.strip():
        raise BrowserFixtureUrlDenied("URL must be a non-empty string.")
    normalized = url.strip()
    try:
        parsed = urlparse(normalized)
    except ValueError as exc:
        raise BrowserFixtureUrlDenied("URL could not be parsed.") from exc
    scheme = (parsed.scheme or "").lower()
    if scheme == "file":
        raise BrowserFixtureUrlDenied("file:// URLs are not allowed for browser fixtures.")
    if scheme not in {"http", "https"}:
        raise BrowserFixtureUrlDenied("Browser fixtures allow only http/https URLs.")
    if parsed.username or parsed.password:
        raise BrowserFixtureUrlDenied("Credential URLs are not allowed for browser fixtures.")
    if not parsed.hostname:
        raise BrowserFixtureUrlDenied("Browser fixture URLs must include a host.")
    if not _matches_allowed_prefix(normalized, allowed_prefixes):
        raise BrowserFixtureUrlDenied("URL is outside the configured fixture URL prefixes.")
    return normalized


def _route_from_url(url: str) -> str:
    parsed = urlparse(url)
    decoded = unquote(parsed.path or "/")
    if not decoded.startswith("/"):
        decoded = f"/{decoded}"
    if "\\" in decoded:
        raise BrowserFixtureUrlDenied("URL path must not contain backslashes.")
    parts = PurePosixPath(decoded).parts
    if any(part == ".." for part in parts):
        raise BrowserFixtureUrlDenied("URL path must not contain traversal.")
    route = PurePosixPath(decoded).as_posix()
    return "/" if route in {"", "."} else route


def _route_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise BrowserFixtureResolverError("Fixture manifest routes must be an object.")
    out: dict[str, str] = {}
    for raw_route, raw_path in value.items():
        if not isinstance(raw_route, str) or not raw_route.startswith("/"):
            raise BrowserFixtureResolverError("Fixture route keys must be absolute URL paths.")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise BrowserFixtureResolverError("Fixture route paths must be non-empty strings.")
        out[raw_route] = raw_path
    return out


def _safe_fixture_file(root: Path, route_path: str) -> Path:
    normalized = route_path.strip().replace("\\", "/")
    if "://" in normalized or PurePosixPath(normalized).is_absolute() or Path(route_path).is_absolute():
        raise BrowserFixtureResolverError("Fixture route file must be a relative path.")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise BrowserFixtureResolverError("Fixture route file must not contain path traversal.")
    resolved = (root / normalized).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise BrowserFixtureResolverError("Fixture route file escapes fixture root.") from exc
    if not resolved.is_file():
        raise BrowserFixtureRouteNotFound("Fixture route file does not exist.")
    return resolved


def _matches_allowed_prefix(url: str, prefixes: list[str]) -> bool:
    parsed = urlparse(url)
    for prefix in prefixes:
        if not isinstance(prefix, str) or not prefix.strip():
            continue
        prefix_parsed = urlparse(prefix.strip())
        if prefix_parsed.scheme not in {"http", "https"} or not prefix_parsed.hostname:
            continue
        if parsed.scheme.lower() != prefix_parsed.scheme.lower():
            continue
        if (parsed.hostname or "").lower() != prefix_parsed.hostname.lower():
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


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BrowserFixtureResolverError("Expected a list of strings.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise BrowserFixtureResolverError("Expected a list of strings.")
        out.append(item)
    return out


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag_lower = tag.lower()
        if tag_lower in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag_lower == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag_lower == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        self.text_parts.append(text)


def _extract_visible_html_text(html: str) -> tuple[str | None, str]:
    parser = _VisibleTextParser()
    parser.feed(html)
    title = _compact_text(" ".join(parser.title_parts)) or None
    text = _compact_text(" ".join(parser.text_parts))
    return title, text


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
