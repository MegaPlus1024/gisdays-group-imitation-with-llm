from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.state import (
    AgentObjective,
    AgentRole,
    AgentState,
    ActionHistoryEntry,
    ActionSpec,
    load_agent_state,
)


def example_state_payload() -> dict:
    return {
        "agent_id": "agent_001",
        "role": {"name": "Student researcher", "description": "Maintains reproducible records."},
        "objective": {"primary": "Prepare next reproducible step."},
        "available_actions": [
            {"name": "create_file", "description": "Create file."},
            {"name": "read_file", "description": "Read file."},
        ],
        "history": [
            {"step": 1, "action": "create_file", "status": "success"},
            {"step": 2, "action": "read_file", "status": "success"},
        ],
        "current_step": 3,
    }


def test_agent_state_loads_from_example_config() -> None:
    state = load_agent_state("configs/agent_state.example.json")
    assert state.agent_id == "student_researcher_001"
    assert state.current_step == 3


def test_to_prompt_context_returns_json_serializable_dict() -> None:
    state = AgentState.model_validate(example_state_payload())
    payload = state.to_prompt_context()
    assert isinstance(payload, dict)
    json.dumps(payload)


def test_available_action_names_returns_expected_set() -> None:
    state = AgentState.model_validate(example_state_payload())
    assert state.available_action_names() == {"create_file", "read_file"}


def test_has_action_works() -> None:
    state = AgentState.model_validate(example_state_payload())
    assert state.has_action("create_file") is True
    assert state.has_action("run_shell_command") is False


def test_duplicate_available_action_names_rejected() -> None:
    payload = example_state_payload()
    payload["available_actions"] = [
        {"name": "create_file", "description": "Create."},
        {"name": "create_file", "description": "Duplicate."},
    ]
    with pytest.raises(ValidationError):
        AgentState.model_validate(payload)


def test_duplicate_history_steps_rejected() -> None:
    payload = example_state_payload()
    payload["history"] = [
        {"step": 1, "action": "create_file"},
        {"step": 1, "action": "read_file"},
    ]
    payload["current_step"] = 2
    with pytest.raises(ValidationError):
        AgentState.model_validate(payload)


def test_current_step_smaller_than_required_rejected() -> None:
    payload = example_state_payload()
    payload["current_step"] = 2
    with pytest.raises(ValidationError):
        AgentState.model_validate(payload)


def test_empty_agent_id_rejected() -> None:
    payload = example_state_payload()
    payload["agent_id"] = ""
    with pytest.raises(ValidationError):
        AgentState.model_validate(payload)


def test_empty_role_name_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentRole(name="", description="desc")


def test_empty_objective_primary_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentObjective(primary="")


def test_load_agent_state_reads_and_validates_temp_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    payload = example_state_payload()
    path.write_text(json.dumps(payload), encoding="utf-8")
    state = load_agent_state(path)
    assert state.agent_id == "agent_001"
