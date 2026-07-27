from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _section(text: str, heading: str, next_heading: str) -> str:
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


def test_research_readiness_docs_exist() -> None:
    for relative_path in [
        "docs/ai/model_research_metadata.md",
        "docs/ai/final_tz_readiness_audit.md",
        "docs/ai/local_orchestrator_executor_runtime_audit.md",
        "docs/ai/local_orchestrator_executor_poc_v1.md",
        "docs/ai/local_orchestrator_executor_poc_blocker.md",
        "docs/ai/local_orchestrator_executor_poc_v2_repair.md",
        "docs/ai/local_orchestrator_executor_executor_failure_analysis.md",
        "docs/ai/local_orchestrator_executor_poc_v3_executor_repair.md",
        "docs/ai/repeated_local_orchestrator_executor_trials_v1.md",
        "docs/ai/orchestrator_executor_pair_matrix_v1.md",
        "docs/ai/heavy_multi_agent_scenario_v1.md",
        "docs/ai/heavy_scenario_error_analysis_v1.md",
        "docs/ai/orchestrator_executor_runtime_capacity_v1.md",
        "docs/ai/orchestrator_executor_pipeline_v1.md",
        "docs/ai/orchestrator_executor_quality_spec.md",
        "docs/ai/gpu_runtime_readiness_audit.md",
        "docs/ai/llama_server_gpu_flags_observed.md",
        "docs/ai/gpu_runtime_configuration_v1.md",
        "docs/ai/gpu_smoke_second_to_second_heavy_v1.md",
        "docs/ai/bounded_stress_candidate_pairs_v1.md",
        "docs/ai/next_implementation_plan_orchestrator_executor.md",
    ]:
        assert (PROJECT_ROOT / relative_path).exists(), relative_path


def test_readme_links_research_model_metadata() -> None:
    readme = _read("README.md")

    assert "docs/ai/model_research_metadata.md" in readme
    assert "docs/ai/orchestrator_executor_runtime_capacity_v1.md" in readme
    assert "docs/ai/gpu_runtime_configuration_v1.md" in readme
    assert "docs/ai/gpu_smoke_second_to_second_heavy_v1.md" in readme
    assert "docs/ai/bounded_stress_candidate_pairs_v1.md" in readme


def test_evaluation_model_registry_has_current_models_and_legacy_aliases() -> None:
    payload = json.loads(_read("configs/evaluation_models.json"))
    models = {item["model_id"]: item for item in payload["models"]}

    assert "first_model" in models
    assert "second_model" in models
    assert models["first_model"]["upstream_model_name"] == "granite-3.3-8b-instruct-q4_k_m.gguf"
    assert models["second_model"]["upstream_model_name"] == "qwen2.5-3b-instruct-q4_k_m.gguf"
    assert "qwen2_5_3b_instruct_q4_k_m" in models["second_model"].get("aliases", [])
    assert models["sixth_model"]["display_name"] == "Qwen3.6-27B Q5_K_M"
    assert models["sixth_model"]["api_model"] == "sixth_model"
    assert "qwen3_6_27b_q5_k_m" in models["sixth_model"].get("aliases", [])


def test_model_research_metadata_contains_required_table_fields() -> None:
    text = _read("docs/ai/model_research_metadata.md")

    for required in [
        "Идентификатор проекта",
        "Локальный GGUF",
        "Полное название",
        "Размер",
        "Квантование",
        "first_model",
        "second_model",
        "IBM Granite 3.3 8B Instruct Q4_K_M",
        "Qwen2.5-3B-Instruct Q4_K_M",
        "Qwen3-14B Q5_K_M",
        "Mistral Small 3.2 24B Instruct Q4_K_M",
        "Qwen3-30B-A3B-Instruct-2507 Q4_K_M",
        "Qwen3.6-27B Q5_K_M",
    ]:
        assert required in text


