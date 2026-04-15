<#
.SYNOPSIS
    DicomPressor Watch Script (Windows PowerShell)

.DESCRIPTION
    Thin wrapper around the Python watch mode for the generic DicomPressor workflow.
    Watches a parent folder for new mergeable DICOM study folders and writes logs to
    the same rotating log file format as the core CLI.
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$WatchDir,

    [int]$IntervalSeconds = 300,

    [string]$OutputDir = "",

    [string]$LogFile = "",

    [string]$ScanStateFile = ""
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Wrapper = Join-Path $ScriptDir "dicompressor.ps1"

if (-not (Test-Path $WatchDir -PathType Container)) {
    Write-Error "Directory not found: $WatchDir"
    exit 1
}

if (-not (Test-Path $Wrapper -PathType Leaf)) {
    Write-Error "dicompressor.ps1 not found at: $Wrapper"
    exit 1
}

if ($OutputDir -ne "" -and -not (Test-Path $OutputDir -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

if ($LogFile -eq "") {
    $LogFile = Join-Path $ScriptDir "dicompressor.log"
}

$logDir = Split-Path -Parent $LogFile
if ($logDir -and -not (Test-Path $logDir -PathType Container)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$effectiveScanState = $ScanStateFile
if ((-not $PSBoundParameters.ContainsKey("ScanStateFile")) -and $PSBoundParameters.ContainsKey("LogFile") -and $LogFile -ne "") {
    $logStem = [System.IO.Path]::GetFileNameWithoutExtension($LogFile)
    $scanStateBaseDir = if ($logDir) { $logDir } else { "." }
    $effectiveScanState = Join-Path $scanStateBaseDir "$logStem.scan-state.json"
}

if ($effectiveScanState -ne "") {
    $scanStateDir = Split-Path -Parent $effectiveScanState
    if ($scanStateDir -and -not (Test-Path $scanStateDir -PathType Container)) {
        New-Item -ItemType Directory -Path $scanStateDir -Force | Out-Null
    }
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " DicomPressor Watch Mode (PowerShell)" -ForegroundColor Cyan
Write-Host " Watching:    $WatchDir" -ForegroundColor Cyan
Write-Host " Interval:    ${IntervalSeconds}s" -ForegroundColor Cyan
if ($OutputDir -ne "") {
    Write-Host " Output dir:  $OutputDir" -ForegroundColor Cyan
}
Write-Host " Log file:    $LogFile" -ForegroundColor Cyan
if ($effectiveScanState -ne "") {
    Write-Host " Scan state:  $effectiveScanState" -ForegroundColor Cyan
}
Write-Host " Press Ctrl+C to stop" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$cmdArgs = @("-j", "--watch", $IntervalSeconds, "--log-file", $LogFile, "-f", $WatchDir)
if ($OutputDir -ne "") {
    $cmdArgs += @("--output-dir", $OutputDir)
}
if ($PSBoundParameters.ContainsKey("ScanStateFile")) {
    $cmdArgs += @("--scan-state-file", $effectiveScanState)
}
elseif ($effectiveScanState -ne "") {
    $cmdArgs += @("--scan-state-file", $effectiveScanState)
}

& $Wrapper @cmdArgs
exit $LASTEXITCODE
