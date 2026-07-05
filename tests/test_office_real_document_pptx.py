from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.agent.scripts.office_real_document_activity import (
    OfficeRealDocumentActivityConfig,
    run_office_real_document_activity,
)


def _config(tmp_path: Path, **overrides: object) -> OfficeRealDocumentActivityConfig:
    payload: dict[str, object] = {
        "enabled": True,
        "project_root": tmp_path,
        "artifact_root": "artifacts",
    }
    payload.update(overrides)
    return OfficeRealDocumentActivityConfig(**payload)


def _pptx_module() -> Any:
    return pytest.importorskip("pptx")


def _pptx_loader() -> dict[str, Any]:
    return {"pptx": _pptx_module()}


def _fake_pptx_loader() -> dict[str, object]:
    class FakePptxModule:
        def Presentation(self, *_args: object, **_kwargs: object) -> object:  # pragma: no cover
            raise AssertionError("test should fail before creating or loading PPTX")

    return {"pptx": FakePptxModule()}


def _assert_no_absolute_root(result: object, tmp_path: Path) -> None:
    metadata = getattr(result, "metadata")
    root = str(tmp_path)
    for value in metadata.values():
        if isinstance(value, str):
            assert root not in value


def _create_deck(tmp_path: Path) -> OfficeRealDocumentActivityConfig:
    cfg = _config(tmp_path)
    result = run_office_real_document_activity(
        "office_create_pptx",
        {
            "path": "artifacts/decks/summary.pptx",
            "title": "Weekly Summary",
            "subtitle": "Controlled local activity",
            "slides": [
                {
                    "title": "Updates",
                    "bullets": ["Reviewed local fixtures.", "Prepared follow-up tasks."],
                }
            ],
        },
        cfg,
        dependency_loader=_pptx_loader,
    )
    assert result.success is True
    return cfg


def test_create_pptx_writes_under_artifact_root_when_dependency_available(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_pptx",
        {
            "path": "artifacts/decks/summary.pptx",
            "title": "Weekly Summary",
            "subtitle": "Controlled local activity",
            "slides": [
                {
                    "title": "Updates",
                    "bullets": ["Reviewed local fixtures.", "Prepared follow-up tasks."],
                }
            ],
        },
        _config(tmp_path),
        dependency_loader=_pptx_loader,
    )

    assert result.success is True
    assert (tmp_path / "artifacts" / "decks" / "summary.pptx").is_file()
    assert result.metadata["document_type"] == "pptx"
    assert result.metadata["path_relative"] == "artifacts/decks/summary.pptx"
    assert result.metadata["slide_count"] == 2
    assert result.metadata["real_office_document_automation"] is True
    assert result.metadata["office_app_opened"] is False
    assert "Weekly Summary" in result.metadata["text_preview"]
    _assert_no_absolute_root(result, tmp_path)


def test_extract_pptx_text_returns_title_subtitle_and_bullets(tmp_path: Path) -> None:
    cfg = _create_deck(tmp_path)

    result = run_office_real_document_activity(
        "office_extract_pptx_text",
        {"path": "artifacts/decks/summary.pptx"},
        cfg,
        dependency_loader=_pptx_loader,
    )

    assert result.success is True
    assert result.metadata["path_relative"] == "artifacts/decks/summary.pptx"
    assert result.metadata["slide_count"] == 2
    assert result.metadata["character_count"] > 0
    assert "Weekly Summary" in result.metadata["text_preview"]
    assert "Controlled local activity" in result.output
    assert "Reviewed local fixtures." in result.output
    _assert_no_absolute_root(result, tmp_path)


def test_add_pptx_slide_then_extract_includes_appended_content(tmp_path: Path) -> None:
    cfg = _create_deck(tmp_path)

    appended = run_office_real_document_activity(
        "office_add_pptx_slide",
        {
            "path": "artifacts/decks/summary.pptx",
            "title": "Next Steps",
            "bullets": ["Record local-only result.", "Avoid external runtime."],
        },
        cfg,
        dependency_loader=_pptx_loader,
    )
    assert appended.success is True
    assert appended.metadata["slide_count"] == 3
    assert appended.metadata["added_slide_title"] == "Next Steps"
    assert appended.metadata["added_bullet_count"] == 2

    extracted = run_office_real_document_activity(
        "office_extract_pptx_text",
        {"path": "artifacts/decks/summary.pptx"},
        cfg,
        dependency_loader=_pptx_loader,
    )
    assert extracted.success is True
    assert "Next Steps" in extracted.metadata["text_preview"]
    assert "Record local-only result." in extracted.metadata["text_preview"]