def test_final_tz_readiness_audit_names_critical_statuses() -> None:
    text = _read("docs/ai/final_tz_readiness_audit.md").lower()

    for required in [
        "group of agents",
        "orchestrator/executor pair",
        "gpu runtime",
        "measured multi-agent capacity",
        "partially complete",
        "missing",
        "estimated only",
    ]:
        assert required in text


def test_gpu_audit_records_wrapper_and_smoke_status() -> None:
    text = _read("docs/ai/gpu_runtime_readiness_audit.md").lower()

    assert "gpu detected: yes" in text
    assert "llama-server gpu flags available: yes" in text
    assert "gpu runtime configured: yes" in text
    assert "gpu runtime measured: yes" in text
    assert "cpu-only short single-agent runs demonstrated: yes" in text
    assert "gpu is likely useful for throughput/capacity" in text
    assert "1.006842" in text


def test_orchestrator_executor_quality_spec_names_prototype_status() -> None:
    text = _read("docs/ai/orchestrator_executor_quality_spec.md").lower()

    assert "pair_quality_score" in text
    assert "prototype implementation" in text
    assert "not a final scientific metric" in text
    assert "group_coordination_score" in text
    assert "task_completion_score" in text


def test_orchestrator_executor_pipeline_doc_names_default_pair_and_artifacts() -> None:
    text = _read("docs/ai/orchestrator_executor_pipeline_v1.md")

    for required in [
        "Orchestrator/Executor Pipeline v1",
        "second_model",
        "first_model",
        "office_developer_group_basic_v1",
        "pair_quality_score",
        "experiments/multi_agent/orchestrator_executor/fake_office_developer_group_v1",
        "Local proof-of-concept follow-up",
        "Plan repair",
        "Executor prompt and repair",
        "Repeated local group trials",
        "Pair matrix comparison",
        "local_orchestrator_executor_poc_blocker.md",
        "local_orchestrator_executor_poc_v2_repair.md",
        "local_orchestrator_executor_poc_v3_executor_repair.md",
        "repeated_local_orchestrator_executor_trials_v1.md",
        "orchestrator_executor_pair_matrix_v1.md",
    ]:
        assert required in text


def test_local_orchestrator_executor_poc_docs_record_blocked_attempt() -> None:
    poc = _read("docs/ai/local_orchestrator_executor_poc_v1.md")
    blocker = _read("docs/ai/local_orchestrator_executor_poc_blocker.md")

    for required in [
        "second_model",
        "first_model",
        "http://127.0.0.1:8081/v1",
        "http://127.0.0.1:8082/v1",
        "invalid orchestrator JSON",
    ]:
        assert required in poc or required in blocker

    assert "No final model-pair recommendation" in blocker


def test_local_orchestrator_executor_v2_doc_records_executor_reachability() -> None:
    text = _read("docs/ai/local_orchestrator_executor_poc_v2_repair.md")

    for required in [
        "completed_with_failures",
        "initial plan parse success",
        "executor calls attempted",
        "2",
        "0.291764",
        "missing_required_parameter",
        "unsafe_path",
    ]:
        assert required in text


def test_local_orchestrator_executor_v3_doc_records_successful_executor_actions() -> None:
    text = _read("docs/ai/local_orchestrator_executor_poc_v3_executor_repair.md")

    for required in [
        "completed",
        "success",
        "0.890597",
        "per_agent_attempts.jsonl",
        "docs/ai/model_research_metadata.md",
        "configs/evaluation_models.json",
        "repair was enabled but not needed",
        "repeated_local_orchestrator_executor_trials_v1.md",
    ]:
        assert required in text


def test_repeated_local_orchestrator_executor_trials_doc_records_n3_result() -> None:
    text = _read("docs/ai/repeated_local_orchestrator_executor_trials_v1.md")

    for required in [
        "Repeated Local Orchestrator/Executor Trials v1",
        "repeated_local_second_to_first_group_n3_v1",
        "attempted trials",
        "completed trials",
        "0.890528",
        "0.000088",
        "read_file: 6",
        "No final model recommendation",
        "orchestrator_executor_pair_matrix_v1.md",
    ]:
        assert required in text


