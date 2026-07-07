from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_flagship_judge_inputs import (
    FLAGSHIP_JUDGE_INPUTS_JSONL_FILENAME,
    FLAGSHIP_JUDGE_PROMPT_PACK_JSONL_FILENAME,
    FLAGSHIP_JUDGE_SCHEMA_JSON_FILENAME,
    FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
    build_flagship_judge_prompt_rows,
    flagship_judge_verdict_schema,
    write_flagship_judge_prompt_pack,
)


def _input_record() -> dict[str, Any]:
    return {
        "schema_version": "flagship_llm_judge_input_v1",
        "summary_id": "phase_8_26_mini_matrix_r1",
        "run_id": "phase_8_26_mini_matrix_r1",
        "repeat_index": 1,
        "trial_id": "office_document_file_workflow_basic_v1__second_model__to__first_model__r01",
        "pair_id": "second_model__to__first_model",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "judge_role": "external_measurement_instrument",
        "evaluated_models": {"orchestrator_model_id": "second_model", "executor_model_id": "first_model"},
        "deterministic_metrics": {
            "trial_status": "succeeded",
            "task_success": True,
            "execution_success_count": 2,
            "office_artifact_count": 2,
            "office_artifact_readable_count": 2,
            "execution_correctness_score": 1.0,
        },
        "actions": [
            {
                "task_id": "t1",
                "agent_id": "document_summary_agent",
                "action": "office_append_docx_section",
                "validation_accepted": True,
                "execution_attempted": True,
                "execution_success": True,
            }
        ],
        "artifacts": [
            {
                "artifact_type": "docx",
                "path": "artifacts/single_trial_runs/phase_8_26_mini_matrix_r1/report.docx",
                "paragraph_count": 2,
                "readable": True,
                "safe_text_excerpt": "Short bounded excerpt.",
            }
        ],
        "judge_dimensions": ["task_fulfillment", "artifact_quality", "normality", "role_consistency", "safety"],
        "notes": [
            "deterministic_execution_correctness_already_scored",
            "judge_should_score_semantic_quality_and_normality_only",
        ],
        "no_runtime_execution": True,
    }


def test_prompt_pack_includes_strict_json_schema_and_dimensions(tmp_path: Path) -> None:
    inputs = [_input_record()]
    prompts = build_flagship_judge_prompt_rows(inputs, summary_id="phase_8_26_mini_matrix_r1")
    paths = write_flagship_judge_prompt_pack(inputs, prompts, tmp_path / "judge_pack")
    schema = json.loads(paths["schema"].read_text(encoding="utf-8"))
    prompt_row = json.loads(paths["prompts"].read_text(encoding="utf-8").splitlines()[0])

    assert paths["inputs"].name == FLAGSHIP_JUDGE_INPUTS_JSONL_FILENAME
    assert paths["prompts"].name == FLAGSHIP_JUDGE_PROMPT_PACK_JSONL_FILENAME
    assert paths["schema"].name == FLAGSHIP_JUDGE_SCHEMA_JSON_FILENAME
    assert schema["properties"]["schema_version"]["const"] == FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION
    assert set(schema["properties"]["scores"]["required"]) == {
        "task_fulfillment",
        "artifact_quality",
        "normality",
        "role_consistency",
        "safety",
        "overall",
    }
    assert "VERDICT_JSON_SCHEMA" in prompt_row["prompt"]
    assert "task_fulfillment" in prompt_row["prompt"]


def test_prompt_pack_says_judge_is_external_not_evaluated_model() -> None:
    prompt = build_flagship_judge_prompt_rows([_input_record()], summary_id="phase_8_26_mini_matrix_r1")[0]["prompt"]

    assert "independent evaluator, not one of the tested models" in prompt
    assert "external measurement instrument" in prompt
    assert "Deterministic execution correctness is already measured" in prompt
    assert "Do not penalize controlled precreate" in prompt


def test_config_example_has_no_secret_and_uses_api_key_env() -> None:
    payload = json.loads(Path("configs/judge/flagship_api_judge.example.json").read_text(encoding="utf-8"))
    encoded = json.dumps(payload, ensure_ascii=False).lower()

    assert payload["api_key_env"] == "OPENAI_API_KEY"
    assert payload["judge_is_evaluated_model"] is False
    assert payload["judge_is_independent_from_tested_pair"] is True
    assert "sk-" not in encoded
    assert "real_api_key" not in encoded
    assert "do not store api keys" in encoded


def test_prompt_pack_does_not_import_runtime_or_api_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("openai", "httpx", "requests", "playwright", "win32com", "pythoncom", "uno", "llama_cpp")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"Forbidden runtime import attempted: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    prompt = build_flagship_judge_prompt_rows([_input_record()], summary_id="phase_8_26_mini_matrix_r1")[0]["prompt"]

    assert "Return strict JSON only" in prompt
    assert flagship_judge_verdict_schema()["type"] == "object"
