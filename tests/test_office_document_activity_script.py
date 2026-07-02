from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.scripts.office_document_activity import (
    OfficeDocumentActivityConfig,
    append_document_section,
    create_document_stub,
    create_table_note_stub,
    extract_document_outline_stub,
    normalize_office_document_path,
    read_document_stub,
    resolve_safe_office_document_path,
    run_office_document_activity,
)
from agent.scripts.results import ScriptExecutionResult


def make_config(tmp_path: Path, **overrides: object) -> OfficeDocumentActivityConfig:
    defaults = dict(project_root=tmp_path)
    defaults.update(overrides)
    return OfficeDocumentActivityConfig(**defaults)


def test_config_defaults_are_valid(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    assert cfg.simulated_only is True
    assert cfg.max_document_bytes > 0


def test_config_rejects_simulated_only_false(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_config(tmp_path, simulated_only=False)


def test_normalize_path_normalizes_backslashes() -> None:
    assert normalize_office_document_path(r"docs\report.md") == "docs/report.md"


def test_normalize_path_rejects_empty() -> None:
    with pytest.raises(Exception):
        normalize_office_document_path("")


def test_normalize_path_rejects_absolute() -> None:
    with pytest.raises(Exception):
        normalize_office_document_path("/docs/report.md")


def test_normalize_path_rejects_traversal() -> None:
    with pytest.raises(Exception):
        normalize_office_document_path("docs/../secret.md")


def test_resolve_safe_path_accepts_docs_md(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    resolved = resolve_safe_office_document_path("docs/example.md", cfg)
    assert resolved.name == "example.md"


def test_resolve_safe_path_rejects_models_gguf(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(Exception):
        resolve_safe_office_document_path("models/gguf/first_model.gguf", cfg)


def test_resolve_safe_path_rejects_venv(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(Exception):
        resolve_safe_office_document_path(".venv/file.txt", cfg)


def test_resolve_safe_path_rejects_git(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(Exception):
        resolve_safe_office_document_path(".git/config", cfg)


def test_resolve_safe_path_rejects_outside_allowed_roots(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(Exception):
        resolve_safe_office_document_path("src/file.md", cfg)


def test_resolve_safe_path_rejects_unsupported_extension(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(Exception):
        resolve_safe_office_document_path("docs/file.docx", cfg)


def test_create_document_stub_writes_allowed_md(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = create_document_stub("docs/report.md", "Title", "Body", cfg)
    assert result.success is True
    assert (tmp_path / "docs" / "report.md").exists()


def test_create_document_stub_respects_allow_overwrite_false(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, allow_overwrite=False)
    first = create_document_stub("docs/report.md", "Title", "Body", cfg)
    second = create_document_stub("docs/report.md", "Title2", "Body2", cfg)
    assert first.success is True
    assert second.success is False
    assert second.error_type == "file_exists"


def test_append_document_section_appends_content(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    create_document_stub("docs/report.md", "Title", "Body", cfg)
    result = append_document_section("docs/report.md", "Next", "More", cfg)
    text = (tmp_path / "docs" / "report.md").read_text(encoding="utf-8")
    assert result.success is True
    assert "## Next" in text
    assert "More" in text


def test_append_document_section_fails_for_missing_document(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = append_document_section("docs/missing.md", "H", "C", cfg)
    assert result.success is False
    assert result.error_type == "document_not_found"


def test_read_document_stub_reads_existing_document(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    create_document_stub("docs/report.md", "Title", "Body", cfg)
    result = read_document_stub("docs/report.md", cfg)
    assert result.success is True
    assert "# Title" in (result.output or "")


def test_read_document_stub_fails_for_missing_document(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = read_document_stub("docs/missing.md", cfg)
    assert result.success is False
    assert result.error_type == "document_not_found"


def test_read_document_stub_rejects_too_large_document(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, max_document_bytes=10)
    create_document_stub("docs/report.md", "Title", "Body Body Body", cfg)
    result = read_document_stub("docs/report.md", cfg)
    assert result.success is False
    assert result.error_type == "document_too_large"


def test_extract_document_outline_stub_extracts_headings(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    create_document_stub("docs/report.md", "Title", "Body", cfg)
    append_document_section("docs/report.md", "Section", "Content", cfg)
    result = extract_document_outline_stub("docs/report.md", cfg)
    assert result.success is True
    assert "# Title" in (result.output or "")
    assert "## Section" in (result.output or "")


def test_create_table_note_stub_writes_markdown_table(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = create_table_note_stub(
        "docs/table.md",
        "Table",
        ["A", "B"],
        [["1", "2"], ["3", "4"]],
        cfg,
    )
    text = (tmp_path / "docs" / "table.md").read_text(encoding="utf-8")
    assert result.success is True
    assert "| A | B |" in text
    assert "| 1 | 2 |" in text


def test_create_table_note_stub_rejects_row_length_mismatch(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = create_table_note_stub(
        "docs/table.md", "Table", ["A", "B"], [["1"]], cfg
    )
    assert result.success is False
    assert result.error_type == "invalid_parameter"


def test_dispatch_create_document_stub(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = run_office_document_activity(
        "create_document_stub",
        {"path": "docs/r.md", "title": "T", "body": "B"},
        cfg,
    )
    assert result.success is True


def test_dispatch_rejects_unknown_action(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = run_office_document_activity("x_unknown", {}, cfg)
    assert result.success is False
    assert result.error_type == "unknown_office_document_action"


def test_dispatch_rejects_missing_parameters_for_create(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    r1 = run_office_document_activity("create_document_stub", {"title": "T", "body": "B"}, cfg)
    r2 = run_office_document_activity("create_document_stub", {"path": "docs/a.md", "body": "B"}, cfg)
    r3 = run_office_document_activity("create_document_stub", {"path": "docs/a.md", "title": "T"}, cfg)
    assert r1.error_type == "missing_parameter"
    assert r2.error_type == "missing_parameter"
    assert r3.error_type == "missing_parameter"


def test_dispatch_returns_unsafe_path_for_forbidden_path(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = run_office_document_activity(
        "create_document_stub",
        {"path": "models/gguf/a.md", "title": "T", "body": "B"},
        cfg,
    )
    assert result.success is False
    assert result.error_type == "unsafe_path"


def test_script_execution_result_failure_requires_error_fields() -> None:
    with pytest.raises(ValidationError):
        ScriptExecutionResult(action="x", success=False)