def test_orchestrator_executor_pair_matrix_doc_records_result() -> None:
    text = _read("docs/ai/orchestrator_executor_pair_matrix_v1.md")

    for required in [
        "Orchestrator/Executor Pair Matrix v1",
        "pair_matrix_office_developer_group_n3_v1",
        "second_model -> first_model",
        "second_model -> second_model",
        "first_model -> first_model",
        "first_model -> second_model",
        "0.952618",
        "0.948958",
        "orchestrator_plan_parse_failed: 6",
        "current best observed pair",
        "No final production recommendation",
        "pair_matrix_heavy_group_n3_workspace_policy_v1",
        "cross_scenario_pair_matrix_workspace_policy_v1",
        "stable_but_low_confidence",
    ]:
        assert required in text


def test_heavy_multi_agent_scenario_doc_records_matrix_result() -> None:
    text = _read("docs/ai/heavy_multi_agent_scenario_v1.md")

    for required in [
        "Heavy Multi-Agent Scenario v1",
        "office_developer_maintenance_group_heavy_v1",
        "office_agent_1",
        "developer_agent_2",
        "artifact_workspace_only",
        "fake_heavy_group_scenario_smoke_workspace_policy_v1",
        "repeated_local_second_to_first_heavy_group_n3_workspace_policy_v1",
        "0.820328",
        "write_path_outside_artifact_workspace",
        "pair_matrix_heavy_group_n3_workspace_policy_v1",
        "second_model -> second_model",
        "0.759188",
        "cross_scenario_pair_matrix_workspace_policy_v1",
        "stable_but_low_confidence",
        "not a final recommendation",
    ]:
        assert required in text


def test_heavy_scenario_error_analysis_records_root_causes() -> None:
    text = _read("docs/ai/heavy_scenario_error_analysis_v1.md")

    for required in [
        "Heavy Scenario Error Analysis v1",
        "repeated_local_second_to_first_heavy_group_n3_workspace_policy_v1",
        "pair_matrix_heavy_group_n3_workspace_policy_v1",
        "write_path_outside_artifact_workspace",
        "HTTPStatusError",
        "400 Bad Request",
        "execution_success_rate = 1.0",
        "No validator or path-policy fix was required",
    ]:
        assert required in text


def test_orchestrator_executor_runtime_capacity_doc_records_probe() -> None:
    text = _read("docs/ai/orchestrator_executor_runtime_capacity_v1.md")

    for required in [
        "Orchestrator/Executor Runtime Capacity v1",
        "runtime_probe_candidate_pairs_v1",
        "second_model -> first_model",
        "second_model -> second_model",
        "0.889947",
        "0.875509",
        "4390.257813",
        "5675.605469",
        "estimated_concurrent_pairs_by_ram",
        "quality/cost winner",
        "GPU detected: yes",
        "GPU smoke artifact",
        "Bounded Stress Follow-up",
        "preliminary only",
    ]:
        assert required in text


def test_gpu_runtime_configuration_docs_record_observed_flags() -> None:
    observed = _read("docs/ai/llama_server_gpu_flags_observed.md")
    config = _read("docs/ai/gpu_runtime_configuration_v1.md")

    for required in [
        "--n-gpu-layers",
        "--main-gpu",
        "--split-mode",
        "--tensor-split",
        "--flash-attn",
        "--device none",
        "version: 9264",
    ]:
        assert required in observed

    for required in [
        "GPU Runtime Configuration v1",
        "-GpuLayers",
        "-MainGpu",
        "-SplitMode",
        "-CpuOnly",
        "GpuLayers all",
    ]:
        assert required in config


