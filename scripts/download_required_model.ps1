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

.PARAMETER MaxRateLimitWaitSeconds
Maximum cumulative time spent waiting after HTTP 429 responses.

.PARAMETER DefaultRateLimitDelaySeconds
Delay used when an HTTP 429 response has no usable reset header.

.EXAMPLE
.\scripts\download_required_model.ps1

.EXAMPLE
.\scripts\download_required_model.ps1 -ForceDownload

.EXAMPLE
Get-Help .\scripts\download_required_model.ps1 -Detailed
#>
[CmdletBinding()]
param(
  [string]$Destination = "models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf",
  [switch]$ForceDownload,
  [switch]$SkipHashCheck,
  [ValidateRange(0, 86400)]
  [int]$MaxRateLimitWaitSeconds = 900,
  [ValidateRange(1, 3600)]
  [int]$DefaultRateLimitDelaySeconds = 60
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$ExpectedBytes = [Int64]19509790944
$ExpectedSha256 = "cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde"
$DownloadUrl = "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/eff7310b099938f3cd9f794b97493201d7c4b11d/Qwen3.6-27B-Q5_K_M.gguf?download=true"
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$DefaultDestination = "models\gguf\sixth_model\Qwen3.6-27B-Q5_K_M.gguf"
$LegacyDestination = "models\gguf\qwen3_6_27b_q5_k_m\Qwen3.6-27B-Q5_K_M.gguf"

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

function Get-LastHttpStatusCode {
  param(
    [string[]]$WriteOut,
    [Parameter(Mandatory = $true)][string]$HeaderPath
  )

  $writeOutLines = @($WriteOut)
  for ($index = $writeOutLines.Count - 1; $index -ge 0; $index--) {
    $candidate = ([string]$writeOutLines[$index]).Trim()
    if ($candidate -match "^\d{3}$") {
      return $candidate
    }
  }

  if (Test-Path -LiteralPath $HeaderPath -PathType Leaf) {
    $headerText = Get-Content -LiteralPath $HeaderPath -Raw
    $matches = [regex]::Matches(
      $headerText,
      "(?im)^HTTP/\S+\s+(\d{3})\b"
    )
    if ($matches.Count -gt 0) {
      return $matches[$matches.Count - 1].Groups[1].Value
    }
  }

  return $null
}

function Get-RateLimitDelaySeconds {
  param(
    [Parameter(Mandatory = $true)][string]$HeaderPath,
    [Parameter(Mandatory = $true)][int]$FallbackSeconds
  )

  if (-not (Test-Path -LiteralPath $HeaderPath -PathType Leaf)) {
    return $FallbackSeconds
  }

  $headerLines = @(Get-Content -LiteralPath $HeaderPath)
  $retryAfterValues = @(
    $headerLines |
    ForEach-Object {
      if ($_ -match "^\s*Retry-After\s*:\s*(.+?)\s*$") {
        $Matches[1]
      }
    }
  )

  if ($retryAfterValues.Count -gt 0) {
    $retryAfter = [string]$retryAfterValues[-1]
    $seconds = 0
    if (
      [int]::TryParse(
        $retryAfter,
        [ref]$seconds
      )
    ) {
      return [Math]::Max(1, $seconds)
    }

    $retryDate = [DateTimeOffset]::MinValue
    if (
      [DateTimeOffset]::TryParse(
        $retryAfter,
        [ref]$retryDate
      )
    ) {
      $delay = [int][Math]::Ceiling(
        ($retryDate.ToUniversalTime() - [DateTimeOffset]::UtcNow).TotalSeconds
      )
      return [Math]::Max(1, $delay)
    }
  }

  $resetValues = @(
    $headerLines |
    ForEach-Object {
      if (
        $_ -match (
          "^\s*(?:" +
          "(?:X-)?RateLimit-Reset|" +
          "RateLimit" +
          ")\s*:\s*(.+?)\s*$"
        )
      ) {
        $Matches[1]
      }
    }
  )

  if ($resetValues.Count -gt 0) {
    $resetValue = [string]$resetValues[-1]
    $resetSeconds = 0
    $resetEpochOrDelay = [Int64]0
    if ($resetValue -match "(?:^|[;,\s])t=(\d+)") {
      $resetSeconds = [int]$Matches[1]
      return [Math]::Max(1, $resetSeconds)
    }
    if (
      [Int64]::TryParse(
        $resetValue.Trim(),
        [ref]$resetEpochOrDelay
      )
    ) {
      if ($resetEpochOrDelay -gt 1000000000) {
        $resetAt = [DateTimeOffset]::FromUnixTimeSeconds($resetEpochOrDelay)
        $delay = [int][Math]::Ceiling(
          ($resetAt - [DateTimeOffset]::UtcNow).TotalSeconds
        )
        return [Math]::Max(1, $delay)
      }
      return [Math]::Max(1, [int]$resetEpochOrDelay)
    }
  }

  return $FallbackSeconds
}

$DestinationPath = Resolve-DestinationPath -Value $Destination
$DefaultDestinationPath = Resolve-DestinationPath -Value $DefaultDestination
$LegacyDestinationPath = Resolve-DestinationPath -Value $LegacyDestination
$DestinationDirectory = Split-Path -Parent $DestinationPath

if ($SkipHashCheck) {
  Write-Warning "-SkipHashCheck disables the model integrity check. Use only when you accept that risk."
}

if ($DestinationPath -eq $DefaultDestinationPath -and
    -not (Test-Path -LiteralPath $DestinationPath) -and
    (Test-Path -LiteralPath $LegacyDestinationPath -PathType Leaf)) {
  $LegacyItem = Get-Item -LiteralPath $LegacyDestinationPath
  if ([Int64]$LegacyItem.Length -eq $ExpectedBytes) {
    Write-Host "Verifying the model at the legacy path before migration."
    $LegacySha256 = (Get-FileHash -LiteralPath $LegacyDestinationPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($LegacySha256 -eq $ExpectedSha256) {
      New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
      Move-Item -LiteralPath $LegacyDestinationPath -Destination $DestinationPath
      Write-Host "Moved the verified model from the legacy path to models\gguf\sixth_model."
    }
    else {
      Write-Warning "The legacy model has the wrong SHA-256 and was preserved. A verified copy will be downloaded to the new path."
    }
  }
  else {
    Write-Warning "The legacy model has the wrong size and was preserved. A verified copy will be downloaded to the new path."
  }
}

$Existing = Get-ModelState -Path $DestinationPath

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
$TemporaryPrefix = "gisdays-model-download-$([Guid]::NewGuid().ToString('N'))"
$HeaderPath = Join-Path ([System.IO.Path]::GetTempPath()) "$TemporaryPrefix.headers"
$CurlConfigPath = $null
$Token = [string]$env:HF_TOKEN
$TotalRateLimitWaitSeconds = 0

try {
  if (-not [string]::IsNullOrWhiteSpace($Token)) {
    if ($Token -match "[\r\n""\\]") {
      throw "HF_TOKEN contains unsupported characters."
    }
    $CurlConfigPath = Join-Path (
      [System.IO.Path]::GetTempPath()
    ) "$TemporaryPrefix.curlrc"
    [System.IO.File]::WriteAllText(
      $CurlConfigPath,
      "header = `"Authorization: Bearer $Token`"`r`n",
      (New-Object System.Text.UTF8Encoding($false))
    )
    Write-Host "Using HF_TOKEN from the environment."
  }

  while ($true) {
    Remove-Item -LiteralPath $HeaderPath -Force -ErrorAction SilentlyContinue
    $CurlArguments = @(
      "--location",
      "--fail",
      "--silent",
      "--show-error",
      "--continue-at", "-",
      "--dump-header", $HeaderPath,
      "--output", $DestinationPath,
      "--write-out", "%{http_code}"
    )
    if ($null -ne $CurlConfigPath) {
      $CurlArguments += @("--config", $CurlConfigPath)
    }
    $CurlArguments += $DownloadUrl

    $WriteOut = @(& $Curl.Source @CurlArguments)
    $CurlExitCode = $LASTEXITCODE
    $HttpStatusCode = Get-LastHttpStatusCode `
      -WriteOut $WriteOut `
      -HeaderPath $HeaderPath

    if ($CurlExitCode -eq 0) {
      break
    }

    if ($HttpStatusCode -ne "429") {
      throw "curl.exe failed with exit code $CurlExitCode (HTTP $HttpStatusCode). The partial file was preserved for resume."
    }

    $RemainingWaitSeconds = (
      $MaxRateLimitWaitSeconds -
      $TotalRateLimitWaitSeconds
    )
    if ($RemainingWaitSeconds -le 0) {
      throw "HTTP 429 persisted until the rate-limit wait budget was exhausted. The partial file was preserved for resume."
    }

    $RequestedDelaySeconds = Get-RateLimitDelaySeconds `
      -HeaderPath $HeaderPath `
      -FallbackSeconds $DefaultRateLimitDelaySeconds
    $WaitSeconds = [Math]::Min(
      $RequestedDelaySeconds,
      $RemainingWaitSeconds
    )
    Write-Warning (
      "HTTP 429 from Hugging Face. Waiting " +
      $WaitSeconds +
      " seconds before resuming. The partial file is preserved."
    )
    Start-Sleep -Seconds $WaitSeconds
    $TotalRateLimitWaitSeconds += $WaitSeconds
  }
}
finally {
  Remove-Item -LiteralPath $HeaderPath -Force -ErrorAction SilentlyContinue
  if ($null -ne $CurlConfigPath) {
    Remove-Item `
      -LiteralPath $CurlConfigPath `
      -Force `
      -ErrorAction SilentlyContinue
  }
  $Token = $null
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
