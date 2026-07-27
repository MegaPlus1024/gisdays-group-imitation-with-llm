<#
.SYNOPSIS
Classifies generated evidence roots and optionally removes them.

.DESCRIPTION
Verifies the final archive name, SHA-256, and member list before inspecting
the configured generated roots. The default mode is dry-run. Nothing is
removed unless -Apply is supplied.

.PARAMETER FinalArchivePath
Path to the verified final evidence archive outside the repository.

.PARAMETER Apply
Removes only roots that pass archive, Git, path, and reparse-point checks.

.EXAMPLE
.\scripts\cleanup_generated_files.ps1 `
  -FinalArchivePath "..\behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz"

.EXAMPLE
Get-Help .\scripts\cleanup_generated_files.ps1 -Detailed
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$FinalArchivePath,
  [switch]$Apply
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$ExpectedArchiveSha256 = "4025b5c8af79335d1cb5ef8c553ccf7f533b11a610872800a179d15a2cfefdb7"
$ExpectedArchiveName = "behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz"
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RepoPrefix = $RepoRoot.TrimEnd("\") + "\"

$CleanupRoots = @(
  @{
    Path = "artifacts/challenger_qwen3_6_27b_q5_k_m"
    TemporaryEntries = @(
      "artifacts/challenger_qwen3_6_27b_q5_k_m/config_dry_run_audit/"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/v207_pilot_01/"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/endpoint_inspection.txt"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/gpu_pilot_snapshot.txt"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/runner_help.txt"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/server_full_cohort_stderr.log"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/server_full_cohort_stdout.log"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/server_pilot_startup.log"
      "artifacts/challenger_qwen3_6_27b_q5_k_m/v207_pilot_01_group_trace.jsonl"
    )
  }
  @{
    Path = "artifacts/descriptive_gpu_resource_profiles"
    TemporaryEntries = @(
      "artifacts/descriptive_gpu_resource_profiles/post_hoc_challenger_comparison/"
    )
  }
)

function Convert-ToRepoPath {
  param([Parameter(Mandatory = $true)][string]$Path)
  return $Path.Replace("\", "/").TrimStart("./")
}

function Test-TemporaryEntry {
  param(
    [Parameter(Mandatory = $true)][string]$RelativePath,
    [Parameter(Mandatory = $true)][object[]]$Entries
  )

  foreach ($entry in $Entries) {
    if ($entry.EndsWith("/")) {
      if ($RelativePath.StartsWith($entry, [System.StringComparison]::Ordinal)) {
        return $true
      }
    }
    elseif ($RelativePath -eq $entry) {
      return $true
    }
  }
  return $false
}

function Test-ArchivedDirectory {
  param(
    [Parameter(Mandatory = $true)][string]$RelativePath,
    [Parameter(Mandatory = $true)][hashtable]$ArchiveMembers
  )

  $prefix = $RelativePath.TrimEnd("/") + "/"
  foreach ($member in $ArchiveMembers.Keys) {
    if ($member.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
      return $true
    }
  }
  return $false
}

function Assert-UntrackedRoot {
  param([Parameter(Mandatory = $true)][string]$RelativeRoot)

  $tracked = @(& git -C $RepoRoot ls-files -- "$RelativeRoot/**")
  if ($LASTEXITCODE -ne 0) {
    throw "git ls-files failed for $RelativeRoot"
  }
  if ($tracked.Count -gt 0) {
    throw "Cleanup root contains tracked files: $RelativeRoot"
  }
}

function Assert-SafeTree {
  param(
    [Parameter(Mandatory = $true)][string]$RelativeRoot,
    [Parameter(Mandatory = $true)][hashtable]$ArchiveMembers,
    [Parameter(Mandatory = $true)][object[]]$TemporaryEntries
  )

  $FullRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $RelativeRoot))
  if (-not $FullRoot.StartsWith($RepoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Cleanup root escapes the repository: $RelativeRoot"
  }
  if (-not (Test-Path -LiteralPath $FullRoot)) {
    return
  }

  Assert-UntrackedRoot -RelativeRoot $RelativeRoot
  $ReparsePoints = @(Get-ChildItem -LiteralPath $FullRoot -Force -Recurse |
    Where-Object { ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 })
  if ($ReparsePoints.Count -gt 0) {
    throw "Cleanup root contains a symlink or junction: $RelativeRoot"
  }

  foreach ($file in Get-ChildItem -LiteralPath $FullRoot -Force -Recurse -File) {
    $relative = Convert-ToRepoPath -Path $file.FullName.Substring($RepoPrefix.Length)
    if (-not $ArchiveMembers.ContainsKey($relative) -and
        -not (Test-TemporaryEntry -RelativePath $relative -Entries $TemporaryEntries)) {
      throw "Unknown cleanup file is neither archived nor explicitly temporary: $relative"
    }
  }
  foreach ($directory in Get-ChildItem -LiteralPath $FullRoot -Force -Recurse -Directory) {
    $relative = Convert-ToRepoPath -Path $directory.FullName.Substring($RepoPrefix.Length)
    if (-not (Test-ArchivedDirectory -RelativePath $relative -ArchiveMembers $ArchiveMembers) -and
        -not (Test-TemporaryEntry -RelativePath ($relative + "/") -Entries $TemporaryEntries)) {
      throw "Unknown cleanup directory is neither archived nor explicitly temporary: $relative"
    }
  }
}

$ArchiveFullPath = [System.IO.Path]::GetFullPath($FinalArchivePath)
if (-not (Test-Path -LiteralPath $ArchiveFullPath -PathType Leaf)) {
  throw "Final archive not found: $ArchiveFullPath"
}
if ((Split-Path -Leaf $ArchiveFullPath) -ne $ExpectedArchiveName) {
  throw "Unexpected final archive name: $(Split-Path -Leaf $ArchiveFullPath)"
}
$ArchiveHash = (Get-FileHash -LiteralPath $ArchiveFullPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ArchiveHash -ne $ExpectedArchiveSha256) {
  throw "Final archive SHA-256 mismatch. Cleanup was not attempted."
}

$Tar = Get-Command "tar.exe" -ErrorAction SilentlyContinue
if ($null -eq $Tar) {
  $Tar = Get-Command "tar" -ErrorAction SilentlyContinue
}
if ($null -eq $Tar) {
  throw "tar was not found; archive membership cannot be verified."
}
$ArchiveMemberLines = @(& $Tar.Source -tzf $ArchiveFullPath)
if ($LASTEXITCODE -ne 0 -or $ArchiveMemberLines.Count -eq 0) {
  throw "Final archive could not be read."
}
$ArchiveMembers = @{}
foreach ($member in $ArchiveMemberLines) {
  $normalized = Convert-ToRepoPath -Path $member
  if (-not $normalized.EndsWith("/")) {
    $ArchiveMembers[$normalized] = $true
  }
}

$ExistingRoots = @()
foreach ($spec in $CleanupRoots) {
  Assert-SafeTree `
    -RelativeRoot $spec.Path `
    -ArchiveMembers $ArchiveMembers `
    -TemporaryEntries $spec.TemporaryEntries
  $fullPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $spec.Path))
  if (Test-Path -LiteralPath $fullPath) {
    $ExistingRoots += @{
      RelativePath = $spec.Path
      FullPath = $fullPath
    }
  }
}