def test_gpu_smoke_doc_records_result_and_caveats() -> None:
    text = _read("docs/ai/gpu_smoke_second_to_second_heavy_v1.md")

    for required in [
        "GPU Smoke Second-to-Second Heavy v1",
        "gpu_smoke_second_to_second_heavy_v1",
        "second_model -> second_model",
        "0.875562",
        "0.875545",
        "8775.802",
        "8716.17",
        "1.006842",
        "not the same as strict `--device none`",
        "not evidence of meaningful acceleration",
    ]:
        assert required in text


def test_bounded_stress_doc_records_failed_result_and_profiles() -> None:
    text = _read("docs/ai/bounded_stress_candidate_pairs_v1.md")

    for required in [
        "Bounded Stress Probe for Candidate Pairs v1",
        "bounded_stress_candidate_pairs_v1",
        "strict_cpu",
        "gpu_full_offload",
        "second_model -> second_model",
        "second_model -> first_model",
        "concurrency levels tested: `1`, `2`",
        "skipped concurrency level: `4`",
        "FileNotFoundError",
        "max stable concurrency observed",
        "none",
        "not proven truly strict",
    ]:
        assert required in text


def test_reproduction_has_one_ordered_clean_clone_path() -> None:
    text = _read("docs/reproducibility.md")
    ordered_headings = [
        "## 1. Проверить требования",
        "## 2. Клонировать репозиторий",
        "## 3. Проверить актуальный коммит",
        "## 4. Создать `.venv`",
        "## 5. Установить и проверить Python-зависимости",
        "## 6. Запустить полный `pytest` без модели",
        "## 7. Выполнить сухой запуск с `sixth_model`",
        "## 8. Найти существующую копию GGUF",
        "## 9. Загрузить модель при отсутствии проверенной копии",
        "## 10. Проверить размер, SHA-256 и Git ignore",
        "## 11. Найти реальный путь к `llama-server.exe`",
        "## 12. Запустить ручной сервер",
        "## 13. Дождаться HTTP 200 от `/health`",
        "## 14. Проверить псевдоним `sixth_model`",
        "## 15. Проверить точный JSON-контракт",
        "## 16. Выполнить полный поведенческий запуск",
        "## 17. Проверить результат `35/35`",
        "## 18. Остановить ручной сервер",
        "## 19. Проверить освобождение порта 8085",
        "## 20. Запустить ресурсный стенд",
        "## 21. Проверить ресурсный результат",
        "## 22. Выполнить необязательную очистку",
        "## 23. Учесть ограничения воспроизведения",
    ]

    positions = [text.index(heading) for heading in ordered_headings]
    assert positions == sorted(positions)
    assert text.count("\n## ") == len(ordered_headings)
    for marker in [
        "**Цель.**",
        "**Ожидаемый результат.**",
        "**Проверка.**",
        "**Диагностика.**",
        "**Переход дальше.**",
    ]:
        assert text.count(marker) == len(ordered_headings)


def test_reproduction_creates_venv_before_using_its_python() -> None:
    text = _read("docs/reproducibility.md")
    creation = "py -3.12 -m venv .venv"
    venv_python = r".\.venv\Scripts\python.exe"

    assert text.index(creation) < text.index(venv_python)
    section = _section(
        text,
        "## 4. Создать `.venv`",
        "## 5. Установить и проверить Python-зависимости",
    )
    normalized = " ".join(section.split())
    assert "До выполнения команды создания этого файла не существует" in normalized
    assert "команду установки зависимостей нельзя запускать раньше" in normalized


def test_reproduction_uses_direct_venv_python_and_documents_vscode() -> None:
    text = _read("docs/reproducibility.md")
    setup = _section(
        text,
        "## 4. Создать `.venv`",
        "## 6. Запустить полный `pytest` без модели",
    )

    for required in [
        "Активация окружения не требуется",
        "автоматически отправить команду активации",
        "Operation cancelled by user",
        "не доказывает, что пользователь нажал `Ctrl+C`",
        '"python-envs.terminal.autoActivationType": "off"',
        '"python.terminal.activateEnvironment": false',
        '"python.terminal.activateEnvInCurrentTerminal": false',
        "закрыть текущий встроенный терминал VS Code",
        r".\.venv\Scripts\python.exe -m pip check",
        r".\.venv\Scripts\python.exe --version",
        r".\.venv\Scripts\python.exe -m pytest --version",
        'throw "Dependency installation failed."',
    ]:
        assert required in setup


