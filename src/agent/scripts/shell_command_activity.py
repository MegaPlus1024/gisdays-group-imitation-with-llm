from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .results import ScriptExecutionResult


class ShellCommandActivityConfig(BaseModel):
    project_root: Path
    allowed_commands: list[str] = Field(
        default_factory=lambda: [
            "python -m pytest -q",
            r"python scripts\run_llama_smoke.py --help",
            r"python scripts\run_runtime_baseline.py --help",
            r"python scripts\compare_runtime_baselines.py --help",
        ]
    )
    timeout_seconds: float = 120.0
    default_encoding: str = "utf-8"

    @field_validator("project_root")
    @classmethod
    def validate_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be > 0.")
        return value


def _error(action: str, error_type: str, error_message: str, **metadata: Any) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        action=action,
        success=False,
        error_type=error_type,
        error_message=error_message,
        metadata=metadata,
    )


def normalize_command(command: str) -> str:
    if not isinstance(command, str):
        raise ValueError("command must be a string.")
    normalized = " ".join(command.strip().split())
    if not normalized:
        raise ValueError("command must be non-empty.")
    return normalized


def validate_shell_command(command: str, config: ShellCommandActivityConfig) -> str:
    normalized = normalize_command(command)
    lower = normalized.lower()

    blocked_fragments = [
        "powershell",
        "pwsh",
        "cmd /c",
        "curl ",
        "wget ",
        "invoke-webrequest",
        "winget install",
        "rm ",
        "rmdir ",
        "del ",
        "format ",
        "shutdown ",
        "reboot ",
        "mkfs",
    ]
    for fragment in blocked_fragments:
        if fragment in lower:
            raise ValueError(f"Command contains blocked fragment: {fragment.strip()}")

    allowed = {normalize_command(cmd) for cmd in config.allowed_commands}
    if normalized not in allowed:
        raise ValueError("Command is not in allowlist.")
    return normalized


def run_allowed_shell_command(
    command: str, config: ShellCommandActivityConfig
) -> ScriptExecutionResult:
    action = "run_shell_command"
    try:
        normalized = validate_shell_command(command, config)
    except ValueError as exc:
        return _error(action, "invalid_shell_command", str(exc), command=command)

    argv = shlex.split(normalized, posix=False)
    if not argv:
        return _error(action, "invalid_shell_command", "Command split is empty.", command=command)

    start = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(config.project_root),
            shell=False,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            encoding=config.default_encoding,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - start, 6)
        return _error(
            action,
            "command_timeout",
            f"Command timed out after {config.timeout_seconds} seconds.",
            command=normalized,
            timeout_seconds=config.timeout_seconds,
            wall_time_seconds=duration,
        )
    except Exception as exc:  # pragma: no cover - defensive
        duration = round(time.perf_counter() - start, 6)
        return _error(
            action,
            "command_execution_error",
            str(exc),
            command=normalized,
            wall_time_seconds=duration,
        )

    duration = round(time.perf_counter() - start, 6)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    output = stdout if stdout else stderr

    if completed.returncode != 0:
        return _error(
            action,
            "command_failed",
            f"Command exited with code {completed.returncode}.",
            command=normalized,
            returncode=completed.returncode,
            stderr=stderr,
            stdout=stdout,
            wall_time_seconds=duration,
        )

    return ScriptExecutionResult(
        action=action,
        success=True,
        output=output,
        metadata={
            "command": normalized,
            "returncode": completed.returncode,
            "stderr": stderr,
            "stdout": stdout,
            "wall_time_seconds": duration,
        },
    )


def simulate_shell_command(
    command: str, config: ShellCommandActivityConfig
) -> ScriptExecutionResult:
    action = "run_shell_command"
    try:
        normalized = validate_shell_command(command, config)
    except ValueError as exc:
        return _error(action, "invalid_shell_command", str(exc), command=command)

    return ScriptExecutionResult(
        action=action,
        success=True,
        output=f"SIMULATED: {normalized}",
        metadata={"command": normalized, "simulated": True},
    )


def run_shell_command_activity(
    parameters: dict[str, Any],
    config: ShellCommandActivityConfig,
) -> ScriptExecutionResult:
    action = "run_shell_command"
    command = parameters.get("command")
    if not isinstance(command, str):
        return _error(
            action,
            "invalid_parameter",
            "Missing or invalid required parameter: command",
            parameters=parameters,
        )

    simulate = bool(parameters.get("simulate", False))
    if simulate:
        return simulate_shell_command(command, config)
    return run_allowed_shell_command(command, config)
