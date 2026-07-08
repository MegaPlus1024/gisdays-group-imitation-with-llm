from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_local_planner_repeated_trials_packet import (
    PACKET_CONFIG_SCHEMA_VERSION,
    build_autonomous_browser_local_planner_repeated_trials_packet,
    write_autonomous_browser_local_planner_repeated_trials_packet_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a repeated local planner trials packet.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        summary = build_autonomous_browser_local_planner_repeated_trials_packet(config, repo_root=PROJECT_ROOT)
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

    if summary.get("output_dir"):
        write_autonomous_browser_local_planner_repeated_trials_packet_summary(
            summary,
            _resolve_repo_path(str(summary["output_dir"])),
        )
    _emit(summary)
    return 0 if str(summary.get("status")) == "succeeded" else 2


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != PACKET_CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_local_planner_repeated_trials_packet_config_v1.")
    return dict(payload)


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

