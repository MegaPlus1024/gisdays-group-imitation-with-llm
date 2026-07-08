from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_local_planner_diagnostics import (
    CONFIG_SCHEMA_VERSION,
    diagnose_autonomous_browser_local_planner,
    write_autonomous_browser_local_planner_diagnostic_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose a guarded local planner runtime endpoint.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--allow-local-model-endpoint", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        output_dir = args.output_dir or config.get("output_dir")
        summary = diagnose_autonomous_browser_local_planner(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "diagnostic_id": config["diagnostic_id"],
                "endpoint_base_url": config["endpoint_base_url"],
                "model": config["model"],
                "health_timeout_sec": config["health_timeout_sec"],
                "models_timeout_sec": config["models_timeout_sec"],
                "tiny_completion_timeout_sec": config["tiny_completion_timeout_sec"],
                "micro_planner_timeout_sec": config["micro_planner_timeout_sec"],
                "tiny_max_tokens": config["tiny_max_tokens"],
                "micro_planner_max_tokens": config["micro_planner_max_tokens"],
                "output_dir": output_dir,
                "limitations": config.get("limitations", []),
            },
            repo_root=PROJECT_ROOT,
            allow_local_model_endpoint=args.allow_local_model_endpoint,
        )
        if output_dir:
            write_autonomous_browser_local_planner_diagnostic_summary(summary, _resolve_repo_path(output_dir))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        summary = {
            "schema_version": "autonomous_browser_local_planner_diagnostic_summary_v1",
            "status": "failed",
            "error_code": "diagnostic_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "model_execution_attempted": False,
            "model_execution_completed": False,
        }
        _emit(summary)
        return 2

    _emit(summary)
    if not args.allow_local_model_endpoint:
        return 2
    return 0 if summary.get("status") == "succeeded" else 1


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_local_planner_diagnostic_config_v1.")
    if payload.get("output_dir") is not None:
        output_dir = _safe_relative_path(payload.get("output_dir"), "output_dir")
    else:
        output_dir = None
    if output_dir is None:
        raise ValueError("output_dir must be a safe relative path.")
    return {
        "diagnostic_id": _safe_identifier(payload.get("diagnostic_id", "browser_local_planner_diagnostic_v1"), "diagnostic_id"),
        "endpoint_base_url": _safe_endpoint_base_url(payload.get("endpoint_base_url", "http://127.0.0.1:8080")),
        "model": _safe_identifier(payload.get("model", "second_model"), "model"),
        "health_timeout_sec": payload.get("health_timeout_sec", 3.0),
        "models_timeout_sec": payload.get("models_timeout_sec", 3.0),
        "tiny_completion_timeout_sec": payload.get("tiny_completion_timeout_sec", 6.0),
        "micro_planner_timeout_sec": payload.get("micro_planner_timeout_sec", 8.0),
        "tiny_max_tokens": payload.get("tiny_max_tokens", 16),
        "micro_planner_max_tokens": payload.get("micro_planner_max_tokens", 96),
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


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


def _safe_endpoint_base_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().rstrip("/")
    return normalized


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
