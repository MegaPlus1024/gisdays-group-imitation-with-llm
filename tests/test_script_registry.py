from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_contract import parse_next_action_text
from agent.action_validation_cases import load_action_validation_cases
from agent.role_template import load_role_template
from agent.script_registry import (
    ScriptDescriptor,
    ScriptParameterSpec,
    ScriptRegistry,
    ScriptSafetySpec,
    ScriptValidationIssue,
    ScriptValidationResult,
    issues_to_failure_categories,
    load_script_registry,
    validate_next_action_against_registry,
)


def test_load_script_registry_loads_example() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    assert reg.registry_id == "script_registry_v1"


def test_registry_contains_expected_scripts() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    names = reg.script_names()
    assert {"read_file", "create_file", "run_shell_command"}.issubset(names)


def test_duplicate_script_names_rejected() -> None:
    with pytest.raises(ValidationError):
        ScriptRegistry(
            registry_id="x",
            scripts=[
                ScriptDescriptor(name="a", description="d"),
                ScriptDescriptor(name="a", description="d2"),
            ],
        )


def test_duplicate_parameter_names_rejected() -> None:
    with pytest.raises(ValidationError):
        ScriptDescriptor(
            name="read_file",
            description="d",
            parameters=[
                ScriptParameterSpec(name="path", type="string"),
                ScriptParameterSpec(name="path", type="string"),
            ],
        )


def test_duplicate_safety_roots_rejected() -> None:
    with pytest.raises(ValidationError):
        ScriptSafetySpec(allowed_file_roots=["docs/", "docs/"])


def test_valid_read_file_action_accepted() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"read_file","parameters":{"path":"docs/ai/model_registry.md"},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is True


def test_unknown_action_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"unknown_x","parameters":{},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code == "unknown_action" for i in result.issues)


def test_missing_required_path_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"read_file","parameters":{},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code == "missing_required_parameter" for i in result.issues)


def test_unknown_parameter_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"read_file","parameters":{"path":"docs/ai/model_registry.md","x":1},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code == "unknown_parameter" for i in result.issues)


def test_wrong_parameter_type_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"read_file","parameters":{"path":123},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code == "wrong_parameter_type" for i in result.issues)


def test_forbidden_model_path_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"read_file","parameters":{"path":"models/gguf/first_model.gguf"},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code in {"forbidden_path", "path_not_in_allowed_roots"} for i in result.issues)


def test_create_file_into_src_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"create_file","parameters":{"path":"src/new_file.py","content":"x"},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code in {"forbidden_path", "path_not_in_allowed_roots"} for i in result.issues)


def test_valid_run_shell_command_accepted() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"run_shell_command","parameters":{"command":"python -m pytest -q"},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is True


def test_unsafe_shell_command_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"run_shell_command","parameters":{"command":"Remove-Item -Recurse -Force ."},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code == "unsafe_action" for i in result.issues)


def test_shell_command_not_in_allowlist_rejected() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    action = parse_next_action_text(
        '{"action":"run_shell_command","parameters":{"command":"python unknown.py"},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg)
    assert result.accepted is False
    assert any(i.code == "unsafe_action" for i in result.issues)


def test_role_template_can_forbid_action() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    role = load_role_template("configs/roles/office_worker.example.json")
    action = parse_next_action_text(
        '{"action":"run_shell_command","parameters":{"command":"python -m pytest -q"},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg, role)
    assert result.accepted is False
    assert any(i.code == "forbidden_by_role" for i in result.issues)


def test_role_allowed_roots_constrain_path_access() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    role = load_role_template("configs/roles/office_worker.example.json")
    action = parse_next_action_text(
        '{"action":"read_file","parameters":{"path":"src/agent/state.py"},"reason":"r","expected_result":"e"}'
    )
    result = validate_next_action_against_registry(action, reg, role)
    assert result.accepted is False
    assert any(i.layer == "role_constraints" for i in result.issues)


def test_script_validation_result_accepted_cannot_have_issues() -> None:
    with pytest.raises(ValidationError):
        ScriptValidationResult(
            accepted=True,
            action="x",
            issues=[ScriptValidationIssue(code="c", message="m")],
        )


def test_script_validation_result_rejected_must_have_issues() -> None:
    with pytest.raises(ValidationError):
        ScriptValidationResult(accepted=False, action="x", issues=[])


def test_integration_with_action_validation_cases() -> None:
    reg = load_script_registry("configs/script_registry.example.json")
    suite = load_action_validation_cases("configs/action_validation_cases.example.json")
    by_id = {c.case_id: c for c in suite.cases}

    reject_ids = [
        "semantic_unknown_action",
        "semantic_missing_required_parameter",
        "semantic_wrong_parameter_type",
        "semantic_forbidden_path_model_file",
        "semantic_unsafe_shell_command",
        "semantic_action_forbidden_by_role",
    ]

    role_office = load_role_template("configs/roles/office_worker.example.json")

    for case_id in reject_ids:
        case = by_id[case_id]
        action = parse_next_action_text(case.model_output_text)
        role = role_office if case_id == "semantic_action_forbidden_by_role" else None
        result = validate_next_action_against_registry(action, reg, role)
        assert result.accepted is False, case_id

    for case_id in [
        "valid_read_file_project_doc",
        "valid_create_file_experiment_note",
        "valid_run_pytest_command",
    ]:
        case = by_id[case_id]
        action = parse_next_action_text(case.model_output_text)
        result = validate_next_action_against_registry(action, reg)
        assert result.accepted is True, case_id
