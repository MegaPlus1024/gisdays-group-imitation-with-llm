from pathlib import Path


def test_readme_exists() -> None:
    assert Path("README.md").exists()


def test_readme_contains_project_name() -> None:
    text = Path("README.md").read_text(encoding="utf-8").lower()
    assert "local-llm-agent-lab" in text


def test_readme_describes_the_execution_environment_in_russian() -> None:
    text = Path("README.md").read_text(encoding="utf-8").lower()
    for phrase in [
        "среда выполнения",
        "одно действие в формате json",
        "права текущей роли",
        "общих фактов",
        "источника и полномочий",
        "условия завершения",
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


def test_readme_explains_the_bounded_autonomy_scope() -> None:
    text = Path("README.md").read_text(encoding="utf-8").lower()
    assert "полностью автономный цикл" in text
    assert "не реализован" in text
    assert "задачи, роли и доступные инструменты задаются сценарием заранее" in text


def test_readme_uses_full_model_names_in_the_main_results_table() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    results = text.split("## Основной результат", 1)[1].split("\n## ", 1)[0]

    for display_name in [
        "Qwen3-14B Q5_K_M",
        "Mistral Small 3.2 24B Instruct Q4_K_M",
        "Qwen3-30B-A3B-Instruct-2507 Q4_K_M",
        "Qwen3.6-27B Q5_K_M",
    ]:
        assert display_name in results
    for internal_id in [
        "third_model",
        "fourth_model",
        "fifth_model",
        "sixth_model",
        "qwen3_6_27b_q5_k_m",
    ]:
        assert internal_id not in results


def test_readme_explains_tools_scope_and_operational_limits() -> None:
    text = " ".join(Path("README.md").read_text(encoding="utf-8").lower().split())

    for phrase in [
        "чтения и создания файлов",
        "публикации и чтения общих фактов",
        "ожидания зависимостей",
        "восстановления после ожидаемых ошибок",
        "длительную непрерывную работу",
        "нагрузку от нескольких пользователей",
        "непредусмотренных входных данных",
        "docs/reproducibility.md",
    ]:
        assert phrase in text


def test_readme_does_not_require_legacy_english_sentences() -> None:
    text = Path("README.md").read_text(encoding="utf-8")

    for phrase in [
        "normal user activity",
        "local LLM agents",
        "safety is not the final objective",
        "action execution",
        "Full autonomous agent loop",
        "fixture-based benchmark",
        "production readiness",
        "Канонический runtime",
        "Методика benchmark",
        "evidence report",
    ]:
        assert phrase not in text
