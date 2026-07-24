from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.schemas import NextAction
from src.agent.script_execution_bridge import (
    ScriptExecutionBridge,
    ScriptExecutionBridgeConfig,
)
from src.agent.script_registry import load_script_registry
from src.agent.scripts.results import ScriptExecutionResult


def _registry() -> object:
    return load_script_registry("configs/script_registry.example.json")


def test_validation_failure_prevents_helper_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bridge = ScriptExecutionBridge(
        ScriptExecutionBridgeConfig(project_root=tmp_path, validate_with_registry=True),
        registry=_registry(),
    )
    called = {"value": False}

    def fail_if_called(*args, **kwargs):  # type: ignore[no-untyped-def]
        called["value"] = True
        raise AssertionError("run_file_activity should not be called")

    monkeypatch.setattr("src.agent.script_execution_bridge.run_file_activity", fail_if_called)

    action = NextAction(
        action_name="read_file",
        parameters={},
    )
    out = bridge.execute_next_action(action)
    assert out.success is False
    assert out.dispatched is False
    assert out.validation_passed is False
    assert called["value"] is False


def test_dispatch_read_file_uses_tmp_path(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "x.txt").write_text("hello", encoding="utf-8")

    bridge = ScriptExecutionBridge(
        ScriptExecutionBridgeConfig(project_root=tmp_path, validate_with_registry=True),
        registry=_registry(),
    )
    action = NextAction(
        action_name="read_file",
        parameters={"path": "docs/x.txt"},
    )
    out = bridge.execute_next_action(action)
    assert out.success is True
    assert out.dispatched is True
    assert out.raw_result.output == "hello"


def test_dispatch_unsupported_action_returns_dispatch_failed(tmp_path: Path) -> None:
    bridge = ScriptExecutionBridge(
        ScriptExecutionBridgeConfig(
            project_root=tmp_path,
            validate_with_registry=False,
            normalize_result=True,
        ),
        registry=None,
    )
    action = NextAction(
        action_name="unknown_action_name",
        parameters={},
    )
    out = bridge.execute_next_action(action)
    assert out.success is False
    assert out.dispatched is False
    assert out.raw_result.error_type == "dispatch_failed"
    assert out.normalized_result is not None


def test_normalized_result_present_when_enabled(tmp_path: Path) -> None:
    bridge = ScriptExecutionBridge(
        ScriptExecutionBridgeConfig(
            project_root=tmp_path,
            validate_with_registry=False,
            normalize_result=True,
        )
    )
    action = NextAction(
        action_name="run_shell_command",
        parameters={"command": "python -m pytest -q", "simulate": True},
    )
    out = bridge.execute_next_action(action)
    assert out.dispatched is True
    assert out.normalized_result is not None


def test_shell_helper_can_be_monkeypatched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = ScriptExecutionBridge(
        ScriptExecutionBridgeConfig(project_root=tmp_path, validate_with_registry=False)
    )

    def fake_shell(parameters, config):  # type: ignore[no-untyped-def]
        return ScriptExecutionResult(
            action="run_shell_command",
            success=True,
            output="fake-shell",
            metadata={"patched": True},
        )

    monkeypatch.setattr("src.agent.script_execution_bridge.run_shell_command_activity", fake_shell)
    action = NextAction(
        action_name="run_shell_command",
        parameters={"command": "python -m pytest -q"},
    )
    out = bridge.execute_next_action(action)
    assert out.success is True
    assert out.raw_result.output == "fake-shell"
    assert out.raw_result.metadata["patched"] is True
