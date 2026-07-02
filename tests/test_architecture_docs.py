from pathlib import Path


def test_readme_exists() -> None:
    assert Path("README.md").exists()


def test_readme_contains_project_name() -> None:
    text = Path("README.md").read_text(encoding="utf-8").lower()
    assert "local-llm-agent-lab" in text


def test_readme_contains_canonical_data_flow_keywords() -> None:
    text = Path("README.md").read_text(encoding="utf-8").lower()
    for phrase in [
        "config",
        "orchestrator",
        "agent state",
        "local llm",
        "next action",
        "script runner",
        "history log",
    ]:
        assert phrase in text


def test_architecture_doc_exists() -> None:
    assert Path("docs/ai/architecture_readme_data_flow_v1.md").exists()


def test_architecture_doc_mentions_not_implemented_layers_and_next_step() -> None:
    text = Path("docs/ai/architecture_readme_data_flow_v1.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "script registry and executor are not implemented yet" in text
    assert "architecture freeze audit" in text


def test_mermaid_files_exist() -> None:
    assert Path("docs/ai/diagrams/architecture_data_flow_v1.mmd").exists()
    assert Path("docs/ai/diagrams/architecture_layers_v1.mmd").exists()


def test_mermaid_files_contain_flowchart_keyword() -> None:
    data_flow = Path("docs/ai/diagrams/architecture_data_flow_v1.mmd").read_text(
        encoding="utf-8"
    ).lower()
    layers = Path("docs/ai/diagrams/architecture_layers_v1.mmd").read_text(
        encoding="utf-8"
    ).lower()
    assert "flowchart" in data_flow
    assert "flowchart" in layers


def test_data_flow_mermaid_contains_required_nodes() -> None:
    text = Path("docs/ai/diagrams/architecture_data_flow_v1.mmd").read_text(
        encoding="utf-8"
    ).lower()
    for phrase in [
        "orchestrator",
        "agent",
        "localllmclient",
        "nextaction contract",
        "future history log",
    ]:
        assert phrase in text


def test_readme_does_not_claim_full_loop_or_execution_implemented() -> None:
    text = Path("README.md").read_text(encoding="utf-8").lower()
    assert "full autonomous agent loop" in text
    assert "not implemented" in text
    assert "action execution" in text
