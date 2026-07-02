from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .role_template import RoleTemplate
from .schemas import NextAction

ParameterType = Literal["string", "integer", "number", "boolean", "object", "array"]


class ScriptRegistryError(Exception):
    """Base error for script registry loading/validation."""


class ScriptRegistryLoadError(ScriptRegistryError):
    """Raised when registry file cannot be loaded or decoded."""


class ScriptRegistryValidationError(ScriptRegistryError):
    """Raised when loaded registry data fails schema validation."""


class ScriptParameterSpec(BaseModel):
    name: str
    type: ParameterType
    required: bool = False
    description: str = ""
    min_length: int | None = None
    max_length: int | None = None
    allowed_values: list[Any] = Field(default_factory=list)
    default: Any | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Parameter name must be non-empty.")
        return value

    @field_validator("min_length", "max_length")
    @classmethod
    def validate_lengths_non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("min_length and max_length must be >= 0 when present.")
        return value

    @model_validator(mode="after")
    def validate_length_bounds(self) -> ScriptParameterSpec:
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.max_length < self.min_length
        ):
            raise ValueError("max_length must be >= min_length.")
        return self

    @field_validator("allowed_values")
    @classmethod
    def validate_allowed_values_list(
        cls, value: list[Any]
    ) -> list[Any]:
        if not isinstance(value, list):
            raise ValueError("allowed_values must be a list.")
        return value


class ScriptSafetySpec(BaseModel):
    allowed_file_roots: list[str] = Field(default_factory=list)
    forbidden_file_roots: list[str] = Field(default_factory=list)
    forbidden_substrings: list[str] = Field(default_factory=list)
    allowed_shell_commands: list[str] = Field(default_factory=list)
    forbidden_shell_commands: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    read_only: bool = False
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_safety_lists(self) -> ScriptSafetySpec:
        for field_name in [
            "allowed_file_roots",
            "forbidden_file_roots",
            "forbidden_substrings",
            "allowed_shell_commands",
            "forbidden_shell_commands",
        ]:
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates.")
        return self


