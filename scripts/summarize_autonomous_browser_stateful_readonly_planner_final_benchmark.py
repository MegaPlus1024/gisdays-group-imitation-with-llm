from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.agent.autonomous_browser_stateful_readonly_planner_final_summary import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    load_json_artifact,
    write_final_presentation_benchmark_summary,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build presentation-ready summary tables for the final stateful readonly benchmark."
    )
    parser.add_argument("--evaluator-summary", required=True)
    parser.add_argument("--runner-summary")
    parser.add_argument("--packet-manifest")
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evaluator_summary = load_json_artifact(args.evaluator_summary)
    runner_summary = load_json_artifact(args.runner_summary) if args.runner_summary else None
    packet_manifest = load_json_artifact(args.packet_manifest) if args.packet_manifest else None
    summary = write_final_presentation_benchmark_summary(
        evaluator_summary=evaluator_summary,
        runner_summary=runner_summary,
        packet_manifest=packet_manifest,
        models_config_path=args.models_config,
        output_dir=args.output_dir,
        repo_root=PROJECT_ROOT,
    )
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
