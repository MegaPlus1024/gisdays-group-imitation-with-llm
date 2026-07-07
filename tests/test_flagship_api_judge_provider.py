from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.agent.flagship_api_judge_provider import (
    FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION,
    FlagshipAPIJudgeError,
    build_openai_responses_payload,
    extract_openai_response_text,
    load_flagship_api_judge_config,
    run_guarded_flagship_api_judge,
)
from src.agent.model_pair_flagship_judge_inputs import (
    FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
    flagship_judge_verdict_schema,
)


SUMMARY_ID = "phase_8_26_mini_matrix_r3"
RUN_ID = "phase_8_26_mini_matrix_r1"
TRIAL_ID = "office_document_file_workflow_basic_v1__second_model__to__first_model__r01"


def _config_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    payload.update(overrides)
    return payload


def _prompt_record() -> dict[str, Any]:
    return {
        "schema_version": "flagship_llm_judge_prompt_pack_v1",
        "summary_id": SUMMARY_ID,
        "run_id": RUN_ID,
        "trial_id": TRIAL_ID,
        "prompt": "Evaluate this safe mini-matrix record and return strict JSON.",
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


def _fixture_files(tmp_path: Path, **config_overrides: Any) -> dict[str, Path]:
    return {
        "config": _write_json(tmp_path / "judge_config.json", _config_payload(**config_overrides)),
        "schema": _write_json(tmp_path / "flagship_judge_schema.json", flagship_judge_verdict_schema()),
        "prompt_pack": _write_jsonl(tmp_path / "flagship_judge_prompt_pack.jsonl", [_prompt_record()]),
    }


def test_request_payload_uses_config_model_and_strict_json_schema() -> None:
    payload = build_openai_responses_payload(_prompt_record(), flagship_judge_verdict_schema(), _config_payload())
    encoded = json.dumps(payload, ensure_ascii=False)

    assert payload["model"] == "flagship_judge_model"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["properties"]["schema_version"]["const"] == (
        FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION
    )
    assert "OPENAI_API_KEY" not in encoded
    assert "Bearer" not in encoded


def test_config_rejects_evaluated_pair_model(tmp_path: Path) -> None:
    config_path = _write_json(tmp_path / "judge_config.json", _config_payload(model="first_model"))

    with pytest.raises(FlagshipAPIJudgeError, match="judge_model_matches_evaluated_pair"):
        load_flagship_api_judge_config(config_path)


def test_missing_api_key_returns_controlled_warning_without_request(tmp_path: Path) -> None:
    paths = _fixture_files(tmp_path)
    calls: list[object] = []

    def fake_transport(*args: object, **kwargs: object) -> dict[str, Any]:
        calls.append((args, kwargs))
        return {"output_text": json.dumps(_verdict(), ensure_ascii=False)}

    result = run_guarded_flagship_api_judge(
        judge_config_path=paths["config"],
        prompt_pack_path=paths["prompt_pack"],
        schema_path=paths["schema"],
        output_path=tmp_path / "raw_responses.jsonl",
        allow_api_judge=True,
        confirm_api_judge=FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION,
        environ={},
        transport=fake_transport,
    )

    assert result["status"] == "invalid_input"
    assert result["warnings"] == ["judge_api_key_missing"]
    assert result["api_call_count"] == 0
    assert calls == []


def test_fake_transport_writes_compatible_raw_response_row(tmp_path: Path) -> None:
    paths = _fixture_files(tmp_path)
    captured_headers: list[Mapping[str, str]] = []

    def fake_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> dict[str, Any]:
        del url, body, timeout
        captured_headers.append(headers)
        return {"output_text": json.dumps(_verdict(), ensure_ascii=False)}

    output_path = tmp_path / "raw_responses.jsonl"
    result = run_guarded_flagship_api_judge(
        judge_config_path=paths["config"],
        prompt_pack_path=paths["prompt_pack"],
        schema_path=paths["schema"],
        output_path=output_path,
        allow_api_judge=True,
        confirm_api_judge=FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION,
        environ={"OPENAI_API_KEY": "test-secret-value"},
        transport=fake_transport,
    )
    row = json.loads(output_path.read_text(encoding="utf-8"))
    encoded = json.dumps(row, ensure_ascii=False)

    assert result["status"] == "ok"
    assert result["api_call_count"] == 1
    assert captured_headers[0]["Authorization"] == "Bearer test-secret-value"
    assert row["schema_version"] == "flagship_api_judge_raw_response_v1"
    assert row["response"]["verdict"] == "pass"
    assert row["raw_response"].startswith("{")
    assert "test-secret-value" not in encoded
    assert "Authorization" not in encoded


def test_response_extraction_supports_output_text_and_content_text() -> None:
    assert extract_openai_response_text({"output_text": "direct text"}) == "direct text"
    assert (
        extract_openai_response_text({"output": [{"content": [{"type": "output_text", "text": "nested text"}]}]})
        == "nested text"
    )


def test_api_error_writes_safe_error_row_without_auth_leakage(tmp_path: Path) -> None:
    paths = _fixture_files(tmp_path)

    def fake_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> dict[str, Any]:
        del url, headers, body, timeout
        raise RuntimeError("Authorization Bearer test-secret-value")

    output_path = tmp_path / "raw_responses.jsonl"
    result = run_guarded_flagship_api_judge(
        judge_config_path=paths["config"],
        prompt_pack_path=paths["prompt_pack"],
        schema_path=paths["schema"],
        output_path=output_path,
        allow_api_judge=True,
        confirm_api_judge=FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION,
        environ={"OPENAI_API_KEY": "test-secret-value"},
        transport=fake_transport,
    )
    encoded = output_path.read_text(encoding="utf-8")

    assert result["status"] == "completed_with_errors"
    assert "judge_api_error:RuntimeError" in result["warnings"]
    assert "test-secret-value" not in encoded
    assert "Authorization" not in encoded


def test_parse_after_run_produces_summary_with_fake_response(tmp_path: Path) -> None:
    paths = _fixture_files(tmp_path)

    def fake_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> dict[str, Any]:
        del url, headers, body, timeout
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(_verdict(), ensure_ascii=False)}]}]}

    parsed_output = tmp_path / "flagship_judge_summary.json"
    result = run_guarded_flagship_api_judge(
        judge_config_path=paths["config"],
        prompt_pack_path=paths["prompt_pack"],
        schema_path=paths["schema"],
        output_path=tmp_path / "raw_responses.jsonl",
        allow_api_judge=True,
        confirm_api_judge=FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION,
        environ={"OPENAI_API_KEY": "test-secret-value"},
        transport=fake_transport,
        parse_after_run=True,
        parsed_output_path=parsed_output,
    )
    summary = json.loads(parsed_output.read_text(encoding="utf-8"))

    assert result["status"] == "ok"
    assert summary["valid_response_count"] == 1
    assert summary["mean_scores"]["overall"] == 0.9


def test_provider_module_does_not_import_runtime_or_api_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("openai", "httpx", "requests", "playwright", "win32com", "pythoncom", "uno", "llama_cpp")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"Forbidden runtime import attempted: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    payload = build_openai_responses_payload(_prompt_record(), flagship_judge_verdict_schema(), _config_payload())

    assert payload["model"] == "flagship_judge_model"
