from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.scripts.file_activity import (
    FileActivityConfig,
    UnsafePathError,
    append_file,
    create_file,
    list_directory,
    normalize_relative_path,
    read_file,
    resolve_safe_project_path,
    run_file_activity,
)
from agent.scripts.results import ScriptExecutionResult


def make_config(tmp_path: Path) -> FileActivityConfig:
    return FileActivityConfig(project_root=tmp_path)


def test_normalize_relative_path_normalizes_backslashes() -> None:
    assert normalize_relative_path(r"docs\ai\file.md") == "docs/ai/file.md"


def test_normalize_relative_path_rejects_empty_path() -> None:
    with pytest.raises(UnsafePathError):
        normalize_relative_path("")


def test_normalize_relative_path_rejects_absolute_path() -> None:
    with pytest.raises(UnsafePathError):
        normalize_relative_path("/etc/passwd")


def test_normalize_relative_path_rejects_path_traversal() -> None:
    with pytest.raises(UnsafePathError):
        normalize_relative_path("../secret.txt")


def test_resolve_safe_project_path_accepts_docs_file(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    p = resolve_safe_project_path("docs/example.md", cfg)
    assert str(p).endswith("docs\\example.md") or str(p).endswith("docs/example.md")


def test_resolve_safe_project_path_rejects_models_gguf(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(UnsafePathError):
        resolve_safe_project_path("models/gguf/first_model.gguf", cfg)


def test_resolve_safe_project_path_rejects_venv(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(UnsafePathError):
        resolve_safe_project_path(".venv/file.txt", cfg)


def test_resolve_safe_project_path_rejects_git(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(UnsafePathError):
        resolve_safe_project_path(".git/config", cfg)


def test_resolve_safe_project_path_rejects_outside_allowed_roots(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(UnsafePathError):
        resolve_safe_project_path("src/agent/file.py", cfg)


def test_read_file_reads_existing_allowed_file(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    p = tmp_path / "docs" / "a.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("hello", encoding="utf-8")
    result = read_file("docs/a.txt", cfg)
    assert result.success is True
    assert result.output == "hello"


def test_read_file_returns_file_not_found_for_missing_file(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = read_file("docs/missing.txt", cfg)
    assert result.success is False
    assert result.error_type == "file_not_found"


def test_read_file_rejects_file_larger_than_limit(tmp_path: Path) -> None:
    cfg = FileActivityConfig(project_root=tmp_path, max_read_bytes=3)
    p = tmp_path / "docs" / "b.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("hello", encoding="utf-8")
    result = read_file("docs/b.txt", cfg)
    assert result.success is False
    assert result.error_type == "file_too_large"


def test_create_file_writes_allowed_file(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = create_file("docs/new.txt", "abc", cfg)
    assert result.success is True
    assert (tmp_path / "docs" / "new.txt").read_text(encoding="utf-8") == "abc"


def test_create_file_respects_allow_overwrite_false(tmp_path: Path) -> None:
    cfg = FileActivityConfig(project_root=tmp_path, allow_overwrite=False)
    p = tmp_path / "docs" / "same.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("old", encoding="utf-8")
    result = create_file("docs/same.txt", "new", cfg)
    assert result.success is False
    assert result.error_type == "file_exists"


def test_create_file_creates_parent_dirs_when_configured(tmp_path: Path) -> None:
    cfg = FileActivityConfig(project_root=tmp_path, create_parent_dirs=True)
    result = create_file("docs/deep/path.txt", "x", cfg)
    assert result.success is True
    assert (tmp_path / "docs" / "deep" / "path.txt").exists()


def test_append_file_appends_content(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    p = tmp_path / "docs" / "append.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("a", encoding="utf-8")
    result = append_file("docs/append.txt", "b", cfg)
    assert result.success is True
    assert p.read_text(encoding="utf-8") == "ab"


def test_list_directory_returns_sorted_entries(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    d = tmp_path / "docs" / "dir"
    d.mkdir(parents=True, exist_ok=True)
    (d / "b.txt").write_text("b", encoding="utf-8")
    (d / "a.txt").write_text("a", encoding="utf-8")
    result = list_directory("docs/dir", cfg)
    assert result.success is True
    assert result.output == "a.txt\nb.txt"


def test_list_directory_rejects_missing_directory(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = list_directory("docs/missing", cfg)
    assert result.success is False
    assert result.error_type == "directory_not_found"


def test_run_file_activity_dispatches_read_file(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    p = tmp_path / "docs" / "x.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("hello", encoding="utf-8")
    result = run_file_activity("read_file", {"path": "docs/x.txt"}, cfg)
    assert result.success is True
    assert result.output == "hello"


def test_run_file_activity_rejects_unknown_action(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = run_file_activity("unknown_action", {}, cfg)
    assert result.success is False
    assert result.error_type == "unknown_file_action"


def test_script_execution_result_failure_requires_error_fields() -> None:
    with pytest.raises(ValidationError):
        ScriptExecutionResult(action="read_file", success=False)
