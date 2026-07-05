from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


MODEL_CATALOG_SCHEMA_VERSION = "model_catalog_v1"
ModelCatalogRole = Literal[
    "orchestrator_candidate",
    "executor_candidate",
    "judge_candidate",
]

_ROLE_ALIASES: dict[str, ModelCatalogRole] = {
    "orchestrator": "orchestrator_candidate",
    "orchestrator_candidate": "orchestrator_candidate",
    "executor": "executor_candidate",
    "executor_candidate": "executor_candidate",
    "judge": "judge_candidate",
    "judge_candidate": "judge_candidate",
}
_FORBIDDEN_LOCAL_PATH_PARTS = {
    ".git",
    ".venv",
    "auth.json",
    "credential",
    "credentials",
    "key",
    "keys",
    "logs",
    "secret",
    "secrets",
    "token",
    "tokens",
}


class ModelResourceProfile(BaseModel):
    expected_vram_gb: float | None = None
    expected_ram_gb: float | None = None
    observed_vram_gb: float | None = None
    observed_ram_gb: float | None = None
    notes: str | None = None

    @field_validator(
        "expected_vram_gb",
        "expected_ram_gb",
        "observed_vram_gb",
        "observed_ram_gb",
    )
    @classmethod
    def validate_non_negative_number(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("resource profile numeric fields must be >= 0 when provided.")
        return value

    @field_validator("notes")
    @classmethod
    def validate_optional_notes(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("resource_profile.notes must be non-empty when provided.")
        return value


class ModelRoleProfile(BaseModel):
    orchestrator_candidate: bool = False
    executor_candidate: bool = False
    judge_candidate: bool = False

    @field_validator("orchestrator_candidate", "executor_candidate", "judge_candidate", mode="before")
    @classmethod
    def validate_boolean_flags(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("model role flags must be booleans.")
        return value


class ModelCatalogEntry(BaseModel):
    model_id: str
    display_name: str
    upstream_name: str
    local_path: str
    family: str
    parameter_count_b: float | None = None
    quantization: str
    context_window_tokens: int | None = None
    enabled: bool = True
    roles: ModelRoleProfile = Field(default_factory=ModelRoleProfile)
    historical_aliases: list[str] = Field(default_factory=list)
    historical_observations: list[str] = Field(default_factory=list)
    resource_profile: ModelResourceProfile = Field(default_factory=ModelResourceProfile)
    tags: list[str] = Field(default_factory=list)

    @field_validator(
        "model_id",
        "display_name",
        "upstream_name",
        "local_path",
        "family",
        "quantization",
    )
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model catalog string fields must be non-empty.")
        return cleaned

    @field_validator("enabled", mode="before")
    @classmethod
    def validate_enabled_bool(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("enabled must be a boolean.")
        return value

    @field_validator("parameter_count_b")
    @classmethod
    def validate_parameter_count(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("parameter_count_b must be > 0 when provided.")
        return value

    @field_validator("context_window_tokens")
    @classmethod
    def validate_context_window(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("context_window_tokens must be > 0 when provided.")
        return value

    @field_validator("historical_aliases", "historical_observations", "tags")
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("model catalog string lists must not contain empty values.")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("model catalog string lists must not contain duplicates.")
        return cleaned

    @field_validator("local_path")
    @classmethod
    def validate_relative_model_path(cls, value: str) -> str:
        _validate_safe_relative_local_path(value)
        return value


class ModelCatalog(BaseModel):
    schema_version: str = MODEL_CATALOG_SCHEMA_VERSION
    models: list[ModelCatalogEntry]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != MODEL_CATALOG_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {MODEL_CATALOG_SCHEMA_VERSION}.")
        return value

    @field_validator("models")
    @classmethod
    def validate_models_non_empty(cls, value: list[ModelCatalogEntry]) -> list[ModelCatalogEntry]:
        if not value:
            raise ValueError("models must not be empty.")
        return value

    @model_validator(mode="after")
    def validate_unique_ids_and_aliases(self) -> ModelCatalog:
        errors = validate_model_catalog(self)
        if errors:
            raise ValueError("; ".join(errors))
        return self


def load_model_catalog(path: str | Path) -> ModelCatalog:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ModelCatalog.model_validate(payload)


def validate_model_catalog(catalog: ModelCatalog) -> list[str]:
    errors: list[str] = []
    model_ids = [entry.model_id for entry in catalog.models]
    duplicate_ids = sorted({model_id for model_id in model_ids if model_ids.count(model_id) > 1})
    for model_id in duplicate_ids:
        errors.append(f"duplicate_model_id:{model_id}")

    id_set = set(model_ids)
    aliases: dict[str, str] = {}
    for entry in catalog.models:
        for alias in entry.historical_aliases:
            if alias in id_set:
                errors.append(f"alias_conflicts_with_model_id:{alias}")
            previous = aliases.get(alias)
            if previous is not None:
                errors.append(f"duplicate_alias:{alias}:{previous}:{entry.model_id}")
            aliases[alias] = entry.model_id
    return errors


def get_model_entry(catalog: ModelCatalog, model_id_or_alias: str) -> ModelCatalogEntry:
    requested = model_id_or_alias.strip()
    for entry in catalog.models:
        if entry.model_id == requested or requested in entry.historical_aliases:
            return entry
    raise KeyError(f"Unknown model catalog id or alias: {model_id_or_alias}")


def list_enabled_models(catalog: ModelCatalog) -> list[ModelCatalogEntry]:
    return [entry for entry in catalog.models if entry.enabled]


def list_models_for_role(
    catalog: ModelCatalog,
    role_name: str,
    *,
    enabled_only: bool = True,
) -> list[ModelCatalogEntry]:
    role = _normalize_role_name(role_name)
    entries = list_enabled_models(catalog) if enabled_only else list(catalog.models)
    return [entry for entry in entries if getattr(entry.roles, role)]


def build_candidate_pairs(
    catalog: ModelCatalog,
    *,
    enabled_only: bool = True,
) -> list[dict[str, Any]]:
    orchestrators = list_models_for_role(catalog, "orchestrator", enabled_only=enabled_only)
    executors = list_models_for_role(catalog, "executor", enabled_only=enabled_only)
    pairs: list[dict[str, Any]] = []
    for orchestrator in orchestrators:
        for executor in executors:
            pairs.append(
                {
                    "pair_id": f"{orchestrator.model_id}__to__{executor.model_id}",
                    "pair_label": f"{orchestrator.model_id}->{executor.model_id}",
                    "orchestrator_model_id": orchestrator.model_id,
                    "executor_model_id": executor.model_id,
                    "known_notes": _pair_known_notes(orchestrator, executor),
                    "tags": sorted({*orchestrator.tags, *executor.tags}),
                    "metadata": {
                        "orchestrator": _entry_pair_metadata(orchestrator),
                        "executor": _entry_pair_metadata(executor),
                    },
                }
            )
    return pairs


def model_catalog_entry_metadata(entry: ModelCatalogEntry) -> dict[str, Any]:
    return {
        "model_id": entry.model_id,
        "display_name": entry.display_name,
        "upstream_name": entry.upstream_name,
        "family": entry.family,
        "parameter_count_b": entry.parameter_count_b,
        "quantization": entry.quantization,
        "enabled": entry.enabled,
        "roles": entry.roles.model_dump(mode="json"),
        "historical_aliases": list(entry.historical_aliases),
        "tags": list(entry.tags),
    }


def _normalize_role_name(role_name: str) -> ModelCatalogRole:
    try:
        return _ROLE_ALIASES[role_name.strip()]
    except KeyError as exc:
        raise ValueError(f"Unknown model catalog role: {role_name}") from exc


def _entry_pair_metadata(entry: ModelCatalogEntry) -> dict[str, Any]:
    metadata = model_catalog_entry_metadata(entry)
    metadata.pop("roles", None)
    return metadata


def _pair_known_notes(orchestrator: ModelCatalogEntry, executor: ModelCatalogEntry) -> list[str]:
    notes: list[str] = []
    notes.extend(f"orchestrator:{note}" for note in orchestrator.historical_observations)
    notes.extend(f"executor:{note}" for note in executor.historical_observations)
    return notes


def _validate_safe_relative_local_path(value: str) -> None:
    if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
        raise ValueError("local_path must be a relative path.")
    path = PureWindowsPath(value) if "\\" in value else PurePosixPath(value)
    parts = [part.strip() for part in path.parts if part.strip()]
    lowered = {part.lower() for part in parts}
    if ".." in parts:
        raise ValueError("local_path must not contain parent directory traversal.")
    if lowered & _FORBIDDEN_LOCAL_PATH_PARTS:
        raise ValueError("local_path must not point into forbidden local/private paths.")