def test_reproduction_runs_all_model_free_checks_before_model_download() -> None:
    text = _read("docs/reproducibility.md")

    assert text.index("## 6. Запустить полный `pytest` без модели") < text.index(
        "## 9. Загрузить модель"
    )
    assert text.index("## 7. Выполнить сухой запуск") < text.index(
        "## 9. Загрузить модель"
    )
    assert "не требует GGUF, сети или работающего `llama-server`" in text


def test_reproduction_dry_run_uses_only_full_sixth_model_config() -> None:
    text = _read("docs/reproducibility.md")
    section = _section(
        text,
        "## 7. Выполнить сухой запуск с `sixth_model`",
        "## 8. Найти существующую копию GGUF",
    )
    config = json.loads(
        _read("configs/behavioral_benchmark_v2_sixth_model_full.json")
    )

    assert "configs\\behavioral_benchmark_v2_sixth_model_full.json" in section
    assert "--models sixth_model" in section
    assert "--trials-per-scenario 1" in section
    assert "--dry-run" in section
    assert "behavioral_benchmark_v2.example.json" not in section
    assert 'model_ids = ["sixth_model"]' in section
    assert "модель не загружается и запросы к ней не выполняются" in section
    assert config["model_profile"]["model_id"] == "sixth_model"
    assert len(config["scenario_ids"]) == 7


def test_reproduction_searches_for_existing_model_before_download() -> None:
    text = _read("docs/reproducibility.md")
    search = _section(
        text,
        "## 8. Найти существующую копию GGUF",
        "## 9. Загрузить модель при отсутствии проверенной копии",
    )
    verification = _section(
        text,
        "## 10. Проверить размер, SHA-256 и Git ignore",
        "## 11. Найти реальный путь к `llama-server.exe`",
    )

    assert text.index("## 8. Найти существующую копию GGUF") < text.index(
        "## 9. Загрузить модель"
    )
    for required in [
        "$modelFilename =",
        '"$env:USERPROFILE\\Documents"',
        "-Recurse",
        "FullName,Length",
        "19509790944",
        "cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde",
    ]:
        assert required in search
    for required in [
        "$sourceModel = Read-Host",
        "Copy-Item",
        "$targetItem",
        "$targetHash",
        "git check-ignore -v",
        "правило `*.gguf`",
    ]:
        assert required in verification


def test_reproduction_documents_rate_limit_resume_and_token_safety() -> None:
    text = _read("docs/reproducibility.md")
    section = _section(
        text,
        "## 9. Загрузить модель при отсутствии проверенной копии",
        "## 10. Проверить размер, SHA-256 и Git ignore",
    )

    for required in [
        "HTTP 429",
        "временно ограничил частоту запросов",
        "Это не означает\nповреждение модели",
        "сохраняет неполный файл",
        "повторно каждую секунду",
        "ограничение может сохраняться дольше шести минут",
        "$env:HF_TOKEN = Read-Host",
        "Remove-Item Env:HF_TOKEN",
        "не печатает токен",
        "Повторное клонирование и пересоздание `.venv` не помогают",
        "Start-Sleep -Seconds 360",
    ]:
        assert required in section
    assert "Start-Sleep -Minutes" not in text
    assert "huggingface_hub" in section


