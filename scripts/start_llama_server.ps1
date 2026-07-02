param(
  [string]$ModelId,
  [string]$ModelsConfig = "configs\evaluation_models.json",
  [string]$ModelPath,
  [string]$HostAddress = "127.0.0.1",
  [Alias("Host")]
  [string]$HostAlias,
  [int]$Port = 8080,
  [int]$CtxSize = 4096,
  [string]$ServerPath,
  [switch]$DryRun,
  [switch]$Help
)

$ErrorActionPreference = "Stop"

function Show-Usage {
  $scriptName = Split-Path -Leaf $PSCommandPath
  @"
Usage:
  .\scripts\$scriptName [-ModelId <id>] [-ModelsConfig <path>] [-ModelPath <path>] [-Host <host>] [-Port <port>] [-CtxSize <tokens>] [-ServerPath <path>] [-DryRun]
  .\scripts\$scriptName -Help

Defaults:
  -ModelId       not required; default model path is <project-root>\models\gguf\first_model.gguf
  -ModelsConfig  configs\evaluation_models.json
  -Host          127.0.0.1
  -Port          8080
  -CtxSize       4096

Examples:
  .\scripts\$scriptName
  .\scripts\$scriptName -ModelId first_model
  .\scripts\$scriptName -ModelId second_model
  .\scripts\$scriptName -Port 8081
  .\scripts\$scriptName -ModelPath "C:\path\to\model.gguf"
  .\scripts\$scriptName -ServerPath "C:\path\to\llama-server.exe"
  .\scripts\$scriptName -ModelId first_model -DryRun

Notes:
  The Python virtual environment is only for Python dependencies.
  It does not add llama-server.exe to PATH.
  GGUF files are local runtime assets and must not be committed.
  If llama-server.exe is not in PATH, this wrapper searches common Windows install/extract locations.
"@
}

function Resolve-PathValue {
  param(
    [Parameter(Mandatory = $true)]
    [string]$PathValue,
    [Parameter(Mandatory = $true)]
    [string]$BasePath
  )

  $candidate = $PathValue
  if (-not [System.IO.Path]::IsPathRooted($candidate)) {
    $candidate = Join-Path $BasePath $candidate
  }

  return [System.IO.Path]::GetFullPath($candidate)
}

function Load-EvaluationModel {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ModelIdValue,
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath
  )

  if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Evaluation models config not found: $ConfigPath"
  }

  $payload = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $matches = @($payload.models | Where-Object {
      $_.model_id -eq $ModelIdValue -or @($_.aliases) -contains $ModelIdValue
    })
  if ($matches.Count -eq 0) {
    throw "ModelId '$ModelIdValue' not found in $ConfigPath"
  }
  if ($matches.Count -gt 1) {
    throw "ModelId '$ModelIdValue' is duplicated in $ConfigPath"
  }
  return $matches[0]
}

function Find-LlamaServer {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$ExplicitServerPath
  )

  if ($ExplicitServerPath) {
    $explicit = Resolve-PathValue -PathValue $ExplicitServerPath -BasePath $ProjectRoot
    if (-not (Test-Path -LiteralPath $explicit -PathType Leaf)) {
      throw "Explicit -ServerPath does not exist: $explicit"
    }
    return $explicit
  }

  $cmd = Get-Command "llama-server" -ErrorAction SilentlyContinue
  if (-not $cmd) {
    $cmd = Get-Command "llama-server.exe" -ErrorAction SilentlyContinue
  }
  if ($cmd -and $cmd.Source) {
    return $cmd.Source
  }

  $repoParent = Split-Path -Parent $ProjectRoot
  $userProfile = [Environment]::GetFolderPath("UserProfile")
  $systemDrive = $env:SystemDrive
  if (-not $systemDrive) {
    $systemDrive = "C:"
  }

  $candidateRoots = @(
    $ProjectRoot,
    $repoParent,
    (Join-Path $ProjectRoot "bin"),
    (Join-Path $ProjectRoot "tools"),
    (Join-Path $repoParent "llama.cpp"),
    (Join-Path $repoParent "llama"),
    (Join-Path $userProfile "AppData\Local\Microsoft\WinGet\Packages"),
    (Join-Path $userProfile "AppData\Local\Programs"),
    (Join-Path $userProfile "AppData\Local"),
    (Join-Path $userProfile "scoop\apps"),
    (Join-Path $userProfile ".local"),
    (Join-Path $userProfile "Downloads"),
    (Join-Path $userProfile "Documents"),
    (Join-Path $userProfile "Desktop"),
    (Join-Path $userProfile "tools"),
    (Join-Path $systemDrive "tools"),
    (Join-Path $systemDrive "dev"),
    (Join-Path $systemDrive "llama.cpp"),
    (Join-Path $systemDrive "llama"),
    (Join-Path $systemDrive "msys64"),
    (Join-Path $systemDrive "ProgramData\chocolatey"),
    (Join-Path $systemDrive "ProgramData\scoop"),
    $env:ProgramFiles,
    ${env:ProgramFiles(x86)}
  ) |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
    Select-Object -Unique

  foreach ($root in $candidateRoots) {
    $match = Get-ChildItem -LiteralPath $root -Recurse -Filter "llama-server.exe" -File -ErrorAction SilentlyContinue |
      Sort-Object FullName |
      Select-Object -First 1
    if ($match) {
      return $match.FullName
    }
  }

  throw @"
