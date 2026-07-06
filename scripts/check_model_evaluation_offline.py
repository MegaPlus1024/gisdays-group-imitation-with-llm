from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the offline model evaluation compatibility gate. "
            "Offline compatibility gate only. No model execution is performed. "
            "Not a production recommendation."
        ),
    )
    parser.add_argument("--output-dir", required=True, help="Compatibility report output directory.")
    parser.add_argument("--golden-fixture-dir", default=None, help="Optional golden fixture pack directory.")
    parser.add_argument("--workflow-output-dir", default=None, help="Optional workflow output directory to compare.")
    parser.add_argument("--strict", action="store_true", default=False, help="Return nonzero on warnings.")
    parser.add_argument("--write-markdown-preview", action="store_true", default=False)
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Print concise machine-readable JSON. This is the default output.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress extra human text and print only JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cli_args = [
        "check",
        "--output-dir",
        args.output_dir,
    ]
    if args.golden_fixture_dir:
        cli_args.extend(["--golden-fixture-dir", args.golden_fixture_dir])
    if args.workflow_output_dir:
        cli_args.extend(["--workflow-output-dir", args.workflow_output_dir])
    if args.strict:
        cli_args.append("--strict")
    if args.write_markdown_preview:
        cli_args.append("--write-markdown-preview")

    from src.agent.model_evaluation_cli import main as model_evaluation_cli_main

    return model_evaluation_cli_main(cli_args)


if __name__ == "__main__":
    raise SystemExit(main())
