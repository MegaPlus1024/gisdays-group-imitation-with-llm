from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from scripts.parse_flagship_judge_responses import main as parse_main
from scripts.run_flagship_api_judge import main as run_main
from src.agent.model_pair_flagship_judge_inputs import (
    FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
    flagship_judge_verdict_schema,
)


SUMMARY_ID = "phase_8_26_mini_matrix_r3"
RUN_ID = "phase_8_26_mini_matrix_r1"
TRIAL_ID = "office_document_file_workflow_basic_v1__second_model__to__first_model__r01"


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _config() -> dict[str, Any]:
    return {
        "schema_version": "flagship_api_judge_config_v1",
        "provider": "openai_responses_api",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "model": "flagship_judge_model",
        "reasoning_effort": "high",
        "temperature": 0,
        "max_output_tokens": 2000,
        "response_format": "json_schema",
        "timeout_seconds": 120,
        "judge_is_evaluated_model": False,
        "judge_is_independent_from_tested_pair": True,
    }


def _prompt_record() -> dict[str, Any]:
    return {
        "schema_version": "flagship_llm_judge_prompt_pack_v1",
        "summary_id": SUMMARY_ID,
        "run_id": RUN_ID,
        "trial_id": TRIAL_ID,
        "prompt": "Evaluate the safe prompt pack row.",
        "verdict_schema": flagship_judge_verdict_schema(),
        "judge_role": "external_measurement_instrument",
        "no_runtime_execution": True,
    }


def _verdict() -> dict[str, Any]:
    return {
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
        "reasons": ["Coherent controlled artifact evidence."],
        "flags": [],
    }


def _fixture_files(tmp_path: Path) -> dict[str, Path]:
    return {
        "config": _write_json(tmp_path / "judge_config.json", _config()),
        "schema": _write_json(tmp_path / "flagship_judge_schema.json", flagship_judge_verdict_schema()),
        "prompt_pack": _write_jsonl(tmp_path / "flagship_judge_prompt_pack.jsonl", [_prompt_record()]),
        "inputs": _write_jsonl(tmp_path / "flagship_judge_inputs.jsonl", [_prompt_record()]),
    }


def test_runner_refuses_without_allow_api_judge(tmp_path: Path, capsys) -> None:
    paths = _fixture_files(tmp_path)
    output_path = tmp_path / "raw_responses.jsonl"

    code = run_main(
        [
            "--judge-config",
            str(paths["config"]),
            "--prompt-pack",
            str(paths["prompt_pack"]),
            "--schema",
            str(paths["schema"]),
            "--output",
            str(output_path),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert code == 2
    assert stdout["status"] == "refused"
    assert stdout["api_call_count"] == 0
    assert "api_judge_not_allowed" in stdout["warnings"]
    assert not output_path.exists()


def test_runner_refuses_without_exact_confirmation(tmp_path: Path, capsys) -> None:
    paths = _fixture_files(tmp_path)

    code = run_main(
        [
            "--judge-config",
            str(paths["config"]),
            "--prompt-pack",
            str(paths["prompt_pack"]),
            "--schema",
            str(paths["schema"]),
            "--output",
            str(tmp_path / "raw_responses.jsonl"),
            "--allow-api-judge",
            "--confirm-api-judge",
            "WRONG",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert code == 2
    assert stdout["status"] == "refused"
    assert stdout["api_call_count"] == 0
    assert "api_judge_confirmation_required" in stdout["warnings"]


def test_dry_run_writes_request_preview_without_api_opt_in(tmp_path: Path, capsys) -> None:
    paths = _fixture_files(tmp_path)
    output_path = tmp_path / "raw_responses.dry_run.jsonl"

    code = run_main(
        [
            "--judge-config",
            str(paths["config"]),
            "--prompt-pack",
            str(paths["prompt_pack"]),
            "--schema",
            str(paths["schema"]),
            "--output",
            str(output_path),
            "--dry-run",
            "--max-records",
            "1",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)
    row = json.loads(output_path.read_text(encoding="utf-8"))
    encoded = json.dumps(row, ensure_ascii=False)

    assert code == 0
    assert stdout["status"] == "dry_run"
    assert stdout["api_call_count"] == 0
    assert row["schema_version"] == "flagship_api_judge_request_preview_v1"
    assert row["request_preview"]["model"] == "flagship_judge_model"
    assert "Authorization" not in encoded
    assert "Bearer" not in encoded


def test_existing_manual_parser_cli_still_works(tmp_path: Path, capsys) -> None:
    paths = _fixture_files(tmp_path)
    raw_path = _write_jsonl(
        tmp_path / "raw_responses.jsonl",
        [
            {
                "run_id": RUN_ID,
                "trial_id": TRIAL_ID,
                "raw_response": json.dumps(_verdict(), ensure_ascii=False),
            }
        ],
    )
    output_path = tmp_path / "flagship_judge_summary.json"

    code = parse_main(
        [
            "--inputs",
            str(paths["inputs"]),
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

    assert code == 0
    assert stdout["status"] == "ok"
    assert summary["valid_response_count"] == 1
    assert summary["mean_scores"]["overall"] == 0.9
