from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_plan_validation import (
    PLAN_SCHEMA_VERSION,
    VALIDATION_RESULT_SCHEMA_VERSION,
    validate_autonomous_browser_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan.example.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "validate_autonomous_browser_plan.py"


def _load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _result(plan: dict[str, Any]) -> dict[str, Any]:
    return validate_autonomous_browser_plan(plan)


def _rejected_plan(**overrides: Any) -> dict[str, Any]:
    payload = _load_plan(PLAN_PATH)
    payload.update(overrides)
    return payload


def test_valid_example_plan_is_accepted() -> None:
    result = _result(_load_plan(PLAN_PATH))

    assert result["schema_version"] == VALIDATION_RESULT_SCHEMA_VERSION
    assert result["status"] == "accepted"
    assert result["error_code"] is None
    assert result["plan_id"] == "browser_policy_research_plan_v1"
    assert result["actions_total"] == 3
    assert result["allowed_actions"] == [
        "browser_open_url",
        "browser_click",
        "browser_extract_text",
        "browser_fill",
        "browser_submit",
        "browser_wait",
        "browser_search",
        "browser_snapshot",
    ]
    assert result["normalized_plan"]["schema_version"] == PLAN_SCHEMA_VERSION
    assert result["normalized_plan"]["actions"][0]["step_id"] == "open_home"
    assert result["normalized_plan"]["actions"][0]["parameters"]["url"] == "https://local.intranet/"
    assert result["limitations"]
    assert "C:\\" not in json.dumps(result)


def test_unknown_action_is_rejected() -> None:
    payload = _rejected_plan()
    payload["actions"][0]["action_name"] = "browser_not_real"
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == "unknown_browser_action"
    assert result["diagnostics"][0]["finding_type"] == "unknown_browser_action"


def test_external_url_is_rejected() -> None:
    payload = _rejected_plan()
    payload["actions"][0]["parameters"]["url"] = "https://example.com/"
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == "external_url_not_allowed"
    assert result["diagnostics"][0]["path"] == "actions[0].parameters.url"


@pytest.mark.parametrize(
    "url,error_code",
    [
        ("http://localhost:8765/", "loopback_url_not_allowed"),
        ("http://127.0.0.1:8765/", "loopback_url_not_allowed"),
        ("file:///tmp/plan.json", "file_url_not_allowed"),
    ],
)
def test_loopback_file_and_localhost_urls_are_rejected(url: str, error_code: str) -> None:
    payload = _rejected_plan()
    payload["actions"][0]["parameters"]["url"] = url
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == error_code


@pytest.mark.parametrize(
    "url,error_code",
    [
        ("C:\\Temp\\plan.json", "absolute_path_not_allowed"),
        ("/tmp/plan.json", "absolute_path_not_allowed"),
    ],
)
def test_absolute_paths_are_rejected(url: str, error_code: str) -> None:
    payload = _rejected_plan()
    payload["actions"][0]["parameters"]["url"] = url
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == error_code


def test_url_credentials_are_rejected_without_leaking_secret() -> None:
    payload = _rejected_plan()
    payload["actions"][0]["parameters"]["url"] = "https://user:supersecret@local.intranet/"
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == "url_credentials_not_allowed"
    diagnostics = json.dumps(result)
    assert "supersecret" not in diagnostics
    assert "user" not in diagnostics


def test_secret_like_parameter_key_or_value_is_rejected_without_printing_secret() -> None:
    payload = _rejected_plan()
    payload["actions"][0]["parameters"] = {"api_key": "super-secret-token"}
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == "secret_like_parameter_key"
    diagnostics = json.dumps(result)
    assert "super-secret-token" not in diagnostics
    assert "api_key" in diagnostics


def test_secret_like_parameter_value_keeps_redacted_key_hint() -> None:
    payload = _rejected_plan()
    payload["actions"][0]["parameters"]["query"] = "api_key=supersecret"
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == "secret_like_parameter_value"
    diagnostics = json.dumps(result)
    assert "supersecret" not in diagnostics
    assert "api_key" in diagnostics


def test_too_many_actions_is_rejected() -> None:
    payload = _rejected_plan(max_actions=1)
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == "max_actions_exceeded"


def test_duplicate_step_id_is_rejected() -> None:
    payload = _rejected_plan()
    payload["actions"].append(dict(payload["actions"][0]))
    result = _result(payload)

    assert result["status"] == "rejected"
    assert result["error_code"] == "duplicate_step_id"


def test_cli_accepts_example_plan_and_prints_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--plan", str(PLAN_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["status"] == "accepted"
    assert payload["schema_version"] == VALIDATION_RESULT_SCHEMA_VERSION
    assert "\n" not in completed.stdout.strip()


def test_cli_rejects_invalid_plan_with_structured_json(tmp_path: Path) -> None:
    plan = _rejected_plan()
    plan["actions"][0]["action_name"] = "browser_bad"
    path = tmp_path / "bad_plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=True, indent=2), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--plan", str(path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode != 0
    assert payload["status"] == "rejected"
    assert payload["error_code"] == "unknown_browser_action"
    assert payload["schema_version"] == VALIDATION_RESULT_SCHEMA_VERSION


def test_plan_validator_imports_without_playwright_or_browser_runtime() -> None:
    spec = importlib.util.spec_from_file_location("validate_autonomous_browser_plan_test_module", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "playwright" not in sys.modules


def test_validator_does_not_execute_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = validate_autonomous_browser_plan(_load_plan(PLAN_PATH))

    assert result["status"] == "accepted"
