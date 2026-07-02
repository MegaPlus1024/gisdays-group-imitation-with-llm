from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


SupportedEvaluationRuntime = Literal["llama.cpp / llama-server", "llama-server", "llama.cpp"]
PreflightStatus = Literal["pass", "warn", "fail"]
PreflightSeverity = Literal["warning", "error"]


class EvaluationModelSpec(BaseModel):
    model_id: str
    display_name: str
    model_name: str
    gguf_path: str
    quantization: str
    parameter_size: str
    runtime: str
    base_url: str
    api_style: str
    expected_cpu_only: bool
    ctx_size: int
    timeout_seconds: float
    temperature: float
    max_tokens: int
    enabled: bool
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        "model_id",
        "display_name",
        "model_name",
        "gguf_path",
        "quantization",
        "parameter_size",
        "runtime",
        "base_url",
        "api_style",
    )
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evaluation model string fields must be non-empty.")
        return value

    @field_validator("ctx_size", "max_tokens")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ctx_size and max_tokens must be > 0.")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be > 0.")
        return value

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0:
            raise ValueError("temperature must be >= 0.")
        return value


class EvaluationModelsConfig(BaseModel):
    schema_version: str = "evaluation_models_v1"
    models: list[EvaluationModelSpec]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("schema_version must be non-empty.")
        return value

    @field_validator("models")
    @classmethod
    def validate_models_non_empty(cls, value: list[EvaluationModelSpec]) -> list[EvaluationModelSpec]:
        if not value:
            raise ValueError("models must not be empty.")
        return value

    @model_validator(mode="after")
    def validate_unique_model_ids(self) -> EvaluationModelsConfig:
        ids = [model.model_id for model in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("model_id values must be unique.")
        return self


class EvaluationModelPreflightIssue(BaseModel):
    code: str
    message: str
    severity: PreflightSeverity
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationModelPreflightResult(BaseModel):
    model_id: str
    status: PreflightStatus
    issues: list[EvaluationModelPreflightIssue] = Field(default_factory=list)
    warnings: list[EvaluationModelPreflightIssue] = Field(default_factory=list)
    resolved_model_path: str | None = None
    resolved_base_url: str | None = None
    can_attempt_local_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationModelRegistry:
    def __init__(self, config: EvaluationModelsConfig) -> None:
        self.config = config
        self._models = {model.model_id: model for model in config.models}

    def model_ids(self) -> list[str]:
        return sorted(self._models)

    def get(self, model_id: str) -> EvaluationModelSpec | None:
        return self._models.get(model_id)

    def require(self, model_id: str) -> EvaluationModelSpec:
        model = self.get(model_id)
        if model is None:
            raise KeyError(f"Unknown evaluation model_id: {model_id}")
        return model


def load_evaluation_models_config(path: str | Path) -> EvaluationModelsConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvaluationModelsConfig.model_validate(payload)


def resolve_evaluation_model(
    model_id: str,
    config_path: str | Path = "configs/evaluation_models.json",
) -> EvaluationModelSpec:
    registry = EvaluationModelRegistry(load_evaluation_models_config(config_path))
    return registry.require(model_id)


def preflight_evaluation_model(
    model_spec: EvaluationModelSpec,
    project_root: str | Path,
    *,
    require_model_file: bool = False,
    allow_disabled: bool = False,
) -> EvaluationModelPreflightResult:
    project_root_path = Path(project_root).resolve()
    issues: list[EvaluationModelPreflightIssue] = []
    warnings: list[EvaluationModelPreflightIssue] = []

    def add_issue(code: str, message: str, severity: PreflightSeverity, **metadata: Any) -> None:
        target = issues if severity == "error" else warnings
        target.append(
            EvaluationModelPreflightIssue(
                code=code,
                message=message,
                severity=severity,
                metadata=metadata,
            )
        )

    if model_spec.runtime not in {"llama.cpp / llama-server", "llama-server", "llama.cpp"}:
        add_issue(
            "unsupported_runtime",
            f"Unsupported runtime: {model_spec.runtime}",
            "error",
            supported=["llama.cpp / llama-server", "llama-server", "llama.cpp"],
        )

    parsed_base_url = urlparse(model_spec.base_url)
    if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
        add_issue("invalid_base_url", f"Invalid base_url: {model_spec.base_url}", "error")

    resolved_model_path = _resolve_path(project_root_path, model_spec.gguf_path)
    model_file_exists = resolved_model_path.exists() and resolved_model_path.is_file()
    if not model_file_exists:
        severity: PreflightSeverity = "error" if require_model_file else "warning"
        add_issue(
            "model_file_missing",
            f"GGUF model file not found: {resolved_model_path}",
            severity,
            gguf_path=model_spec.gguf_path,
        )

    if not model_spec.enabled and not allow_disabled:
        add_issue(
            "model_disabled",
            f"Model is disabled in evaluation model registry: {model_spec.model_id}",
            "error" if require_model_file else "warning",
        )

    status: PreflightStatus
    if issues:
        status = "fail"
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    can_attempt_local_run = (
        not issues
        and (model_spec.enabled or allow_disabled)
        and model_file_exists
    )

    return EvaluationModelPreflightResult(
        model_id=model_spec.model_id,
        status=status,
        issues=issues,
        warnings=warnings,
        resolved_model_path=str(resolved_model_path),
        resolved_base_url=model_spec.base_url.rstrip("/"),
        can_attempt_local_run=bool(can_attempt_local_run),
        metadata={
            "model_file_exists": model_file_exists,
            "enabled": model_spec.enabled,
            "runtime": model_spec.runtime,
            "api_style": model_spec.api_style,
            "require_model_file": require_model_file,
            "allow_disabled": allow_disabled,
        },
    )


def _resolve_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()
