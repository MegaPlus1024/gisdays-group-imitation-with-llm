from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections.abc import Callable
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_playwright_operator import (
    REQUIRED_ALLOW_FLAG,
    REQUIRED_CONFIRM_VALUE,
    PlaywrightOperatorConfigError,
    build_playwright_operator_packet,
    load_playwright_operator_config,
    validate_playwright_operator_config,
)
from src.agent.autonomous_browser_playwright_execution import (
    PlaywrightExecutionConfig,
    run_guarded_playwright_suite,
    run_guarded_playwright_smoke,
)
from src.agent.autonomous_runtime_scenarios import (
    AutonomousRuntimeScenarioValidationError,
    write_autonomous_runtime_scenario_summary,
)


def main(
    argv: list[str] | None = None,
    *,
    execution_runner: Callable[[PlaywrightExecutionConfig], Any] = run_guarded_playwright_smoke,
    suite_execution_runner: Callable[[PlaywrightExecutionConfig], Any] = run_guarded_playwright_suite,
) -> int:
    parser = argparse.ArgumentParser(description="Prepare guarded Playwright browser operator readiness.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--packet-output")
    parser.add_argument("--allow-real-browser", action="store_true")
    parser.add_argument("--confirm-real-browser")
    args = parser.parse_args(argv)

    try:
        config = load_playwright_operator_config(args.config)
        readiness = validate_playwright_operator_config(config, repo_root=PROJECT_ROOT)
        packet = None
        if args.packet_output:
            packet = build_playwright_operator_packet(
                config,
                config_path=_display_arg_path(args.config),
                packet_output_dir=args.packet_output,
                repo_root=PROJECT_ROOT,
            )
        if args.output:
            write_autonomous_runtime_scenario_summary(readiness.to_dict(), args.output)
    except (PlaywrightOperatorConfigError, AutonomousRuntimeScenarioValidationError) as exc:
        _emit({"status": "invalid_input", "error": str(exc), "no_runtime_execution": True})
        return 2
    except OSError:
        _emit({"status": "write_failed", "error": "playwright_operator_output_write_failed", "no_runtime_execution": True})
        return 1

    if args.dry_run:
        _emit(
            {
                "status": "ready" if readiness.ready else "not_ready",
                "readiness": readiness.to_dict(),
                "packet": packet.to_dict() if packet else None,
                "dry_run": True,
                "no_runtime_execution": True,
            }
        )
        return 0 if readiness.ready else 1

    guard_error = _guard_error(args.allow_real_browser, args.confirm_real_browser)
    if guard_error is not None:
        _emit(
            {
                "status": "refused",
                "error": guard_error,
                "required_operator_guards": readiness.to_dict()["required_operator_guards"],
                "no_runtime_execution": True,
            }
        )
        return 2

    if not readiness.ready:
        _emit({"status": "not_ready", "readiness": readiness.to_dict(), "no_runtime_execution": True})
        return 1

    execution_config = PlaywrightExecutionConfig.from_operator_config(config, repo_root=PROJECT_ROOT)
    summary = suite_execution_runner(execution_config) if _execution_scope_mode(config.execution_scope) == "suite" else execution_runner(execution_config)
    if config.output_dir:
        output_path = Path(config.output_dir) / _summary_filename(config.execution_scope)
        write_autonomous_runtime_scenario_summary(summary.to_dict(), output_path)
    _emit(summary.to_dict())
    return 0 if summary.status == "succeeded" else 1


def _guard_error(allow_real_browser: bool, confirm_real_browser: str | None) -> str | None:
    if not allow_real_browser:
        return f"missing_required_guard:{REQUIRED_ALLOW_FLAG}"
    if confirm_real_browser != REQUIRED_CONFIRM_VALUE:
        return "missing_or_invalid_confirm_real_browser"
    return None


def _display_arg_path(value: str) -> str:
    try:
        return Path(value).resolve(strict=False).relative_to(PROJECT_ROOT.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        try:
            return Path(value).resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
        except (OSError, ValueError):
            return Path(value).name


def _execution_scope_mode(execution_scope: dict[str, Any]) -> str:
    mode = execution_scope.get("mode", "first_scenario_only")
    return str(mode)


def _summary_filename(execution_scope: dict[str, Any]) -> str:
    return "playwright_suite_summary.json" if _execution_scope_mode(execution_scope) == "suite" else "playwright_smoke_summary.json"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
