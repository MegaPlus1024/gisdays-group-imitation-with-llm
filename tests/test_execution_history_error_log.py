from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.execution_history import (
    ExecutionErrorRecord,
    ExecutionHistoryConfig,
    ExecutionHistoryLogger,
    ExecutionHistoryRecord,
    load_execution_history_config,
    stable_record_id,
    truncate_text,
    utc_now_iso,
)


def test_load_execution_history_example_config() -> None:
    cfg = load_execution_history_config("configs/execution_history.example.json")
    assert cfg.history_id == "execution_history_v1"
    assert cfg.history_filename.endswith(".jsonl")
    assert cfg.error_filename.endswith(".jsonl")


def test_execution_history_config_rejects_bad_filenames() -> None:
    with pytest.raises(ValidationError):
        ExecutionHistoryConfig(history_filename="history.log")
    with pytest.raises(ValidationError):
        ExecutionHistoryConfig(error_filename="errors.log")


def test_stable_record_id_is_deterministic() -> None:
    a = stable_record_id("decision", "run 1", "agent/1", 2, "selected")
    b = stable_record_id("decision", "run 1", "agent/1", 2, "selected")
    assert a == b
    assert " " not in a
    assert "/" not in a


def test_truncate_text_truncates_when_needed() -> None:
    short = "abc"
    assert truncate_text(short, 10) == short
    long = "x" * 20
    out = truncate_text(long, 5)
    assert out.endswith("...[truncated]")


def test_logger_append_and_read_history_and_error(tmp_path: Path) -> None:
    logger = ExecutionHistoryLogger(
        config=ExecutionHistoryConfig(log_root=str(tmp_path / "logs"))
    )

    history = ExecutionHistoryRecord(
        record_id="decision_run_agent_step1_selected",
        record_type="decision",
        status="success",
        created_at=utc_now_iso(),
        run_id="run",
        agent_id="agent",
        step_index=1,
        summary="Selected one action",
    )
    error = ExecutionErrorRecord(
        error_id="error_run_agent_step1_failed",
        created_at=utc_now_iso(),
        run_id="run",
        agent_id="agent",
        step_index=1,
        error_type="SampleError",
        error_message="Something went wrong",
    )

    hp = logger.append_history(history)
    ep = logger.append_error(error)
    assert hp.exists()
    assert ep.exists()

    history_rows = logger.read_history()
    error_rows = logger.read_errors()
    assert len(history_rows) == 1
    assert len(error_rows) == 1
    assert history_rows[0]["record_id"] == history.record_id
    assert error_rows[0]["error_id"] == error.error_id


def test_logger_clear_logs_removes_files(tmp_path: Path) -> None:
    logger = ExecutionHistoryLogger(
        config=ExecutionHistoryConfig(log_root=str(tmp_path / "logs"))
    )
    history = ExecutionHistoryRecord(
        record_id="decision_run_agent_step1_selected",
        record_type="decision",
        status="success",
        created_at=utc_now_iso(),
        run_id="run",
        agent_id="agent",
        step_index=1,
        summary="Selected one action",
    )
    logger.append_history(history)
    assert logger.history_path.exists()
    logger.clear_logs()
    assert not logger.history_path.exists()


def test_load_jsonl_raises_on_non_object_line(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text(json.dumps([1, 2, 3]) + "\n", encoding="utf-8")
    logger = ExecutionHistoryLogger(
        config=ExecutionHistoryConfig(log_root=str(tmp_path / "logs"))
    )
    # Reuse module parser through logger by replacing path target.
    logger.history_path = p
    with pytest.raises(ValueError):
        logger.read_history()