Write-Host "Final archive verified: $ArchiveFullPath"
Write-Host "SHA-256: $ArchiveHash"
Write-Host "Mode: $(if ($Apply) { 'apply' } else { 'dry-run' })"
if ($ExistingRoots.Count -eq 0) {
  Write-Host "No classified generated roots are present."
}
else {
  Write-Host "Classified generated roots:"
  foreach ($root in $ExistingRoots) {
    Write-Host "  $($root.RelativePath)"
  }
}

if ($Apply) {
  $RemovalFailures = @()
  foreach ($root in $ExistingRoots) {
    try {
      Remove-Item -LiteralPath $root.FullPath -Recurse -Force
      Write-Host "Removed: $($root.RelativePath)"
    }
    catch {
      $RemovalFailures += "$($root.RelativePath): $($_.Exception.Message)"
      Write-Warning "Could not remove: $($root.RelativePath)"
    }
  }
  if ($RemovalFailures.Count -gt 0) {
    throw "Cleanup completed with removal failures: $($RemovalFailures -join '; ')"
  }
}
else {
  Write-Host "Dry-run only. Re-run with -Apply to remove the listed roots."
}

Write-Host "Git status:"
& git -C $RepoRoot status --short
if ($LASTEXITCODE -ne 0) {
  throw "git status failed."
}
