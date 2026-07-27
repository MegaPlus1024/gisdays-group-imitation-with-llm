from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return " ".join(Path(path).read_text(encoding="utf-8").lower().split())


def test_readme_exists() -> None:
    assert Path("README.md").exists()


def test_readme_describes_coordinated_user_tasks() -> None:
    text = _read("README.md")
    assert "совместно выполняют одну задачу" in text
    assert "согласованно работать" in text
    assert "документами и структурированными данными" in text


def test_readme_mentions_multiple_local_model_agents() -> None:
    text = _read("README.md")
    assert "несколько агентов" in text
    assert "языковых моделей" in text


def test_readme_mentions_roles_tools_shared_state_and_history() -> None:
    text = _read("README.md")
    assert "роль" in text
    assert "инструмент" in text
    assert "единой среде" in text
    assert "выполнения" in text
    assert "история" in text


def test_readme_frames_validation_as_support_for_useful_work() -> None:
    text = _read("README.md")
    assert "функциональной корректности" in text
    assert "совместно" in text


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