def test_missing_pptx_dependency_returns_controlled_error(tmp_path: Path) -> None:
    def missing_loader() -> dict[str, object]:
        raise ImportError("python-pptx unavailable for test")

    result = run_office_real_document_activity(
        "office_create_pptx",
        {"path": "artifacts/deck.pptx", "title": "Deck"},
        _config(tmp_path),
        dependency_loader=missing_loader,
    )

    assert result.success is False
    assert result.error_type == "office_dependency_missing"
    assert result.metadata["real_office_document_automation"] is False
    assert result.metadata["office_app_opened"] is False


def test_disabled_pptx_action_still_returns_controlled_denial(tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("disabled actions must not load python-pptx")

    result = run_office_real_document_activity(
        "office_create_pptx",
        {"path": "artifacts/deck.pptx", "title": "Deck"},
        _config(tmp_path, enabled=False),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == "real_office_document_automation_disabled"


@pytest.mark.parametrize(
    ("path", "expected_error"),
    [
        (r"C:\Temp\deck.pptx", "office_path_absolute_denied"),
        ("artifacts/../deck.pptx", "office_path_traversal_denied"),
        ("models/gguf/deck.pptx", "office_path_forbidden_root_denied"),
        ("artifacts/deck.pptm", "office_macro_extension_denied"),
    ],
)
def test_pptx_actions_keep_path_safety(path: str, expected_error: str, tmp_path: Path) -> None:
    def fail_loader() -> dict[str, object]:
        raise AssertionError("unsafe paths must be rejected before dependency loading")

    result = run_office_real_document_activity(
        "office_create_pptx",
        {"path": path, "title": "Deck"},
        _config(tmp_path),
        dependency_loader=fail_loader,
    )

    assert result.success is False
    assert result.error_type == expected_error


def test_extract_missing_pptx_file_returns_controlled_error(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_extract_pptx_text",
        {"path": "artifacts/missing.pptx"},
        _config(tmp_path),
        dependency_loader=_fake_pptx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_pptx_file_missing"
    assert result.metadata["path_relative"] == "artifacts/missing.pptx"


def test_extract_oversized_pptx_file_is_rejected_before_read(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "large.pptx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not pptx but intentionally larger than limit")

    result = run_office_real_document_activity(
        "office_extract_pptx_text",
        {"path": "artifacts/large.pptx"},
        _config(tmp_path, max_file_bytes=4),
        dependency_loader=_fake_pptx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_pptx_file_too_large"
    assert result.metadata["path_relative"] == "artifacts/large.pptx"


def test_invalid_pptx_file_returns_controlled_read_error(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "invalid.pptx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not a real pptx file")

    result = run_office_real_document_activity(
        "office_extract_pptx_text",
        {"path": "artifacts/invalid.pptx"},
        _config(tmp_path),
        dependency_loader=_pptx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_pptx_read_failed"
    assert result.metadata["path_relative"] == "artifacts/invalid.pptx"


def test_pptx_nul_text_is_rejected(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_pptx",
        {"path": "artifacts/deck.pptx", "title": "bad\x00title"},
        _config(tmp_path),
        dependency_loader=_fake_pptx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_pptx_invalid_content"


def test_create_pptx_rejects_too_many_slides(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_pptx",
        {
            "path": "artifacts/deck.pptx",
            "title": "Deck",
            "slides": [{"title": "Extra"}],
        },
        _config(tmp_path, max_pptx_slides=1),
        dependency_loader=_fake_pptx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_pptx_too_many_slides"


def test_create_pptx_rejects_too_many_bullets(tmp_path: Path) -> None:
    result = run_office_real_document_activity(
        "office_create_pptx",
        {
            "path": "artifacts/deck.pptx",
            "slides": [{"title": "Deck", "bullets": ["one", "two"]}],
        },
        _config(tmp_path, max_pptx_bullets=1),
        dependency_loader=_fake_pptx_loader,
    )

    assert result.success is False
    assert result.error_type == "office_pptx_too_many_bullets"
