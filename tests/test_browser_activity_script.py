from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.scripts.browser_activity import (
    BrowserActivityConfig,
    BrowserActivityParameterError,
    UnsafeBrowserUrlError,
    fill_form_stub,
    normalize_url,
    open_url,
    read_page_summary,
    run_browser_activity,
    search_web,
    validate_browser_url,
)


def test_browser_activity_config_defaults_are_valid() -> None:
    cfg = BrowserActivityConfig()
    assert cfg.simulated_only is True
    assert "http" in cfg.allowed_schemes


def test_browser_activity_config_rejects_simulated_only_false() -> None:
    with pytest.raises(ValidationError):
        BrowserActivityConfig(simulated_only=False)


def test_normalize_url_strips_whitespace() -> None:
    assert normalize_url("  http://localhost:8080  ") == "http://localhost:8080"


def test_validate_browser_url_accepts_localhost() -> None:
    cfg = BrowserActivityConfig()
    assert validate_browser_url("http://localhost:8080", cfg) == "http://localhost:8080"


def test_validate_browser_url_accepts_loopback() -> None:
    cfg = BrowserActivityConfig()
    assert validate_browser_url("http://127.0.0.1:8080", cfg) == "http://127.0.0.1:8080"


def test_validate_browser_url_rejects_empty_url() -> None:
    cfg = BrowserActivityConfig()
    with pytest.raises(BrowserActivityParameterError):
        validate_browser_url("", cfg)


def test_validate_browser_url_rejects_missing_scheme() -> None:
    cfg = BrowserActivityConfig()
    with pytest.raises(UnsafeBrowserUrlError):
        validate_browser_url("localhost:8080", cfg)


def test_validate_browser_url_rejects_javascript_scheme() -> None:
    cfg = BrowserActivityConfig()
    with pytest.raises(UnsafeBrowserUrlError):
        validate_browser_url("javascript:alert(1)", cfg)


def test_validate_browser_url_rejects_data_scheme() -> None:
    cfg = BrowserActivityConfig()
    with pytest.raises(UnsafeBrowserUrlError):
        validate_browser_url("data:text/plain,hello", cfg)


def test_validate_browser_url_rejects_file_url_by_default() -> None:
    cfg = BrowserActivityConfig()
    with pytest.raises(UnsafeBrowserUrlError):
        validate_browser_url("file:///tmp/x.txt", cfg)


def test_validate_browser_url_rejects_external_host_by_default() -> None:
    cfg = BrowserActivityConfig()
    with pytest.raises(UnsafeBrowserUrlError):
        validate_browser_url("https://example.com", cfg)


def test_validate_browser_url_accepts_external_when_enabled() -> None:
    cfg = BrowserActivityConfig(allow_external_hosts=True)
    assert validate_browser_url("https://example.com", cfg) == "https://example.com"


def test_validate_browser_url_rejects_credential_url() -> None:
    cfg = BrowserActivityConfig()
    with pytest.raises(UnsafeBrowserUrlError):
        validate_browser_url("http://user:pass@localhost:8080", cfg)


def test_open_url_returns_success_and_browser_not_opened() -> None:
    cfg = BrowserActivityConfig()
    result = open_url("http://localhost:8080", cfg)
    assert result.success is True
    assert result.metadata["browser_opened"] is False


def test_search_web_returns_success_and_network_false() -> None:
    cfg = BrowserActivityConfig()
    result = search_web("local llm", cfg)
    assert result.success is True
    assert result.metadata["network_used"] is False


def test_search_web_rejects_empty_query() -> None:
    cfg = BrowserActivityConfig()
    result = search_web("", cfg)
    assert result.success is False
    assert result.error_type == "invalid_parameter"


def test_search_web_rejects_too_long_query() -> None:
    cfg = BrowserActivityConfig(max_query_length=3)
    result = search_web("abcd", cfg)
    assert result.success is False
    assert result.error_type == "invalid_parameter"


def test_read_page_summary_returns_simulated_result() -> None:
    cfg = BrowserActivityConfig()
    result = read_page_summary("http://localhost:8080", cfg)
    assert result.success is True
    assert result.metadata["simulated"] is True
    assert result.metadata["network_used"] is False


def test_fill_form_stub_returns_simulated_result() -> None:
    cfg = BrowserActivityConfig()
    result = fill_form_stub("http://localhost:8080/form", {"x": "1"}, cfg)
    assert result.success is True
    assert result.metadata["submitted"] is False


def test_fill_form_stub_rejects_non_dict_fields() -> None:
    cfg = BrowserActivityConfig()
    result = fill_form_stub("http://localhost:8080/form", "x", cfg)  # type: ignore[arg-type]
    assert result.success is False
    assert result.error_type == "invalid_parameter"


def test_run_browser_activity_dispatches_open_url() -> None:
    cfg = BrowserActivityConfig()
    result = run_browser_activity("open_url", {"url": "http://localhost:8080"}, cfg)
    assert result.success is True
    assert result.action == "open_url"


def test_run_browser_activity_rejects_unknown_action() -> None:
    cfg = BrowserActivityConfig()
    result = run_browser_activity("x", {}, cfg)
    assert result.success is False
    assert result.error_type == "unknown_browser_action"


def test_run_browser_activity_rejects_missing_url_for_open_url() -> None:
    cfg = BrowserActivityConfig()
    result = run_browser_activity("open_url", {}, cfg)
    assert result.success is False
    assert result.error_type == "missing_parameter"


def test_run_browser_activity_returns_unsafe_url_for_unsafe_input() -> None:
    cfg = BrowserActivityConfig()
    result = run_browser_activity("open_url", {"url": "javascript:alert(1)"}, cfg)
    assert result.success is False
    assert result.error_type == "unsafe_url"
