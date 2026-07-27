# Local LLM Agent Lab

`local-llm-agent-lab` — локальный исследовательский runtime.

Локальная система для запуска нескольких специализированных LLM-агентов в
детерминированных рабочих процессах с проверяемыми инструментами, общей
средой, границами ролей и автоматическим benchmark.

Проект исследует normal user activity: группа local LLM agents получает роли,
resources и constraints, выбирает по одному действию за ход и сохраняет
раздельную history. Roles, resources, constraints, scripts and history
являются частью проверяемого контракта. Безопасность задаёт границы
эксперимента, но safety is not the final objective: основная проверка состоит
в корректном завершении полезной совместной задачи.

Это исследовательский прототип, а не готовая производственная система.

## Возможности

- несколько агентов с разными ролями и разрешениями;
- отдельные `agent state` и `history log` для каждого агента;
- общие файлы, факты и состояние ресурсов;
- зависимости и ожидание результатов других ролей;
- allowlist инструментов и проверка параметров до выполнения;
- восстановление после ошибочного действия;
- проверка источника, полномочий и точного значения факта;
- защита от повторов и преждевременного завершения;
- один JSON `next action` на ход;
- JSONL trace, сводки испытаний и evidence manifests;
- детерминированное измерение ресурсов локальной модели.

Канонический поток данных:

```text
config -> orchestrator -> agent state -> local LLM policy
       -> next action -> script runner -> observation -> history log
```

Модель выбирает действие, runtime проверяет его, а action execution выполняется
только зарегистрированным инструментом. Full autonomous agent loop is not implemented;
внешняя сеть, произвольные команды и свободный доступ к файлам не входят в
канонический контур.

## Основной результат

| Модель | Пройдено | Длительный сценарий | Итог |
| --- | ---: | ---: | --- |
| `third_model` | 30/35 | 0/5 | обязательный критерий не пройден |
| `fourth_model` | 30/35 | 0/5 | обязательный критерий не пройден |
| `fifth_model` | 30/35 | 0/5 | обязательный критерий не пройден |
| Qwen3.6-27B Q5_K_M | 35/35 | 5/5 | все критерии пройдены |

Исходное сравнение трёх моделей остаётся отдельным зафиксированным результатом.
Qwen3.6-27B Q5_K_M была проверена дополнительным полным запуском с теми же
семью сценариями, пятью повторами и теми же критериями. Результат показывает
поведение моделей только в этом fixture-based benchmark и не доказывает
production readiness.

## Быстрый запуск

