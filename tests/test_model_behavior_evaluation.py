from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.activity_evaluator import ActivityEvaluationResult
from src.agent.activity_profile import load_activity_profile
from src.agent.model_behavior_evaluation import (
    ModelBehaviorEvaluationConfig,
    ModelBehaviorEvaluationResult,
    ModelBehaviorModelSpec,
    ModelBehaviorResourceMetrics,
    ModelBehaviorSelectedAction,
    ModelBehaviorValidationMetrics,
    activity_steps_from_model_actions,
    build_synthetic_model_behavior_result,
    build_validation_metrics_from_actions,
    derive_model_behavior_verdict,
    load_model_behavior_evaluation_config,
    load_model_behavior_result,
    save_model_behavior_result,
)


def _actions() -> list[ModelBehaviorSelectedAction]:
    return [
        ModelBehaviorSelectedAction(
            step_index=1,
            action="read_file",
            parameters={"path": "docs/ai/project_objective_normal_activity_v1.md"},
            registry_accepted=True,
            role_compliant=True,
            executed=True,
            success=True,
        ),
        ModelBehaviorSelectedAction(
            step_index=2,
            action="office_create_document_stub",
            parameters={"path": "docs/ai/x.md", "title": "x", "body": "y"},
            registry_accepted=True,
            role_compliant=True,
            executed=True,
            success=True,
            reason="Based on previous step context.",
        ),
    ]


def test_config_defaults_valid() -> None:
    cfg = ModelBehaviorEvaluationConfig()
    assert cfg.harness_id == "model_behavior_evaluation_v1"


def test_load_config() -> None:
    cfg = load_model_behavior_evaluation_config("configs/model_behavior_evaluation.example.json")
    assert cfg.default_run_mode == "synthetic"


def test_model_spec_rejects_empty_model_id() -> None:
    with pytest.raises(ValueError):
        ModelBehaviorModelSpec(model_id="", model_name="x")


def test_resource_metrics_reject_negative_values() -> None:
    with pytest.raises(ValueError):
        ModelBehaviorResourceMetrics(cpu_percent_avg=-1)


def test_validation_rates_zero_when_no_steps() -> None:
    m = ModelBehaviorValidationMetrics(total_steps=0)
    assert m.json_validity_rate() == 0.0
    assert m.registry_acceptance_rate() == 0.0


def test_validation_rates_compute_correctly() -> None:
    m = ModelBehaviorValidationMetrics(
        total_steps=4,
        json_valid_count=4,
        next_action_parse_success_count=3,
        registry_accepted_count=2,
        role_compliant_count=3,
        validation_failure_count=1,
        unsafe_action_count=1,
    )
    assert m.json_validity_rate() == 1.0
    assert m.next_action_parse_success_rate() == 0.75
    assert m.registry_acceptance_rate() == 0.5
    assert m.role_compliance_rate() == 0.75
    assert m.validation_failure_rate() == 0.25
    assert m.unsafe_action_rate() == 0.25


def test_selected_action_rejects_duplicate_issue_codes() -> None:
    with pytest.raises(ValueError):
        ModelBehaviorSelectedAction(step_index=1, action="read_file", issue_codes=["x", "x"])


def test_build_validation_metrics_from_actions_counts() -> None:
    actions = [
        ModelBehaviorSelectedAction(
            step_index=1,
            action="read_file",
            registry_accepted=True,
            role_compliant=True,
            executed=True,
            success=True,
        ),
        ModelBehaviorSelectedAction(
            step_index=2,
            action="run_shell_command",
            registry_accepted=False,
            role_compliant=False,
            executed=True,
            success=False,
            issue_codes=["unsafe_action"],
        ),
    ]
    m = build_validation_metrics_from_actions(actions)
    assert m.total_steps == 2
    assert m.registry_accepted_count == 1
    assert m.role_compliant_count == 1
    assert m.validation_failure_count == 1
    assert m.unsafe_action_count == 1
    assert m.execution_success_count == 1
    assert m.execution_failure_count == 1


def test_activity_steps_from_model_actions_converts() -> None:
    steps = activity_steps_from_model_actions(_actions())
    assert len(steps) == 2
    assert steps[0].action == "read_file"


def test_activity_steps_from_model_actions_detects_history_usage() -> None:
    steps = activity_steps_from_model_actions(_actions())
    assert steps[1].used_history is True


def test_derive_verdict_insufficient_data_zero_steps() -> None:
    v = derive_model_behavior_verdict(ModelBehaviorValidationMetrics(total_steps=0), None)
    assert v == "insufficient_data"


