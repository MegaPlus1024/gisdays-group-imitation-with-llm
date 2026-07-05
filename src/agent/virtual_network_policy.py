from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from .state import AgentState
from .virtual_network import VirtualNetworkSpec


URL_PARAMETER_NAMES = frozenset({"url", "target_url", "base_url"})
SERVICE_PARAMETER_NAMES = frozenset({"service_id", "target_service_id"})


@dataclass(frozen=True)
class VirtualNetworkPolicyDecision:
    allowed: bool
    applied: bool
    code: str
    message: str
    agent_id: str
    action: str
    network_id: str | None = None
    host_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_virtual_network_action_policy(
    *,
    action_name: str,
    parameters: dict[str, Any],
    agent_id: str,
    state: AgentState | dict[str, Any] | None = None,
    network_metadata: dict[str, Any] | None = None,
    virtual_network_spec: VirtualNetworkSpec | None = None,
) -> VirtualNetworkPolicyDecision:
    url_params = _known_string_parameters(parameters, URL_PARAMETER_NAMES)
    service_params = _known_string_parameters(parameters, SERVICE_PARAMETER_NAMES)
    has_policy_inputs = bool(url_params or service_params)

    if virtual_network_spec is None:
        return _allowed_noop(
            action_name=action_name,
            agent_id=agent_id,
            code="virtual_network_not_configured",
            details={"policy_relevant": has_policy_inputs},
        )

    metadata = network_metadata if network_metadata is not None else _state_virtual_network_metadata(state)
    network_id = virtual_network_spec.network_id
    host_id = _metadata_string(metadata, "host_id")

    if not has_policy_inputs:
        return _allowed_noop(
            action_name=action_name,
            agent_id=agent_id,
            code="virtual_network_no_relevant_parameters",
            network_id=network_id,
            host_id=host_id,
            details={"metadata_only": True, "policy_relevant": False},
        )

    common_details: dict[str, Any] = {
        "metadata_only": True,
        "policy_relevant": True,
        "checked_url_params": [],
        "checked_service_params": [],
    }

    if host_id is None:
        return _denied(
            action_name=action_name,
            agent_id=agent_id,
            code="virtual_network_no_host_binding",
            message="Virtual network policy requires a host binding for URL or service parameters.",
            network_id=network_id,
            host_id=None,
            details=common_details,
        )

    host = virtual_network_spec.get_host(host_id)
    if host is None:
        return _denied(
            action_name=action_name,
            agent_id=agent_id,
            code="virtual_network_unknown_host",
            message="Virtual network policy references an unknown host.",
            network_id=network_id,
            host_id=host_id,
            details=common_details,
        )

    for parameter_name, service_id in service_params.items():
        service_check = {
            "parameter": parameter_name,
            "service_id": service_id,
            "service_known": virtual_network_spec.get_service(service_id) is not None,
            "allowed": virtual_network_spec.is_service_allowed(host_id, service_id),
        }
        common_details["checked_service_params"].append(service_check)
        if not service_check["allowed"]:
            return _denied(
                action_name=action_name,
                agent_id=agent_id,
                code="virtual_network_service_denied",
                message="Virtual network policy denied the requested service for this host.",
                network_id=network_id,
                host_id=host_id,
                details=common_details,
            )

    for parameter_name, url in url_params.items():
        url_check = _sanitized_url_check(parameter_name, url)
        common_details["checked_url_params"].append(url_check)
        if url_check["scheme"] == "file":
            return _denied(
                action_name=action_name,
                agent_id=agent_id,
                code="virtual_network_file_url_denied",
                message="Virtual network policy denies file URLs.",
                network_id=network_id,
                host_id=host_id,
                details=common_details,
            )
        if url_check["has_credentials"]:
            return _denied(
                action_name=action_name,
                agent_id=agent_id,
                code="virtual_network_credential_url_denied",
                message="Virtual network policy denies URLs with credentials.",
                network_id=network_id,
                host_id=host_id,
                details=common_details,
            )
        url_allowed = virtual_network_spec.is_url_allowed(host_id, url)
        url_check["allowed"] = url_allowed
        if not url_allowed:
            return _denied(
                action_name=action_name,
                agent_id=agent_id,
                code="virtual_network_url_denied",
                message="Virtual network policy denied the requested URL for this host.",
                network_id=network_id,
                host_id=host_id,
                details=common_details,
            )

    return VirtualNetworkPolicyDecision(
        allowed=True,
        applied=True,
        code="virtual_network_policy_allowed",
        message="Virtual network policy allowed the action parameters.",
        agent_id=agent_id,
        action=action_name,
        network_id=network_id,
        host_id=host_id,
        details=common_details,
    )


def _allowed_noop(
    *,
    action_name: str,
    agent_id: str,
    code: str,
    network_id: str | None = None,
    host_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> VirtualNetworkPolicyDecision:
    return VirtualNetworkPolicyDecision(
        allowed=True,
        applied=False,
        code=code,
        message="Virtual network policy did not apply to this action.",
        agent_id=agent_id,
        action=action_name,
        network_id=network_id,
        host_id=host_id,
        details=details or {},
    )


def _denied(
    *,
    action_name: str,
    agent_id: str,
    code: str,
    message: str,
    network_id: str | None,
    host_id: str | None,
    details: dict[str, Any],
) -> VirtualNetworkPolicyDecision:
    return VirtualNetworkPolicyDecision(
        allowed=False,
        applied=True,
        code=code,
        message=message,
        agent_id=agent_id,
        action=action_name,
        network_id=network_id,
        host_id=host_id,
        details=details,
    )


def _known_string_parameters(parameters: dict[str, Any], names: frozenset[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        value = parameters.get(name)
        if isinstance(value, str) and value.strip():
            out[name] = value.strip()
    return out


def _state_virtual_network_metadata(state: AgentState | dict[str, Any] | None) -> dict[str, Any]:
    if state is None:
        return {}
    if isinstance(state, AgentState):
        metadata = state.metadata.get("virtual_network")
        return dict(metadata) if isinstance(metadata, dict) else {}
    if isinstance(state, dict):
        if isinstance(state.get("virtual_network"), dict):
            return dict(state["virtual_network"])
        metadata = state.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("virtual_network"), dict):
            return dict(metadata["virtual_network"])
    return {}


def _metadata_string(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _sanitized_url_check(parameter_name: str, url: str) -> dict[str, Any]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return {
            "parameter": parameter_name,
            "scheme": "",
            "host": None,
            "port": None,
            "origin": None,
            "has_credentials": False,
            "allowed": False,
        }

    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname.lower() if parsed.hostname else None
    try:
        port = parsed.port
    except ValueError:
        port = None
    origin = None
    if scheme and host:
        origin = f"{scheme}://{host}"
        if port is not None:
            origin = f"{origin}:{port}"
    return {
        "parameter": parameter_name,
        "scheme": scheme,
        "host": host,
        "port": port,
        "origin": origin,
        "has_credentials": bool(parsed.username or parsed.password),
        "allowed": False,
    }
