from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_multi_agent_runtime import load_runtime_from_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the canonical deterministic multi-agent fixture slice.",
    )
    parser.add_argument("--config", required=True, help="Relative runtime config path.")
    parser.add_argument(
        "--output",
        help="Optional relative JSON summary path under artifacts/.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config_path = _resolve_repo_path(args.config, required_root="configs")
        runtime = load_runtime_from_config(config_path, project_root=PROJECT_ROOT)
        summary = runtime.run()
        if args.output:
            output_path = _resolve_repo_path(args.output, required_root="artifacts")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            summary["summary_path"] = output_path.relative_to(PROJECT_ROOT).as_posix()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        summary = {
            "schema_version": "canonical_multi_agent_runtime_summary_v1",
            "status": "failed",
            "error_code": "config_or_runtime_failed",
            "error_message": _safe_error(exc),
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "external_network": False,
        }
        _emit(summary)
        return 2

    _emit(summary)
    return 0 if summary.get("status") == "succeeded" else 1


def _resolve_repo_path(value: str, *, required_root: str) -> Path:
    normalized = str(value).strip().replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or pure.drive
        or ".." in pure.parts
        or not pure.parts
        or pure.parts[0] != required_root
    ):
        raise ValueError(f"Path must be relative and under {required_root}/.")
    resolved = (PROJECT_ROOT / pure.as_posix()).resolve(strict=False)
    resolved.relative_to(PROJECT_ROOT)
    return resolved


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    root = str(PROJECT_ROOT)
    return message.replace(root, "<repo>")[:500]


def _emit(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
