from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from .results import ScriptExecutionResult


class BrowserActivityError(Exception):
    pass


class UnsafeBrowserUrlError(BrowserActivityError):
    pass


class BrowserActivityParameterError(BrowserActivityError):
    pass


class BrowserActivityConfig(BaseModel):
    allowed_schemes: list[str] = Field(default_factory=lambda: ["http", "https"])
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    forbidden_hosts: list[str] = Field(default_factory=list)
    allow_external_hosts: bool = False
    allow_file_urls: bool = False
    max_url_length: int = 2048
    max_query_length: int = 500
    simulated_only: bool = True

    @field_validator("max_url_length", "max_query_length")
    @classmethod
    def validate_positive_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Limits must be > 0.")
        return value

    @model_validator(mode="after")
    def validate_unique_and_simulated(self) -> BrowserActivityConfig:
        if len(self.allowed_schemes) != len(set(self.allowed_schemes)):
            raise ValueError("allowed_schemes must not contain duplicates.")
        if len(self.allowed_hosts) != len(set(self.allowed_hosts)):
            raise ValueError("allowed_hosts must not contain duplicates.")
        if len(self.forbidden_hosts) != len(set(self.forbidden_hosts)):
            raise ValueError("forbidden_hosts must not contain duplicates.")
        if not self.simulated_only:
            raise ValueError("BrowserActivityConfig v1 supports simulated_only=True only.")
        return self


def normalize_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise BrowserActivityParameterError("URL must be a non-empty string.")
    return url.strip()


def validate_browser_url(url: str, config: BrowserActivityConfig) -> str:
    normalized = normalize_url(url)
    if len(normalized) > config.max_url_length:
        raise UnsafeBrowserUrlError("URL exceeds max_url_length.")

    parsed = urlparse(normalized)
    scheme = (parsed.scheme or "").lower()
    if not scheme:
        raise UnsafeBrowserUrlError("URL scheme is required.")

    forbidden_schemes = {"javascript", "data", "about", "chrome", "edge", "powershell", "cmd"}
    if scheme in forbidden_schemes:
        raise UnsafeBrowserUrlError(f"Scheme '{scheme}' is not allowed.")
    if scheme == "file" and not config.allow_file_urls:
        raise UnsafeBrowserUrlError("file:// URLs are not allowed.")
    if scheme not in config.allowed_schemes:
        raise UnsafeBrowserUrlError(f"Scheme '{scheme}' is not in allowed_schemes.")

    if parsed.username or parsed.password:
        raise UnsafeBrowserUrlError("Credential URLs are not allowed.")

    host = parsed.hostname
    if scheme in {"http", "https"} and not host:
        raise UnsafeBrowserUrlError("Host is required for http/https URLs.")
    if host:
        host_lower = host.lower()
        if host_lower in {h.lower() for h in config.forbidden_hosts}:
            raise UnsafeBrowserUrlError(f"Host '{host}' is forbidden.")
        if not config.allow_external_hosts:
            allowed = {h.lower() for h in config.allowed_hosts}
            if host_lower not in allowed:
                raise UnsafeBrowserUrlError(f"External host '{host}' is not allowed.")

    return normalized


def _error(action: str, error_type: str, error_message: str, **metadata: Any) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        action=action,
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata=metadata,
    )


def open_url(url: str, config: BrowserActivityConfig) -> ScriptExecutionResult:
    action = "open_url"
    validated = validate_browser_url(url, config)
    return ScriptExecutionResult(
        action=action,
        success=True,
        output="Navigation request validated and simulated. No browser was opened.",
        metadata={"url": validated, "simulated": True, "browser_opened": False},
    )


def search_web(query: str, config: BrowserActivityConfig) -> ScriptExecutionResult:
    action = "search_web"
    if not isinstance(query, str) or not query.strip():
        return _error(action, "invalid_parameter", "query must be a non-empty string.")
    normalized = query.strip()
    if len(normalized) > config.max_query_length:
        return _error(action, "invalid_parameter", "query exceeds max_query_length.")
    return ScriptExecutionResult(
        action=action,
        success=True,
        output="Search query validated and simulated. No network request was made.",
        metadata={
            "query": normalized,
            "simulated": True,
            "browser_opened": False,
            "network_used": False,
        },
    )


def read_page_summary(url: str, config: BrowserActivityConfig) -> ScriptExecutionResult:
    action = "read_page_summary"
    validated = validate_browser_url(url, config)
    return ScriptExecutionResult(
        action=action,
        success=True,
        output="Page summary action validated and simulated. Future browser automation is required for real page reading.",
        metadata={
            "url": validated,
            "simulated": True,
            "browser_opened": False,
            "network_used": False,
        },
    )


def fill_form_stub(
    url: str, fields: dict[str, str], config: BrowserActivityConfig
) -> ScriptExecutionResult:
    action = "fill_form_stub"
    validated = validate_browser_url(url, config)
    if not isinstance(fields, dict):
        return _error(action, "invalid_parameter", "fields must be a dict.")
    for key, value in fields.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return _error(action, "invalid_parameter", "fields keys and values must be strings.")
    return ScriptExecutionResult(
        action=action,
        success=True,
        output="Form fill request validated and simulated. No form was submitted.",
        metadata={
            "url": validated,
            "field_count": len(fields),
            "simulated": True,
            "submitted": False,
            "browser_opened": False,
            "network_used": False,
        },
    )


def run_browser_activity(
    action: str, parameters: dict[str, Any], config: BrowserActivityConfig
) -> ScriptExecutionResult:
    try:
        if action == "open_url":
            if "url" not in parameters:
                return _error(action, "missing_parameter", "Missing required parameter: url")
            return open_url(parameters["url"], config)
        if action == "search_web":
            if "query" not in parameters:
                return _error(action, "missing_parameter", "Missing required parameter: query")
            return search_web(parameters["query"], config)
        if action == "read_page_summary":
            if "url" not in parameters:
                return _error(action, "missing_parameter", "Missing required parameter: url")
            return read_page_summary(parameters["url"], config)
        if action == "fill_form_stub":
            if "url" not in parameters:
                return _error(action, "missing_parameter", "Missing required parameter: url")
            if "fields" not in parameters:
                return _error(action, "missing_parameter", "Missing required parameter: fields")
            return fill_form_stub(parameters["url"], parameters["fields"], config)

        return _error(
            action if isinstance(action, str) and action.strip() else "unknown",
            "unknown_browser_action",
            f"Unknown browser action: {action}",
        )
    except UnsafeBrowserUrlError as exc:
        return _error(
            action if isinstance(action, str) and action.strip() else "unknown",
            "unsafe_url",
            str(exc),
        )
    except BrowserActivityParameterError as exc:
        return _error(
            action if isinstance(action, str) and action.strip() else "unknown",
            "invalid_parameter",
            str(exc),
        )
