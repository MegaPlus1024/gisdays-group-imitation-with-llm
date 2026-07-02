from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .action_selector import ActionSelectionResult
from .runner import RunnerRunResult, RunnerStepResult
from .script_registry import ScriptValidationResult
from .script_runner_errors import NormalizedScriptResult

ExecutionRecordType = Literal[
    "decision",
    "validation",
    "execution",
    "runner_step",
    "runner_run",
    "error",
    "note",
]

ExecutionRecordStatus = Literal[
    "success",
    "failure",
    "skipped",
    "pending_execution",
    "validation_failed",
    "decision_failed",
    "execution_failed",
    "unknown",
]

LogSeverity = Literal["debug", "info", "warning", "error", "critical"]


class ExecutionHistoryConfig(BaseModel):
    history_id: str = "execution_history_v1"
    log_root: str = "logs/execution"
    history_filename: str = "history.jsonl"
    error_filename: str = "errors.jsonl"
    create_parent_dirs: bool = True
    include_raw_metadata: bool = True
    max_message_length: int = 10_000
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("history_id", "log_root")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("history_id and log_root must be non-empty.")
        return value

    @field_validator("history_filename")
    @classmethod
    def validate_history_filename(cls, value: str) -> str:
        if not value.endswith(".jsonl"):
            raise ValueError("history_filename must end with .jsonl.")
        return value

    @field_validator("error_filename")
    @classmethod
    def validate_error_filename(cls, value: str) -> str:
        if not value.endswith(".jsonl"):
            raise ValueError("error_filename must end with .jsonl.")
        return value

    @field_validator("max_message_length")
    @classmethod
    def validate_max_message_length(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_message_length must be > 0.")
        return value


class ExecutionHistoryRecord(BaseModel):
    record_id: str
    record_type: ExecutionRecordType
    status: ExecutionRecordStatus
    created_at: str
    run_id: str
    agent_id: str
    step_index: int | None = None
    action: str | None = None
    next_action: dict[str, Any] | None = None
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    error_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("record_id", "created_at", "run_id", "agent_id", "summary")
    @classmethod
    def validate_non_empty_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("record_id/created_at/run_id/agent_id/summary must be non-empty.")
        return value

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("step_index must be >= 1 when provided.")
        return value


class ExecutionErrorRecord(BaseModel):
    error_id: str
    created_at: str
    run_id: str
    agent_id: str
    step_index: int | None = None
    action: str | None = None
    error_type: str
    error_message: str
    severity: LogSeverity = "error"
    retryable: bool = False
    recovery_category: str | None = None
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("error_id", "created_at", "run_id", "agent_id", "error_type", "error_message")
    @classmethod
    def validate_non_empty_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required string field must be non-empty.")
        return value

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("step_index must be >= 1 when provided.")
        return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_token(value: str) -> str:
    sanitized = value.replace("\\", "_").replace("/", "_").replace(" ", "_")
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    return sanitized.strip("_")


def stable_record_id(
    prefix: str,
    run_id: str,
    agent_id: str,
    step_index: int | None = None,
    suffix: str | None = None,
) -> str:
    parts = [_sanitize_token(prefix), _sanitize_token(run_id), _sanitize_token(agent_id)]
    if step_index is not None:
        parts.append(f"step{step_index}")
    if suffix is not None and suffix.strip():
        parts.append(_sanitize_token(suffix))
    return "_".join(parts)


def truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + "...[truncated]"


def record_to_json_line(record: BaseModel) -> str:
    payload = record.model_dump()
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path_obj = Path(path)
    if not path_obj.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw_line in path_obj.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError("JSONL line must be a JSON object.")
        out.append(parsed)
    return out


class ExecutionHistoryLogger:
    def __init__(
        self,
        config: ExecutionHistoryConfig | None = None,
        log_root: str | Path | None = None,
    ) -> None:
        self.config = config or ExecutionHistoryConfig()
        root = Path(log_root) if log_root is not None else Path(self.config.log_root)
        self.log_root = root
        self.history_path = self.log_root / self.config.history_filename
        self.error_path = self.log_root / self.config.error_filename
        if self.config.create_parent_dirs:
            self.log_root.mkdir(parents=True, exist_ok=True)

    def append_history(self, record: ExecutionHistoryRecord) -> Path:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(record_to_json_line(record))
        return self.history_path

    def append_error(self, record: ExecutionErrorRecord) -> Path:
        self.error_path.parent.mkdir(parents=True, exist_ok=True)
        with self.error_path.open("a", encoding="utf-8") as f:
            f.write(record_to_json_line(record))
        return self.error_path

    def append_history_and_error(
        self,
        history_record: ExecutionHistoryRecord,
        error_record: ExecutionErrorRecord | None = None,
    ) -> tuple[Path, Path | None]:
        hp = self.append_history(history_record)
        ep: Path | None = None
        if error_record is not None:
            ep = self.append_error(error_record)
        return hp, ep

    def read_history(self) -> list[dict[str, Any]]:
        return load_jsonl(self.history_path)

    def read_errors(self) -> list[dict[str, Any]]:
        return load_jsonl(self.error_path)

    def clear_logs(self) -> None:
        if self.history_path.exists():
            self.history_path.unlink()
        if self.error_path.exists():
            self.error_path.unlink()


def _build_error_record(
    *,
    error_id: str,
    run_id: str,
    agent_id: str,
    step_index: int | None,
    action: str | None,
    error_type: str,
    error_message: str,
    severity: LogSeverity = "error",
    retryable: bool = False,
    recovery_category: str | None = None,
    source: str | None = None,
    details: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExecutionErrorRecord:
    return ExecutionErrorRecord(
        error_id=error_id,
        created_at=utc_now_iso(),
        run_id=run_id,
        agent_id=agent_id,
        step_index=step_index,
        action=action,
        error_type=error_type,
        error_message=error_message,
        severity=severity,
        retryable=retryable,
        recovery_category=recovery_category,
        source=source,
        details=details or {},
        metadata=metadata or {},
    )


def _validation_issue_codes(validation_result: ScriptValidationResult | None) -> list[str]:
    if validation_result is None:
        return []
    return [issue.code for issue in validation_result.issues]


def history_from_action_selection(
    result: ActionSelectionResult,
    run_id: str,
    step_index: int | None = None,
) -> tuple[ExecutionHistoryRecord, ExecutionErrorRecord | None]:
    now = utc_now_iso()
    action_name = result.next_action.action if result.next_action is not None else None
    next_action_dict = result.next_action.model_dump() if result.next_action is not None else None
    if result.success:
        return (
            ExecutionHistoryRecord(
                record_id=stable_record_id("decision", run_id, result.agent_id, step_index, "selected"),
                record_type="decision",
                status="success",
                created_at=now,
                run_id=run_id,
                agent_id=result.agent_id,
                step_index=step_index,
                action=action_name,
                next_action=next_action_dict,
                summary=f"Action selected: {action_name}",
                details={"status": result.status},
                metadata=dict(result.metadata),
            ),
            None,
        )

    status: ExecutionRecordStatus = "decision_failed"
    record_type: ExecutionRecordType = "decision"
    if result.status == "validation_failed":
        status = "validation_failed"
        record_type = "validation"
    issue_codes = _validation_issue_codes(result.validation_result)
    error_id = stable_record_id("error", run_id, result.agent_id, step_index, result.error_type or "unknown")
    error = _build_error_record(
        error_id=error_id,
        run_id=run_id,
        agent_id=result.agent_id,
        step_index=step_index,
        action=action_name,
        error_type=result.error_type or "validation_failed",
        error_message=result.error_message or "Action selection failed.",
        details={"issue_codes": issue_codes},
        source="ActionSelector",
    )
    history = ExecutionHistoryRecord(
        record_id=stable_record_id(record_type, run_id, result.agent_id, step_index, "failed"),
        record_type=record_type,
        status=status,
        created_at=now,
        run_id=run_id,
        agent_id=result.agent_id,
        step_index=step_index,
        action=action_name,
        next_action=next_action_dict,
        summary=result.error_message or "Action selection failed.",
        details={"status": result.status, "issue_codes": issue_codes},
        error_id=error.error_id,
        metadata=dict(result.metadata),
    )
    return history, error


def history_from_runner_step(
    result: RunnerStepResult,
) -> tuple[ExecutionHistoryRecord, ExecutionErrorRecord | None]:
    status_map: dict[str, ExecutionRecordStatus] = {
        "decision_succeeded": "success",
        "decision_failed": "decision_failed",
        "validation_succeeded": "success",
        "validation_failed": "validation_failed",
        "pending_execution": "pending_execution",
        "skipped": "skipped",
        "stopped": "failure",
    }
    status = status_map.get(result.status, "unknown")
    next_action_dict = result.next_action.model_dump() if result.next_action is not None else None
    action_name = result.next_action.action if result.next_action is not None else None
    issue_codes = _validation_issue_codes(result.validation_result)
    error: ExecutionErrorRecord | None = None
    error_id: str | None = None
    if not result.success:
        error_id = stable_record_id("error", result.run_id, result.agent_id, result.step_index, result.error_type or "runner_error")
        error = _build_error_record(
            error_id=error_id,
            run_id=result.run_id,
            agent_id=result.agent_id,
            step_index=result.step_index,
            action=action_name,
            error_type=result.error_type or "runner_step_failed",
            error_message=result.error_message or "Runner step failed.",
            details={"runner_status": result.status, "issue_codes": issue_codes},
            source="AgentRunner",
        )
    history = ExecutionHistoryRecord(
        record_id=stable_record_id("runner_step", result.run_id, result.agent_id, result.step_index, result.status),
        record_type="runner_step",
        status=status,
        created_at=utc_now_iso(),
        run_id=result.run_id,
        agent_id=result.agent_id,
        step_index=result.step_index,
        action=action_name,
        next_action=next_action_dict,
        summary=f"Runner step status: {result.status}",
        details={"runner_status": result.status, "issue_codes": issue_codes},
        error_id=error_id,
        metadata=dict(result.metadata),
    )
    return history, error


def history_from_normalized_script_result(
    result: NormalizedScriptResult,
    run_id: str,
    agent_id: str,
    step_index: int | None = None,
) -> tuple[ExecutionHistoryRecord, ExecutionErrorRecord | None]:
    if result.success:
        history = ExecutionHistoryRecord(
            record_id=stable_record_id("execution", run_id, agent_id, step_index, "success"),
            record_type="execution",
            status="success",
            created_at=utc_now_iso(),
            run_id=run_id,
            agent_id=agent_id,
            step_index=step_index,
            action=result.action,
            summary=f"Execution succeeded for action '{result.action}'.",
            details={"output": result.output},
            metadata=dict(result.metadata),
        )
        return history, None

    assert result.error is not None
    error_id = stable_record_id("error", run_id, agent_id, step_index, result.error.category)
    error = _build_error_record(
        error_id=error_id,
        run_id=run_id,
        agent_id=agent_id,
        step_index=step_index,
        action=result.action,
        error_type=result.error.original_error_type or result.error.category,
        error_message=result.error.message,
        severity=result.error.severity,
        retryable=result.error.retryable,
        recovery_category=result.error.recovery_category,
        source=result.error.source,
        details={"category": result.error.category},
        metadata=dict(result.error.metadata),
    )
    history = ExecutionHistoryRecord(
        record_id=stable_record_id("execution", run_id, agent_id, step_index, "failed"),
        record_type="execution",
        status="execution_failed",
        created_at=utc_now_iso(),
        run_id=run_id,
        agent_id=agent_id,
        step_index=step_index,
        action=result.action,
        summary=f"Execution failed for action '{result.action}'.",
        details={"error_category": result.error.category},
        error_id=error_id,
        metadata=dict(result.metadata),
    )
    return history, error


def load_execution_history_config(path: str | Path) -> ExecutionHistoryConfig:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return ExecutionHistoryConfig.model_validate(payload)
