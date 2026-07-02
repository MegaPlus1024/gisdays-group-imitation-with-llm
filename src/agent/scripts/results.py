from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ScriptExecutionResult(BaseModel):
    action: str
    success: bool
    output: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_error_shape(self) -> ScriptExecutionResult:
        if self.success:
            if self.error_type is not None or self.error_message is not None:
                raise ValueError(
                    "error_type and error_message must be None when success=True."
                )
        else:
            if not self.error_type or not self.error_type.strip():
                raise ValueError("error_type must be non-empty when success=False.")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message must be non-empty when success=False.")
        return self