def test_reproduction_finds_llama_server_on_path_then_winget() -> None:
    text = _read("docs/reproducibility.md")
    section = _section(
        text,
        "## 11. Найти реальный путь к `llama-server.exe`",
        "## 12. Запустить ручной сервер",
    )

    assert "Get-Command `\n  llama-server.exe" in section
    assert '$env:LOCALAPPDATA\\Microsoft\\WinGet\\Packages' in section
    assert section.index("if ($serverCommand)") < section.index(
        "Get-ChildItem `"
    )
    assert "else {" in section
    assert 'throw "llama-server.exe was not found."' in section
    assert "& $serverPath --version" in section


def test_reproduction_separates_server_and_check_windows() -> None:
    text = _read("docs/reproducibility.md")

    assert "Окно PowerShell 1 — сервер" in text
    assert "Окно PowerShell 2 — проверки и запуск набора" in text
    server = _section(
        text,
        "## 12. Запустить ручной сервер",
        "## 13. Дождаться HTTP 200 от `/health`",
    )
    assert "& $serverPath `" in server
    assert "--alias sixth_model" in server
    assert "--reasoning off" in server
    assert r"C:\path\to\llama-server.exe" not in server


def test_reproduction_waits_for_http_200_before_checking_models() -> None:
    text = _read("docs/reproducibility.md")
    health = _section(
        text,
        "## 13. Дождаться HTTP 200 от `/health`",
        "## 14. Проверить псевдоним `sixth_model`",
    )

    for required in [
        "HTTP 503",
        "Loading model",
        "(Get-Date).AddMinutes(10)",
        '$httpCode -eq "200"',
        '$httpCode -eq "503"',
        "Start-Sleep -Seconds 5",
        'if ($httpCode -ne "200")',
        'throw "The server did not become ready within 10 minutes."',
    ]:
        assert required in health
    assert text.index('if ($httpCode -ne "200")') < text.index(
        "$modelsResponse = Invoke-RestMethod"
    )


def test_reproduction_asserts_sixth_model_alias_after_health() -> None:
    text = _read("docs/reproducibility.md")
    section = _section(
        text,
        "## 14. Проверить псевдоним `sixth_model`",
        "## 15. Проверить точный JSON-контракт",
    )

    assert "/v1/models" in section
    assert '$modelIds -notcontains "sixth_model"' in section
    assert "Returned models:" in section
    assert text.index("## 13. Дождаться HTTP 200") < text.index(
        "## 14. Проверить псевдоним"
    )


def test_reproduction_checks_exact_json_action_before_full_run() -> None:
    text = _read("docs/reproducibility.md")
    section = _section(
        text,
        "## 15. Проверить точный JSON-контракт",
        "## 16. Выполнить полный поведенческий запуск",
    )

    assert '{"action_name":"finish","parameters":{}}' in section
    assert "$content.Trim() -cne" in section
    assert 'throw "The model did not return the expected JSON action."' in section
    assert "Return exactly OK" not in section
    assert "Только после точного совпадения" in section


def test_reproduction_validates_behavioral_summary_after_run() -> None:
    text = _read("docs/reproducibility.md")
    run = _section(
        text,
        "## 16. Выполнить полный поведенческий запуск",
        "## 17. Проверить результат `35/35`",
    )
    result = _section(
        text,
        "## 17. Проверить результат `35/35`",
        "## 18. Остановить ручной сервер",
    )

    assert "--allow-model-execution" in run
    assert "artifacts\\reproduction\\sixth_model_full" in run
    assert text.index("## 16. Выполнить полный") < text.index(
        "$summary = Get-Content"
    )
    for required in [
        "TrialsTotal = 35",
        "TrialsSucceeded = 35",
        "TrialsFailed = 0",
        "PassRate = 1.0",
        "ModelExecution = True",
        "ExternalNetwork = False",
        "BrowserExecution = False",
        "PlaywrightExecution = False",
        "$scenarioRates.Count -ne 7",
        "`1,0`",
    ]:
        assert required in result


