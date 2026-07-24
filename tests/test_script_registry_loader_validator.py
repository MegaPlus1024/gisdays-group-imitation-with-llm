from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.action_contract import parse_next_action_text
from agent.role_template import load_role_template
from agent.script_registry import (
    ScriptDescriptor,
    ScriptParameterSpec,
    ScriptRegistry,
    ScriptRegistryLoadError,
    ScriptRegistryValidationError,
    ScriptSafetySpec,
    ScriptValidationResult,
    load_script_registry,
    validate_next_action_against_registry,
)


def _registry() -> ScriptRegistry:
    return load_script_registry("configs/script_registry.example.json")


def _next_action(text: str):
    return parse_next_action_text(text)


def _issue_codes(result: ScriptValidationResult) -> set[str]:
    return {i.code for i in result.issues}


def test_load_script_registry_loads_example() -> None:
    registry = _registry()
    assert registry.registry_id == "script_registry_v1"


def test_invalid_json_file_raises_loader_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ScriptRegistryLoadError):
        load_script_registry(p)


def test_missing_registry_file_raises_loader_error(tmp_path: Path) -> None:
    with pytest.raises(ScriptRegistryLoadError):
        load_script_registry(tmp_path / "missing.json")


def test_empty_registry_id_rejected() -> None:
    with pytest.raises(ValidationError):
        ScriptRegistry(registry_id="", schema_version="x", scripts=[ScriptDescriptor(name="a", description="b")])


def test_duplicate_script_names_rejected() -> None:
    with pytest.raises(ValidationError):
        ScriptRegistry(
            registry_id="r",
            schema_version="v",
            scripts=[
                ScriptDescriptor(name="x", description="d"),
                ScriptDescriptor(name="x", description="d2"),
            ],
        )


def test_duplicate_parameter_names_rejected() -> None:
    with pytest.raises(ValidationError):
        ScriptDescriptor(
            name="x",
            description="d",
            parameters=[
                ScriptParameterSpec(name="p", type="string"),
                ScriptParameterSpec(name="p", type="string"),
            ],
        )


def test_duplicate_safety_roots_rejected() -> None:
    with pytest.raises(ValidationError):
        ScriptSafetySpec(allowed_file_roots=["docs/", "docs/"])


def test_registry_contains_required_script_families() -> None:
    names = _registry().script_names()
    assert {
        "read_file",
        "create_file",
        "append_file",
        "list_directory",
        "browser_open_url",
        "office_create_document_stub",
        "run_shell_command",
    }.issubset(names)


