from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal
from urllib.parse import urlparse


WorkspaceMode = Literal["read_only", "read_write"]

LOCAL_URL_PREFIXES = (
    "http://127.0.0.1",
    "https://127.0.0.1",
    "http://localhost",
    "https://localhost",
)


class VirtualNetworkValidationError(ValueError):
    """Raised when a virtual network specification is unsafe or inconsistent."""


@dataclass(frozen=True)
class ServiceSpec:
    service_id: str
    kind: str
    display_name: str
    base_url: str | None = None
    root_path: str | None = None
    allowed_actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ServiceSpec:
        return cls(
            service_id=str(payload.get("service_id", "")),
            kind=str(payload.get("kind", "")),
            display_name=str(payload.get("display_name", "")),
            base_url=_optional_str(payload.get("base_url")),
            root_path=_optional_str(payload.get("root_path")),
            allowed_actions=_string_list(payload.get("allowed_actions", [])),
            metadata=_dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceMount:
    mount_id: str
    host_id: str | None
    root_path: str
    mode: WorkspaceMode = "read_only"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkspaceMount:
        return cls(
            mount_id=str(payload.get("mount_id", "")),
            host_id=_optional_str(payload.get("host_id")),
            root_path=str(payload.get("root_path", "")),
            mode=str(payload.get("mode", "read_only")),  # type: ignore[arg-type]
            metadata=_dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VirtualHostSpec:
    host_id: str
    display_name: str
    role: str | None
    workspace_root: str
    allowed_service_ids: list[str] = field(default_factory=list)
    allowed_url_prefixes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> VirtualHostSpec:
        return cls(
            host_id=str(payload.get("host_id", "")),
            display_name=str(payload.get("display_name", "")),
            role=_optional_str(payload.get("role")),
            workspace_root=str(payload.get("workspace_root", "")),
            allowed_service_ids=_string_list(payload.get("allowed_service_ids", [])),
            allowed_url_prefixes=_string_list(payload.get("allowed_url_prefixes", [])),
            metadata=_dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class NetworkEvent:
    agent_id: str
    host_id: str
    action: str
    allowed: bool
    status: str
    timestamp_utc: str = field(default_factory=_utc_now)
    target_service_id: str | None = None
    target_url: str | None = None
    target_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> NetworkEvent:
        return cls(
            timestamp_utc=str(payload.get("timestamp_utc") or _utc_now()),
            agent_id=str(payload.get("agent_id", "")),
            host_id=str(payload.get("host_id", "")),
            action=str(payload.get("action", "")),
            target_service_id=_optional_str(payload.get("target_service_id")),
            target_url=_optional_str(payload.get("target_url")),
            target_path=_optional_str(payload.get("target_path")),
            allowed=bool(payload.get("allowed", False)),
            status=str(payload.get("status", "")),
            details=_dict(payload.get("details", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VirtualNetworkSpec:
    network_id: str
    description: str
    hosts: list[VirtualHostSpec] = field(default_factory=list)
    services: list[ServiceSpec] = field(default_factory=list)
    shared_workspaces: list[WorkspaceMount] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> VirtualNetworkSpec:
        spec = cls(
            network_id=str(payload.get("network_id", "")),
            description=str(payload.get("description", "")),
            hosts=[
                VirtualHostSpec.from_dict(item)
                for item in _dict_list(payload.get("hosts", []), "hosts")
            ],
            services=[
                ServiceSpec.from_dict(item)
                for item in _dict_list(payload.get("services", []), "services")
            ],
            shared_workspaces=[
                WorkspaceMount.from_dict(item)
                for item in _dict_list(payload.get("shared_workspaces", []), "shared_workspaces")
            ],
            metadata=_dict(payload.get("metadata", {})),
        )
        return spec.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def get_host(self, host_id: str) -> VirtualHostSpec | None:
        for host in self.hosts:
            if host.host_id == host_id:
                return host
        return None

    def get_service(self, service_id: str) -> ServiceSpec | None:
        for service in self.services:
            if service.service_id == service_id:
                return service
        return None

    def is_service_allowed(self, host_id: str, service_id: str) -> bool:
        host = self.get_host(host_id)
        service = self.get_service(service_id)
        if host is None or service is None:
            return False
        return service_id in host.allowed_service_ids

    def is_url_allowed(self, host_id: str, url: str) -> bool:
        host = self.get_host(host_id)
        if host is None or not _is_safe_http_url(url):
            return False
        normalized = url.strip()
        allowed_prefixes = list(LOCAL_URL_PREFIXES) + list(host.allowed_url_prefixes)
        return any(normalized.startswith(prefix) for prefix in allowed_prefixes)

    def validate(self) -> VirtualNetworkSpec:
        _require_non_empty(self.network_id, "network_id")
        _require_non_empty(self.description, "description")

        host_ids = [host.host_id for host in self.hosts]
        service_ids = [service.service_id for service in self.services]
        workspace_ids = [workspace.mount_id for workspace in self.shared_workspaces]
        _reject_duplicates(host_ids, "host_id")
        _reject_duplicates(service_ids, "service_id")
        _reject_duplicates(workspace_ids, "mount_id")

        service_id_set = set(service_ids)
        host_id_set = set(host_ids)

        for host in self.hosts:
            _require_non_empty(host.host_id, "host_id")
            _require_non_empty(host.display_name, f"host {host.host_id} display_name")
            _validate_safe_config_path(host.workspace_root, f"host {host.host_id} workspace_root")
            _reject_duplicates(host.allowed_service_ids, f"host {host.host_id} allowed_service_ids")
            for service_id in host.allowed_service_ids:
                if service_id not in service_id_set:
                    raise VirtualNetworkValidationError(
                        f"Host '{host.host_id}' references unknown service_id '{service_id}'."
                    )
            for prefix in host.allowed_url_prefixes:
                _validate_url_prefix(prefix, f"host {host.host_id} allowed_url_prefixes")

        for service in self.services:
            _require_non_empty(service.service_id, "service_id")
            _require_non_empty(service.kind, f"service {service.service_id} kind")
            _require_non_empty(service.display_name, f"service {service.service_id} display_name")
            _reject_duplicates(service.allowed_actions, f"service {service.service_id} allowed_actions")
            if service.base_url is not None:
                _validate_url_prefix(service.base_url, f"service {service.service_id} base_url")
            if service.root_path is not None:
                _validate_safe_config_path(service.root_path, f"service {service.service_id} root_path")

        for workspace in self.shared_workspaces:
            _require_non_empty(workspace.mount_id, "mount_id")
            _validate_safe_config_path(workspace.root_path, f"workspace {workspace.mount_id} root_path")
            if workspace.mode not in {"read_only", "read_write"}:
                raise VirtualNetworkValidationError(
                    f"Workspace '{workspace.mount_id}' has invalid mode '{workspace.mode}'."
                )
            if workspace.host_id is not None and workspace.host_id not in host_id_set:
                raise VirtualNetworkValidationError(
                    f"Workspace '{workspace.mount_id}' references unknown host_id '{workspace.host_id}'."
                )

        return self


def load_virtual_network_spec(path: Path | str) -> VirtualNetworkSpec:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VirtualNetworkValidationError("Virtual network spec root must be a JSON object.")
    return VirtualNetworkSpec.from_dict(payload)


def write_network_event_jsonl(event: NetworkEvent, path: Path | str) -> Path:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(json.dumps(event.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")
    return path_obj


def append_network_event_jsonl(event: NetworkEvent, path: Path | str) -> Path:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with path_obj.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
    return path_obj


def read_network_events_jsonl(path: Path | str) -> list[NetworkEvent]:
    path_obj = Path(path)
    if not path_obj.exists():
        return []
    events: list[NetworkEvent] = []
    for line in path_obj.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise VirtualNetworkValidationError("Network event JSONL rows must be objects.")
        events.append(NetworkEvent.from_dict(payload))
    return events


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise VirtualNetworkValidationError("Expected a dictionary value.")
    return dict(value)


def _dict_list(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise VirtualNetworkValidationError(f"{field_name} must be a list.")
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise VirtualNetworkValidationError(f"{field_name} must contain only objects.")
        out.append(item)
    return out


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise VirtualNetworkValidationError("Expected a list of strings.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise VirtualNetworkValidationError("Expected a list of strings.")
        out.append(item)
    return out


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise VirtualNetworkValidationError(f"{field_name} must be non-empty.")


def _reject_duplicates(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise VirtualNetworkValidationError(f"{field_name} contains duplicate values.")


def _validate_safe_config_path(value: str, field_name: str) -> None:
    _require_non_empty(value, field_name)
    raw = value.strip().replace("\\", "/")
    lowered = raw.lower()
    codex_fragment = "." + "codex"
    if "://" in raw:
        raise VirtualNetworkValidationError(f"{field_name} must be a local relative path, not a URL.")
    if lowered.startswith("c:/users/") or "/users/" in lowered:
        raise VirtualNetworkValidationError(f"{field_name} must not contain a private user path.")
    if "downloads/telegram desktop" in lowered or codex_fragment in lowered or "auth.json" in lowered:
        raise VirtualNetworkValidationError(f"{field_name} contains a forbidden local/private path fragment.")
    if PureWindowsPath(value).is_absolute() or PurePosixPath(raw).is_absolute():
        raise VirtualNetworkValidationError(f"{field_name} must be relative or a generic placeholder path.")
    parts = PurePosixPath(raw).parts
    if any(part == ".." for part in parts):
        raise VirtualNetworkValidationError(f"{field_name} must not contain path traversal.")


def _validate_url_prefix(value: str, field_name: str) -> None:
    _require_non_empty(value, field_name)
    parsed = urlparse(value.strip())
    if parsed.scheme == "file":
        raise VirtualNetworkValidationError(f"{field_name} must not use file:// URLs.")
    if parsed.scheme not in {"http", "https"}:
        raise VirtualNetworkValidationError(f"{field_name} must use http or https.")
    if parsed.username or parsed.password:
        raise VirtualNetworkValidationError(f"{field_name} must not contain credentials.")
    if not parsed.hostname:
        raise VirtualNetworkValidationError(f"{field_name} must include a host.")
    if not _is_local_or_internal_host(parsed.hostname):
        raise VirtualNetworkValidationError(
            f"{field_name} must use a localhost, loopback, or reserved internal/test host."
        )


def _is_safe_http_url(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    if parsed.scheme == "file":
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password:
        return False
    return bool(parsed.hostname)


def _is_local_or_internal_host(hostname: str) -> bool:
    host = hostname.lower()
    return (
        host == "localhost"
        or host == "::1"
        or host.startswith("127.")
        or host.endswith(".localhost")
        or host.endswith(".test")
        or host.endswith(".internal")
    )
