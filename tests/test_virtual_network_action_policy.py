from __future__ import annotations

from pathlib import Path

from src.agent.state import AgentObjective, AgentRole, AgentState
from src.agent.virtual_network import load_virtual_network_spec
from src.agent.virtual_network_policy import evaluate_virtual_network_action_policy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "configs/virtual_networks/local_office_network_v1.json"


def _state(host_id: str | None = "office_user_host") -> AgentState:
    virtual_network = {
        "network_id": "local_office_network_v1",
        "metadata_only": True,
    }
    if host_id is not None:
        virtual_network["host_id"] = host_id
    return AgentState(
        agent_id="office_agent",
        role=AgentRole(name="Office worker", description="Test role"),
        objective=AgentObjective(primary="Validate virtual network policy"),
        metadata={"virtual_network": virtual_network},
    )


def test_policy_noop_without_virtual_network_spec() -> None:
    decision = evaluate_virtual_network_action_policy(
        action_name="read_file",
        parameters={"path": "docs/ai/model_research_metadata.md"},
        agent_id="office_agent",
        state=_state(),
        virtual_network_spec=None,
    )

    assert decision.allowed is True
    assert decision.applied is False
    assert decision.code == "virtual_network_not_configured"


def test_policy_allows_localhost_url_for_bound_host() -> None:
    spec = load_virtual_network_spec(SPEC_PATH)

    decision = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"url": "http://localhost:8088/tickets/1"},
        agent_id="office_agent",
        state=_state("office_user_host"),
        virtual_network_spec=spec,
    )

    assert decision.allowed is True
    assert decision.applied is True
    assert decision.code == "virtual_network_policy_allowed"
    assert decision.details["checked_url_params"][0]["origin"] == "http://localhost:8088"


def test_policy_denies_external_url() -> None:
    spec = load_virtual_network_spec(SPEC_PATH)

    decision = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"url": "https://example.com/report"},
        agent_id="office_agent",
        state=_state("office_user_host"),
        virtual_network_spec=spec,
    )

    assert decision.allowed is False
    assert decision.code == "virtual_network_url_denied"
    assert decision.details["checked_url_params"][0]["host"] == "example.com"


def test_policy_denies_file_url() -> None:
    spec = load_virtual_network_spec(SPEC_PATH)

    decision = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"url": "file:///tmp/report.html"},
        agent_id="office_agent",
        state=_state("office_user_host"),
        virtual_network_spec=spec,
    )

    assert decision.allowed is False
    assert decision.code == "virtual_network_file_url_denied"


def test_policy_denies_credential_url_without_logging_credentials() -> None:
    spec = load_virtual_network_spec(SPEC_PATH)

    decision = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"url": "http://user:pass@localhost:8088/tickets/1"},
        agent_id="office_agent",
        state=_state("office_user_host"),
        virtual_network_spec=spec,
    )

    assert decision.allowed is False
    assert decision.code == "virtual_network_credential_url_denied"
    url_check = decision.details["checked_url_params"][0]
    assert url_check["has_credentials"] is True
    assert url_check["origin"] == "http://localhost:8088"


def test_policy_allows_allowed_service_id() -> None:
    spec = load_virtual_network_spec(SPEC_PATH)

    decision = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"service_id": "shared_docs"},
        agent_id="office_agent",
        state=_state("office_user_host"),
        virtual_network_spec=spec,
    )

    assert decision.allowed is True
    assert decision.code == "virtual_network_policy_allowed"
    assert decision.details["checked_service_params"][0]["service_id"] == "shared_docs"


def test_policy_denies_unknown_or_disallowed_service_id() -> None:
    spec = load_virtual_network_spec(SPEC_PATH)

    unknown = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"target_service_id": "missing_service"},
        agent_id="office_agent",
        state=_state("office_user_host"),
        virtual_network_spec=spec,
    )
    disallowed = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"target_service_id": "ticket_board"},
        agent_id="maintenance_agent",
        state=_state("maintenance_host"),
        virtual_network_spec=spec,
    )

    assert unknown.allowed is False
    assert unknown.code == "virtual_network_service_denied"
    assert unknown.details["checked_service_params"][0]["service_known"] is False
    assert disallowed.allowed is False
    assert disallowed.code == "virtual_network_service_denied"


def test_policy_denies_url_when_host_binding_is_missing() -> None:
    spec = load_virtual_network_spec(SPEC_PATH)

    decision = evaluate_virtual_network_action_policy(
        action_name="browser_open_url",
        parameters={"url": "http://localhost:8088/tickets/1"},
        agent_id="office_agent",
        state=_state(host_id=None),
        virtual_network_spec=spec,
    )

    assert decision.allowed is False
    assert decision.code == "virtual_network_no_host_binding"
