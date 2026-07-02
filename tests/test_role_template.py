from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.role_template import (
    RoleTemplate,
    load_role_template,
    role_template_to_agent_state_defaults,
)
from agent.state import AgentConstraints, AgentRole


def _minimal_valid_payload() -> dict:
    return {
        "role_id": "r1",
        "name": "Role",
        "description": "Desc",
        "primary_goals": ["Goal 1"],
        "constraints": {
            "allowed_action_names": ["read_file"],
            "forbidden_action_names": [],
        },
        "allowed_activity_scenarios": [
            {"name": "s1", "description": "scenario"}
        ],
    }


def test_load_role_template_loads_generic_example() -> None:
    tpl = load_role_template("configs/role_template.example.json")
    assert tpl.role_id == "student_researcher"


def test_load_role_template_loads_student_researcher() -> None:
    tpl = load_role_template("configs/roles/student_researcher.example.json")
    assert tpl.role_id == "student_researcher"


def test_load_role_template_loads_developer() -> None:
    tpl = load_role_template("configs/roles/developer.example.json")
    assert tpl.role_id == "developer"


def test_load_role_template_loads_office_worker() -> None:
    tpl = load_role_template("configs/roles/office_worker.example.json")
    assert tpl.role_id == "office_worker"


def test_empty_role_id_rejected() -> None:
    payload = _minimal_valid_payload()
    payload["role_id"] = ""
    with pytest.raises(ValidationError):
        RoleTemplate.model_validate(payload)


def test_empty_name_rejected() -> None:
    payload = _minimal_valid_payload()
    payload["name"] = ""
    with pytest.raises(ValidationError):
        RoleTemplate.model_validate(payload)


def test_empty_description_rejected() -> None:
    payload = _minimal_valid_payload()
    payload["description"] = ""
    with pytest.raises(ValidationError):
        RoleTemplate.model_validate(payload)


def test_primary_goals_must_not_be_empty() -> None:
    payload = _minimal_valid_payload()
    payload["primary_goals"] = []
    with pytest.raises(ValidationError):
        RoleTemplate.model_validate(payload)


def test_duplicate_allowed_action_names_rejected() -> None:
    payload = _minimal_valid_payload()
    payload["constraints"]["allowed_action_names"] = ["read_file", "read_file"]
    with pytest.raises(ValidationError):
        RoleTemplate.model_validate(payload)


def test_action_in_both_allowed_and_forbidden_rejected() -> None:
    payload = _minimal_valid_payload()
    payload["constraints"]["allowed_action_names"] = ["read_file"]
    payload["constraints"]["forbidden_action_names"] = ["read_file"]
    with pytest.raises(ValidationError):
        RoleTemplate.model_validate(payload)


def test_duplicate_activity_scenario_names_rejected() -> None:
    payload = _minimal_valid_payload()
    payload["allowed_activity_scenarios"] = [
        {"name": "same", "description": "a"},
        {"name": "same", "description": "b"},
    ]
    with pytest.raises(ValidationError):
        RoleTemplate.model_validate(payload)


def test_to_agent_role_returns_agent_role() -> None:
    tpl = load_role_template("configs/role_template.example.json")
    role = tpl.to_agent_role()
    assert isinstance(role, AgentRole)


def test_to_agent_constraints_returns_agent_constraints() -> None:
    tpl = load_role_template("configs/role_template.example.json")
    constraints = tpl.to_agent_constraints()
    assert isinstance(constraints, AgentConstraints)


def test_allowed_action_set_returns_expected_actions() -> None:
    tpl = load_role_template("configs/role_template.example.json")
    assert tpl.allowed_action_set() == {"create_file", "read_file", "run_shell_command"}


def test_role_template_to_agent_state_defaults_json_serializable() -> None:
    tpl = load_role_template("configs/role_template.example.json")
    defaults = role_template_to_agent_state_defaults(tpl)
    json.dumps(defaults)
    assert "role" in defaults
    assert "objective" in defaults


def test_student_researcher_forbidden_roots_include_models_gguf() -> None:
    tpl = load_role_template("configs/roles/student_researcher.example.json")
    assert "models/gguf/" in tpl.constraints.forbidden_file_roots
