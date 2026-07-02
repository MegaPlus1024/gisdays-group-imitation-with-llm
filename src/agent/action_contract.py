from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from .schemas import NextAction


class NextActionContractError(Exception):
    """Base error for NextAction contract parsing/validation."""


class NextActionJSONError(NextActionContractError):
    """Raised when next-action text is not valid JSON."""


class NextActionValidationError(NextActionContractError):
    """Raised when JSON does not match the NextAction contract."""


def parse_next_action_text(text: str) -> NextAction:
    if not isinstance(text, str):
        raise NextActionValidationError("Next-action input must be a string.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NextActionJSONError(f"Invalid JSON output: {exc}") from exc

    if not isinstance(payload, dict):
        raise NextActionValidationError("Next-action JSON must be an object.")

    try:
        return NextAction.model_validate(payload)
    except ValidationError as exc:
        raise NextActionValidationError(
            f"Next-action JSON failed schema validation: {exc}"
        ) from exc
