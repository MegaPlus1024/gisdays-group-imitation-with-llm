# Воспроизведение проекта

Эта инструкция начинается с чистой копии Git-репозитория и воспроизводит
основной подтверждённый результат с Qwen3.6-27B Q5_K_M. Репозиторий и
Python-зависимости можно проверить до загрузки GGUF размером 19,5 ГБ.

## 1. Требования

### Программное обеспечение

- Windows 10 или Windows 11;
- PowerShell 5.1 или новее;
- Git;
- Python 3.12;
- актуальный драйвер NVIDIA;
- `llama-server.exe` из
  [официальных выпусков llama.cpp](https://github.com/ggml-org/llama.cpp/releases);
- `curl.exe`, входящий в современные версии Windows.

`pyproject.toml` допускает Python 3.11+, но подтверждённые испытания и
измерение ресурсов выполнялись на Python 3.12.

### Аппаратные ресурсы

Нужен графический процессор NVIDIA с достаточным объёмом видеопамяти для
выбранной конфигурации. Qwen3.6-27B Q5_K_M при размере контекста 12288 занимала
около 19,4 GiB видеопамяти на проверенной машине.

Это не означает, что 24 GB является универсальным минимумом. Потребление
зависит от версии `llama.cpp`, способа вычислений, размера контекста, кеша
ключей и значений (KV) и переноса слоёв на GPU. Перед запуском проверьте
доступную память:

```powershell
nvidia-smi
```

Рекомендуется не менее 30 GB свободного места для GGUF и создаваемых файлов.

## 2. Клонирование

```powershell
git clone https://github.com/MegaPlus1024/gisdays-group-imitation-with-llm.git
Set-Location gisdays-group-imitation-with-llm
```

Если репозиторий недоступен публично, Git запросит доступ к
`MegaPlus1024/gisdays-group-imitation-with-llm`.

Проверьте адрес удалённого репозитория:

```powershell
git remote -v
```

Ожидаемый URL:

```text
https://github.com/MegaPlus1024/gisdays-group-imitation-with-llm.git
```

## 3. Python-окружение

Создайте виртуальное окружение в каталоге репозитория и установите основные
зависимости:

```powershell
py -3.12 -m venv .venv

.\.venv\Scripts\python.exe `
  -m pip install `
  --upgrade pip

.\.venv\Scripts\python.exe `
  -m pip install `
  -r requirements.txt

if ($LASTEXITCODE -ne 0) {
  throw "Установка зависимостей не завершена."
}

.\.venv\Scripts\python.exe -m pip check

.\.venv\Scripts\python.exe `
  -m pytest `
  --version
```

Не переходите к следующим шагам, если `pip install` завершился с ошибкой.
Повторный запуск `pip install -r requirements.txt` продолжит установку;
пересоздавать `.venv` обычно не требуется. Активировать виртуальное окружение
необязательно, потому что все команды напрямую вызывают его Python.

Основные зависимости:

- `httpx`;
- `pydantic`;
- `pytest`;
- `psutil`;
- `rich`.

Дополнительные `requirements-browser.txt` и `requirements-office.txt` не нужны
для основного многоагентного набора испытаний.

### Если pip сообщает `Operation cancelled by user`

Это сообщение означает, что процесс получил внешнее прерывание. Оно само по
себе не доказывает, каким способом процесс был остановлен. Повторите основную
команду установки:

```powershell
.\.venv\Scripts\python.exe `
  -m pip install `
  -r requirements.txt
```

Если прерывание повторяется, диагностический запуск можно выполнить отдельным
процессом с журналами во временном каталоге:

```powershell
$pythonPath = (
  Resolve-Path `
    ".\.venv\Scripts\python.exe"
).Path

$pipStdout = Join-Path `
  $env:TEMP `
  "gisdays-pip-stdout.log"

$pipStderr = Join-Path `
  $env:TEMP `
  "gisdays-pip-stderr.log"

$pipProcess = Start-Process `
  -FilePath $pythonPath `
  -ArgumentList @(
    "-m",
    "pip",
    "install",
    "-r",
    "requirements.txt"
  ) `
  -Wait `
  -PassThru `
  -NoNewWindow `
  -RedirectStandardOutput $pipStdout `
  -RedirectStandardError $pipStderr

if ($pipProcess.ExitCode -ne 0) {
  throw (
    "Установка завершилась с кодом " +
    $pipProcess.ExitCode +
    ". Проверьте журналы в $env:TEMP."
  )
}
```