llama-server.exe was not found.

Fix options:
1. Pass the executable explicitly:
   .\scripts\start_llama_server.ps1 -ServerPath "C:\path\to\llama-server.exe"
2. Add the directory containing llama-server.exe to User PATH.
3. Install llama.cpp / llama-server and retry.
"@
}

if ($Help) {
  Show-Usage
  exit 0
}

if ($HostAlias) {
  $HostAddress = $HostAlias
}

if (-not $PSScriptRoot) {
  throw "Cannot determine script directory. Run this file as a PowerShell script."
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ResolvedModelsConfig = Resolve-PathValue -PathValue $ModelsConfig -BasePath $ProjectRoot
$SelectedModel = $null

if ($ModelId) {
  $SelectedModel = Load-EvaluationModel -ModelIdValue $ModelId -ConfigPath $ResolvedModelsConfig
  if (-not $SelectedModel.enabled) {
    throw "ModelId '$ModelId' is disabled in $ResolvedModelsConfig"
  }
  if (-not $ModelPath) {
    $ModelPath = $SelectedModel.gguf_path
  }
  if (-not $PSBoundParameters.ContainsKey("CtxSize") -and $SelectedModel.ctx_size) {
    $CtxSize = [int]$SelectedModel.ctx_size
  }
}

if (-not $ModelPath) {
  $ModelPath = "models\gguf\first_model.gguf"
}

$ResolvedModelPath = Resolve-PathValue -PathValue $ModelPath -BasePath $ProjectRoot
if (-not (Test-Path -LiteralPath $ResolvedModelPath -PathType Leaf)) {
  throw @"
Model file not found: $ResolvedModelPath

Fix options:
1. Put the GGUF model at the configured path.
2. Pass a model path explicitly:
   .\scripts\start_llama_server.ps1 -ModelPath "C:\path\to\model.gguf"
3. Check model registry metadata:
   .\.venv\Scripts\python.exe scripts\check_evaluation_model.py --model-id $ModelId --require-model-file
"@
}

$ResolvedServerPath = Find-LlamaServer -ProjectRoot $ProjectRoot -ExplicitServerPath $ServerPath

Write-Host "Project root:  $ProjectRoot"
Write-Host "Models config: $ResolvedModelsConfig"
if ($ModelId) {
  Write-Host "Model id:      $ModelId"
  if ($SelectedModel.model_id -ne $ModelId) {
    Write-Host "Resolved id:   $($SelectedModel.model_id)"
  }
  Write-Host "Model name:    $($SelectedModel.model_name)"
}
Write-Host "Model path:    $ResolvedModelPath"
Write-Host "Server path:   $ResolvedServerPath"
Write-Host "Host/port:     $HostAddress`:$Port"
Write-Host "Ctx size:      $CtxSize"
Write-Host ""

if ($DryRun) {
  Write-Host "Dry run: server was not started."
  Write-Host "Command:"
  Write-Host "& `"$ResolvedServerPath`" -m `"$ResolvedModelPath`" --host $HostAddress --port $Port --ctx-size $CtxSize"
  exit 0
}

& $ResolvedServerPath `
  -m $ResolvedModelPath `
  --host $HostAddress `
  --port $Port `
  --ctx-size $CtxSize
