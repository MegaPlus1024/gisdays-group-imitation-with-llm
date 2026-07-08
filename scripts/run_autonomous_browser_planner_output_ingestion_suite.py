from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_planner_output_ingestion_suite import (
    SUITE_CONFIG_SCHEMA_VERSION,
    SUITE_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_planner_output_ingestion_suite,
    write_autonomous_browser_planner_output_ingestion_suite_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline planner output ingestion suite.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--execute-fixture", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = _load_config(_resolve_repo_path(args.config))
        output_dir = args.output_dir or config.get("output_dir")
        summary = run_autonomous_browser_planner_output_ingestion_suite(
            {
                "schema_version": SUITE_CONFIG_SCHEMA_VERSION,
                "suite_id": config["suite_id"],
                "captured_outputs": config["captured_outputs"],
                "replay_mode": config["replay_mode"],
                "output_dir": output_dir,
                "expected_min_ingested": config["expected_min_ingested"],
                "expected_max_rejected": config["expected_max_rejected"],
                "limitations": config.get("limitations", []),
            },
            repo_root=PROJECT_ROOT,
            execute_fixture=args.execute_fixture,
        )
        if output_dir:
            write_autonomous_browser_planner_output_ingestion_suite_summary(summary, _resolve_repo_path(output_dir))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        summary = {
            "schema_version": SUITE_SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "suite_ingestion_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "real_browser_execution": False,
            "model_execution": False,
        }
        _emit(summary)
        return 2

    _emit(summary)
    return 0 if summary.get("status") in {"succeeded", "completed_with_failures"} else 1


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != SUITE_CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_planner_output_ingestion_suite_config_v1.")
    suite_id = _safe_text(payload.get("suite_id"))
    if not suite_id:
        raise ValueError("suite_id must be a non-empty string.")
    captured_outputs = payload.get("captured_outputs")
    if not isinstance(captured_outputs, list) or not captured_outputs:
        raise ValueError("captured_outputs must be a non-empty list.")
    cleaned_captured_outputs: list[str] = []
    for index, candidate in enumerate(captured_outputs):
        safe_output = _safe_relative_path(candidate)
        if safe_output is None:
            raise ValueError(f"captured_outputs[{index}] must be a safe relative path.")
        cleaned_captured_outputs.append(safe_output)
    replay_mode = str(payload.get("replay_mode", "dry_run")).strip()
    if replay_mode not in {"dry_run", "fixture_execution"}:
        raise ValueError("replay_mode must be dry_run or fixture_execution.")
    output_dir = _safe_relative_path(payload.get("output_dir"))
    if output_dir is None:
        raise ValueError("output_dir must be a safe relative path.")
    expected_min_ingested = payload.get("expected_min_ingested", 1)
    expected_max_rejected = payload.get("expected_max_rejected", 0)
    if not isinstance(expected_min_ingested, int) or isinstance(expected_min_ingested, bool) or expected_min_ingested < 0:
        raise ValueError("expected_min_ingested must be a non-negative integer.")
    if not isinstance(expected_max_rejected, int) or isinstance(expected_max_rejected, bool) or expected_max_rejected < 0:
        raise ValueError("expected_max_rejected must be a non-negative integer.")
    return {
        "suite_id": suite_id,
        "captured_outputs": cleaned_captured_outputs,
        "replay_mode": replay_mode,
        "output_dir": output_dir,
        "expected_min_ingested": expected_min_ingested,
        "expected_max_rejected": expected_max_rejected,
        "limitations": payload.get("limitations", []),
    }


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
