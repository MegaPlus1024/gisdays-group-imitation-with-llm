from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str
    expected_result: str

    @field_validator("action", "reason", "expected_result")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be empty.")
        return value


class RuntimeConfig(BaseModel):
    name: str
    mode: str
    host: str
    port: int
    base_url: str
    api_style: str


class PythonConfig(BaseModel):
    version: str
    packages: list[str]


class ModelConfig(BaseModel):
    format: str
    path: str
    size_class: str
    quantization_target: str
    context_size: int


class HardwareConfig(BaseModel):
    first_assumption: str
    gpu_required: bool
    gpu_optional_later: bool


class LoggingConfig(BaseModel):
    log_model_filename: bool
    log_prompt_tokens: bool
    log_output_tokens: bool
    log_wall_time: bool
    log_ram_usage: bool
    log_cpu_usage: bool
    log_errors: bool


class AgentContractConfig(BaseModel):
    output_format: dict[str, str]
    reject_if: list[str]


class ProjectRuntimeConfig(BaseModel):
    runtime: RuntimeConfig
    python: PythonConfig
    model: ModelConfig
    hardware: HardwareConfig
    logging: LoggingConfig
    agent_contract: AgentContractConfig