Этот вариант предназначен только для диагностики. Основным способом остаётся
прямой вызов Python из `.venv`.

## 4. Проверка установки и тесты без модели

Сначала проверьте версию Python:

```powershell
.\.venv\Scripts\python.exe --version
```

Затем запустите полный набор тестов:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Основную среду выполнения можно проверить отдельно:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_autonomous_multi_agent_runtime.py `
  tests\test_canonical_multi_agent_experiments.py
```

Полный `pytest` не требует GGUF-моделей или запущенного `llama-server`.
Настоящий запуск модели начинается только после загрузки Qwen3.6-27B.
Тесты, зависящие от необязательных браузерных библиотек, могут быть пропущены.
Их отсутствие может увеличить число `skipped`, но не должно приводить к
`failed`.

## 5. Сухой запуск среды выполнения

Сухой запуск проверяет все семь сценариев с одним повтором:

```powershell
.\.venv\Scripts\python.exe `
  scripts\run_autonomous_multi_agent_runtime.py `
  --config `
    configs\behavioral_benchmark_v2_sixth_model_full.json `
  --models sixth_model `
  --trials-per-scenario 1 `
  --dry-run `
  --output-dir `
    artifacts\reproduction\dry_run
```

В `artifacts\reproduction\dry_run\experiment_summary.json` ожидаются:

```text
status = succeeded
model_execution = false
model_ids = ["sixth_model"]
trials_total = 7
trials_succeeded = 7
trials_failed = 0
external_network = false
real_browser_execution = false
playwright_execution = false
```

При сухом запуске модель не загружается и запросы к ней не выполняются.
Идентификатор `sixth_model` используется для проверки конфигурации и структуры
выходных данных.

## 6. Скачивание основной модели

### Закреплённые данные

| Поле | Значение |
| --- | --- |
| Модель | Qwen3.6-27B Q5_K_M |
| Репозиторий | `unsloth/Qwen3.6-27B-GGUF` |
| Версия | `eff7310b099938f3cd9f794b97493201d7c4b11d` |
| Имя файла | `Qwen3.6-27B-Q5_K_M.gguf` |
| Размер | `19509790944` байт |
| SHA-256 | `cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde` |
| Локальный путь | `models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf` |

### Автоматическая загрузка

```powershell
.\scripts\download_required_model.ps1
```

Скрипт:

- использует закреплённую версию файла на Hugging Face;
- вызывает `curl.exe`;
- продолжает частичную загрузку с помощью `--continue-at -`;
- не загружает повторно уже проверенный файл;
- проверяет размер и SHA-256;
- сохраняет GGUF только в локальном каталоге, исключённом из Git.

Чтобы указать другой путь:

```powershell
.\scripts\download_required_model.ps1 `
  -Destination "D:\models\Qwen3.6-27B-Q5_K_M.gguf"
```

Если частично загруженный файл повреждён или имеет неверный размер, скрипт
сохраняет его. Для явного удаления и повторной загрузки:

```powershell
.\scripts\download_required_model.ps1 -ForceDownload
```

Режим без проверки SHA-256 доступен только при явном указании:

```powershell
.\scripts\download_required_model.ps1 -SkipHashCheck
```

Скрипт выводит предупреждение. Для воспроизводимого результата этот режим не
используйте.

### Ручная загрузка с закреплённой версией

Если вспомогательный скрипт недоступен, выполните эквивалентную загрузку
вручную:

```powershell
$revision = "eff7310b099938f3cd9f794b97493201d7c4b11d"
$file = "Qwen3.6-27B-Q5_K_M.gguf"
$destination = "models\gguf\sixth_model\$file"
$url = "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/$revision/$file?download=true"

New-Item `
  -ItemType Directory `
  -Path (Split-Path $destination) `
  -Force |
Out-Null

curl.exe `
  --location `
  --fail `
  --retry 3 `
  --continue-at - `
  --output $destination `
  $url

(Get-Item -LiteralPath $destination).Length

(Get-FileHash `
  -LiteralPath $destination `
  -Algorithm SHA256
).Hash
```

Последние две команды должны вернуть `19509790944` байт и
`CFECAB168156269F25D5FFE9E13CF2A401CA2F43A9693FA00BCD1625316CCBDE`.
Не запускайте испытания с файлом, который не прошёл обе проверки.

