from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_playwright_evidence import (
    PlaywrightSmokeEvidenceError,
    build_playwright_smoke_evidence_report,
    render_playwright_smoke_evidence_markdown,
    report_to_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize a guarded Playwright smoke result as committed evidence.")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output-doc", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--allow-outside-docs", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = _read_json(args.summary)
        report = build_playwright_smoke_evidence_report(summary)
        output_doc = _validated_output_doc_path(args.output_doc, allow_outside_docs=args.allow_outside_docs)
        output_doc.parent.mkdir(parents=True, exist_ok=True)
        output_doc.write_text(render_playwright_smoke_evidence_markdown(report), encoding="utf-8")
        if args.output_json:
            output_json = Path(args.output_json)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(report_to_json(report), encoding="utf-8")
    except (OSError, json.JSONDecodeError, PlaywrightSmokeEvidenceError, ValueError) as exc:
        _emit({"status": "invalid_input", "error": str(exc), "no_runtime_execution": True})
        return 2

    _emit({"status": "succeeded", "output_doc": _display_path(output_doc), "passed": report["passed"], "no_runtime_execution": True})
    return 0


def _read_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("summary JSON root must be an object.")
    return payload


def _validated_output_doc_path(value: str, *, allow_outside_docs: bool) -> Path:
    path = Path(value)
    normalized = str(path).replace("\\", "/")
    if any(part == ".." for part in Path(normalized).parts):
        raise ValueError("output-doc must not contain traversal.")
    if path.suffix.lower() != ".md":
        raise ValueError("output-doc must be a markdown file.")
    if allow_outside_docs:
        return path
    if len(path.parts) < 3 or path.parts[-3:-1] != ("docs", "status"):
        raise ValueError("output-doc must be under docs/status unless --allow-outside-docs is used.")
    return path


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(PROJECT_ROOT.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