Требуются Windows 10/11, PowerShell 5.1+, Git, Python 3.12 и `llama-server`
из [llama.cpp](https://github.com/ggml-org/llama.cpp/releases). Проект объявляет
совместимость с Python 3.11+, а подтверждённые запуски выполнялись на Python
3.12.

Клонирование и окружение:

```powershell
git clone https://github.com/MegaPlus1024/gisdays-group-imitation-with-llm.git
Set-Location gisdays-group-imitation-with-llm
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Скачать и проверить основную модель:

```powershell
.\scripts\download_required_model.ps1
```

Скрипт загружает закреплённый файл Qwen3.6-27B Q5_K_M, поддерживает resume и
проверяет размер и SHA-256. GGUF остаётся в
`models/gguf/qwen3_6_27b_q5_k_m/` и не добавляется в Git.

Запустить тесты без модели:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Запустить сервер в отдельном окне PowerShell:

```powershell
llama-server.exe `
  --model models\gguf\qwen3_6_27b_q5_k_m\Qwen3.6-27B-Q5_K_M.gguf `
  --alias qwen3_6_27b_q5_k_m `
  --host 127.0.0.1 `
  --port 8085 `
  --ctx-size 12288 `
  --n-gpu-layers 999 `
  --parallel 1 `
  --jinja `
  --reasoning off
```

Запустить полный benchmark из второго окна:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\behavioral_benchmark_v2_qwen3_6_27b_q5_k_m_full.json `
  --models qwen3_6_27b_q5_k_m `
  --allow-model-execution `
  --output-dir artifacts\reproduction\qwen3_6_27b_q5_k_m_full
```

Вызовы модели требуют явного `--allow-model-execution`. Без этого параметра
runtime не отправляет HTTP-запросы модели.

Безопасная демонстрация с fake policy:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent_long_horizon.example.json `
  --trials-per-scenario 1 `
  --dry-run
```

## Архитектура

Основные компоненты:

- `src/agent/autonomous_multi_agent_runtime.py` — состояния агентов, scheduler,
  turn loop, guards, общая среда и registry инструментов;
- `src/agent/canonical_multi_agent_experiments.py` — семь сценариев,
  повторные испытания, trace и сводные метрики;
- `scripts/run_autonomous_multi_agent_runtime.py` — CLI для безопасного и
  model-backed запуска;
- `configs/behavioral_benchmark_v2_qwen3_6_27b_q5_k_m_full.json` — полный
  воспроизводимый набор сценариев для основной модели;
- `scripts/run_deterministic_gpu_resource_harness.py` — lifecycle-owned
  измерение GPU/CPU/RAM и задержек;
- `configs/evaluation_models.json` — исторические локальные aliases.

Подробное описание канонического runtime:
[docs/architecture/canonical_runtime.md](docs/architecture/canonical_runtime.md).

## Локальные модели

Минимальное воспроизведение итогового результата требует только
Qwen3.6-27B Q5_K_M. Исторические `third_model`, `fourth_model` и `fifth_model`
использовались как базовые варианты; их веса не распространяются в
репозитории, а полностью закреплённые публичные checksum/revision для них не
сохранены.

Старые локальные aliases, включая `models/gguf/second_model.gguf`, нужны только
для исторических экспериментов. В архивных командах встречаются
`--model-id second_model` и `--model-ids first_model,second_model`; они не нужны
для минимального запуска Qwen.

## Документация

- [Краткий итоговый отчёт](docs/project_report.md)
- [Воспроизведение из чистого clone](docs/reproducibility.md)
- [Канонический runtime](docs/architecture/canonical_runtime.md)
- [Методика benchmark](docs/behavioral_benchmark_v2.md)
- [Подробный итоговый evidence report](docs/status/behavioral_benchmark_v2_post_hoc_challenger_final_report.md)
- [Проверка публикационной безопасности](docs/security/publication_security_check.md)

Сохранённые исследовательские материалы:

- [reports/experiments/final_evaluation_report.md](reports/experiments/final_evaluation_report.md)
- [reports/experiments/final_multi_agent_research_report.md](reports/experiments/final_multi_agent_research_report.md)
- [reports/experiments/manager_summary.md](reports/experiments/manager_summary.md)
- [reports/experiments/project_usage_appendix.md](reports/experiments/project_usage_appendix.md)
- [reports/experiments/final_evaluation_summary.json](reports/experiments/final_evaluation_summary.json)
- [docs/ai/model_research_metadata.md](docs/ai/model_research_metadata.md)
- [docs/ai/orchestrator_executor_runtime_capacity_v1.md](docs/ai/orchestrator_executor_runtime_capacity_v1.md)
- [docs/ai/gpu_runtime_configuration_v1.md](docs/ai/gpu_runtime_configuration_v1.md)
- [docs/ai/gpu_smoke_second_to_second_heavy_v1.md](docs/ai/gpu_smoke_second_to_second_heavy_v1.md)
- [docs/ai/bounded_stress_candidate_pairs_v1.md](docs/ai/bounded_stress_candidate_pairs_v1.md)

## Ограничения

- инструменты работают с локальными fixtures и ограниченными путями;
- round-robin означает логическое чередование, а не параллельный inference;
- benchmark не обращается к открытому интернету;
- resource profile измерен на одном GPU и в single-user режиме;
- не измерены multi-user throughput и длительная нагрузка;
- результаты не являются общей оценкой качества модели;
- production capacity и production security не подтверждены.
