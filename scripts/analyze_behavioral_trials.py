from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build consolidated behavioral analysis from existing repeated-trials artifacts."
    )
    parser.add_argument("--trials-root", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", default="consolidated_behavioral_analysis")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def _project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.consolidated_behavioral_analysis import (
        build_consolidated_behavioral_analysis,
        write_consolidated_behavioral_analysis,
    )

    trials_root = _project_path(args.trials_root)
    out_dir = _project_path(args.out_dir)
    if not trials_root.exists():
        print(f"ERROR: repeated trials root not found: {trials_root}", file=sys.stderr)
        return 2

    try:
        analysis = build_consolidated_behavioral_analysis(trials_root, analysis_id=args.label)
        output = write_consolidated_behavioral_analysis(analysis, out_dir, force=args.force)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: behavioral analysis failed: {exc}", file=sys.stderr)
        return 1

    if args.json_only:
        print(json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    print(f"analysis_id: {analysis.analysis_id}")
    print(f"trials_root: {analysis.trials_root}")
    print(f"out_dir: {output}")
    print("")
    print("model_id,role_verdict,coherence_verdict,diversity_verdict,latency_verdict")
    for model_id in analysis.model_ids:
        print(
            f"{model_id},"
            f"{analysis.role_compliance[model_id].verdict},"
            f"{analysis.coherence_history_usage[model_id].verdict},"
            f"{analysis.diversity_template_behavior[model_id].verdict},"
            f"{analysis.resource_latency[model_id].verdict}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
