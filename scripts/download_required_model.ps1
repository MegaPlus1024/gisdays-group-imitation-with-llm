<#
.SYNOPSIS
Downloads and verifies the pinned Qwen3.6-27B Q5_K_M model.

.DESCRIPTION
Uses curl.exe with resume support, validates the expected byte count and
SHA-256, and keeps the GGUF in the ignored local model directory.

.PARAMETER Destination
Repository-relative or absolute destination for the GGUF file.

.PARAMETER ForceDownload
Replaces an existing invalid or partial file instead of resuming it.

.PARAMETER SkipHashCheck
Explicitly skips SHA-256 verification. This is not recommended.

.EXAMPLE
.\scripts\download_required_model.ps1

.EXAMPLE
.\scripts\download_required_model.ps1 -ForceDownload

.EXAMPLE
Get-Help .\scripts\download_required_model.ps1 -Detailed
#>
[CmdletBinding()]
param(
  [string]$Destination = "models\gguf\qwen3_6_27b_q5_k_m\Qwen3.6-27B-Q5_K_M.gguf",
  [switch]$ForceDownload,
  [switch]$SkipHashCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$ExpectedBytes = [Int64]19509790944
$ExpectedSha256 = "cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde"
$DownloadUrl = "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/eff7310b099938f3cd9f794b97493201d7c4b11d/Qwen3.6-27B-Q5_K_M.gguf?download=true"
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Resolve-DestinationPath {
  param([Parameter(Mandatory = $true)][string]$Value)

  if ([System.IO.Path]::IsPathRooted($Value)) {
    return [System.IO.Path]::GetFullPath($Value)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Value))
}

function Get-ModelState {
  param([Parameter(Mandatory = $true)][string]$Path)

  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    return $null
  }

  $item = Get-Item -LiteralPath $Path
  $hash = $null
  if (-not $SkipHashCheck -and $item.Length -eq $ExpectedBytes) {
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  }

  return @{
    Bytes = [Int64]$item.Length
    Sha256 = $hash
  }
}

function Write-VerifiedState {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][Int64]$Bytes,
    [string]$Sha256
  )

  Write-Host "Model path: $Path"
  Write-Host "Bytes:      $Bytes"
  if ($SkipHashCheck) {
    Write-Warning "SHA-256 verification was skipped by explicit request. This is unsafe."
  }
  else {
    Write-Host "SHA-256:    $Sha256"
  }
}

$DestinationPath = Resolve-DestinationPath -Value $Destination
$DestinationDirectory = Split-Path -Parent $DestinationPath
$Existing = Get-ModelState -Path $DestinationPath

if ($SkipHashCheck) {
  Write-Warning "-SkipHashCheck disables the model integrity check. Use only when you accept that risk."
}

if ($null -ne $Existing) {
  if ($Existing.Bytes -eq $ExpectedBytes) {
    if ($SkipHashCheck -or $Existing.Sha256 -eq $ExpectedSha256) {
      Write-Host "The required model is already present and satisfies the enabled checks."
      Write-VerifiedState -Path $DestinationPath -Bytes $Existing.Bytes -Sha256 $Existing.Sha256
      exit 0
    }

    if (-not $ForceDownload) {
      throw "Existing file has the expected size but the wrong SHA-256. It was preserved. Use -ForceDownload to replace it."
    }
    Remove-Item -LiteralPath $DestinationPath -Force
  }
  elseif ($Existing.Bytes -gt $ExpectedBytes) {
    if (-not $ForceDownload) {
      throw "Existing file is larger than expected. It was preserved. Use -ForceDownload to replace it."
    }
    Remove-Item -LiteralPath $DestinationPath -Force
  }
  elseif ($ForceDownload) {
    Remove-Item -LiteralPath $DestinationPath -Force
  }
  else {
    Write-Host "Resuming partial download at $($Existing.Bytes) bytes."
  }
}

New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
$Curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
if ($null -eq $Curl) {
  throw "curl.exe was not found. Install or enable curl.exe and retry."
}

Write-Host "Downloading Qwen3.6-27B Q5_K_M from the pinned Hugging Face revision."
& $Curl.Source `
  --location `
  --fail `
  --retry 3 `
  --continue-at - `
  --output $DestinationPath `
  $DownloadUrl
if ($LASTEXITCODE -ne 0) {
  throw "curl.exe failed with exit code $LASTEXITCODE. The partial file was preserved for resume."
}

$Downloaded = Get-Item -LiteralPath $DestinationPath
if ([Int64]$Downloaded.Length -ne $ExpectedBytes) {
  if ($ForceDownload) {
    Remove-Item -LiteralPath $DestinationPath -Force
    throw "Downloaded file size mismatch. The invalid partial file was removed because -ForceDownload was supplied."
  }
  throw "Downloaded file size mismatch: expected $ExpectedBytes, got $($Downloaded.Length). The partial file was preserved."
}

$DownloadedSha256 = $null
if (-not $SkipHashCheck) {
  $DownloadedSha256 = (Get-FileHash -LiteralPath $DestinationPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($DownloadedSha256 -ne $ExpectedSha256) {
    if ($ForceDownload) {
      Remove-Item -LiteralPath $DestinationPath -Force
      throw "Downloaded file SHA-256 mismatch. The invalid file was removed because -ForceDownload was supplied."
    }
    throw "Downloaded file SHA-256 mismatch. The file was preserved; use -ForceDownload to remove and retry."
  }
}

Write-VerifiedState -Path $DestinationPath -Bytes ([Int64]$Downloaded.Length) -Sha256 $DownloadedSha256
Write-Host "The GGUF file remains local and is excluded by .gitignore."