def test_valid_read_file_is_accepted() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{"path":"docs/ai/model_registry.md"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is True


def test_valid_create_file_is_accepted() -> None:
    action = _next_action('{"action_name":"create_file","parameters":{"path":"docs/ai/new_note.md","content":"x"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is True


def test_valid_append_file_is_accepted() -> None:
    action = _next_action('{"action_name":"append_file","parameters":{"path":"docs/ai/new_note.md","content":"x"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is True


def test_valid_list_directory_is_accepted() -> None:
    action = _next_action('{"action_name":"list_directory","parameters":{"path":"docs/ai/"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is True


def test_valid_browser_open_url_is_accepted_registry_level() -> None:
    action = _next_action('{"action_name":"browser_open_url","parameters":{"url":"https://example.com"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is True


def test_valid_office_create_document_stub_is_accepted() -> None:
    action = _next_action('{"action_name":"office_create_document_stub","parameters":{"path":"docs/office/doc.txt","title":"t","body":"b"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is True


def test_valid_run_shell_command_is_accepted() -> None:
    action = _next_action('{"action_name":"run_shell_command","parameters":{"command":"python -m pytest -q"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is True


def test_unknown_action_rejected() -> None:
    action = _next_action('{"action_name":"not_real","parameters":{}}')
    result = validate_next_action_against_registry(action, _registry())
    assert result.accepted is False
    assert "unknown_action" in _issue_codes(result)


def test_missing_required_parameter_rejected() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "missing_required_parameter" in _issue_codes(result)


def test_unknown_parameter_rejected() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{"path":"docs/ai/model_registry.md","x":1}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "unknown_parameter" in _issue_codes(result)


def test_wrong_string_parameter_type_rejected() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{"path":5}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "wrong_parameter_type" in _issue_codes(result)


def test_wrong_integer_number_boolean_object_array_types_rejected() -> None:
    registry = ScriptRegistry(
        registry_id="r",
        schema_version="v",
        scripts=[
            ScriptDescriptor(
                name="typed",
                description="typed",
                parameters=[
                    ScriptParameterSpec(name="i", type="integer", required=True),
                    ScriptParameterSpec(name="n", type="number", required=True),
                    ScriptParameterSpec(name="b", type="boolean", required=True),
                    ScriptParameterSpec(name="o", type="object", required=True),
                    ScriptParameterSpec(name="a", type="array", required=True),
                ],
            )
        ],
    )
    action = _next_action('{"action_name":"typed","parameters":{"i":true,"n":false,"b":"x","o":[],"a":{}}}')
    result = validate_next_action_against_registry(action, registry)
    assert result.accepted is False
    assert "wrong_parameter_type" in _issue_codes(result)


def test_string_min_length_and_max_length_enforced() -> None:
    registry = ScriptRegistry(
        registry_id="r",
        schema_version="v",
        scripts=[
            ScriptDescriptor(
                name="sized",
                description="d",
                parameters=[
                    ScriptParameterSpec(
                        name="p", type="string", required=True, min_length=2, max_length=4
                    )
                ],
            )
        ],
    )
    action_short = _next_action('{"action_name":"sized","parameters":{"p":"a"}}')
    res_short = validate_next_action_against_registry(action_short, registry)
    assert "string_too_short" in _issue_codes(res_short)
    action_long = _next_action('{"action_name":"sized","parameters":{"p":"abcde"}}')
    res_long = validate_next_action_against_registry(action_long, registry)
    assert "string_too_long" in _issue_codes(res_long)


def test_allowed_values_enforced() -> None:
    registry = ScriptRegistry(
        registry_id="r",
        schema_version="v",
        scripts=[
            ScriptDescriptor(
                name="allowed",
                description="d",
                parameters=[
                    ScriptParameterSpec(
                        name="p", type="string", required=True, allowed_values=["a", "b"]
                    )
                ],
            )
        ],
    )
    action = _next_action('{"action_name":"allowed","parameters":{"p":"z"}}')
    result = validate_next_action_against_registry(action, registry)
    assert "value_not_allowed" in _issue_codes(result)


def test_absolute_path_rejected() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{"path":"/etc/passwd"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "unsafe_path" in _issue_codes(result)


def test_windows_drive_path_rejected() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{"path":"C:/tmp/a.txt"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "unsafe_path" in _issue_codes(result)


def test_path_traversal_rejected() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{"path":"docs/../secrets.txt"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "unsafe_path" in _issue_codes(result)


def test_forbidden_model_path_rejected() -> None:
    action = _next_action('{"action_name":"read_file","parameters":{"path":"models/gguf/first_model.gguf"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "forbidden_path" in _issue_codes(result)


def test_path_outside_allowed_roots_rejected() -> None:
    action = _next_action('{"action_name":"create_file","parameters":{"path":"tmp/out.txt","content":"x"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "path_outside_allowed_roots" in _issue_codes(result)


def test_unsafe_shell_command_rejected() -> None:
    action = _next_action('{"action_name":"run_shell_command","parameters":{"command":"Remove-Item -Recurse -Force ."}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "unsafe_command" in _issue_codes(result)


def test_shell_command_with_andand_rejected() -> None:
    action = _next_action('{"action_name":"run_shell_command","parameters":{"command":"python -m pytest -q && echo ok"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "unsafe_command" in _issue_codes(result)


def test_non_allowlisted_shell_command_rejected() -> None:
    action = _next_action('{"action_name":"run_shell_command","parameters":{"command":"python -V"}}')
    result = validate_next_action_against_registry(action, _registry())
    assert "command_not_allowlisted" in _issue_codes(result)


def test_office_worker_role_can_forbid_run_shell_command() -> None:
    role = load_role_template("configs/roles/office_worker.example.json")
    action = _next_action('{"action_name":"run_shell_command","parameters":{"command":"python -m pytest -q"}}')
    result = validate_next_action_against_registry(action, _registry(), role_template=role)
    assert "action_forbidden_by_role" in _issue_codes(result)


def test_role_allowed_file_roots_constrain_path_access() -> None:
    role = load_role_template("configs/roles/office_worker.example.json")
    action = _next_action('{"action_name":"read_file","parameters":{"path":"src/agent/state.py"}}')
    result = validate_next_action_against_registry(action, _registry(), role_template=role)
    assert "path_outside_allowed_roots" in _issue_codes(result)


def test_script_validation_result_consistency_rules() -> None:
    with pytest.raises(ValidationError):
        ScriptValidationResult(accepted=True, action="x", issues=[{"code": "c", "message": "m"}])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        ScriptValidationResult(accepted=False, action="x", issues=[])


def test_action_validation_cases_integration() -> None:
    registry = _registry()
    payload = json.loads(
        Path("configs/action_validation_cases.example.json").read_text(encoding="utf-8")
    )
    cases = {c["case_id"]: c for c in payload["cases"]}

    positives = [
        "valid_read_file_project_doc",
        "valid_create_file_experiment_note",
        "valid_run_pytest_command",
    ]
    for cid in positives:
        na = _next_action(cases[cid]["model_output_text"])
        res = validate_next_action_against_registry(na, registry)
        assert res.accepted is True

    na_unknown = _next_action(cases["semantic_unknown_action"]["model_output_text"])
    assert validate_next_action_against_registry(na_unknown, registry).accepted is False

    na_missing = _next_action(
        cases["semantic_missing_required_parameter"]["model_output_text"]
    )
    assert (
        validate_next_action_against_registry(na_missing, registry).accepted is False
    )

    na_wrong_type = _next_action(cases["semantic_wrong_parameter_type"]["model_output_text"])
    assert (
        validate_next_action_against_registry(na_wrong_type, registry).accepted is False
    )

    na_forbidden_path = _next_action(
        cases["semantic_forbidden_path_model_file"]["model_output_text"]
    )
    assert (
        validate_next_action_against_registry(na_forbidden_path, registry).accepted
        is False
    )

    na_unsafe_cmd = _next_action(cases["semantic_unsafe_shell_command"]["model_output_text"])
    assert (
        validate_next_action_against_registry(na_unsafe_cmd, registry).accepted is False
    )

    role = load_role_template("configs/roles/office_worker.example.json")
    na_role_forbidden = _next_action(
        cases["semantic_action_forbidden_by_role"]["model_output_text"]
    )
    assert (
        validate_next_action_against_registry(
            na_role_forbidden, registry, role_template=role
        ).accepted
        is False
    )
