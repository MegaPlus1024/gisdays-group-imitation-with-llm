from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import src.agent.orchestrator_executor_pipeline as pipeline
from src.agent.prompt_contract import PromptBuilder, PromptContractConfig
from src.agent.state import (
    ActionHistoryEntry,
    ActionSpec,
    AgentConstraints,
    AgentObjective,
    AgentResources,
    AgentRole,
    AgentState,
)
from src.agent.orchestrator_executor_pipeline import (
    ExecutorModelConfig,
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
    PromptBudgetConfig,
)
from src.agent.orchestrator_prompt_contract import (
    OrchestratorPlanJSONError,
    parse_orchestrator_plan_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"


def _config(tmp_path: Path, **overrides: object) -> OrchestratorExecutorRunConfig:
    payload: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "mode": "fake",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": SCENARIO,
        "out_dir": str(tmp_path / "group_artifacts"),
        "run_id": "test_orchestrator_executor_fake",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "max_group_steps": 2,
        "max_steps_per_agent": 2,
        "repair_attempts": 1,
        "execute_actions": False,
        "force": True,
    }
    payload.update(overrides)
    return OrchestratorExecutorRunConfig.model_validate(payload)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bloated_agent_state() -> AgentState:
    action_schemas = {
        f"action_{index}": {
            "description": "Long registry action description. " * 60,
            "required_parameters": ["path", "content"],
            "parameters": {
                "path": {
                    "type": "string",
                    "required": True,
                    "description": "Relative project path under safe roots. " * 30,
                },
                "content": {
                    "type": "string",
                    "required": False,
                    "description": "Short local note content. " * 30,
                },
            },
            "allowed_file_roots": ["artifacts/single_trial_runs/phase_8_20_compact_retry/workspace/"],
            "forbidden_file_roots": ["models/gguf/", ".venv/", ".git/"],
            "allowed_shell_commands": [],
            "examples": [{"path": f"artifacts/example_{index}.md", "content": "example " * 80}],
        }
        for index in range(12)
    }
    return AgentState(
        agent_id="document_summary_agent",
        role=AgentRole(
            name="document_summary_agent",
            description="Summarize safe local project document workflow state. " * 50,
            constraints=["Use local files only. " * 20],
        ),
        objective=AgentObjective(
            primary="TASK_SENTINEL summarize controlled local document workflow.",
            success_criteria=["Return one valid NextAction JSON object."],
        ),
        resources=AgentResources(
            files=[f"configs/example_{index}.json" for index in range(40)],
            notes=["Large resource note. " * 80 for _ in range(10)],
        ),
        constraints=AgentConstraints(
            allowed_file_roots=["configs/", "docs/", "artifacts/"],
            forbidden_file_roots=["models/gguf/", ".venv/", ".git/"],
        ),
        available_actions=[
            ActionSpec(
                name=f"action_{index}",
                description="Large action description. " * 80,
                parameters_schema=action_schemas[f"action_{index}"]["parameters"],
                safety_notes=["Do not touch forbidden paths. " * 20],
            )
            for index in range(12)
        ],
        history=[
            ActionHistoryEntry(
                step=index,
                action="read_file",
                parameters={"path": f"configs/history_{index}.json", "content": "history " * 100},
                status="success",
                summary="Historical action summary. " * 40,
            )
            for index in range(1, 12)
        ],
        current_step=12,
        metadata={
            "assigned_goal": "TASK_SENTINEL summarize controlled local document workflow.",
            "orchestrator_task_id": "t1",
            "executor_prompt_hints": {
                "agent_id": "document_summary_agent",
                "role_id": "document_summary_agent",
                "task_id": "t1",
                "assigned_goal": "TASK_SENTINEL summarize controlled local document workflow.",
                "success_criteria": "Return one valid NextAction JSON object.",
                "allowed_actions": list(action_schemas),
                "action_schemas": action_schemas,
                "safe_path_roots": ["configs/", "docs/", "artifacts/"],
                "safe_existing_read_paths": [f"configs/example_{index}.json" for index in range(40)],
                "safe_write_path_examples": [f"artifacts/out_{index}.md" for index in range(40)],
                "path_rules": ["Use relative project paths only.", "Do not use absolute paths."],
                "json_only_example": {
                    "action": "action_0",
                    "parameters": {"path": "configs/example_0.json"},
                    "reason": "Read safe local input.",
                    "expected_result": "Local input is available.",
                },
            },
            "raw_prompt": "RAW_PROMPT_MARKER_SHOULD_NOT_LEAK",
        },
    )


def test_parse_valid_orchestrator_plan_json() -> None:
    raw = json.dumps(
        {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_id": "office_agent",
                    "goal": "Read local metadata.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Local metadata was reviewed.",
                }
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "A local-only group run completes.",
        }
    )

    plan = parse_orchestrator_plan_text(
        raw,
        known_agent_ids={"office_agent"},
        allowed_action_names_by_agent={"office_agent": {"read_file", "create_file"}},
    )

    assert plan.tasks[0].task_id == "task_1"
    assert plan.tasks[0].agent_id == "office_agent"


def test_parse_orchestrator_plan_rejects_unknown_agent() -> None:
    raw = json.dumps(
        {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_id": "missing_agent",
                    "goal": "Read local metadata.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Local metadata was reviewed.",
                }
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "A local-only group run completes.",
        }
    )

    with pytest.raises(OrchestratorPlanJSONError, match="Unknown agent_id"):
        parse_orchestrator_plan_text(raw, known_agent_ids={"office_agent"})


