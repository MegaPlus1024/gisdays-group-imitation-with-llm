from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_evaluation_models_use_canonical_gguf_paths() -> None:
    data = json.loads(_read("configs/evaluation_models.json"))
    models = {item["model_id"]: item for item in data["models"]}

    assert models["first_model"]["gguf_path"] == "models/gguf/first_model.gguf"
    assert models["second_model"]["model_name"] == "second_model.gguf"
    assert models["second_model"]["gguf_path"] == "models/gguf/second_model.gguf"
    assert "qwen2_5_3b_instruct_q4_k_m" in models["second_model"].get("aliases", [])


def test_readme_mentions_second_model_local_path() -> None:
    text = _read("README.md").replace("\\", "/")

    assert "models/gguf/second_model.gguf" in text
    assert "--model-id second_model" in text
    assert "--model-ids first_model,second_model" in text
    assert "--model-id qwen2_5_3b_instruct_q4_k_m" not in text
    assert "--model-ids first_model,qwen2_5_3b_instruct_q4_k_m" not in text


def test_models_md_mentions_second_model_alias() -> None:
    text = _read("models/gguf/MODELS.md")

    assert "second_model.gguf" in text
    assert "models/gguf/second_model.gguf" in text


def test_model_file_mapping_exists_and_mentions_canonical_mapping() -> None:
    path = Path("docs/ai/model_file_mapping.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")

    assert "configs/evaluation_models.json" in text
    assert "second_model" in text
    assert "models/gguf/second_model.gguf" in text


def test_no_tracked_forbidden_binary_or_secret_patterns() -> None:
    completed = subprocess.run(
        ["git", "ls-files"],
        text=True,
        capture_output=True,
        check=True,
    )
    forbidden_fragments = [
        ".venv/",
        ".env",
        "llama-server.exe",
    ]
    forbidden_suffixes = (
        ".gguf",
        ".safetensors",
        ".pem",
        ".key",
        ".log",
    )
    forbidden_words = ("token", "secret", "credential")
    violations: list[str] = []
    for raw_path in completed.stdout.splitlines():
        path = raw_path.replace("\\", "/").lower()
        if any(fragment in path for fragment in forbidden_fragments):
            violations.append(raw_path)
        if path.endswith(forbidden_suffixes):
            violations.append(raw_path)
        if any(word in path for word in forbidden_words):
            violations.append(raw_path)

    assert violations == []


def test_final_evaluation_summary_json_is_valid() -> None:
    data = json.loads(_read("reports/experiments/final_evaluation_summary.json"))

    assert data["total_trajectories"] == 12
    assert data["recommendation_readiness"]["status"] == "not_ready_for_final_recommendation"


def test_readme_references_existing_key_report_files() -> None:
    text = _read("README.md")
    for path in [
        "reports/experiments/final_evaluation_report.md",
        "reports/experiments/manager_summary.md",
        "reports/experiments/project_usage_appendix.md",
        "reports/experiments/final_evaluation_summary.json",
    ]:
        assert path in text
        assert Path(path).exists()


def test_current_readme_uses_canonical_test_command_without_stale_counts() -> None:
    text = _read("README.md")

    assert r".\.venv\Scripts\python.exe -m pytest" in text
    for stale_count in [
        "567 passed",
        "576 passed",
        "586 passed",
        "592 passed",
        "602 passed",
        "608 passed",
        "617 passed",
        "618 passed",
        "627 passed",
        "675 tests",
        "675 passed",
    ]:
        assert stale_count not in text
