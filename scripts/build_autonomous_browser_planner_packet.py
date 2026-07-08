from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_planner_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    build_autonomous_browser_planner_packet,
    write_autonomous_browser_planner_packet,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an offline planner prompt packet for future browser tasks.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        packet = build_autonomous_browser_planner_packet(
            packet_id=config["packet_id"],
            candidate_plan_example_path=config["candidate_plan_example_path"],
        )
        paths = write_autonomous_browser_planner_packet(packet, _resolve_repo_path(config["output_dir"]))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _emit(
            {
                "status": "failed",
                "error_code": "config_validation_failed",
                "error_message": str(exc),
                "no_runtime_execution": True,
            }
        )
        return 2

    _emit(
        {
            "status": "succeeded",
            "packet_id": packet["packet_id"],
            "schema_version": packet["schema_version"],
            "prompt_path": _display_path(paths["prompt"]),
            "packet_path": _display_path(paths["packet"]),
            "no_runtime_execution": True,
        }
    )
    return 0


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != PACKET_CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_planner_packet_config_v1.")
    if payload.get("no_runtime_execution") is not True:
        raise ValueError("no_runtime_execution must be true.")
    packet_id = _safe_identifier(payload.get("packet_id", "browser_planner_packet_v1"), "packet_id")
    output_dir = _safe_relative_path(str(payload.get("output_dir", "")), "output_dir")
    candidate_plan_example_path = payload.get("candidate_plan_example_path")
    if candidate_plan_example_path is not None:
        candidate_plan_example_path = _safe_relative_path(str(candidate_plan_example_path), "candidate_plan_example_path")
    return {
        "packet_id": packet_id,
        "output_dir": output_dir,
        "candidate_plan_example_path": candidate_plan_example_path,
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


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(PROJECT_ROOT.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
