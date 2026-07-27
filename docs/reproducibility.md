# Воспроизведение проекта из чистого клона

Эта инструкция описывает один последовательный путь для Windows: от чистого
клона до проверки поведенческого результата Qwen3.6-27B Q5_K_M и измерения
ресурсов. Проверки без модели выполняются до загрузки GGUF размером около
19,5 ГБ.

В шагах 1-11 достаточно одного окна PowerShell. Начиная с шага 12 используются
два независимых окна:

```text
Окно PowerShell 1 — сервер
Окно PowerShell 2 — проверки и запуск набора
```

Переменные PowerShell не передаются между окнами. Поэтому реальный путь к
`llama-server.exe` определяется в каждом окне, где он нужен.

## 1. Проверить требования

**Цель.** Убедиться, что на машине доступны Windows PowerShell 5.1+, Git,
Python 3.12, `curl.exe`, NVIDIA GPU и не менее 30 ГБ свободного места.
`pyproject.toml` допускает Python 3.11+, но подтверждённые запуски выполнялись
на Python 3.12.

**Основная команда.**

```powershell
$PSVersionTable.PSVersion
git --version
py -3.12 --version
curl.exe --version
nvidia-smi
```

**Ожидаемый результат.** Все команды найдены, Python сообщает версию 3.12, а
`nvidia-smi` показывает актуальный драйвер и доступную видеопамять.
Qwen3.6-27B Q5_K_M с контекстом 12288 занимала около 19,4 GiB видеопамяти на
проверенной машине, но это не универсальный минимум.

**Проверка.** Каждая команда должна завершиться без сообщения о том, что она
не найдена. Свободное место проверяется в свойствах диска, выбранного для
репозитория и модели.

**Диагностика.** Если `py -3.12` не найден, установите Python 3.12 с Python
Launcher. Если `nvidia-smi` не найден, сначала установите совместимый драйвер
NVIDIA. Потребление памяти зависит от сборки `llama.cpp`, контекста, KV-кеша и
числа слоёв на GPU.

**Переход дальше.** Продолжайте только после успешной проверки всех программ,
GPU и свободного места.

## 2. Клонировать репозиторий

**Цель.** Получить чистую рабочую копию и перейти в её корень.

**Основная команда.**

```powershell
git clone https://github.com/MegaPlus1024/gisdays-group-imitation-with-llm.git
Set-Location gisdays-group-imitation-with-llm
```

**Ожидаемый результат.** Создан каталог
`gisdays-group-imitation-with-llm`, текущий каталог PowerShell совпадает с
корнем клона.

**Проверка.**

```powershell
git remote -v
```

Ожидаемый URL:

```text
https://github.com/MegaPlus1024/gisdays-group-imitation-with-llm.git
```

**Диагностика.** Если репозиторий недоступен публично, Git запросит доступ к
`MegaPlus1024/gisdays-group-imitation-with-llm`. Не продолжайте из другого
репозитория с похожим именем.

**Переход дальше.** Продолжайте только из корня клона с ожидаемым `origin`.

## 3. Проверить актуальный коммит

**Цель.** Подтвердить чистое состояние актуальной ветки `main` без
разрушительного обновления или перезаписи локальных коммитов.

**Основная команда.**

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git log -5 --oneline
```

**Ожидаемый результат.** `git status --short` ничего не выводит, текущая ветка
равна `main`, а в только что созданном клоне `HEAD` совпадает с `origin/main`.

**Проверка.**

```powershell
$branch = git branch --show-current
$head = git rev-parse HEAD
$originMain = git rev-parse origin/main
$changes = @(git status --short)

if ($changes.Count -ne 0) {
  throw "The working tree is not clean."
}

if ($branch -ne "main") {
  throw "The current branch is not main."
}

