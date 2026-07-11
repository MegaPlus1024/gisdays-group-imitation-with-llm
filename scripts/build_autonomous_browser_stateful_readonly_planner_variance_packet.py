from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_stateful_readonly_planner_variance import (  # noqa: E402 - repo-local import after path setup.
    BUILD_CONFIG_SCHEMA_VERSION,
    build_autonomous_browser_stateful_readonly_planner_variance_packet,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the repeated stateful read-only planner variance packet.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        summary = build_autonomous_browser_stateful_readonly_planner_variance_packet(config, repo_root=PROJECT_ROOT)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _emit(
            {
                "schema_version": "autonomous_browser_stateful_readonly_planner_variance_packet_summary_v1",
                "status": "failed",
                "error_code": "config_validation_failed",
                "error_message": str(exc),
                "no_runtime_execution": True,
                "model_execution": False,
                "real_browser_execution": False,
                "playwright_execution": False,
                "browser_opened": False,
            }
        )
        return 2

    _emit(summary)
    return 0 if str(summary.get("status")) == "succeeded" else 2


def _load_config(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != BUILD_CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "config schema_version must match autonomous_browser_stateful_readonly_planner_variance_config_v1."
        )
    return dict(payload)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
