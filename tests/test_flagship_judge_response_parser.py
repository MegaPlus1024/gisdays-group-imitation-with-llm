from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.parse_flagship_judge_responses import main as parse_cli_main
from src.agent.model_pair_flagship_judge_inputs import (
    FLAGSHIP_JUDGE_SUMMARY_SCHEMA_VERSION,
    FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
    build_flagship_judge_summary_from_responses,
)


SUMMARY_ID = "phase_8_26_mini_matrix_r1"
RUN_ID = "phase_8_26_mini_matrix_r1"
TRIAL_ID = "office_document_file_workflow_basic_v1__second_model__to__first_model__r01"


def _input_record() -> dict[str, Any]:
    return {
        "schema_version": "flagship_llm_judge_input_v1",
        "summary_id": SUMMARY_ID,
        "run_id": RUN_ID,
        "trial_id": TRIAL_ID,
        "pair_id": "second_model__to__first_model",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "judge_role": "external_measurement_instrument",
        "no_runtime_execution": True,
    }


def _verdict(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
        "summary_id": SUMMARY_ID,
        "run_id": RUN_ID,
        "trial_id": TRIAL_ID,
        "scores": {
            "task_fulfillment": 0.9,
            "artifact_quality": 0.8,
            "normality": 0.85,
            "role_consistency": 0.95,
            "safety": 1.0,
            "overall": 0.9,
        },
        "verdict": "pass",
        "confidence": 0.8,
        "reasons": ["Artifacts look coherent from bounded excerpts."],
        "flags": [],
    }
    payload.update(overrides)
    return payload


def _summary_for_response(response: dict[str, Any] | str, *, run_id: str = RUN_ID, trial_id: str = TRIAL_ID) -> dict[str, Any]:
    row: dict[str, Any] = {"run_id": run_id, "trial_id": trial_id}
    if isinstance(response, str):
        row["raw_response"] = response
    else:
        row["response"] = response
    return build_flagship_judge_summary_from_responses([_input_record()], [row], summary_id=SUMMARY_ID)


def test_parser_accepts_valid_strict_json_verdict() -> None:
    summary = _summary_for_response(_verdict())

    assert summary["schema_version"] == FLAGSHIP_JUDGE_SUMMARY_SCHEMA_VERSION
    assert summary["response_count"] == 1
    assert summary["valid_response_count"] == 1
    assert summary["invalid_response_count"] == 0
    assert summary["mean_scores"]["overall"] == 0.9
    assert summary["verdict_counts"]["pass"] == 1
    assert summary["results"][0]["status"] == "valid"


def test_parser_accepts_raw_response_json_string() -> None:
    summary = _summary_for_response(json.dumps(_verdict(), ensure_ascii=False))

    assert summary["valid_response_count"] == 1
    assert summary["results"][0]["scores"]["artifact_quality"] == 0.8


def test_parser_rejects_invalid_json() -> None:
    summary = _summary_for_response("{not json")

    assert summary["valid_response_count"] == 0
    assert summary["invalid_response_count"] == 1
    assert summary["results"][0]["error_code"] == "response_json_invalid"


def test_parser_rejects_missing_required_scores() -> None:
    verdict = _verdict()
    del verdict["scores"]["safety"]

    summary = _summary_for_response(verdict)

    assert summary["invalid_response_count"] == 1
    assert summary["results"][0]["error_code"] == "score_invalid:safety"


def test_parser_rejects_score_outside_range() -> None:
    verdict = _verdict()
    verdict["scores"]["overall"] = 1.2

    summary = _summary_for_response(verdict)

    assert summary["invalid_response_count"] == 1
    assert summary["results"][0]["error_code"] == "score_invalid:overall"


def test_parser_rejects_wrong_run_id_or_trial_id() -> None:
    summary = _summary_for_response(_verdict(run_id="other_run"), run_id="other_run")

    assert summary["invalid_response_count"] == 1
    assert summary["results"][0]["error_code"] == "run_id_mismatch"


def test_parser_summarizes_mean_scores_and_verdict_counts() -> None:
    second = _verdict(
        scores={
            "task_fulfillment": 0.7,
            "artifact_quality": 0.6,
            "normality": 0.5,
            "role_consistency": 0.8,
            "safety": 1.0,
            "overall": 0.7,
        },
        verdict="borderline",
    )
    rows = [
        {"run_id": RUN_ID, "trial_id": TRIAL_ID, "response": _verdict()},
        {"run_id": RUN_ID, "trial_id": TRIAL_ID, "response": second},
    ]

    summary = build_flagship_judge_summary_from_responses([_input_record()], rows, summary_id=SUMMARY_ID)

    assert summary["valid_response_count"] == 2
    assert summary["mean_scores"]["overall"] == 0.8
    assert summary["verdict_counts"] == {"pass": 1, "borderline": 1, "fail": 0}


def test_parse_script_writes_summary_without_raw_prompts(
    tmp_path: Path,
    capsys,
) -> None:
    inputs_path = tmp_path / "flagship_judge_inputs.jsonl"
    raw_path = tmp_path / "raw_responses.jsonl"
    output_path = tmp_path / "flagship_judge_summary.json"
    inputs_path.write_text(json.dumps(_input_record(), ensure_ascii=False) + "\n", encoding="utf-8")
    raw_path.write_text(
        json.dumps(
            {"run_id": RUN_ID, "trial_id": TRIAL_ID, "raw_response": json.dumps(_verdict(), ensure_ascii=False)},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    code = parse_cli_main(
        [
            "--inputs",
            str(inputs_path),
            "--raw-responses",
            str(raw_path),
            "--output",
            str(output_path),
            "--summary-id",
            SUMMARY_ID,
        ]
    )
    stdout = json.loads(capsys.readouterr().out)
    summary = json.loads(output_path.read_text(encoding="utf-8"))
    encoded = json.dumps(summary, ensure_ascii=False).lower()

    assert code == 0
    assert stdout["status"] == "ok"
    assert summary["valid_response_count"] == 1
    assert "raw_prompt" not in encoded
    assert "prompt_text" not in encoded
