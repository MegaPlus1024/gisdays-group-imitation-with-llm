from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_stepwise_article_benchmark import (
    DEFAULT_OUTPUT_JSON,
    build_default_fake_model_factories,
    build_default_stepwise_article_scenarios,
    run_stepwise_article_benchmark,
    write_stepwise_article_benchmark_summary,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fixture-only fake stepwise article benchmark.",
    )
    parser.add_argument(
        "--trials-per-scenario",
        type=int,
        default=3,
        help="Number of fake-model trials to run per scenario.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum steps per scenario trial.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional JSON output path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_stepwise_article_benchmark(
        scenarios=build_default_stepwise_article_scenarios(),
        model_factories=build_default_fake_model_factories(),
        trials_per_scenario=args.trials_per_scenario,
        max_steps=args.max_steps,
    )
    if args.output_json:
        write_stepwise_article_benchmark_summary(summary, Path(args.output_json))
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