if ($head -ne $originMain) {
  throw "HEAD does not match origin/main."
}
```

**Диагностика.** Несовпадение в существующей рабочей копии может означать
локальные коммиты или устаревшие ссылки. Не применяйте `reset --hard` и не
перезаписывайте локальную историю. Для этой инструкции проще создать новый
чистый клон.

**Переход дальше.** Для чистого клона продолжайте только при пустом статусе,
ветке `main` и совпадающих SHA.

## 4. Создать `.venv`

**Цель.** Создать изолированное окружение Python 3.12 до первого обращения к
его `python.exe`.

**Основная команда.**

```powershell
py -3.12 -m venv .venv
```

**Ожидаемый результат.** Появляется файл
`.\.venv\Scripts\python.exe`. До выполнения команды создания этого файла не
существует, поэтому команду установки зависимостей нельзя запускать раньше.

**Проверка.**

```powershell
if (-not (
  Test-Path `
    -LiteralPath ".\.venv\Scripts\python.exe" `
    -PathType Leaf
)) {
  throw ".venv Python was not created."
}
```

**Диагностика.** Если создание не завершилось, проверьте `py -0p`, права
записи и свободное место. Не запускайте `.venv\Scripts\python.exe`, пока этот
шаг не завершился успешно.

**Переход дальше.** Продолжайте только после появления
`.\.venv\Scripts\python.exe`.

### Примечание для VS Code

Расширение Python в VS Code может автоматически отправить команду активации
только что созданной `.venv` в текущий встроенный терминал. Если это происходит
во время работы `pip`, процесс может получить внешнее прерывание и вывести:

```text
ERROR: Operation cancelled by user
```

Это сообщение не доказывает, что пользователь нажал `Ctrl+C`. Надёжный путь:

1. создать `.venv`;
2. закрыть текущий встроенный терминал VS Code;
3. открыть новый терминал;
4. запускать `.\.venv\Scripts\python.exe` напрямую.

Активация окружения не требуется: все команды инструкции используют Python из
`.venv` напрямую. Если проблема действительно проявилась, автоматическую
активацию можно необязательно отключить в пользовательских настройках VS Code:

```json
{
  "python-envs.terminal.autoActivationType": "off",
  "python.terminal.activateEnvironment": false,
  "python.terminal.activateEnvInCurrentTerminal": false
}
```

Не меняйте глобальные настройки, если автоматическая активация не мешает.

## 5. Установить и проверить Python-зависимости

**Цель.** Установить только обязательные зависимости и проверить целостность
окружения. Дополнительные `requirements-browser.txt` и
`requirements-office.txt` для основного набора не нужны.

**Основная команда.**

```powershell
.\.venv\Scripts\python.exe `
  -m pip install `
  --upgrade pip

if ($LASTEXITCODE -ne 0) {
  throw "pip upgrade failed."
}

.\.venv\Scripts\python.exe `
  -m pip install `
  -r requirements.txt

if ($LASTEXITCODE -ne 0) {
  throw "Dependency installation failed."
}
```

**Ожидаемый результат.** Установлены `httpx`, `pydantic`, `pytest`, `psutil` и
`rich`, последняя команда возвращает код 0.

**Проверка.**

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest --version
```

`pip check` должен сообщить `No broken requirements found`, Python должен быть
версии 3.12, а `pytest` должен вывести номер версии.

**Диагностика.** После `Operation cancelled by user` закройте встроенный
терминал VS Code, откройте новый и повторите установку напрямую. Повторный
запуск продолжит установку; пересоздание `.venv` обычно не требуется.

**Переход дальше.** Продолжайте только после кода 0 у установки, `pip check` и
проверок версий.

## 6. Запустить полный `pytest` без модели

**Цель.** Проверить код до загрузки большого GGUF и до запуска сервера.

**Основная команда.**

```powershell
.\.venv\Scripts\python.exe -m pytest
```

**Ожидаемый результат.** Тесты завершаются без `failures` и `errors`.
Необязательные браузерные тесты могут быть пропущены.

**Проверка.**

```powershell
if ($LASTEXITCODE -ne 0) {
  throw "pytest failed."
}
```

Полный `pytest` не требует GGUF, сети или работающего `llama-server`.

**Диагностика.** Не загружайте модель, чтобы скрыть ошибку тестов: модель не
участвует в этом шаге. Проверьте, что команда запущена из корня клона и через
Python из `.venv`.

**Переход дальше.** Продолжайте только при отсутствии `failed` и `errors`.

## 7. Выполнить сухой запуск с `sixth_model`

**Цель.** Автономно проверить семь сценариев, конфигурацию `sixth_model` и
структуру результатов без загрузки модели и без запросов к серверу.

**Основная команда.**

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

**Ожидаемый результат.**

```text
status = succeeded
dry_run = true
model_execution = false
model_ids = ["sixth_model"]
trials_total = 7
trials_succeeded = 7
trials_failed = 0
external_network = false
real_browser_execution = false
playwright_execution = false
```

**Проверка.**

```powershell
$drySummary = Get-Content `
  -LiteralPath `
    "artifacts\reproduction\dry_run\experiment_summary.json" `
  -Raw |
ConvertFrom-Json

