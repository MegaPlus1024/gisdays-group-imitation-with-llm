from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").lower()


def test_readme_exists() -> None:
    assert Path("README.md").exists()


def test_readme_mentions_normal_user_activity() -> None:
    text = _read("README.md")
    assert "normal user activity" in text or "normal user activity simulation" in text


def test_readme_mentions_group_and_local_llm_agents() -> None:
    text = _read("README.md")
    assert "group" in text
    assert "local llm agents" in text


def test_readme_mentions_roles_resources_constraints_scripts_history() -> None:
    text = _read("README.md")
    assert "role" in text or "roles" in text
    assert "resource" in text or "resources" in text
    assert "constraint" in text or "constraints" in text
    assert "script" in text or "scripts" in text
    assert "history" in text


def test_readme_not_safety_only_framing() -> None:
    text = _read("README.md")
    assert "not the final objective" in text or "not only safe" in text


def test_objective_doc_exists() -> None:
    assert Path("docs/ai/project_objective_normal_activity_v1.md").exists()


def test_objective_doc_mentions_curator_objective() -> None:
    text = _read("docs/ai/project_objective_normal_activity_v1.md")
    assert "curator objective" in text or "curator specification" in text


def test_objective_doc_distinguishes_technical_vs_behavioral() -> None:
    text = _read("docs/ai/project_objective_normal_activity_v1.md")
    assert "technical validity" in text
    assert "behavioral normality" in text


def test_objective_doc_mentions_behavioral_criteria() -> None:
    text = _read("docs/ai/project_objective_normal_activity_v1.md")
    assert "role compliance" in text
    assert "coherence" in text
    assert "diversity" in text
    assert "repeated" in text or "template" in text


def test_objective_doc_mentions_future_stages() -> None:
    text = _read("docs/ai/project_objective_normal_activity_v1.md")
    assert "behavioral evaluation readiness" in text
    assert "experiments and evaluation" in text


def test_objective_doc_not_claim_final_evaluation_complete() -> None:
    text = _read("docs/ai/project_objective_normal_activity_v1.md")
    assert "final behavioral evaluation is already complete" not in text
