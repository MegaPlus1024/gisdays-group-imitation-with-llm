from __future__ import annotations

from pathlib import Path

from agent.registry_fixtures import evaluate_fixture_pack, load_validation_expectations


FIXTURE_ROOT = Path("tests/fixtures/registry")
EXPECTATIONS_PATH = FIXTURE_ROOT / "expected_results" / "validation_expectations.json"


def test_registry_fixture_directories_exist() -> None:
    assert FIXTURE_ROOT.exists()
    assert (FIXTURE_ROOT / "registries").exists()
    assert (FIXTURE_ROOT / "next_actions").exists()
    assert (FIXTURE_ROOT / "role_templates").exists()
    assert (FIXTURE_ROOT / "expected_results").exists()


def test_validation_expectations_load() -> None:
    pack = load_validation_expectations(EXPECTATIONS_PATH)
    assert pack.fixture_pack_id == "registry_fixture_pack_v1"
    assert len(pack.expectations) > 0


def test_expectation_references_exist() -> None:
    pack = load_validation_expectations(EXPECTATIONS_PATH)
    for exp in pack.expectations:
        assert (FIXTURE_ROOT / exp.registry_path).exists()
        assert (FIXTURE_ROOT / exp.next_action_path).exists()
        if exp.role_template_path is not None:
            assert (FIXTURE_ROOT / exp.role_template_path).exists()


def test_registry_fixture_pack_matches_expectations() -> None:
    result = evaluate_fixture_pack(FIXTURE_ROOT, EXPECTATIONS_PATH)
    assert result.total_cases > 0
    assert result.matched_cases == result.total_cases, [
        {
            "case_id": mismatch.case_id,
            "accepted": mismatch.accepted,
            "issue_codes": mismatch.issue_codes,
            "expected_issue_codes": mismatch.expected_issue_codes,
        }
        for mismatch in result.mismatches
    ]