### Исторические модели

В предыдущем сравнении использовались Qwen3-14B Q5_K_M,
Mistral Small 3.2 24B Instruct Q4_K_M и
Qwen3-30B-A3B-Instruct-2507 Q4_K_M. Их веса не распространяются в
репозитории. Для основного воспроизведения нужна только Qwen3.6-27B Q5_K_M.

| Внутренний идентификатор | Полное название |
| --- | --- |
| `third_model` | Qwen3-14B Q5_K_M |
| `fourth_model` | Mistral Small 3.2 24B Instruct Q4_K_M |
| `fifth_model` | Qwen3-30B-A3B-Instruct-2507 Q4_K_M |
| `sixth_model` | Qwen3.6-27B Q5_K_M |

В метаданных, отслеживаемых Git, сохранены семейства, квантование и локальные
псевдонимы, но не полный набор версий, размеров и SHA-256 для каждого старого
GGUF. Поэтому инструкция не публикует непроверенные адреса загрузки.

## 7. Установка и поиск `llama-server`

Загрузите подходящую сборку из
[официальных выпусков llama.cpp](https://github.com/ggml-org/llama.cpp/releases)
или установите её с помощью WinGet.

В окне PowerShell, где будет запущен сервер, сначала найдите исполняемый файл:

```powershell
try {
  $serverPath = (
    Get-Command `
      llama-server.exe `
      -ErrorAction Stop
  ).Source
} catch {
  $serverPath = (
    Get-ChildItem `
      "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" `
      -Recurse `
      -File `
      -Filter "llama-server.exe" `
      -ErrorAction SilentlyContinue |
    Select-Object -First 1
  ).FullName
}

if (-not $serverPath) {
  throw "llama-server.exe не найден."
}

$serverPath
```

Если файл не находится ни через `PATH`, ни в каталоге WinGet, установите
`llama.cpp` и повторите поиск. Не подставляйте выдуманный путь.

## 8. Запуск сервера и ожидание готовности

Сервер запускается в отдельном окне PowerShell. В этом окне сначала выполните
поиск из предыдущего раздела, затем запустите:

```powershell
& $serverPath `
  --model `
    "models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf" `
  --alias sixth_model `
  --host 127.0.0.1 `
  --port 8085 `
  --ctx-size 12288 `
  --n-gpu-layers 999 `
  --parallel 1 `
  --jinja `
  --reasoning off
```

Загрузка модели может занять некоторое время. Пока она продолжается,
`/health` штатно возвращает HTTP 503 с текстом `Loading model`. Это не означает
ошибку модели. Полный набор испытаний нельзя запускать до ответа HTTP 200.

Во втором окне PowerShell дождитесь готовности с ограничением в 10 минут:

```powershell
$healthUrl = "http://127.0.0.1:8085/health"
$deadline = (Get-Date).AddMinutes(10)
$healthFile = Join-Path $env:TEMP "llama-health.json"

do {
  $httpCode = curl.exe `
    --silent `
    --output $healthFile `
    --write-out "%{http_code}" `
    $healthUrl

  $responseBody = if (
    Test-Path -LiteralPath $healthFile
  ) {
    Get-Content `
      -LiteralPath $healthFile `
      -Raw
  } else {
    ""
  }

  if ($httpCode -eq "200") {
    Write-Host "Модель загружена, сервер готов."
    break
  }

  if ($httpCode -eq "503") {
    Write-Host "Модель загружается..."
    Start-Sleep -Seconds 5
    continue
  }

  throw (
    "Неожиданный ответ сервера: HTTP " +
    $httpCode +
    " " +
    $responseBody
  )
} while ((Get-Date) -lt $deadline)

if ($httpCode -ne "200") {
  throw "Сервер не стал готов за 10 минут."
}
```

Только после успешного HTTP 200 запросите список моделей:

```powershell
$models = Invoke-RestMethod `
  http://127.0.0.1:8085/v1/models

$models |
  ConvertTo-Json `
    -Depth 10

$modelIds = @(
  $models.data |
    ForEach-Object {
      [string]$_.id
    }
)

if ($modelIds -notcontains "sixth_model") {
  throw "В /v1/models отсутствует sixth_model."
}
```

### Если HTTP 503 сохраняется слишком долго

Не завершайте неизвестные процессы автоматически. Сначала определите процесс,
который слушает порт 8085:

```powershell
$listener = Get-NetTCPConnection `
  -LocalPort 8085 `
  -State Listen `
  -ErrorAction Stop

Get-CimInstance `
  Win32_Process `
  -Filter "ProcessId = $($listener.OwningProcess)" |
Select-Object `
  ProcessId,Name,CommandLine |
