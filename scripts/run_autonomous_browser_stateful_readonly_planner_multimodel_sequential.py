from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_stateful_readonly_planner_multimodel_sequential import (  # noqa: E402
    run_autonomous_browser_stateful_readonly_planner_multimodel_sequential,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen raw stateful read-only planner benchmark sequentially across local model aliases."
    )
    parser.add_argument("--packet-dir", required=True)
    parser.add_argument("--run-config", required=True)
    parser.add_argument("--models", default="")
    parser.add_argument("--start-servers", dest="start_servers", action="store_true", default=False)
    parser.add_argument("--no-start-servers", dest="start_servers", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    selected_models = tuple(item.strip() for item in args.models.split(",") if item.strip())
    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=args.packet_dir,
        run_config_artifact=args.run_config,
        repo_root=PROJECT_ROOT,
        selected_models=selected_models,
        start_servers=args.start_servers,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
    )
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if summary.get("status") in {"succeeded", "completed_with_failures"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
