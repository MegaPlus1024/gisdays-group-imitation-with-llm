from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_plan_fixture_execution import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_plan_fixture_execution,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline fixture-backed execution for a validated browser plan.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        output_dir_value = args.output_dir or config.get("output_dir")
        summary = run_autonomous_browser_plan_fixture_execution(
            _resolve_repo_path(str(config["plan_path"])),
            repo_root=PROJECT_ROOT,
            runtime_id=config["runtime_id"],
            agent_id=config["agent_id"],
            task_id=config["task_id"],
        )
        if output_dir_value:
            output_dir = _resolve_repo_path(str(output_dir_value))
            output_dir.mkdir(parents=True, exist_ok=True)
            summary_path = output_dir / "autonomous_browser_plan_fixture_execution_summary.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        _emit(summary)
        return 0 if summary.get("status") == "succeeded" else 1
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "real_browser_execution": False,
        }
        _emit(payload)
        return 2


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_plan_fixture_execution_config_v1.")
    if payload.get("no_runtime_execution") is not True:
        raise ValueError("no_runtime_execution must be true.")
    plan_path = _safe_relative_path(str(payload.get("plan_path", "")), "plan_path")
    runtime_id = _safe_identifier(payload.get("runtime_id", "browser_plan_fixture_runtime"), "runtime_id")
    agent_id = _safe_identifier(payload.get("agent_id", "browser_plan_executor"), "agent_id")
    task_id = _safe_identifier(payload.get("task_id", "browser_plan_fixture_task"), "task_id")
    output_dir = payload.get("output_dir")
    if output_dir is not None:
        output_dir = _safe_relative_path(str(output_dir), "output_dir")
    return {
        "plan_path": plan_path,
        "runtime_id": runtime_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "output_dir": output_dir,
    }


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _safe_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        raise ValueError(f"{label} must be a safe identifier.")
    return stripped


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise ValueError(f"{label} must be non-empty.")
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        raise ValueError(f"{label} must be a safe relative path.")
    return path.as_posix()


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
