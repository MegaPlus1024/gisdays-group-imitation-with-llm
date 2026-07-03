param(
  [string]$ModelId,
  [string]$ModelsConfig = "configs\evaluation_models.json",
  [string]$ModelPath,
  [string]$HostAddress = "127.0.0.1",
  [Alias("Host")]
  [string]$HostAlias,
  [int]$Port = 8080,
  [int]$CtxSize = 4096,
  [Alias("NGpuLayers")]
  [string]$GpuLayers,
  [System.Nullable[int]]$MainGpu,
  [string]$TensorSplit,
  [ValidateSet("none", "layer", "row", "tensor")]
  [string]$SplitMode,
  [System.Nullable[int]]$BatchSize,
  [System.Nullable[int]]$UBatchSize,
  [System.Nullable[int]]$Threads,
  [ValidateSet("on", "off", "auto")]
  [string]$FlashAttention,
  [switch]$CpuOnly,
  [string]$ServerPath,
  [switch]$DryRun,
  [switch]$Help
)

$ErrorActionPreference = "Stop"
$WrapperBoundParameters = $PSBoundParameters

function Show-Usage {
  $scriptName = Split-Path -Leaf $PSCommandPath
  @"
Usage:
  .\scripts\$scriptName [-ModelId <id>] [-ModelsConfig <path>] [-ModelPath <path>] [-Host <host>] [-Port <port>] [-CtxSize <tokens>] [-GpuLayers <n|all|auto>] [-MainGpu <index>] [-SplitMode <none|layer|row|tensor>] [-TensorSplit <weights>] [-BatchSize <n>] [-UBatchSize <n>] [-Threads <n>] [-FlashAttention <on|off|auto>] [-CpuOnly] [-ServerPath <path>] [-DryRun]
  .\scripts\$scriptName -Help

Defaults:
  -ModelId       not required; default model path is <project-root>\models\gguf\first_model.gguf
  -ModelsConfig  configs\evaluation_models.json
  -Host          127.0.0.1
  -Port          8080
  -CtxSize       4096
  GPU offload is not forced by this wrapper unless GPU parameters are provided.

Examples:
  .\scripts\$scriptName
  .\scripts\$scriptName -ModelId first_model
  .\scripts\$scriptName -ModelId second_model
  .\scripts\$scriptName -Port 8081
  .\scripts\$scriptName -ModelPath "C:\path\to\model.gguf"
  .\scripts\$scriptName -ServerPath "C:\path\to\llama-server.exe"
  .\scripts\$scriptName -ModelId first_model -DryRun
  .\scripts\$scriptName -ModelId second_model -GpuLayers all -MainGpu 0 -SplitMode none -DryRun
  .\scripts\$scriptName -ModelId second_model -CpuOnly -DryRun

Notes:
  The Python virtual environment is only for Python dependencies.
  It does not add llama-server.exe to PATH.
  GGUF files are local runtime assets and must not be committed.
  If llama-server.exe is not in PATH, this wrapper searches common Windows install/extract locations.
  GPU-related arguments are mapped only to flags observed in the local llama-server --help output.
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

function Quote-CommandPart {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Value
  )

  if ($Value -match '[\s"]') {
    return '"' + ($Value -replace '"', '\"') + '"'
  }
  return $Value
}

function Format-CommandLine {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  $parts = @("&", (Quote-CommandPart -Value $Executable))
  foreach ($arg in $Arguments) {
    $parts += (Quote-CommandPart -Value $arg)
  }
  return ($parts -join " ")
}

function Add-OptionalArgument {
  param(
    [Parameter(Mandatory = $true)]
    [System.Collections.Generic.List[string]]$Arguments,
    [Parameter(Mandatory = $true)]
    [string]$Flag,
    [object]$Value
  )

  if ($null -eq $Value) {
    return
  }
  $stringValue = [string]$Value
  if ([string]::IsNullOrWhiteSpace($stringValue)) {
    return
  }
  $Arguments.Add($Flag)
  $Arguments.Add($stringValue)
}