class ScriptDescriptor(BaseModel):
    name: str
    description: str
    parameters: list[ScriptParameterSpec] = Field(default_factory=list)
    safety: ScriptSafetySpec = Field(default_factory=ScriptSafetySpec)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    result_shape: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("name", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Script name and description must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_unique_parameter_names_and_tags(self) -> ScriptDescriptor:
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("Parameter names must be unique.")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates.")
        for example in self.examples:
            if not isinstance(example, dict):
                raise ValueError("examples must contain only dictionaries.")
        if not isinstance(self.result_shape, dict):
            raise ValueError("result_shape must be a dictionary.")
        return self

    def required_parameter_names(self) -> set[str]:
        return {p.name for p in self.parameters if p.required}

    def parameter_names(self) -> set[str]:
        return {p.name for p in self.parameters}

    def get_parameter(self, name: str) -> ScriptParameterSpec | None:
        for p in self.parameters:
            if p.name == name:
                return p
        return None


class ScriptRegistry(BaseModel):
    registry_id: str
    schema_version: str = "script_registry_v1"
    scripts: list[ScriptDescriptor]

    @field_validator("registry_id", "schema_version")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("registry_id and schema_version must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_scripts(self) -> ScriptRegistry:
        if not self.scripts:
            raise ValueError("scripts must not be empty.")
        names = [s.name for s in self.scripts]
        if len(names) != len(set(names)):
            raise ValueError("script names must be unique.")
        return self

    def script_names(self) -> set[str]:
        return {s.name for s in self.scripts}

    def has_script(self, name: str) -> bool:
        return self.get_script(name) is not None

    def get_script(self, name: str) -> ScriptDescriptor | None:
        for s in self.scripts:
            if s.name == name:
                return s
        return None


def load_script_registry(path: str | Path) -> ScriptRegistry:
    path_obj = Path(path)
    try:
        raw = path_obj.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ScriptRegistryLoadError(
            f"Script registry file not found: {path_obj}"
        ) from exc
    except OSError as exc:
        raise ScriptRegistryLoadError(
            f"Failed to read script registry file: {path_obj}"
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScriptRegistryLoadError(
            f"Invalid JSON in script registry file: {path_obj}"
        ) from exc

    try:
        return ScriptRegistry.model_validate(payload)
    except Exception as exc:
        raise ScriptRegistryValidationError(
            f"Script registry validation failed for: {path_obj}"
        ) from exc


class ScriptValidationIssue(BaseModel):
    code: str
    message: str
    layer: Literal["script_registry", "role_constraints", "safety_policy"] = (
        "script_registry"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code and message must be non-empty.")
        return value


class ScriptValidationResult(BaseModel):
    accepted: bool
    action: str
    issues: list[ScriptValidationIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_result_consistency(self) -> ScriptValidationResult:
        if self.accepted and self.issues:
            raise ValueError("accepted=True cannot have issues.")
        if not self.accepted and not self.issues:
            raise ValueError("accepted=False must have issues.")
        return self


def _value_matches_parameter_type(value: Any, ptype: ParameterType) -> bool:
    if ptype == "string":
        return isinstance(value, str)
    if ptype == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if ptype == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(
            value, bool
        )
    if ptype == "boolean":
        return isinstance(value, bool)
    if ptype == "object":
        return isinstance(value, dict)
    if ptype == "array":
        return isinstance(value, list)
    return False


def _starts_with_any(value: str, prefixes: list[str]) -> bool:
    return any(value.startswith(prefix) for prefix in prefixes)


def _command_matches_allowed(command: str, allowed_prefixes: list[str]) -> bool:
    return any(command == p or command.startswith(p) for p in allowed_prefixes)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _is_windows_drive_path(path: str) -> bool:
    return re.match(r"^[a-zA-Z]:", path) is not None


def _is_unsafe_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if normalized.startswith("/"):
        return True
    if _is_windows_drive_path(normalized):
        return True
    parts = normalized.split("/")
    return ".." in parts


def validate_next_action_against_registry(
    next_action: NextAction,
    registry: ScriptRegistry,
    role_template: RoleTemplate | None = None,
) -> ScriptValidationResult:
    issues: list[ScriptValidationIssue] = []
    action_name = next_action.action
    descriptor = registry.get_script(action_name)

    if descriptor is None:
        issues.append(
            ScriptValidationIssue(
                code="unknown_action",
                message=f"Action '{action_name}' is not in the script registry.",
                layer="script_registry",
            )
        )
        return ScriptValidationResult(
            accepted=False, action=action_name, issues=issues, metadata={}
        )

    if role_template is not None:
        rc = role_template.constraints
        if rc.forbidden_action_names and action_name in rc.forbidden_action_names:
            issues.append(
                ScriptValidationIssue(
                    code="forbidden_by_role",
                    message=f"Action '{action_name}' is forbidden by role constraints.",
                    layer="role_constraints",
                    metadata={"specific_reason": "action_forbidden_by_role"},
                )
            )
            issues.append(
                ScriptValidationIssue(
                    code="action_forbidden_by_role",
                    message=f"Action '{action_name}' is forbidden by role constraints.",
                    layer="role_constraints",
                    metadata={"specific_reason": "action_forbidden_by_role", "legacy_code": True},
                )
            )
        if rc.allowed_action_names and action_name not in rc.allowed_action_names:
            issues.append(
                ScriptValidationIssue(
                    code="forbidden_by_role",
                    message=f"Action '{action_name}' is not in role allowed_action_names.",
                    layer="role_constraints",
                    metadata={"specific_reason": "action_not_in_role_allowlist"},
                )
            )
            issues.append(
                ScriptValidationIssue(
                    code="action_forbidden_by_role",
                    message=f"Action '{action_name}' is not in role allowed_action_names.",
                    layer="role_constraints",
                    metadata={"specific_reason": "action_not_in_role_allowlist", "legacy_code": True},
                )
            )

    params = next_action.parameters
    required = descriptor.required_parameter_names()
    provided = set(params.keys())

    for missing in sorted(required - provided):
        issues.append(
            ScriptValidationIssue(
                code="missing_required_parameter",
                message=f"Missing required parameter '{missing}'.",
                layer="script_registry",
            )
        )

    for unknown in sorted(provided - descriptor.parameter_names()):
        issues.append(
            ScriptValidationIssue(
                code="unknown_parameter",
                message=f"Unknown parameter '{unknown}' for action '{action_name}'.",
                layer="script_registry",
            )
        )

    for p in descriptor.parameters:
        if p.name not in params:
            continue
        value = params[p.name]
        if not _value_matches_parameter_type(value, p.type):
            issues.append(
                ScriptValidationIssue(
                    code="wrong_parameter_type",
                    message=f"Parameter '{p.name}' must be type '{p.type}'.",
                    layer="script_registry",
                )
            )
            continue

        if isinstance(value, str):
            if p.min_length is not None and len(value) < p.min_length:
                issues.append(
                    ScriptValidationIssue(
                        code="string_too_short",
                        message=f"Parameter '{p.name}' shorter than min_length {p.min_length}.",
                        layer="script_registry",
                    )
                )
            if p.max_length is not None and len(value) > p.max_length:
                issues.append(
                    ScriptValidationIssue(
                        code="string_too_long",
                        message=f"Parameter '{p.name}' longer than max_length {p.max_length}.",
                        layer="script_registry",
                    )
                )

        if p.allowed_values and value not in p.allowed_values:
            issues.append(
                ScriptValidationIssue(
                    code="value_not_allowed",
                    message=f"Parameter '{p.name}' value not in allowed_values.",
                    layer="script_registry",
                )
            )

    # Basic safety checks: path and command parameters.
    for key, value in params.items():
        if key == "path" and isinstance(value, str):
            safety = descriptor.safety
            normalized_path = _normalize_path(value)
            if _is_unsafe_path(normalized_path):
                issues.append(
                    ScriptValidationIssue(
                        code="unsafe_path",
                        message=f"Path '{value}' is unsafe (absolute, drive-prefixed, or traversal).",
                        layer="safety_policy",
                    )
                )

            if _starts_with_any(normalized_path, [_normalize_path(p) for p in safety.forbidden_file_roots]):
                issues.append(
                    ScriptValidationIssue(
                        code="forbidden_path",
                        message=f"Path '{value}' is under forbidden_file_roots.",
                        layer="safety_policy",
                    )
                )
            if safety.allowed_file_roots and not _starts_with_any(
                normalized_path, [_normalize_path(p) for p in safety.allowed_file_roots]
            ):
                issues.append(
                    ScriptValidationIssue(
                        code="path_outside_allowed_roots",
                        message=f"Path '{value}' is not under allowed_file_roots.",
                        layer="safety_policy",
                    )
                )

            if role_template is not None:
                rc = role_template.constraints
                if rc.forbidden_file_roots and _starts_with_any(
                    normalized_path, [_normalize_path(p) for p in rc.forbidden_file_roots]
                ):
                    issues.append(
                        ScriptValidationIssue(
                            code="forbidden_path",
                            message=f"Path '{value}' is forbidden by role constraints.",
                            layer="role_constraints",
                        )
                    )
                if rc.allowed_file_roots and not _starts_with_any(
                    normalized_path, [_normalize_path(p) for p in rc.allowed_file_roots]
                ):
                    issues.append(
                        ScriptValidationIssue(
                            code="path_outside_allowed_roots",
                            message=f"Path '{value}' is outside role allowed_file_roots.",
                            layer="role_constraints",
                        )
                    )

        if key == "command" and isinstance(value, str):
            safety = descriptor.safety
            if any(substr in value for substr in safety.forbidden_substrings):
                issues.append(
                    ScriptValidationIssue(
                        code="unsafe_action",
                        message="Command contains forbidden substring.",
                        layer="safety_policy",
                        metadata={"specific_reason": "forbidden_substring"},
                    )
                )
                issues.append(
                    ScriptValidationIssue(
                        code="unsafe_command",
                        message="Command contains forbidden substring.",
                        layer="safety_policy",
                        metadata={"specific_reason": "forbidden_substring", "legacy_code": True},
                    )
                )
            if any(value == cmd or value.startswith(cmd) for cmd in safety.forbidden_shell_commands):
                issues.append(
                    ScriptValidationIssue(
                        code="unsafe_action",
                        message="Command matches forbidden_shell_commands.",
                        layer="safety_policy",
                        metadata={"specific_reason": "forbidden_shell_command"},
                    )
                )
                issues.append(
                    ScriptValidationIssue(
                        code="unsafe_command",
                        message="Command matches forbidden_shell_commands.",
                        layer="safety_policy",
                        metadata={"specific_reason": "forbidden_shell_command", "legacy_code": True},
                    )
                )
            if safety.allowed_shell_commands and not _command_matches_allowed(
                value, safety.allowed_shell_commands
            ):
                issues.append(
                    ScriptValidationIssue(
                        code="unsafe_action",
                        message="Command is not in allowed_shell_commands.",
                        layer="safety_policy",
                        metadata={"specific_reason": "command_not_allowlisted"},
                    )
                )
                issues.append(
                    ScriptValidationIssue(
                        code="command_not_allowlisted",
                        message="Command is not in allowed_shell_commands.",
                        layer="safety_policy",
                        metadata={"specific_reason": "command_not_allowlisted", "legacy_code": True},
                    )
                )

    return ScriptValidationResult(
        accepted=not issues,
        action=action_name,
        issues=issues,
        metadata={"registry_id": registry.registry_id},
    )


def issues_to_failure_categories(result: ScriptValidationResult) -> list[str]:
    mapping = {
        "unknown_action": "unknown_action",
        "missing_required_parameter": "missing_required_parameter",
        "wrong_parameter_type": "wrong_parameter_type",
        "forbidden_path": "forbidden_path",
        "unsafe_action": "unsafe_action",
        "forbidden_by_role": "forbidden_by_role",
    }
    categories: list[str] = []
    for issue in result.issues:
        mapped = mapping.get(issue.code)
        if mapped is not None and mapped not in categories:
            categories.append(mapped)
    return categories
