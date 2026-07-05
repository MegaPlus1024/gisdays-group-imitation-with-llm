from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.normality_comparison import (
    NORMALITY_COMPARISON_PREVIEW_FILENAME,
    NORMALITY_COMPARISON_SUMMARY_FILENAME,
    compare_normality_batch_summaries,
    load_normality_batch_summary,
    write_normality_comparison_summary,
)
from src.agent.normality_evaluation_cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _entry(
    *,
    scenario_id: str = "office_document_file_workflow_basic_v1",
    trial_id: str = "run_001",
    orchestrator: str = "second_model",
    executor: str = "first_model",
    tags: list[str] | None = None,
    status: str = "ok",
    label: str | None = "normal",
    overall_score: float | None = 0.9,
    findings: list[str] | None = None,
    warnings: list[str] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "scenario_id": scenario_id,
        "trial_id": trial_id,
        "model_pair": {"orchestrator": orchestrator, "executor": executor},
        "tags": tags or ["office", "smoke"],
        "status": status,
        "label": label,
        "overall_score": overall_score,
        "event_count": 2,
        "findings": findings or [],
        "warnings": warnings or [],
    }
    payload.update(extra or {})
    return payload


def _summary(entries: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "ok",
        "batch_id": "batch_a",
        "input_count": len(entries),
        "evaluated_count": sum(1 for entry in entries if entry.get("status") == "ok"),
        "failed_count": sum(1 for entry in entries if entry.get("status") != "ok"),
        "entries": entries,
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _comparison_summary(out_dir: Path) -> dict[str, Any]:
    return json.loads((out_dir / NORMALITY_COMPARISON_SUMMARY_FILENAME).read_text(encoding="utf-8"))


def _run_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    summaries: list[Path],
    output_dir: Path | None = None,
    extra_args: list[str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    args: list[str] = []
    for summary_path in summaries:
        args.extend(["--compare-batch-summary", str(summary_path)])
    args.extend(["--output-dir", str(output_dir or tmp_path / "out")])
    args.extend(extra_args or [])
    code = main(args)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_loads_valid_batch_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "summary.json", _summary([_entry()]))

    result = load_normality_batch_summary(path, project_root=tmp_path)

    assert result.status == "ok"
    assert result.summary is not None
    assert result.input_path_display == "summary.json"


def test_compares_one_summary_with_two_model_pairs(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(orchestrator="second_model", executor="first_model", overall_score=0.9),
                _entry(orchestrator="second_model", executor="second_model", overall_score=0.8),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    assert result.status == "ok"
    assert result.total_entries == 2
    assert set(result.groups["by_model_pair"]) == {
        "second_model->first_model",
        "second_model->second_model",
    }


def test_compares_multiple_summaries(tmp_path: Path) -> None:
    first = _write_json(tmp_path / "first.json", _summary([_entry(trial_id="run_001")]))
    second = _write_json(tmp_path / "second.json", _summary([_entry(trial_id="run_002")]))

    result = compare_normality_batch_summaries([first, second], project_root=tmp_path)

    assert result.input_summary_count == 2
    assert result.valid_summary_count == 2
    assert result.total_entries == 2
    assert sorted(result.overall["trial_ids"]) == ["run_001", "run_002"]


def test_groups_by_model_pair(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(orchestrator="second_model", executor="first_model", overall_score=0.9),
                _entry(orchestrator="second_model", executor="first_model", overall_score=0.7),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)
    group = result.groups["by_model_pair"]["second_model->first_model"]

    assert group["entry_count"] == 2
    assert group["mean_overall_score"] == pytest.approx(0.8)


def test_groups_by_scenario_id(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(scenario_id="scenario_a"),
                _entry(scenario_id="scenario_b"),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    assert set(result.groups["by_scenario_id"]) == {"scenario_a", "scenario_b"}


def test_groups_by_tags(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(tags=["office", "smoke"]),
                _entry(tags=["office", "nightly"]),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    assert result.groups["by_tag"]["office"]["entry_count"] == 2
    assert result.groups["by_tag"]["smoke"]["entry_count"] == 1
    assert result.groups["by_tag"]["nightly"]["entry_count"] == 1


def test_leaderboard_sorted_by_mean_score_descending(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(orchestrator="second_model", executor="first_model", overall_score=0.7),
                _entry(orchestrator="second_model", executor="second_model", overall_score=0.9),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    assert [row["pair_label"] for row in result.leaderboard] == [
        "second_model->second_model",
        "second_model->first_model",
    ]


def test_failed_entries_counted_but_not_included_in_mean_score(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(overall_score=0.8),
                _entry(status="invalid_input", label=None, overall_score=None),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)
    group = result.groups["by_model_pair"]["second_model->first_model"]

    assert result.evaluated_entries == 1
    assert result.failed_entries == 1
    assert group["mean_overall_score"] == pytest.approx(0.8)
    assert group["status_counts"] == {"ok": 1, "invalid_input": 1}


def test_label_and_status_counts_aggregate_correctly(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(label="normal", status="ok"),
                _entry(label="suspicious", status="ok"),
                _entry(label=None, status="input_missing", overall_score=None),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    assert result.overall["label_counts"] == {"normal": 1, "suspicious": 1}
    assert result.overall["status_counts"] == {"ok": 2, "input_missing": 1}


def test_top_findings_aggregate_correctly(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(findings=["minor_issue", "minor_issue"]),
                _entry(findings=["minor_issue", "other_issue"]),
            ]
        ),
    )

    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    assert result.overall["top_findings"][0] == {"finding": "minor_issue", "count": 3}


def test_missing_summary_file_handled_controlled(tmp_path: Path) -> None:
    result = compare_normality_batch_summaries([tmp_path / "missing.json"], project_root=tmp_path)

    assert result.status == "invalid_input"
    assert result.input_summary_count == 1
    assert any("summary_file_missing" in warning for warning in result.warnings)


def test_malformed_summary_handled_controlled(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")

    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    assert result.status == "invalid_input"
    assert any("summary_json_decode_error" in warning for warning in result.warnings)


def test_one_malformed_and_one_valid_still_produces_warning_and_comparison(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    good = _write_json(tmp_path / "good.json", _summary([_entry()]))

    result = compare_normality_batch_summaries([bad, good], project_root=tmp_path)

    assert result.status == "ok"
    assert result.valid_summary_count == 1
    assert result.evaluated_entries == 1
    assert any("summary_json_decode_error" in warning for warning in result.warnings)


def test_output_summary_json_written_to_tmp_output_dir(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "summary.json", _summary([_entry()]))
    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    summary_path, markdown_path = write_normality_comparison_summary(result, tmp_path / "out")

    assert summary_path == tmp_path / "out" / NORMALITY_COMPARISON_SUMMARY_FILENAME
    assert markdown_path is None
    assert _comparison_summary(tmp_path / "out")["status"] == "ok"


def test_optional_markdown_preview_written(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "summary.json", _summary([_entry()]))
    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    _, markdown_path = write_normality_comparison_summary(
        result,
        tmp_path / "out",
        write_markdown=True,
    )

    assert markdown_path == tmp_path / "out" / NORMALITY_COMPARISON_PREVIEW_FILENAME
    assert markdown_path.is_file()


def test_absolute_windows_path_from_input_summary_is_redacted(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "secret.docx"])
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(
                    findings=[f"found {windows_path}"],
                    warnings=[f"warning {windows_path}"],
                    extra={
                        "input_path_display": windows_path,
                        "event_preview": [{"artifact_paths": [windows_path]}],
                    },
                )
            ]
        ),
    )
    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    write_normality_comparison_summary(result, tmp_path / "out")
    text = (tmp_path / "out" / NORMALITY_COMPARISON_SUMMARY_FILENAME).read_text(encoding="utf-8")

    assert windows_path not in text
    assert "<absolute_path>" in text


def test_absolute_posix_path_from_input_summary_is_redacted(tmp_path: Path) -> None:
    posix_path = "/home/example/outside_workspace/secret.docx"
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(
                    findings=[f"found {posix_path}"],
                    extra={"event_preview": [{"artifact_paths": [posix_path]}]},
                )
            ]
        ),
    )
    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    write_normality_comparison_summary(result, tmp_path / "out")
    text = (tmp_path / "out" / NORMALITY_COMPARISON_SUMMARY_FILENAME).read_text(encoding="utf-8")

    assert posix_path not in text
    assert "<absolute_path>" in text


