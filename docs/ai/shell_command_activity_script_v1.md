# Shell Command Activity Script v1

## Purpose

Define a safe, allowlist-only shell command activity script for controlled project diagnostics.

## Scope

- Supports only pre-approved commands.
- Uses `subprocess.run(..., shell=False)` only.
- Runs inside configured `project_root`.

## Out of scope

- No arbitrary shell access.
- No PowerShell execution.
- No `cmd /c`.
- No internet download commands (`curl`, `wget`, `Invoke-WebRequest`).
- No package installation (`winget install`).
- No destructive command support.
- No executor/runner/full agent loop logic.

## Default allowed commands

- `python -m pytest -q`
- `python scripts\run_llama_smoke.py --help`
- `python scripts\run_runtime_baseline.py --help`
- `python scripts\compare_runtime_baselines.py --help`

## API

- `normalize_command(command)`
- `validate_shell_command(command, config)`
- `run_allowed_shell_command(command, config)`
- `simulate_shell_command(command, config)`
- `run_shell_command_activity(parameters, config)`

## Behavior summary

- Unknown or unsafe commands return structured failed `ScriptExecutionResult`.
- `simulate_shell_command` validates but does not execute.
- timeouts and non-zero exits are converted to structured failures.