def test_fake_group_run_completes_and_writes_artifacts(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    out_dir = Path(result.artifact_dir or "")

    assert result.status == "completed"
    assert result.success is True
    assert result.orchestrator_model_id == "second_model"
    assert result.executor_model_ids == ["first_model"]
    assert 0.0 <= result.quality_metrics.pair_quality_score <= 1.0

    for name in [
        "manifest.json",
        "orchestrator_prompt.json",
        "orchestrator_raw_output.json",
        "orchestrator_plan.json",
        "orchestrator_validation.json",
        "agent_assignments.json",
        "group_steps.jsonl",
        "group_history.jsonl",
        "per_agent_actions.jsonl",
        "per_agent_attempts.jsonl",
        "per_agent_validation_results.jsonl",
        "per_agent_execution_results.jsonl",
        "errors.jsonl",
        "pair_quality_metrics.json",
        "pair_evaluation.json",
        "resource_summary.json",
        "README.md",
        "replay_commands.ps1",
    ]:
        assert (out_dir / name).exists(), name


def test_fake_group_run_logs_per_agent_actions_and_group_history(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    out_dir = Path(result.artifact_dir or "")

    actions = _jsonl(out_dir / "per_agent_actions.jsonl")
    group_history = _jsonl(out_dir / "group_history.jsonl")

    assert len(actions) == 4
    assert len(group_history) == 4
    assert {row["agent_id"] for row in actions} == {"office_agent", "developer_agent"}
    assert {row["agent_id"] for row in group_history} == {"office_agent", "developer_agent"}
    assert all(row["validation_accepted"] is True for row in actions)


def test_pair_quality_score_is_persisted_in_range(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    metrics = _json(Path(result.artifact_dir or "") / "pair_quality_metrics.json")

    assert metrics["orchestrator_plan_valid"] is True
    assert 0.0 <= metrics["pair_quality_score"] <= 1.0
    assert metrics["metadata"]["prototype_scoring"] is True
    assert result.pair_evaluation.verdict in {"prototype_pass", "prototype_with_failures", "failed"}


def test_fake_mode_does_not_call_http_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.orchestrator_executor_pipeline as pipeline

    def fail_http_client(*args: object, **kwargs: object) -> object:
        raise AssertionError("fake mode must not create an HTTP client")

    monkeypatch.setattr(pipeline.httpx, "Client", fail_http_client)

    result = OrchestratorExecutorRunner(_config(tmp_path)).run()

    assert result.status == "completed"


def test_executor_compact_prompt_budget_reduces_context_and_preserves_contract() -> None:
    state = _bloated_agent_state()
    builder = PromptBuilder(PromptContractConfig(include_history_limit=20))

    messages, metadata = pipeline._executor_messages_with_budget(
        builder,
        state,
        PromptBudgetConfig(
            executor_max_prompt_chars=12000,
            max_history_items=3,
            compact_executor_context=True,
        ),
    )
    text = json.dumps(messages, ensure_ascii=False)

    assert metadata["prompt_budget_applied"] is True
    assert metadata["prompt_chars_before"] > metadata["prompt_chars_after"]
    assert metadata["estimated_prompt_chars"] == metadata["prompt_chars_after"]
    assert metadata["prompt_budget_strategy"] in {"compact_executor_context", "minimal_executor_context"}
    assert "NEXT_ACTION_OUTPUT_CONTRACT" in text
    assert "TASK_SENTINEL" in text
    assert "document_summary_agent" in text
    assert "RAW_PROMPT_MARKER_SHOULD_NOT_LEAK" not in text
    assert metadata["prompt_chars_after"] <= 12000


def test_local_executor_request_diagnostics_include_prompt_budget_metadata() -> None:
    model = ExecutorModelConfig(
        model_id="first_model",
        base_url="http://127.0.0.1:8081/v1",
        model_name="first_model.gguf",
        api_model="first_model",
    )
    payload = {
        "model": "first_model",
        "messages": [{"role": "user", "content": "shape only"}],
        "temperature": 0.0,
        "max_tokens": 1,
    }

    error = pipeline._local_model_http_error(
        pipeline.httpx.ConnectError("offline shape check"),
        model=model,
        payload=payload,
        url="http://127.0.0.1:8081/v1/chat/completions",
        request_metadata={
            "estimated_prompt_chars": 11800,
            "prompt_budget_applied": True,
            "prompt_chars_before": 42000,
            "prompt_chars_after": 11800,
            "prompt_budget_max_chars": 12000,
            "compact_executor_context": True,
            "max_history_items": 6,
            "prompt_budget_strategy": "compact_executor_context",
        },
    )

    shape = error.diagnostics["request_shape"]
    assert shape["estimated_prompt_chars"] == 11800
    assert shape["prompt_budget_applied"] is True
    assert shape["prompt_chars_before"] == 42000
    assert shape["prompt_chars_after"] == 11800
    assert shape["compact_executor_context"] is True
    assert shape["max_tokens_present"] is True


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_orchestrator_executor_group.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--scenario" in completed.stdout
    assert "--orchestrator-model-id" in completed.stdout


def test_cli_fake_run_writes_manifest_and_pair_evaluation(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_group_artifacts"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_orchestrator_executor_group.py",
            "--mode",
            "fake",
            "--models-config",
            "configs/evaluation_models.json",
            "--scenario",
            SCENARIO,
            "--out-dir",
            str(out_dir),
            "--run-id",
            "cli_orchestrator_executor_fake",
            "--orchestrator-model-id",
            "second_model",
            "--executor-model-id",
            "first_model",
            "--max-group-steps",
            "2",
            "--max-steps-per-agent",
            "2",
            "--repair-attempts",
            "1",
            "--no-execute-actions",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "pair_quality_score:" in completed.stdout
    assert _json(out_dir / "manifest.json")["run_id"] == "cli_orchestrator_executor_fake"
    assert _json(out_dir / "pair_evaluation.json")["orchestrator_model_id"] == "second_model"