def test_cli_comparison_mode_writes_comparison_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = _write_json(tmp_path / "summary.json", _summary([_entry()]))

    code, payload, stderr = _run_cli(tmp_path, capsys, summaries=[summary])

    assert code == 0
    assert stderr == ""
    assert payload["status"] == "ok"
    assert payload["top_model_pair"] == "second_model->first_model"
    assert (tmp_path / "out" / NORMALITY_COMPARISON_SUMMARY_FILENAME).is_file()


def test_cli_rejects_incompatible_args_with_comparison_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = _write_json(tmp_path / "summary.json", _summary([_entry()]))
    input_path = _write_json(tmp_path / "events.json", [])

    code = main(
        [
            "--compare-batch-summary",
            str(summary),
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "comparison_mode_incompatible_args"


def test_comparison_does_not_write_reports_or_experiments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = _write_json(tmp_path / "summary.json", _summary([_entry()]))

    code, _, _ = _run_cli(tmp_path, capsys, summaries=[summary])

    assert code == 0
    assert not (PROJECT_ROOT / "reports" / NORMALITY_COMPARISON_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_COMPARISON_SUMMARY_FILENAME).exists()


def test_comparison_does_not_create_model_browser_or_office_clients(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("comparison must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    summary = _write_json(tmp_path / "summary.json", _summary([_entry()]))

    code, payload, _ = _run_cli(tmp_path, capsys, summaries=[summary])

    assert code == 0
    assert payload["status"] == "ok"


def test_comparison_does_not_include_raw_event_previews(tmp_path: Path) -> None:
    raw_marker = "RAW_FULL_EVENT_MARKER_SHOULD_NOT_APPEAR"
    path = _write_json(
        tmp_path / "summary.json",
        _summary(
            [
                _entry(
                    extra={
                        "event_preview": [{"result_summary": raw_marker}],
                        "raw_payload": raw_marker,
                    }
                )
            ]
        ),
    )
    result = compare_normality_batch_summaries([path], project_root=tmp_path)

    write_normality_comparison_summary(result, tmp_path / "out")
    text = (tmp_path / "out" / NORMALITY_COMPARISON_SUMMARY_FILENAME).read_text(encoding="utf-8")

    assert raw_marker not in text