def test_reproduction_requires_free_port_before_resource_harness() -> None:
    text = _read("docs/reproducibility.md")
    port = _section(
        text,
        "## 19. Проверить освобождение порта 8085",
        "## 20. Запустить ресурсный стенд",
    )
    harness = _section(
        text,
        "## 20. Запустить ресурсный стенд",
        "## 21. Проверить ресурсный результат",
    )
    normalized_port = " ".join(port.split())

    for required in [
        "Get-NetTCPConnection",
        "-LocalPort 8085",
        "Get-CimInstance",
        "OwningProcess",
    ]:
        assert required in port
    assert "не завершайте неизвестный процесс автоматически" in normalized_port
    assert harness.index("Get-NetTCPConnection") < harness.index(
        "run_deterministic_gpu_resource_harness.py"
    )
    assert "--server-path $serverPath" in harness
    assert r"C:\path\to\llama-server.exe" not in harness
    assert "стенд сам запускает\nсервер" in harness


def test_reproduction_reads_resource_summary_only_after_harness() -> None:
    text = _read("docs/reproducibility.md")
    harness_heading = text.index("## 20. Запустить ресурсный стенд")
    harness_command = text.index("run_deterministic_gpu_resource_harness.py")
    summary_heading = text.index("## 21. Проверить ресурсный результат")
    summary_read = text.index("$resourceSummary = Get-Content")

    assert harness_heading < harness_command < summary_heading < summary_read
    result = _section(
        text,
        "## 21. Проверить ресурсный результат",
        "## 22. Выполнить необязательную очистку",
    )
    for required in [
        "Requests = 30",
        "Successful = 30",
        "Failed = 0",
        "GpuOffload = 65/65",
        "GpuVerified = True",
        "ProcessStopped = True",
        "PortReleased = True",
        "ValidationFailures = 0",
        "server_return_code = 1",
        "не\nопределяет успешность всего измерения",
    ]:
        assert required in result


def test_reproduction_has_symptom_diagnostics_table() -> None:
    text = _read("docs/reproducibility.md")
    table = text.split("### Диагностика по симптомам", 1)[1]

    for symptom in [
        r".\.venv\Scripts\python.exe",
        "Operation cancelled by user",
        "HTTP 429",
        "third_model",
        "/health",
        r"FileNotFoundError: C:\path\to\llama-server.exe",
        "Порт 8085 занят",
        "benchmark_summary.json",
        "server_return_code = 1",
        "1,0",
    ]:
        assert symptom in table


def test_reproduction_powershell_throw_messages_are_ascii() -> None:
    text = _read("docs/reproducibility.md")
    throw_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith('throw "')
    ]

    assert throw_lines
    assert all(line.isascii() for line in throw_lines)
    assert "Start-Sleep -Minutes" not in text


def test_reproduction_keeps_historical_names_and_archive_evidence() -> None:
    text = _read("docs/reproducibility.md")

    for display_name in [
        "Qwen3-14B Q5_K_M",
        "Mistral Small 3.2 24B Instruct Q4_K_M",
        "Qwen3-30B-A3B-Instruct-2507 Q4_K_M",
        "Qwen3.6-27B Q5_K_M",
    ]:
        assert display_name in text
    for required in [
        "не загружается при клонировании\nGitHub-репозитория",
        "только если архив был передан\nотдельно",
        "behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_"
        "final_20260727T063525Z.tar.gz",
        "960961",
        "4025b5c8af79335d1cb5ef8c553ccf7f533b11a610872800a179d15a2cfefdb7",
        "231 verified",
        "$finalArchive = Read-Host",
        "-FinalArchivePath $finalArchive",
    ]:
        assert required in text


def test_reproduction_document_tests_are_static_and_offline() -> None:
    source = _read("tests/test_research_readiness_docs.py")
    module_setup = source.split(
        "def test_reproduction_has_one_ordered_clean_clone_path",
        1,
    )[0]

    for forbidden in [
        "import subprocess",
        "import httpx",
        "import requests",
        "import socket",
    ]:
        assert forbidden not in module_setup
