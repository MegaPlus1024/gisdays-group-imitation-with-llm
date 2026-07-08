from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_planner_output_ingestion import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    ingest_autonomous_browser_planner_output,
    write_autonomous_browser_planner_output_ingestion_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest captured browser planner output offline.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--execute-fixture", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = _load_config(_resolve_repo_path(args.config))
        output_dir = args.output_dir or config.get("output_dir")
        summary = ingest_autonomous_browser_planner_output(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "source_output_path": config["source_output_path"],
                "output_dir": output_dir,
                "limitations": config.get("limitations", []),
            },
            repo_root=PROJECT_ROOT,
            execute_fixture=args.execute_fixture,
        )
        if output_dir:
            write_autonomous_browser_planner_output_ingestion_summary(summary, _resolve_repo_path(output_dir))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "ingestion_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "real_browser_execution": False,
            "model_execution": False,
        }
        _emit(summary)
        return 2

    _emit(summary)
    return 0 if summary.get("status") == "succeeded" else 1


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_planner_output_ingestion_config_v1.")
    source_output_path = _safe_relative_path(payload.get("source_output_path"), "source_output_path")
    if source_output_path is None:
        raise ValueError("source_output_path must be a safe relative path.")
    output_dir = payload.get("output_dir")
    if output_dir is not None:
        output_dir = _safe_relative_path(output_dir, "output_dir")
        if output_dir is None:
            raise ValueError("output_dir must be a safe relative path.")
    return {
        "source_output_path": source_output_path,
        "output_dir": output_dir,
        "limitations": payload.get("limitations", []),
    }


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _safe_relative_path(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