if (
  $drySummary.status -ne "succeeded" -or
  $drySummary.dry_run -ne $true -or
  $drySummary.model_execution -ne $false -or
  @($drySummary.model_ids) -notcontains "sixth_model" -or
  $drySummary.trials_total -ne 7 -or
  $drySummary.trials_succeeded -ne 7 -or
  $drySummary.trials_failed -ne 0 -or
  $drySummary.external_network -ne $false -or
  $drySummary.real_browser_execution -ne $false -or
  $drySummary.playwright_execution -ne $false
) {
  throw "Dry-run summary validation failed."
}
```

В сухом запуске модель не загружается и запросы к ней не выполняются.
Идентификатор `sixth_model` используется для проверки конфигурации и структуры
результатов.

**Диагностика.** Если сводка показывает `third_model`, использована не основная
конфигурация. Повторите именно приведённую команду с full-конфигурацией и
`--models sixth_model`.

**Переход дальше.** Продолжайте только после создания и успешной проверки
`experiment_summary.json`.

## 8. Найти существующую копию GGUF

**Цель.** Не загружать 19,5 ГБ повторно, если проверенная копия модели уже есть
в пользовательских документах.

**Основная команда.**

```powershell
$modelFilename = "Qwen3.6-27B-Q5_K_M.gguf"

Get-ChildItem `
  "$env:USERPROFILE\Documents" `
  -Filter $modelFilename `
  -File `
  -Recurse `
  -ErrorAction SilentlyContinue |
Select-Object FullName,Length
```

**Ожидаемый результат.** Команда либо ничего не выводит, либо показывает один
или несколько путей-кандидатов. Само совпадение имени ещё не подтверждает
целостность.

**Проверка.** Сохраните полный путь подходящего кандидата. Использовать его
можно только после проверки размера `19509790944` байт и SHA-256
`cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde`
на шаге 10.

**Диагностика.** Рекурсивный поиск может быть долгим. Не расширяйте его на весь
диск без необходимости и не копируйте файл только по совпадению имени.

**Переход дальше.** Если кандидат найден, пропустите загрузку на шаге 9 и
перейдите к шагу 10. Если кандидатов нет, выполните шаг 9.

## 9. Загрузить модель при отсутствии проверенной копии

**Цель.** Продолжить или начать загрузку закреплённого GGUF скриптом проекта,
не удаляя partial-файл при временном HTTP 429.

**Основная команда.**

```powershell
.\scripts\download_required_model.ps1
```

Скрипт загружает закреплённую версию
`eff7310b099938f3cd9f794b97493201d7c4b11d` из
`unsloth/Qwen3.6-27B-GGUF`, использует `--continue-at -`, ограниченно ожидает
после HTTP 429 и после успеха проверяет размер и SHA-256.

**Ожидаемый результат.** Создан проверенный файл:

```text
models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf
```

При HTTP 429 Hugging Face временно ограничил частоту запросов. Это не означает
повреждение модели. Скрипт сохраняет неполный файл, учитывает доступный
`Retry-After`, параметр сброса `t=` из `RateLimit` или отдельный заголовок
сброса лимита и при отсутствии такого заголовка использует ограниченную
задержку. Повторный запуск продолжает загрузку.
Повторное клонирование и пересоздание `.venv` не помогают. Не запускайте скрипт
повторно каждую секунду; ограничение может сохраняться дольше шести минут.

Для авторизованного запроса предпочтительно временно задать `HF_TOKEN`:

```powershell
$env:HF_TOKEN = Read-Host `
  "Hugging Face read token"

.\scripts\download_required_model.ps1

