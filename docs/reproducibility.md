# Воспроизведение проекта

Инструкция начинается с чистого clone и воспроизводит основной подтверждённый
результат с Qwen3.6-27B Q5_K_M. Исторические локальные модели для минимального
запуска не требуются.

## 1. Требования

### Программное обеспечение

- Windows 10 или Windows 11;
- PowerShell 5.1 или новее;
- Git;
- Python 3.12;
- актуальный NVIDIA driver;
- `llama-server.exe` из
  [официальных releases llama.cpp](https://github.com/ggml-org/llama.cpp/releases);
- `curl.exe`, входящий в современные версии Windows.

`pyproject.toml` допускает Python 3.11+, но подтверждённые испытания и
измерение ресурсов выполнялись на Python 3.12.

### Аппаратные ресурсы

Нужен NVIDIA GPU с достаточным объёмом VRAM для выбранной конфигурации.
Qwen3.6-27B Q5_K_M при context 12288 занимала около 19.4 GiB VRAM на
проверенной машине.

Это не означает, что 24 GB является универсальным минимумом: потребление
зависит от llama.cpp, backend, context, KV cache и offload. Перед запуском
проверьте доступную память:

```powershell
nvidia-smi
```

Рекомендуется не менее 30 GB свободного места для GGUF и создаваемых файлов.

## 2. Клонирование

```powershell
git clone https://github.com/MegaPlus1024/gisdays-group-imitation-with-llm.git
Set-Location gisdays-group-imitation-with-llm
```

Если репозиторий недоступен публично, Git запросит GitHub-доступ к
`MegaPlus1024/gisdays-group-imitation-with-llm`.

Проверить remote:

```powershell
git remote -v
```

Ожидаемый URL:

```text
https://github.com/MegaPlus1024/gisdays-group-imitation-with-llm.git
```

## 3. Python-окружение

Создать repository-local virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Основные зависимости:

- `httpx`;
- `pydantic`;
- `pytest`;
- `psutil`;
- `rich`.

Проверить interpreter:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest --version
```

Дополнительные `requirements-browser.txt` и `requirements-office.txt` не нужны
для основного многоагентного набора испытаний.

## 4. Основная модель

### Закреплённые данные

| Поле | Значение |
| --- | --- |
| Модель | Qwen3.6-27B Q5_K_M |
| Репозиторий | `unsloth/Qwen3.6-27B-GGUF` |
| Revision | `eff7310b099938f3cd9f794b97493201d7c4b11d` |
| Filename | `Qwen3.6-27B-Q5_K_M.gguf` |
| Размер | `19509790944` bytes |
| SHA-256 | `cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde` |
| Локальный путь | `models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf` |

### Автоматическая загрузка

```powershell
.\scripts\download_required_model.ps1
```

Скрипт:

- использует закреплённую версию файла на Hugging Face;
- вызывает `curl.exe`;
- продолжает partial download через `--continue-at -`;
- не скачивает повторно уже проверенный файл;
- проверяет размер и SHA-256;
- сохраняет GGUF только в ignored local directory.

Указать другой путь:

```powershell
.\scripts\download_required_model.ps1 `
  -Destination "D:\models\Qwen3.6-27B-Q5_K_M.gguf"
```

Если partial file повреждён или имеет неверный размер, скрипт сохраняет его.
Явное удаление и повторная загрузка:

```powershell
.\scripts\download_required_model.ps1 -ForceDownload
```

Небезопасный режим без проверки SHA-256 доступен только явно:

```powershell
.\scripts\download_required_model.ps1 -SkipHashCheck
```

Скрипт выводит предупреждение. Для воспроизводимого результата этот режим не
используйте.

### Ручная загрузка с закреплённой версией

Если вспомогательный скрипт недоступен, выполните эквивалентную загрузку
вручную. URL содержит ту же закреплённую версию, а `--continue-at -`
сохраняет возможность продолжить partial download:

```powershell
$revision = "eff7310b099938f3cd9f794b97493201d7c4b11d"
$file = "Qwen3.6-27B-Q5_K_M.gguf"
$destination = "models\gguf\sixth_model\$file"
$url = "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/$revision/$file?download=true"
New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
curl.exe --location --fail --retry 3 --continue-at - --output $destination $url
(Get-Item -LiteralPath $destination).Length
(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
```

Последние две команды должны вернуть `19509790944` bytes и
`CFECAB168156269F25D5FFE9E13CF2A401CA2F43A9693FA00BCD1625316CCBDE`.
Не запускайте испытания с файлом, который не прошёл обе проверки.

### Исторические модели

`third_model`, `fourth_model` и `fifth_model` использовались как исторические
базовые варианты. Их веса не распространяются в репозитории, а проверяемый
минимальный запуск требует только Qwen3.6-27B Q5_K_M.

В tracked metadata сохранены семейства, quantization и локальные aliases, но
не полный набор версий, размеров и SHA-256 для каждого старого GGUF. Поэтому
инструкция не публикует непроверенные download URL.

## 5. Тесты без модели

Полный набор тестов:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Основную среду выполнения можно проверить отдельно:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_autonomous_multi_agent_runtime.py `
  tests\test_canonical_multi_agent_experiments.py
```

Тесты не требуют запуска `llama-server`.

Безопасный dry-run одного повтора каждого сценария:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\behavioral_benchmark_v2.example.json `
  --trials-per-scenario 1 `
  --dry-run `
  --output-dir artifacts\reproduction\dry_run
```

В summary должны быть:

```text
model_execution = false
external_network = false
real_browser_execution = false
playwright_execution = false
```

## 6. Запуск локального сервера

Добавьте каталог с `llama-server.exe` в `PATH` либо укажите полный путь к
executable.

В отдельном окне PowerShell:

```powershell
llama-server.exe `
  --model models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf `
  --alias sixth_model `
  --host 127.0.0.1 `
  --port 8085 `
  --ctx-size 12288 `
  --n-gpu-layers 999 `
  --parallel 1 `
  --jinja `
  --reasoning off
```

Проверить готовность из второго окна:

```powershell
Invoke-RestMethod http://127.0.0.1:8085/health
Invoke-RestMethod http://127.0.0.1:8085/v1/models
```

В `/v1/models` должен присутствовать alias
`sixth_model`.

Проверить OpenAI-compatible protocol одним коротким локальным запросом:

```powershell
$body = @{
  model = "sixth_model"
  messages = @(
    @{ role = "user"; content = "/no_think Return exactly OK." }
  )
  max_tokens = 8
  temperature = 0.0
} | ConvertTo-Json -Depth 4
$response = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8085/v1/chat/completions" `
  -ContentType "application/json" `
  -Body $body
$response.choices[0].message.content
```

Этот короткий запрос проверяет только локальный протокол и имя модели. Он не
входит в набор испытаний и не заменяет полный запуск.

## 7. Полный набор испытаний

Запускайте из корня репозитория во втором окне PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\behavioral_benchmark_v2_sixth_model_full.json `
  --models sixth_model `
  --allow-model-execution `
  --output-dir artifacts\reproduction\sixth_model_full
```

Параметр `--allow-model-execution` является обязательным opt-in. Endpoint
ограничен `127.0.0.1`/`localhost`; внешний model URL config loader не принимает.

Конфигурация задаёт:

- семь сценариев;
- пять повторов каждого сценария;
- максимум 40 ходов;
- round-robin scheduler;
- temperature `0.0`;
- response limit `512`;
- `/no_think`;
- timeout `120` секунд.

После завершения остановите вручную запущенный сервер в его окне с `Ctrl+C`.

## 8. Проверка результатов

Прочитать experiment summary:

```powershell
$summaryPath = "artifacts\reproduction\sixth_model_full\experiment_summary.json"
$summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
$summary | Select-Object status,trials_total,trials_succeeded,trials_failed,trial_pass_rate
```

Для совпадения с подтверждённым результатом ожидаются:

```text
status            = succeeded
trials_total      = 35
trials_succeeded  = 35
trials_failed     = 0
trial_pass_rate   = 1.0
```

Проверить все сценарии:

```powershell
$summary.per_scenario_pass_rate
```

Каждый из семи показателей должен быть `1.0`.

Ключевые служебные поля безопасности:

```powershell
$summary | Select-Object `
  model_execution,external_network,real_browser_execution,playwright_execution
```

Для запуска с моделью на подготовленных данных ожидаются:

```text
model_execution        = true
external_network       = false
real_browser_execution = false
playwright_execution   = false
```

Каждый trial directory содержит `trial_summary.json` и `group_trace.jsonl`.
Журнал позволяет проверить предложенные действия, наблюдения, результаты
инструментов и выполненные требования по ходам.

## 9. Измерение ресурсов

Стенд измерения ресурсов сам запускает и останавливает ровно один
`llama-server`.
Перед запуском остановите сервер из предыдущего раздела. Порт 8085 должен быть
свободен.

Укажите реальный путь к `llama-server.exe` и новый output directory:

```powershell
.\.venv\Scripts\python.exe scripts\run_deterministic_gpu_resource_harness.py `
  --model-id sixth_model `
  --model-path models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf `
  --server-path "C:\path\to\llama-server.exe" `
  --host 127.0.0.1 `
  --port 8085 `
  --ctx-size 12288 `
  --gpu-layers 999 `
  --parallel 1 `
  --jinja `
  --reasoning off `
  --server-log-verbosity 4 `
  --expected-model-bytes 19509790944 `
  --expected-model-sha256 cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde `
  --expected-offloaded-layers 65/65 `
  --require-startup-alias `
  --out-dir artifacts\descriptive_gpu_resource_profiles\sixth_model_reproduction
```

Стенд проверяет файл модели, отсутствие другого `llama-server`, свободный
порт, исходное потребление памяти GPU, `/health`, `/v1/models`, имя модели и
журнал запуска.

Он записывает:

- `manifest.json`;
- `server_command.json`;
- `benchmark_summary.json`;
- `resource_summary.json`;
- `resource_samples.jsonl`;
- `resource_samples.csv`;
- `requests.jsonl`;
- `responses.jsonl`;
- `server_stdout.log`;
- `server_stderr.log`;
- `evidence_manifest.json`;
- `replay_commands.md`.

Успешная итоговая проверка должна показывать:

```text
status = succeeded
measured requests = 30/30
offloaded layers = 65/65
process stopped = true
port released = true
```

Синтетическая нагрузка для измерения ресурсов не заменяет проверку поведения
моделей.

## 10. Проверка сохранённых подтверждающих данных

Основные tracked документы:

```text
docs/status/behavioral_benchmark_v2_final_report.md
docs/status/behavioral_benchmark_v2_descriptive_gpu_resource_profile.md
docs/status/behavioral_benchmark_v2_post_hoc_challenger_final_report.md
docs/status/behavioral_benchmark_v2_post_hoc_challenger_final_summary.json
docs/status/behavioral_benchmark_v2_post_hoc_challenger_archive.json
docs/status/behavioral_benchmark_v2_post_hoc_challenger_evidence.sha256
```

Итоговый созданный архив хранится вне Git:

```text
behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz
```

Ожидаемые свойства:

```text
bytes    = 960961
SHA-256  = 4025b5c8af79335d1cb5ef8c553ccf7f533b11a610872800a179d15a2cfefdb7
files    = 231 verified
mismatch = 0
```

Если архив предоставлен отдельно, проверить его:

```powershell
$archive = "..\behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz"
(Get-Item -LiteralPath $archive).Length
(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
tar -tzf $archive
```

## 11. Очистка созданных файлов

Сначала только dry-run:

```powershell
.\scripts\cleanup_generated_files.ps1 `
  -FinalArchivePath "..\behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz"
```

Фактическое удаление разрешённых каталогов:

```powershell
.\scripts\cleanup_generated_files.ps1 `
  -FinalArchivePath "..\behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz" `
  -Apply
```

Скрипт проверяет SHA-256 архива, archive member list, tracked-файлы и reparse
points. Он не удаляет GGUF, archives, source, configs, tests, docs или `.venv`.

## 12. Ограничения воспроизведения

- Значения latency и ресурсов зависят от GPU, driver и сборки llama.cpp.
- Поведенческий результат относится к задачам с локально подготовленными
  данными.
- Испытания не используют открытый интернет, реальный браузер или Playwright.
- Поочерёдные ходы не являются параллельным выводом нескольких моделей.
- Один успешный набор не подтверждает эксплуатационную производительность или
  безопасность.
- Для точной архивной сверки нужен отдельно предоставленный архив
  подтверждающих данных.
