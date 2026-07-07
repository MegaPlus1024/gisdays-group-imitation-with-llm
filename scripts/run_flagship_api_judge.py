from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.flagship_api_judge_provider import (
    FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION,
    FlagshipAPIJudgeError,
    run_guarded_flagship_api_judge,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a guarded external flagship API judge over a prompt pack.")
    parser.add_argument("--judge-config", required=True)
    parser.add_argument("--prompt-pack", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-api-judge", action="store_true")
    parser.add_argument("--confirm-api-judge")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--parse-after-run", action="store_true")
    parser.add_argument("--parsed-output")
    args = parser.parse_args(argv)

    try:
        result = run_guarded_flagship_api_judge(
            judge_config_path=args.judge_config,
            prompt_pack_path=args.prompt_pack,
            schema_path=args.schema,
            output_path=args.output,
            allow_api_judge=args.allow_api_judge,
            confirm_api_judge=args.confirm_api_judge,
            dry_run=args.dry_run,
            max_records=args.max_records,
            parse_after_run=args.parse_after_run,
            parsed_output_path=args.parsed_output,
        )
    except FlagshipAPIJudgeError as exc:
        _emit(
            {
                "status": "invalid_input",
                "error": str(exc),
                "api_call_count": 0,
                "confirmation_required": FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION,
                "no_runtime_execution": True,
            }
        )
        return 2
    except OSError:
        _emit(
            {
                "status": "write_failed",
                "error": "flagship_api_judge_output_write_failed",
                "api_call_count": 0,
                "no_runtime_execution": True,
            }
        )
        return 1

    _emit(result)
    if result.get("status") in {"refused", "invalid_input"}:
        return 2
    return 0


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