Remove-Item Env:HF_TOKEN
```

Скрипт не печатает токен и не записывает его в журналы. Не вставляйте токен в
документацию, Git или публикуемый терминальный вывод и не передавайте его
открытым аргументом, сохраняющимся в истории. `huggingface_hub` не является
обязательной зависимостью; официальный Hugging Face CLI остаётся только
резервным способом.

**Проверка.**

```powershell
if (-not (
  Test-Path `
    -LiteralPath `
      "models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf" `
    -PathType Leaf
)) {
  throw "The model file was not created."
}
```

**Диагностика.** При HTTP 429 оставьте partial-файл и повторите позже, лучше с
read-токеном. Для паузы в Windows PowerShell 5.1 допустима команда
`Start-Sleep -Seconds 360`, но шесть минут не гарантируют снятие ограничения.
При других ошибках проверьте сеть, свободное место и сообщение скрипта.

**Переход дальше.** Продолжайте только после успешного кода возврата скрипта.

## 10. Проверить размер, SHA-256 и Git ignore

**Цель.** Проверить источник, безопасно скопировать найденную модель при
необходимости, повторно проверить целевой файл и убедиться, что GGUF не попадёт
в Git.

**Основная команда.**

```powershell
$expectedBytes = [Int64]19509790944
$expectedSha256 = (
  "cfecab168156269f25d5ffe9e13cf2a401ca2f43" +
  "a9693fa00bcd1625316ccbde"
)
$modelPath = (
  "models\gguf\sixth_model\" +
  "Qwen3.6-27B-Q5_K_M.gguf"
)

if (-not (
  Test-Path `
    -LiteralPath $modelPath `
    -PathType Leaf
)) {
  $sourceModel = Read-Host `
    "Full path to the existing GGUF"

  if (-not (
    Test-Path `
      -LiteralPath $sourceModel `
      -PathType Leaf
  )) {
    throw "Source model was not found."
  }

  $sourceItem = Get-Item -LiteralPath $sourceModel
  $sourceHash = (
    Get-FileHash `
      -LiteralPath $sourceModel `
      -Algorithm SHA256
  ).Hash.ToLowerInvariant()

  if (
    [Int64]$sourceItem.Length -ne $expectedBytes -or
    $sourceHash -ne $expectedSha256
  ) {
    throw "Source model verification failed."
  }

  New-Item `
    -ItemType Directory `
    -Path (Split-Path -Parent $modelPath) `
    -Force |
  Out-Null

  Copy-Item `
    -LiteralPath $sourceModel `
    -Destination $modelPath
}

$targetItem = Get-Item -LiteralPath $modelPath
$targetHash = (
  Get-FileHash `
    -LiteralPath $modelPath `
    -Algorithm SHA256
).Hash.ToLowerInvariant()

if (
  [Int64]$targetItem.Length -ne $expectedBytes -or
  $targetHash -ne $expectedSha256
) {
  throw "Target model verification failed."
}

[PSCustomObject]@{
  Path = $targetItem.FullName
  Bytes = [Int64]$targetItem.Length
  Sha256 = $targetHash
} |
Format-List

git check-ignore -v `
  "models/gguf/sixth_model/Qwen3.6-27B-Q5_K_M.gguf"
```

**Ожидаемый результат.**

```text
Размер:  19509790944 bytes
SHA-256: cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde
Git:     правило *.gguf
```

**Проверка.** Блок сам останавливается при несовпадении размера или хеша.
Последняя команда должна показать правило `*.gguf` из `.gitignore`.

**Диагностика.** Не используйте файл с правильным размером, но другим хешем.
Если `git check-ignore` ничего не выводит, не запускайте модель и не добавляйте
GGUF в индекс.

**Переход дальше.** Продолжайте только после двух проверок целевого файла и
подтверждения правила `*.gguf`.

## 11. Найти реальный путь к `llama-server.exe`

**Цель.** Получить существующий путь без условной заглушки. Выполните этот шаг
в будущем окне проверок; переменная `$serverPath` понадобится ресурсному стенду.

**Основная команда.**

```powershell
$serverCommand = Get-Command `
  llama-server.exe `
  -ErrorAction SilentlyContinue

if ($serverCommand) {
  $serverPath = $serverCommand.Source
} else {
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

if (
  -not $serverPath -or
  -not (
    Test-Path `
      -LiteralPath $serverPath `
      -PathType Leaf
  )
) {
  throw "llama-server.exe was not found."
}

$serverPath
```

**Ожидаемый результат.** PowerShell печатает полный существующий путь к
`llama-server.exe`, а не вымышленный пример.

**Проверка.**

```powershell
& $serverPath --version
```

**Диагностика.** Если файл не найден, установите подходящую сборку из
[официальных выпусков llama.cpp](https://github.com/ggml-org/llama.cpp/releases)
или выполните `winget install --id ggml.llamacpp --exact`, затем повторите
основной блок. Поиск WinGet находится в ветке `else` и выполняется именно тогда,
когда `Get-Command` ничего не нашёл.

**Переход дальше.** Продолжайте только с существующим `$serverPath`, который
запускается через `& $serverPath`.

## 12. Запустить ручной сервер

**Цель.** Запустить один ручной `llama-server` для поведенческой проверки.

**Окно PowerShell 1 — сервер.** Откройте новое окно, перейдите в корень клона и
выполните один блок. Путь ищется повторно, потому что переменная шага 11 осталась
в другом окне.

**Основная команда.**

```powershell
$serverCommand = Get-Command `
  llama-server.exe `
  -ErrorAction SilentlyContinue

if ($serverCommand) {
  $serverPath = $serverCommand.Source
} else {
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

if (
  -not $serverPath -or
  -not (
    Test-Path `
      -LiteralPath $serverPath `
      -PathType Leaf
  )
) {
  throw "llama-server.exe was not found."
}

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

**Ожидаемый результат.** Сервер остаётся запущенным в этом окне, начинает
загрузку Qwen3.6-27B Q5_K_M и использует псевдоним `sixth_model`.

**Проверка.** Не закрывайте окно. В журнале не должно быть `out of memory`,
`failed to allocate` или `failed to load model`.

**Диагностика.** При ошибке неизвестного параметра проверьте актуальность сборки
командой `& $serverPath --help`; нужны `--alias`, `--jinja` и
`--reasoning off`. При нехватке памяти освободите GPU, а не меняйте закреплённую
команду воспроизведения.

**Переход дальше.** Оставьте сервер работающим и перейдите в окно 2. Не
запускайте набор, пока `/health` не вернёт HTTP 200.

## 13. Дождаться HTTP 200 от `/health`

**Цель.** Отличить нормальную загрузку с HTTP 503 от готового сервера.

**Окно PowerShell 2 — проверки и запуск набора.** Используйте прежнее окно, в
котором сохранён `$serverPath`.

**Основная команда.**

```powershell
$healthUrl = "http://127.0.0.1:8085/health"
$deadline = (Get-Date).AddMinutes(10)
$healthFile = Join-Path `
  $env:TEMP `
  "llama-health.json"

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
    Write-Host "Model loaded. Server is ready."
    break
  }

  if ($httpCode -eq "503") {
    Write-Host "Model is loading..."
    Start-Sleep -Seconds 5
    continue
  }

  throw (
    "Unexpected server response: HTTP " +
    $httpCode +
    " " +
    $responseBody
  )
} while ((Get-Date) -lt $deadline)

if ($httpCode -ne "200") {
  throw "The server did not become ready within 10 minutes."
}
```

**Ожидаемый результат.** Во время загрузки допустимы HTTP 503 и тело с
`Loading model`; это нормальная стадия, а не повреждение модели. Итоговый ответ
должен быть HTTP 200.

**Проверка.** Последняя проверка в блоке останавливает процесс инструкции, если
за 10 минут не получен HTTP 200.

**Диагностика.** При длительном 503 проверьте окно сервера и `nvidia-smi`.
Время зависит от накопителя, RAM, GPU и сборки. Не завершайте неизвестный
процесс автоматически.

**Переход дальше.** Только после HTTP 200 проверяйте `/v1/models`.

## 14. Проверить псевдоним `sixth_model`

**Цель.** Убедиться, что API публикует именно идентификатор, используемый
конфигурацией.

**Основная команда.**

```powershell
$modelsResponse = Invoke-RestMethod `
  "http://127.0.0.1:8085/v1/models"

$modelIds = @(
  $modelsResponse.data |
  ForEach-Object {
    $_.id
  }
)

if ($modelIds -notcontains "sixth_model") {
  throw (
    "sixth_model was not returned by /v1/models. " +
    "Returned models: " +
    ($modelIds -join ", ")
  )
}

$modelIds
```

**Ожидаемый результат.** Массив содержит `sixth_model`.

**Проверка.** Блок не просто печатает полный JSON, а явно проверяет наличие
идентификатора.

**Диагностика.** Если псевдоним отсутствует, остановите сервер через `Ctrl+C`,
проверьте `--alias sixth_model`, повторно запустите его и снова дождитесь HTTP
200.

**Переход дальше.** Продолжайте только при наличии `sixth_model`.

## 15. Проверить точный JSON-контракт

**Цель.** Подтвердить основной контракт проекта: модель возвращает одно
необрамлённое JSON-действие без Markdown, рассуждений или дополнительной прозы.

**Основная команда.**

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
ConvertTo-Json -Depth 10

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

if (
  $content.Trim() -cne `
    '{"action_name":"finish","parameters":{}}'
) {
  throw "The model did not return the expected JSON action."
}
```

**Ожидаемый результат.**

```text
{"action_name":"finish","parameters":{}}
```

**Проверка.** Сравнение чувствительно к регистру и отклоняет Markdown,
дополнительный текст и другой объект. Строка `OK` не является достаточной
проверкой.

**Диагностика.** При лишних рассуждениях убедитесь, что сервер запущен с
`--reasoning off` и `--jinja`. При тайм-ауте проверьте окно сервера и GPU.

**Переход дальше.** Только после точного совпадения разрешён полный
поведенческий запуск.

## 16. Выполнить полный поведенческий запуск

**Цель.** Выполнить семь сценариев по пять повторов с настоящей локальной
моделью.

**Основная команда.**

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

**Ожидаемый результат.** Команда выполняет 35 trials и создаёт
`artifacts\reproduction\sixth_model_full\experiment_summary.json`.
`--allow-model-execution` является обязательным явным разрешением. Допустимы
только `127.0.0.1` и `localhost`; открытый интернет, реальный браузер и
Playwright не используются.

**Проверка.**

```powershell
if ($LASTEXITCODE -ne 0) {
  throw "Behavioral run failed."
}
```

**Диагностика.** Не применяйте `--skip-existing` к непроверенному каталогу.
При ошибке сначала прочитайте `experiment_summary.json` и сводку конкретного
trial, не меняя сценарии или критерии оценки.

**Переход дальше.** Продолжайте только после завершения команды и создания
общей сводки.

## 17. Проверить результат `35/35`

**Цель.** Кратко сверить итог с подтверждённым поведенческим результатом.

**Основная команда.**

```powershell
$summaryPath = `
  "artifacts\reproduction\sixth_model_full\experiment_summary.json"

$summary = Get-Content `
  -LiteralPath $summaryPath `
  -Raw |
ConvertFrom-Json

[PSCustomObject]@{
  Status = $summary.status
  TrialsTotal = $summary.trials_total
  TrialsSucceeded = $summary.trials_succeeded
  TrialsFailed = $summary.trials_failed
  PassRate = $summary.trial_pass_rate
  ModelExecution = $summary.model_execution
  ExternalNetwork = $summary.external_network
  BrowserExecution = $summary.real_browser_execution
  PlaywrightExecution = $summary.playwright_execution
} |
Format-List
```

**Ожидаемый результат.**

```text
Status = succeeded
TrialsTotal = 35
TrialsSucceeded = 35
TrialsFailed = 0
PassRate = 1.0
ModelExecution = True
ExternalNetwork = False
BrowserExecution = False
PlaywrightExecution = False
```

В русской локали PowerShell может вывести `1,0`; это только формат отображения
числа.

**Проверка.**

```powershell
$scenarioRates = @(
  $summary.per_scenario_pass_rate.PSObject.Properties.Value
)

if (
  $summary.status -ne "succeeded" -or
  $summary.trials_total -ne 35 -or
  $summary.trials_succeeded -ne 35 -or
  $summary.trials_failed -ne 0 -or
  $summary.trial_pass_rate -ne 1.0 -or
  $summary.model_execution -ne $true -or
  $summary.external_network -ne $false -or
  $summary.real_browser_execution -ne $false -or
  $summary.playwright_execution -ne $false -or
  $scenarioRates.Count -ne 7 -or
  @($scenarioRates | Where-Object { $_ -ne 1.0 }).Count -ne 0
) {
  throw "Behavioral summary validation failed."
}
```

**Диагностика.** Если сводка не найдена, сначала выполните шаг 16. При
несовпадении проверяйте `trial_summary.json` и `group_trace.jsonl` неуспешного
повтора.

**Переход дальше.** Останавливайте ручной сервер только после проверки общей
сводки и семи pass rate.

## 18. Остановить ручной сервер

**Цель.** Освободить GPU и порт до ресурсного стенда, который сам запускает
собственный сервер.

**Окно PowerShell 1 — сервер.**

**Основное действие.**

```text
Ctrl+C
```

**Ожидаемый результат.** Ручной `llama-server` завершён, а приглашение
PowerShell снова доступно.

**Проверка.** Перейдите в окно 2 и выполните проверку порта на шаге 19.

**Диагностика.** Дождитесь штатного завершения. Не завершайте неизвестные
процессы автоматически.

**Переход дальше.** Не запускайте ресурсный стенд, пока шаг 19 не подтвердит,
что порт свободен.

## 19. Проверить освобождение порта 8085

**Цель.** Не допустить конфликта ручного сервера со стендом.

**Окно PowerShell 2 — проверки и запуск набора.**

**Основная команда.**

```powershell
$listener = Get-NetTCPConnection `
  -LocalPort 8085 `
  -State Listen `
  -ErrorAction SilentlyContinue

if ($listener) {
  Get-CimInstance `
    Win32_Process `
    -Filter "ProcessId = $($listener.OwningProcess)" |
  Select-Object `
    ProcessId,Name,CommandLine |
  Format-List

  throw "Port 8085 is already in use. Stop the manual llama-server first."
}
```

**Ожидаемый результат.** Команда ничего не выводит и не выбрасывает исключение.

**Проверка.** Отсутствие объекта `$listener` означает, что на порту 8085 нет
слушателя.

**Диагностика.** Если порт занят, блок показывает PID, имя и командную строку.
Определите владельца и остановите ручной сервер через `Ctrl+C`; не завершайте
неизвестный процесс автоматически.

**Переход дальше.** Продолжайте только при свободном порту.

## 20. Запустить ресурсный стенд

**Цель.** Выполнить детерминированное измерение, в котором стенд сам запускает
сервер, ждёт готовности, выполняет 30 запросов, завершает сервер и проверяет
освобождение порта.

Ручной поведенческий сервер и сервер ресурсного стенда — два разных режима.
Переменная `$serverPath` должна сохраняться в окне 2 после шага 11.

**Основная команда.**

```powershell
if (-not (
  Test-Path `
    -LiteralPath $serverPath `
    -PathType Leaf
)) {
  throw "llama-server.exe was not found."
}

$listener = Get-NetTCPConnection `
  -LocalPort 8085 `
  -State Listen `
  -ErrorAction SilentlyContinue

if ($listener) {
  throw "Port 8085 is already in use."
}

$outDir = Join-Path `
  "artifacts\descriptive_gpu_resource_profiles" `
  (
    "sixth_model_reproduction_" +
    (Get-Date -Format "yyyyMMdd_HHmmss")
  )

$outDir

.\.venv\Scripts\python.exe `
  scripts\run_deterministic_gpu_resource_harness.py `
  --model-id sixth_model `
  --model-path `
    models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf `
  --server-path $serverPath `
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
  --out-dir $outDir
```

**Ожидаемый результат.** После завершения в новом `$outDir` появляется
`benchmark_summary.json` и остальные подтверждающие файлы. Не пытайтесь читать
`benchmark_summary.json` до завершения этой команды.

**Проверка.**

```powershell
if ($LASTEXITCODE -ne 0) {
  throw "Resource harness failed."
}
```

**Диагностика.** Если порт занят, вернитесь к шагу 19. Если `$serverPath`
потерян из-за нового окна, повторите блок поиска из шага 11. Стенд откажется
работать с неверным размером или SHA-256 модели.

**Переход дальше.** Продолжайте только после завершения стенда и создания
каталога `$outDir`.

## 21. Проверить ресурсный результат

**Цель.** Сверить итоговые поля, управление сервером и фактический GPU offload.

**Основная команда.**

```powershell
$resourceSummaryPath = Join-Path `
  $outDir `
  "benchmark_summary.json"

if (
  -not (
    Test-Path `
      -LiteralPath $resourceSummaryPath `
      -PathType Leaf
  )
) {
  throw "benchmark_summary.json was not created."
}

$resourceSummary = Get-Content `
  -LiteralPath $resourceSummaryPath `
  -Raw |
ConvertFrom-Json

[PSCustomObject]@{
  Status = $resourceSummary.status
  Requests = (
    $resourceSummary.requests.measured_request_count
  )
  Successful = (
    $resourceSummary.requests.successful_request_count
  )
  Failed = (
    $resourceSummary.requests.failed_request_count
  )
  GpuOffload = (
    $resourceSummary.startup_log_evidence.offloaded_layers
  )
  GpuVerified = (
    $resourceSummary.actual_gpu_offload_evidence.verified
  )
  ProcessStopped = (
    $resourceSummary.shutdown.process_stopped
  )
  PortReleased = (
    $resourceSummary.post_shutdown.port_released
  )
  ValidationFailures = @(
    $resourceSummary.validation_failures
  ).Count
} |
Format-List
```

**Ожидаемый результат.**

```text
Status = succeeded
Requests = 30
Successful = 30
Failed = 0
GpuOffload = 65/65
GpuVerified = True
ProcessStopped = True
PortReleased = True
ValidationFailures = 0
```

**Проверка.**

```powershell
if (
  $resourceSummary.status -ne "succeeded" -or
  $resourceSummary.requests.measured_request_count -ne 30 -or
  $resourceSummary.requests.successful_request_count -ne 30 -or
  $resourceSummary.requests.failed_request_count -ne 0 -or
  $resourceSummary.startup_log_evidence.offloaded_layers -ne "65/65" -or
  $resourceSummary.actual_gpu_offload_evidence.verified -ne $true -or
  $resourceSummary.shutdown.process_stopped -ne $true -or
  $resourceSummary.post_shutdown.port_released -ne $true -or
  @($resourceSummary.validation_failures).Count -ne 0
) {
  throw "Resource summary validation failed."
}
```

`server_return_code = 1` сам по себе не является ошибкой результата, если
одновременно:

```text
status = succeeded
initiated_by_harness = true
process_stopped = true
forced_kill = false
port_released = true
validation_failures = []
```

Стенд сам завершает сервер, поэтому код возврата процесса в этом контексте не
определяет успешность всего измерения.

**Диагностика.** Если файл не найден, стенд ещё не запускался либо завершился
до записи сводки. Проверяйте `error.json`, журналы сервера и
`validation_failures`, а не только `server_return_code`.

**Переход дальше.** Воспроизведение завершено только после успешной проверки
всех полей и свободного порта.

## 22. Выполнить необязательную очистку

**Цель.** При необходимости удалить только результаты нового воспроизведения,
не затрагивая исходный код, модель или подтверждённые исторические данные.

**Основная команда.**

```powershell
$pathsToRemove = @(
  "artifacts\reproduction\dry_run",
  "artifacts\reproduction\sixth_model_full",
  $outDir
)

foreach ($path in $pathsToRemove) {
  if (
    $path -and
    (Test-Path -LiteralPath $path)
  ) {
    Remove-Item `
      -LiteralPath $path `
      -Recurse `
      -Force
  }
}
```

**Ожидаемый результат.** Удалены только три явно перечисленных каталога,
созданных этой инструкцией.

**Проверка.**

```powershell
git status --short
```

Статус клона должен оставаться чистым; GGUF в `models\gguf` не удаляется.

**Диагностика.** Перед удалением проверьте значение `$outDir`. Не применяйте
рекурсивное удаление к вычисленному или произвольному пути, если не проверили
его полное значение.

**Переход дальше.** Очистка необязательна. Если результаты нужны для анализа,
оставьте их на месте.

### Отдельно предоставленный архив

Архив подтверждающих данных не загружается при клонировании
GitHub-репозитория. Следующая проверка нужна только если архив был передан
отдельно. Его техническое имя и подтверждённые свойства не изменяются:

```text
behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz
bytes    = 960961
SHA-256  = 4025b5c8af79335d1cb5ef8c553ccf7f533b11a610872800a179d15a2cfefdb7
files    = 231 verified
mismatch = 0
```

Проверка отдельно полученного файла:

```powershell
$archive = Read-Host `
  "Full path to the separately provided archive"

if (-not (
  Test-Path `
    -LiteralPath $archive `
    -PathType Leaf
)) {
  throw "Archive was not found."
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

Архивная очистка требуется только после проверки полного пути и архива:

```powershell
$finalArchive = Read-Host `
  "Full path to the separately provided archive"

if (-not (
  Test-Path `
    -LiteralPath $finalArchive `
    -PathType Leaf
)) {
  throw "Archive was not found."
}

.\scripts\cleanup_generated_files.ps1 `
  -FinalArchivePath $finalArchive
```

После проверки предварительного вывода удаление можно явно разрешить:

```powershell
.\scripts\cleanup_generated_files.ps1 `
  -FinalArchivePath $finalArchive `
  -Apply
```

Скрипт не удаляет GGUF, архивы, исходный код, конфигурации, тесты,
документацию или `.venv`.

## 23. Учесть ограничения воспроизведения

**Цель.** Правильно интерпретировать результат и отличать поведенческую
проверку от эксплуатационной готовности.

**Основная команда.**

```powershell
git status --short
```

**Ожидаемый результат.** Инструкция не изменила отслеживаемые файлы клона.
Локальные GGUF и `artifacts` исключены из Git.

**Проверка.** Подтверждённый результат относится к заданным локальным
сценариям, а измерение ресурсов — к одному GPU, одному серверу и одному
пользователю.

**Диагностика.** Не переносите результат на длительную непрерывную нагрузку,
нескольких пользователей, отказоустойчивость, реальные данные или
непредусмотренные входы без отдельных испытаний.

**Переход дальше.** Для публикации сохраняйте только разрешённые документы и
обезличенные подтверждающие данные, но не модель, токены, журналы или
пользовательские абсолютные пути.

Ограничения:

- задержка и потребление ресурсов зависят от GPU, драйвера и сборки
  `llama.cpp`;
- испытания используют локально подготовленные статьи и файлы;
- открытый интернет, реальный браузер и Playwright не используются;
- поочерёдные ходы не означают параллельный вывод нескольких моделей;
- один успешный набор не подтверждает эксплуатационную производительность или
  безопасность;
- для точной архивной сверки нужен отдельно предоставленный архив.

Исторические модели не нужны для основного воспроизведения:

| Внутренний идентификатор | Полное название |
| --- | --- |
| `third_model` | Qwen3-14B Q5_K_M |
| `fourth_model` | Mistral Small 3.2 24B Instruct Q4_K_M |
| `fifth_model` | Qwen3-30B-A3B-Instruct-2507 Q4_K_M |
| `sixth_model` | Qwen3.6-27B Q5_K_M |

### Диагностика по симптомам

| Симптом | Причина | Действие |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe` не найден | `.venv` ещё не создана | Выполнить `py -3.12 -m venv .venv` |
| `Operation cancelled by user` во время pip | Возможное внешнее прерывание или автоактивация VS Code | Открыть новый терминал и повторить установку |
| HTTP 429 при скачивании | Ограничение запросов Hugging Face | Использовать токен, сохранить partial-файл, повторить позже |
| Сухой запуск показывает `third_model` | Использована example-конфигурация | Использовать full-конфигурацию и `--models sixth_model` |
| `/health` возвращает 503 | Модель ещё загружается | Продолжать ожидание до HTTP 200 |
| `FileNotFoundError: C:\path\to\llama-server.exe` | Не заменена заглушка | Найти `$serverPath` автоматически |
| Порт 8085 занят | Продолжает работать ручной сервер | Проверить процесс и остановить его через `Ctrl+C` |
| `benchmark_summary.json` не найден | Стенд ещё не запускался или завершился ошибкой | Сначала выполнить ресурсный стенд |
| `server_return_code = 1` | Сервер завершён стендом | Проверять итоговый `status`, shutdown и port release |
| `1,0` вместо `1.0` | Русская локаль PowerShell | Это формат отображения числа |
