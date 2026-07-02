from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.activity_profile import (
    ActivityDiversityPolicy,
    ActivityRepetitionPolicy,
    ActivitySequencePattern,
    NormalActivityProfile,
    activity_profile_summary,
    load_activity_profile,
    load_activity_profiles_from_dir,
)


def _base_profile() -> dict:
    return {
        "profile_id": "p1",
        "role_id": "r1",
        "name": "n1",
        "description": "d1",
        "typical_actions": ["read_file"],
    }


def test_load_office_worker_profile() -> None:
    p = load_activity_profile("configs/activity_profiles/office_worker.json")
    assert p.profile_id == "office_worker_normal_activity_v1"


def test_load_developer_profile() -> None:
    p = load_activity_profile("configs/activity_profiles/developer.json")
    assert p.profile_id == "developer_normal_activity_v1"


def test_load_student_researcher_profile() -> None:
    p = load_activity_profile("configs/activity_profiles/student_researcher.json")
    assert p.profile_id == "student_researcher_normal_activity_v1"


def test_load_activity_profiles_from_dir_sorted() -> None:
    profiles = load_activity_profiles_from_dir("configs/activity_profiles")
    assert [p.profile_id for p in profiles] == sorted([p.profile_id for p in profiles])
    assert len(profiles) == 3


def test_profile_id_cannot_be_empty() -> None:
    data = _base_profile()
    data["profile_id"] = ""
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_role_id_cannot_be_empty() -> None:
    data = _base_profile()
    data["role_id"] = ""
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_typical_actions_cannot_be_empty() -> None:
    data = _base_profile()
    data["typical_actions"] = []
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_duplicate_typical_actions_rejected() -> None:
    data = _base_profile()
    data["typical_actions"] = ["read_file", "read_file"]
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_duplicate_atypical_actions_rejected() -> None:
    data = _base_profile()
    data["atypical_actions"] = ["browser_open_url", "browser_open_url"]
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_duplicate_forbidden_actions_rejected() -> None:
    data = _base_profile()
    data["forbidden_for_normality"] = ["run_shell_command", "run_shell_command"]
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_action_cannot_be_typical_and_atypical() -> None:
    data = _base_profile()
    data["typical_actions"] = ["read_file"]
    data["atypical_actions"] = ["read_file"]
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_action_cannot_be_typical_and_forbidden() -> None:
    data = _base_profile()
    data["typical_actions"] = ["read_file"]
    data["forbidden_for_normality"] = ["read_file"]
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_duplicate_expected_sequence_pattern_id_rejected() -> None:
    data = _base_profile()
    data["expected_sequences"] = [
        {"pattern_id": "x", "description": "d", "action_sequence": ["read_file"]},
        {"pattern_id": "x", "description": "d2", "action_sequence": ["create_file"]},
    ]
    with pytest.raises(ValueError):
        NormalActivityProfile.model_validate(data)


def test_sequence_pattern_requires_non_empty_action_sequence() -> None:
    with pytest.raises(ValueError):
        ActivitySequencePattern(
            pattern_id="x",
            description="d",
            action_sequence=[],
        )


def test_repetition_policy_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        ActivityRepetitionPolicy(max_same_action_consecutive=0)


def test_repetition_policy_rejects_warning_threshold_too_high() -> None:
    with pytest.raises(ValueError):
        ActivityRepetitionPolicy(max_same_action_total=2, repeated_action_warning_threshold=3)


def test_diversity_policy_rejects_duplicate_families() -> None:
    with pytest.raises(ValueError):
        ActivityDiversityPolicy(preferred_action_families=["file", "file"])


def test_is_typical_action_works() -> None:
    p = load_activity_profile("configs/activity_profiles/developer.json")
    assert p.is_typical_action("run_shell_command")


def test_is_atypical_action_works() -> None:
    p = load_activity_profile("configs/activity_profiles/student_researcher.json")
    assert p.is_atypical_action("run_shell_command")


def test_is_forbidden_for_normality_works() -> None:
    p = load_activity_profile("configs/activity_profiles/office_worker.json")
    assert p.is_forbidden_for_normality("run_shell_command")


def test_expected_action_names_includes_sequence_actions() -> None:
    p = load_activity_profile("configs/activity_profiles/office_worker.json")
    names = p.expected_action_names()
    assert "office_create_document_stub" in names
    assert "append_file" in names


def test_activity_profile_summary_json_serializable() -> None:
    p = load_activity_profile("configs/activity_profiles/developer.json")
    summary = activity_profile_summary(p)
    json.dumps(summary)
    assert summary["profile_id"] == "developer_normal_activity_v1"


def test_office_worker_forbids_shell_for_normality() -> None:
    p = load_activity_profile("configs/activity_profiles/office_worker.json")
    assert "run_shell_command" in p.forbidden_action_set()


def test_developer_shell_is_typical() -> None:
    p = load_activity_profile("configs/activity_profiles/developer.json")
    assert "run_shell_command" in p.typical_action_set()


def test_student_researcher_shell_is_atypical() -> None:
    p = load_activity_profile("configs/activity_profiles/student_researcher.json")
    assert "run_shell_command" in p.atypical_action_set()


def test_doc_exists_and_mentions_roletemplate_and_future_evaluator() -> None:
    path = Path("docs/ai/normal_activity_profile_schema_v1.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8").lower()
    assert "roletemplate" in text
    assert "future trajectory evaluator" in text