function Build-LlamaServerArgs {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ModelPathValue,
    [Parameter(Mandatory = $true)]
    [string]$HostValue,
    [Parameter(Mandatory = $true)]
    [int]$PortValue,
    [Parameter(Mandatory = $true)]
    [int]$CtxSizeValue
  )

  if ($CpuOnly -and (
      $WrapperBoundParameters.ContainsKey("GpuLayers") -or
      $WrapperBoundParameters.ContainsKey("MainGpu") -or
      $WrapperBoundParameters.ContainsKey("TensorSplit") -or
      $WrapperBoundParameters.ContainsKey("SplitMode")
    )) {
    throw "-CpuOnly cannot be combined with GPU placement options."
  }

  $argsList = [System.Collections.Generic.List[string]]::new()
  $argsList.Add("-m")
  $argsList.Add($ModelPathValue)
  $argsList.Add("--host")
  $argsList.Add($HostValue)
  # DryRun command still emits: --port $Port
  $argsList.Add("--port")
  $argsList.Add([string]$PortValue)
  $argsList.Add("--ctx-size")
  $argsList.Add([string]$CtxSizeValue)

  if ($CpuOnly) {
    $argsList.Add("--device")
    $argsList.Add("none")
  }

  Add-OptionalArgument -Arguments $argsList -Flag "--n-gpu-layers" -Value $GpuLayers
  if ($WrapperBoundParameters.ContainsKey("MainGpu")) {
    Add-OptionalArgument -Arguments $argsList -Flag "--main-gpu" -Value $MainGpu
  }
  Add-OptionalArgument -Arguments $argsList -Flag "--tensor-split" -Value $TensorSplit
  Add-OptionalArgument -Arguments $argsList -Flag "--split-mode" -Value $SplitMode
  if ($WrapperBoundParameters.ContainsKey("BatchSize")) {
    Add-OptionalArgument -Arguments $argsList -Flag "--batch-size" -Value $BatchSize
  }
  if ($WrapperBoundParameters.ContainsKey("UBatchSize")) {
    Add-OptionalArgument -Arguments $argsList -Flag "--ubatch-size" -Value $UBatchSize
  }
  if ($WrapperBoundParameters.ContainsKey("Threads")) {
    Add-OptionalArgument -Arguments $argsList -Flag "--threads" -Value $Threads
  }
  Add-OptionalArgument -Arguments $argsList -Flag "--flash-attn" -Value $FlashAttention

  return $argsList.ToArray()
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
Write-Host "GPU config:    $(if ($CpuOnly) { 'cpu-only (--device none)' } elseif ($GpuLayers -or $PSBoundParameters.ContainsKey('MainGpu') -or $TensorSplit -or $SplitMode) { 'explicit GPU/runtime flags requested' } else { 'default llama-server behavior; no wrapper GPU flags' })"
if ($GpuLayers) {
  Write-Host "GPU layers:    $GpuLayers"
}
if ($PSBoundParameters.ContainsKey("MainGpu")) {
  Write-Host "Main GPU:      $MainGpu"
}
if ($SplitMode) {
  Write-Host "Split mode:    $SplitMode"
}
if ($TensorSplit) {
  Write-Host "Tensor split:  $TensorSplit"
}
if ($PSBoundParameters.ContainsKey("BatchSize")) {
  Write-Host "Batch size:    $BatchSize"
}
if ($PSBoundParameters.ContainsKey("UBatchSize")) {
  Write-Host "UBatch size:   $UBatchSize"
}
if ($PSBoundParameters.ContainsKey("Threads")) {
  Write-Host "Threads:       $Threads"
}
if ($FlashAttention) {
  Write-Host "Flash attn:    $FlashAttention"
}
Write-Host ""

$CommandArgs = Build-LlamaServerArgs -ModelPathValue $ResolvedModelPath -HostValue $HostAddress -PortValue $Port -CtxSizeValue $CtxSize

if ($DryRun) {
  Write-Host "Dry run: server was not started."
  Write-Host "Command:"
  Write-Host (Format-CommandLine -Executable $ResolvedServerPath -Arguments $CommandArgs)
  exit 0
}

& $ResolvedServerPath @CommandArgs
