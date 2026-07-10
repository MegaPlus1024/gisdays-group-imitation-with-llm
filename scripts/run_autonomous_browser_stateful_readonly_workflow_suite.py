from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_stateful_readonly_workflow_suite import (  # noqa: E402 - repo-local import after sys.path setup.
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_stateful_readonly_workflow_suite,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the scripted fixture-only stateful readonly workflow suite.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)

    try:
        config = _load_config(_resolve_repo_path(args.config))
        if args.output_dir:
            config["output_dir"] = args.output_dir
        summary = run_autonomous_browser_stateful_readonly_workflow_suite(config, repo_root=PROJECT_ROOT)
        _emit(summary)
        return 0 if summary.get("status") == "succeeded" else 1
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "real_network_traffic": False,
            "fixture_only": True,
            "no_runtime_execution": True,
        }
        _emit(payload)
        return 2


def _load_config(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("stateful readonly workflow suite config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        raise ValueError("stateful readonly workflow suite config schema_version is invalid.")
    return dict(payload)


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
