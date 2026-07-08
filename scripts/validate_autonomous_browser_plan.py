from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_plan_validation import validate_autonomous_browser_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an offline autonomous browser plan artifact.")
    parser.add_argument("--plan", required=True)
    args = parser.parse_args(argv)

    try:
        result = validate_autonomous_browser_plan(Path(args.plan))
    except OSError as exc:
        result = {
            "schema_version": "autonomous_browser_plan_validation_result_v1",
            "status": "rejected",
            "error_code": "plan_file_read_failed",
            "plan_id": None,
            "actions_total": 0,
            "allowed_actions": [],
            "diagnostics": [{"finding_type": "plan_file_read_failed", "message": str(exc)}],
            "limitations": [
                "offline validation only",
                "no LLM planning",
                "no browser execution",
                "no Playwright import",
                "no model runtime",
                "no production readiness claim",
            ],
        }
        _emit(result)
        return 2
    except ValueError as exc:
        result = {
            "schema_version": "autonomous_browser_plan_validation_result_v1",
            "status": "rejected",
            "error_code": "plan_validation_failed",
            "plan_id": None,
            "actions_total": 0,
            "allowed_actions": [],
            "diagnostics": [{"finding_type": "plan_validation_failed", "message": str(exc)}],
            "limitations": [
                "offline validation only",
                "no LLM planning",
                "no browser execution",
                "no Playwright import",
                "no model runtime",
                "no production readiness claim",
            ],
        }
        _emit(result)
        return 2

    _emit(result)
    return 0 if result.get("status") == "accepted" else 1


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