def test_derive_verdict_fail_low_registry_rate() -> None:
    metrics = ModelBehaviorValidationMetrics(total_steps=2, registry_accepted_count=0, role_compliant_count=2)
    v = derive_model_behavior_verdict(metrics, None, ModelBehaviorEvaluationConfig(require_behavioral_evaluation=False))
    assert v == "fail"


def test_derive_verdict_fail_low_role_compliance() -> None:
    metrics = ModelBehaviorValidationMetrics(total_steps=2, registry_accepted_count=2, role_compliant_count=0)
    v = derive_model_behavior_verdict(metrics, None, ModelBehaviorEvaluationConfig(require_behavioral_evaluation=False))
    assert v == "fail"


def test_derive_verdict_insufficient_data_when_behavior_required_but_missing() -> None:
    metrics = ModelBehaviorValidationMetrics(total_steps=2, registry_accepted_count=2, role_compliant_count=2)
    v = derive_model_behavior_verdict(metrics, None, ModelBehaviorEvaluationConfig(require_behavioral_evaluation=True))
    assert v == "insufficient_data"


def test_derive_verdict_pass_for_high_score() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    model = ModelBehaviorModelSpec(model_id="m1", model_name="first_model.gguf")
    result = build_synthetic_model_behavior_result(
        evaluation_id="e1",
        run_id="r1",
        scenario_id="s1",
        model=model,
        actions=_actions(),
        activity_profile=profile,
    )
    assert result.verdict in {"pass", "warning"}


def test_derive_verdict_warning_for_medium_score() -> None:
    metrics = ModelBehaviorValidationMetrics(total_steps=2, registry_accepted_count=2, role_compliant_count=2)
    behavioral = ActivityEvaluationResult.model_validate(
        {
            "evaluator_id": "x",
            "profile_id": "p",
            "role_id": "r",
            "verdict": "suspicious",
            "score": 0.65,
            "metrics": {"normal_activity_score": 0.65},
            "explanations": [],
        }
    )
    v = derive_model_behavior_verdict(metrics, behavioral)
    assert v == "warning"


def test_derive_verdict_fail_for_low_score() -> None:
    metrics = ModelBehaviorValidationMetrics(total_steps=2, registry_accepted_count=2, role_compliant_count=2)
    behavioral = ActivityEvaluationResult.model_validate(
        {
            "evaluator_id": "x",
            "profile_id": "p",
            "role_id": "r",
            "verdict": "failed",
            "score": 0.4,
            "metrics": {"normal_activity_score": 0.4},
            "explanations": [],
        }
    )
    v = derive_model_behavior_verdict(metrics, behavioral)
    assert v == "fail"


def test_build_synthetic_result_includes_behavioral_eval() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    model = ModelBehaviorModelSpec(model_id="m1", model_name="first_model.gguf")
    result = build_synthetic_model_behavior_result(
        evaluation_id="eval_1",
        run_id="run_1",
        scenario_id="office_worker_basic_session_v1",
        model=model,
        actions=_actions(),
        activity_profile=profile,
    )
    assert result.behavioral_evaluation is not None
    assert result.validation_metrics.total_steps == 2


def test_summary_dict_json_serializable() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    model = ModelBehaviorModelSpec(model_id="m1", model_name="first_model.gguf")
    result = build_synthetic_model_behavior_result(
        evaluation_id="eval_1",
        run_id="run_1",
        scenario_id="office_worker_basic_session_v1",
        model=model,
        actions=_actions(),
        activity_profile=profile,
    )
    summary = result.summary_dict()
    json.dumps(summary)
    assert summary["evaluation_id"] == "eval_1"


def test_save_load_roundtrip(tmp_path) -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    model = ModelBehaviorModelSpec(model_id="m1", model_name="first_model.gguf")
    result = build_synthetic_model_behavior_result(
        evaluation_id="eval_1",
        run_id="run_1",
        scenario_id="office_worker_basic_session_v1",
        model=model,
        actions=_actions(),
        activity_profile=profile,
    )
    out = tmp_path / "result.json"
    save_model_behavior_result(result, out)
    loaded = load_model_behavior_result(out)
    assert isinstance(loaded, ModelBehaviorEvaluationResult)
    assert loaded.evaluation_id == result.evaluation_id


def test_doc_exists_mentions_curator_spec_and_future_local_model_mode() -> None:
    text = Path("docs/ai/model_behavior_evaluation_v1.md").read_text(encoding="utf-8").lower()
    assert "curator specification" in text or "original curator specification" in text
    assert "future local-model mode" in text
