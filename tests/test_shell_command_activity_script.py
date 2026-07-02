from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.scripts.shell_command_activity import (
    ShellCommandActivityConfig,
    normalize_command,
    run_allowed_shell_command,
    run_shell_command_activity,
    simulate_shell_command,
    validate_shell_command,
)


def make_config() -> ShellCommandActivityConfig:
    return ShellCommandActivityConfig(project_root=Path.cwd())


def test_normalize_command_compacts_whitespace() -> None:
    assert normalize_command("  python   -m   pytest   -q  ") == "python -m pytest -q"


def test_unsafe_commands_are_rejected() -> None:
    cfg = make_config()
    with pytest.raises(ValueError):
        validate_shell_command("powershell -Command whoami", cfg)
    with pytest.raises(ValueError):
        validate_shell_command("cmd /c dir", cfg)
    with pytest.raises(ValueError):
        validate_shell_command("curl https://example.com", cfg)


def test_unknown_commands_are_rejected() -> None:
    cfg = make_config()
    with pytest.raises(ValueError):
        validate_shell_command("python -m pip list", cfg)


def test_simulate_shell_command_does_not_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"run": False}

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        called["run"] = True
        raise AssertionError("subprocess.run should not be called in simulation")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = make_config()
    result = simulate_shell_command("python -m pytest -q", cfg)
    assert result.success is True
    assert called["run"] is False
    assert result.metadata.get("simulated") is True


def test_run_allowed_shell_command_uses_shell_false_and_project_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(*args: Any, **kwargs: Any) -> Completed:
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = make_config()
    result = run_allowed_shell_command("python -m pytest -q", cfg)
    assert result.success is True
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["cwd"] == str(cfg.project_root)


def test_run_shell_command_activity_dispatches_simulate_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"run": False}

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        called["run"] = True
        raise AssertionError("must not run in simulate mode")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = make_config()
    result = run_shell_command_activity(
        {"command": "python -m pytest -q", "simulate": True}, cfg
    )
    assert result.success is True
    assert result.metadata.get("simulated") is True
    assert called["run"] is False


def test_run_shell_command_activity_dispatches_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        returncode = 0
        stdout = "help"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Completed())
    cfg = make_config()
    result = run_shell_command_activity(
        {"command": r"python scripts\run_llama_smoke.py --help"}, cfg
    )
    assert result.success is True


def test_timeout_converted_to_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = make_config()
    result = run_allowed_shell_command("python -m pytest -q", cfg)
    assert result.success is False
    assert result.error_type == "command_timeout"


def test_command_failure_converted_to_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        returncode = 2
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Completed())
    cfg = make_config()
    result = run_allowed_shell_command("python -m pytest -q", cfg)
    assert result.success is False
    assert result.error_type == "command_failed"