Format-List
```

Проверьте загрузку GPU:

```powershell
nvidia-smi
```

В окне сервера проверьте наличие сообщений:

```text
out of memory
failed to allocate
failed to load model
```

Время загрузки зависит от накопителя, памяти, видеокарты и сборки
`llama.cpp`, поэтому универсального ожидаемого времени нет.

## 9. Проверка формата действий

После готовности сервера проверьте основной контракт проекта: модель должна
вернуть одно действие как необрамлённый объект JSON. Запуск сервера с
`--reasoning off` нужен, чтобы рассуждения не добавлялись к ответу.

```powershell
$baseUrl = "http://127.0.0.1:8085"

$body = @{
  model = "sixth_model"
  messages = @(
    @{
      role = "system"
      content = (
        "Return exactly one raw JSON object. " +
        "Do not use Markdown or prose. " +
        "Use exactly the top-level keys " +
        "action_name and parameters."
      )
    }
    @{
      role = "user"
      content = (
        "Return exactly: " +
        '{"action_name":"finish","parameters":{}}'
      )
    }
  )
  temperature = 0
  seed = 0
  max_tokens = 256
  stream = $false
} |
  ConvertTo-Json `
    -Depth 10

$response = Invoke-RestMethod `
  -Uri "$baseUrl/v1/chat/completions" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body `
  -TimeoutSec 180

$content = [string](
  $response.choices[0].message.content
)

$content

$content.Trim() -ceq `
  '{"action_name":"finish","parameters":{}}'
```

Ожидается:

```text
{"action_name":"finish","parameters":{}}
True
```

Только после успешной проверки HTTP 200, наличия `sixth_model` и точного
JSON-действия запускайте полный набор испытаний.

## 10. Полный набор испытаний

Файл `configs/behavioral_benchmark_v2_sixth_model_full.json` содержит семь
сценариев для Qwen3.6-27B Q5_K_M. Запускайте команду из корня репозитория во
втором окне PowerShell:

```powershell
.\.venv\Scripts\python.exe `
  scripts\run_autonomous_multi_agent_runtime.py `
  --config `
    configs\behavioral_benchmark_v2_sixth_model_full.json `
  --models sixth_model `
  --allow-model-execution `
  --output-dir `
    artifacts\reproduction\sixth_model_full
```

Параметр `--allow-model-execution` является обязательным явным разрешением.
Допустимы только адреса `127.0.0.1` и `localhost`; загрузчик конфигурации не
принимает внешний адрес модели.

Конфигурация задаёт:

- семь сценариев;
- пять повторов каждого сценария;
- максимум 40 ходов;
- циклическую очерёдность агентов;
- `temperature` со значением `0.0`;
- ограничение ответа в 512 токенов;
- префикс `/no_think`;
- время ожидания ответа 120 секунд.

После завершения остановите вручную запущенный сервер в его окне с помощью
`Ctrl+C`.

## 11. Проверка результатов

Прочитайте общую сводку:

```powershell
$summaryPath = (
  "artifacts\reproduction\sixth_model_full\" +
  "experiment_summary.json"
)

$summary = Get-Content `
  -LiteralPath $summaryPath `
  -Raw |
ConvertFrom-Json

$summary |
  Select-Object `
    status,
    trials_total,
    trials_succeeded,
    trials_failed,
    trial_pass_rate
```

Для совпадения с подтверждённым результатом ожидаются:

```text
status            = succeeded
trials_total      = 35
trials_succeeded  = 35
trials_failed     = 0
trial_pass_rate   = 1.0
```

Проверьте все сценарии:

```powershell
$summary.per_scenario_pass_rate
```

Каждый из семи показателей должен быть `1.0`.

Проверьте служебные поля безопасности:

```powershell
$summary |
  Select-Object `
    model_execution,
    external_network,
    real_browser_execution,
    playwright_execution
```

Для запуска с моделью на подготовленных данных ожидаются:

```text
model_execution        = true
external_network       = false
real_browser_execution = false
playwright_execution   = false
```

Каталог каждого повтора содержит `trial_summary.json` и `group_trace.jsonl`.
Журнал позволяет проверить предложенные действия, наблюдения, результаты
инструментов и выполнение требований по ходам.

