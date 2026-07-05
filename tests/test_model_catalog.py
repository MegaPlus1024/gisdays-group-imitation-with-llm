from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.model_catalog import (
    MODEL_CATALOG_SCHEMA_VERSION,
    ModelCatalog,
    build_candidate_pairs,
    get_model_entry,
    list_enabled_models,
    list_models_for_role,
    load_model_catalog,
    model_catalog_entry_metadata,
    validate_model_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"


def _payload() -> dict[str, object]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _model_payload(model_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "model_id": model_id,
        "display_name": model_id,
        "upstream_name": f"{model_id}.gguf",
        "local_path": f"models/gguf/{model_id}.gguf",
        "family": "qwen2.5",
        "parameter_count_b": 1.0,
        "quantization": "Q4_K_M",
        "context_window_tokens": None,
        "enabled": True,
        "roles": {
            "orchestrator_candidate": False,
            "executor_candidate": True,
            "judge_candidate": False,
        },
        "historical_aliases": [],
        "historical_observations": [],
        "resource_profile": {
            "expected_vram_gb": None,
            "expected_ram_gb": None,
            "observed_vram_gb": None,
            "observed_ram_gb": None,
            "notes": "Metadata only.",
        },
        "tags": ["local"],
    }
    payload.update(overrides)
    return payload


def _catalog_from_models(*models: dict[str, object]) -> ModelCatalog:
    return ModelCatalog.model_validate(
        {"schema_version": MODEL_CATALOG_SCHEMA_VERSION, "models": list(models)}
    )


def test_example_catalog_loads() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    assert catalog.schema_version == MODEL_CATALOG_SCHEMA_VERSION
    assert [entry.model_id for entry in catalog.models] == ["first_model", "second_model"]


def test_example_catalog_contains_canonical_model_metadata() -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    first = get_model_entry(catalog, "first_model")
    second = get_model_entry(catalog, "second_model")

    assert first.local_path == "models/gguf/first_model.gguf"
    assert first.parameter_count_b == pytest.approx(1.5)
    assert second.upstream_name == "qwen2.5-3b-instruct-q4_k_m.gguf"
    assert second.parameter_count_b == pytest.approx(3.0)


def test_legacy_alias_resolves_to_second_model() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    assert get_model_entry(catalog, "qwen2_5_3b_instruct_q4_k_m").model_id == "second_model"


def test_catalog_loading_does_not_check_model_file_existence(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_exists(self: Path) -> bool:
        raise AssertionError(f"unexpected exists check: {self}")

    monkeypatch.setattr(Path, "exists", forbidden_exists)

    catalog = load_model_catalog(CATALOG_PATH)

    assert get_model_entry(catalog, "first_model").local_path == "models/gguf/first_model.gguf"


def test_absolute_windows_local_path_rejected() -> None:
    payload = _payload()
    payload["models"][0]["local_path"] = "\\".join(["C:", "Temp", "outside_workspace", "model.gguf"])

    with pytest.raises(ValueError, match="local_path must be a relative path"):
        ModelCatalog.model_validate(payload)


def test_absolute_posix_local_path_rejected() -> None:
    payload = _payload()
    payload["models"][0]["local_path"] = "/tmp/outside_workspace/model.gguf"

    with pytest.raises(ValueError, match="local_path must be a relative path"):
        ModelCatalog.model_validate(payload)


def test_parent_traversal_local_path_rejected() -> None:
    payload = _payload()
    payload["models"][0]["local_path"] = "models/../secret/model.gguf"

    with pytest.raises(ValueError, match="parent directory traversal"):
        ModelCatalog.model_validate(payload)


def test_forbidden_local_path_root_rejected() -> None:
    payload = _payload()
    payload["models"][0]["local_path"] = ".venv/models/model.gguf"

    with pytest.raises(ValueError, match="forbidden local/private paths"):
        ModelCatalog.model_validate(payload)


def test_duplicate_model_id_rejected() -> None:
    first = _model_payload("dup")
    second = _model_payload("dup")

    with pytest.raises(ValueError, match="duplicate_model_id:dup"):
        _catalog_from_models(first, second)


def test_alias_conflicting_with_model_id_rejected() -> None:
    first = _model_payload("one", historical_aliases=["two"])
    second = _model_payload("two")

    with pytest.raises(ValueError, match="alias_conflicts_with_model_id:two"):
        _catalog_from_models(first, second)


def test_duplicate_alias_rejected() -> None:
    first = _model_payload("one", historical_aliases=["legacy"])
    second = _model_payload("two", historical_aliases=["legacy"])

    with pytest.raises(ValueError, match="duplicate_alias:legacy:one:two"):
        _catalog_from_models(first, second)


def test_validate_model_catalog_returns_empty_list_for_example() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    assert validate_model_catalog(catalog) == []


def test_list_enabled_models_returns_enabled_entries() -> None:
    catalog = _catalog_from_models(
        _model_payload("enabled_model"),
        _model_payload("disabled_model", enabled=False),
    )

    assert [entry.model_id for entry in list_enabled_models(catalog)] == ["enabled_model"]


def test_list_orchestrator_candidates_returns_second_model_only() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    assert [entry.model_id for entry in list_models_for_role(catalog, "orchestrator")] == ["second_model"]


def test_list_executor_candidates_returns_both_models() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    assert [entry.model_id for entry in list_models_for_role(catalog, "executor")] == [
        "first_model",
        "second_model",
    ]


def test_list_judge_candidates_accepts_full_role_name() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    assert [entry.model_id for entry in list_models_for_role(catalog, "judge_candidate")] == [
        "second_model"
    ]


def test_unknown_role_rejected() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    with pytest.raises(ValueError, match="Unknown model catalog role"):
        list_models_for_role(catalog, "planner")


def test_build_candidate_pairs_uses_role_flags() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    pairs = build_candidate_pairs(catalog)

    assert [pair["pair_label"] for pair in pairs] == [
        "second_model->first_model",
        "second_model->second_model",
    ]
    assert all(not pair["orchestrator_model_id"].startswith("first_model") for pair in pairs)


def test_build_candidate_pairs_excludes_disabled_models_by_default() -> None:
    catalog = _catalog_from_models(
        _model_payload(
            "orchestrator_model",
            roles={
                "orchestrator_candidate": True,
                "executor_candidate": False,
                "judge_candidate": False,
            },
        ),
        _model_payload("executor_model"),
        _model_payload("disabled_executor", enabled=False),
    )

    pairs = build_candidate_pairs(catalog)

    assert [pair["pair_label"] for pair in pairs] == ["orchestrator_model->executor_model"]


def test_build_candidate_pairs_can_include_disabled_models() -> None:
    catalog = _catalog_from_models(
        _model_payload(
            "orchestrator_model",
            roles={
                "orchestrator_candidate": True,
                "executor_candidate": False,
                "judge_candidate": False,
            },
        ),
        _model_payload("executor_model", enabled=False),
    )

    pairs = build_candidate_pairs(catalog, enabled_only=False)

    assert [pair["pair_label"] for pair in pairs] == ["orchestrator_model->executor_model"]


def test_pair_metadata_includes_resource_neutral_notes_and_tags() -> None:
    catalog = load_model_catalog(CATALOG_PATH)

    pair = build_candidate_pairs(catalog)[0]

    assert pair["pair_id"] == "second_model__to__first_model"
    assert pair["tags"] == ["gguf", "local", "qwen2.5", "small"]
    assert any(note.startswith("orchestrator:") for note in pair["known_notes"])
    assert pair["metadata"]["orchestrator"]["parameter_count_b"] == pytest.approx(3.0)


def test_catalog_metadata_helper_is_json_ready() -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    metadata = model_catalog_entry_metadata(get_model_entry(catalog, "second_model"))

    encoded = json.dumps(metadata, sort_keys=True)

    assert "second_model" in encoded
    assert "qwen2_5_3b_instruct_q4_k_m" in encoded


def test_example_catalog_has_no_private_absolute_paths() -> None:
    text = CATALOG_PATH.read_text(encoding="utf-8")

    assert "C:" not in text
    assert "/Users/" not in text
    assert "\\Users\\" not in text


def test_example_catalog_makes_no_production_recommendation_claim() -> None:
    text = CATALOG_PATH.read_text(encoding="utf-8").lower()

    assert "production recommendation" not in text
    assert "production-ready" not in text
    assert "no production capacity claim" in text


def test_catalog_actions_do_not_open_gguf_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    original_read_text = Path.read_text

    def forbid_model_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError(f"unexpected GGUF read: {self}")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_model_read_text)

    assert len(list_enabled_models(catalog)) == 2
    assert len(build_candidate_pairs(catalog)) == 2