## 12. Измерение ресурсов

Стенд измерения ресурсов сам запускает и останавливает ровно один
`llama-server`. Перед запуском остановите сервер из предыдущего раздела.
Порт 8085 должен быть свободен.

Укажите фактический путь к `llama-server.exe` и новый каталог результатов:

```powershell
.\.venv\Scripts\python.exe `
  scripts\run_deterministic_gpu_resource_harness.py `
  --model-id sixth_model `
  --model-path `
    models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf `
  --server-path `
    "C:\path\to\llama-server.exe" `
  --host 127.0.0.1 `
  --port 8085 `
  --ctx-size 12288 `
  --gpu-layers 999 `
  --parallel 1 `
  --jinja `
  --reasoning off `
  --server-log-verbosity 4 `
  --expected-model-bytes 19509790944 `
  --expected-model-sha256 `
    cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde `
  --expected-offloaded-layers 65/65 `
  --require-startup-alias `
  --out-dir `
    artifacts\descriptive_gpu_resource_profiles\sixth_model_reproduction
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

## 13. Проверка отдельно предоставленного архива

Этот архив не загружается при клонировании GitHub-репозитория. Раздел
применяется только в том случае, если архив был передан отдельно.

Техническое имя оставлено без изменения, поскольку оно связано с ранее
зафиксированными контрольными суммами:

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

Если архив предоставлен отдельно, запросите его полный путь:

```powershell
$archive = Read-Host `
  "Введите полный путь к отдельно полученному архиву"

if (-not (
  Test-Path `
    -LiteralPath $archive `
    -PathType Leaf
)) {
  throw "Архив не найден: $archive"
}

(Get-Item -LiteralPath $archive).Length

(Get-FileHash `
  -LiteralPath $archive `
  -Algorithm SHA256
).Hash

tar -tzf $archive
```

Основные документы с подтверждающими данными уже отслеживаются Git:

```text
docs/status/behavioral_benchmark_v2_final_report.md
docs/status/behavioral_benchmark_v2_descriptive_gpu_resource_profile.md
docs/status/behavioral_benchmark_v2_post_hoc_challenger_final_report.md
docs/status/behavioral_benchmark_v2_post_hoc_challenger_final_summary.json
docs/status/behavioral_benchmark_v2_post_hoc_challenger_archive.json
docs/status/behavioral_benchmark_v2_post_hoc_challenger_evidence.sha256
```

## 14. Дополнительная очистка

Этот раздел необязателен. Он предназначен для очистки после повторного
формирования проверочных данных. Обычному пользователю после тестов или нового
запуска не требуется очистка с проверкой итогового архива.

Скрипт нельзя запускать с выдуманным или отсутствующим архивом. Запросите
полный путь к отдельно полученному файлу и проверьте его:

```powershell
$finalArchive = Read-Host `
  "Введите полный путь к отдельно полученному архиву"

if (-not (
  Test-Path `
    -LiteralPath $finalArchive `
    -PathType Leaf
)) {
  throw "Архив не найден: $finalArchive"
}
```

Сначала выполните только предварительную проверку:

```powershell
.\scripts\cleanup_generated_files.ps1 `
  -FinalArchivePath $finalArchive
```

После проверки вывода разрешите удаление:

```powershell
.\scripts\cleanup_generated_files.ps1 `
  -FinalArchivePath $finalArchive `
  -Apply
```

Скрипт проверяет SHA-256 архива, список файлов внутри архива, отслеживаемые Git
файлы и точки повторной обработки файловой системы. Он не удаляет GGUF,
архивы, исходный код, конфигурации, тесты, документацию или `.venv`.

Для удаления обычного нового каталога результатов достаточно вручную указать
созданный вами каталог после проверки его содержимого. Не применяйте архивную
очистку к произвольному пути.

## 15. Ограничения воспроизведения

- Задержка и потребление ресурсов зависят от GPU, драйвера и сборки
  `llama.cpp`.
- Поведенческий результат относится к задачам с локально подготовленными
  данными.
- Испытания не используют открытый интернет, реальный браузер или Playwright.
- Поочерёдные ходы не являются параллельным выводом нескольких моделей.
- Один успешный набор не подтверждает эксплуатационную производительность или
  безопасность.
- Для точной архивной сверки нужен отдельно предоставленный архив
  подтверждающих данных.
