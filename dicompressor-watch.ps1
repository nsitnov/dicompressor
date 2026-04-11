<#
.SYNOPSIS
    DicomPressor Watch Script (Windows PowerShell)

.DESCRIPTION
    Watches a parent folder containing patient subfolders.
    Every INTERVAL seconds, scans for new (unprocessed) subfolders
    and automatically merges their DICOM files into multi-frame.

.PARAMETER WatchDir
    Path to the parent folder containing patient subfolders.

.PARAMETER IntervalSeconds
    How often to scan (default: 300 = 5 minutes).

.EXAMPLE
    .\dicompressor-watch.ps1 -WatchDir "D:\DICOM\Patients"
    .\dicompressor-watch.ps1 -WatchDir "D:\DICOM\Patients" -IntervalSeconds 60

.NOTES
    Folder structure:
      D:\DICOM\Patients\
        patient_001\        <- contains 400 single-frame .dcm files
        patient_002\        <- new patient, will be auto-merged
        patient_003\        <- already has .dicompressor_done, skipped

    Creates .dicompressor_done marker in each folder after processing.
    Delete the marker to re-process a folder.
    Press Ctrl+C to stop.
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$WatchDir,

    [int]$IntervalSeconds = 300
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dicompressor = Join-Path $ScriptDir "dicompressor.py"
$Marker = ".dicompressor_done"

# Validate
if (-not (Test-Path $WatchDir -PathType Container)) {
    Write-Error "Directory not found: $WatchDir"
    exit 1
}

if (-not (Test-Path $Dicompressor -PathType Leaf)) {
    Write-Error "dicompressor.py not found at: $Dicompressor"
    exit 1
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " DicomPressor Watch Mode (PowerShell)" -ForegroundColor Cyan
Write-Host " Watching: $WatchDir" -ForegroundColor Cyan
Write-Host " Interval: ${IntervalSeconds}s" -ForegroundColor Cyan
Write-Host " Marker:   $Marker" -ForegroundColor Cyan
Write-Host " Press Ctrl+C to stop" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Main loop
while ($true) {
    $NewCount = 0
    $DoneCount = 0
    $EmptyCount = 0

    $subdirs = Get-ChildItem -Path $WatchDir -Directory

    foreach ($dir in $subdirs) {
        $markerPath = Join-Path $dir.FullName $Marker

        # Already processed?
        if (Test-Path $markerPath) {
            $DoneCount++
            continue
        }

        # Has DICOM files?
        $dcmFiles = Get-ChildItem -Path $dir.FullName -Filter "*.dcm" -File
        if ($dcmFiles.Count -eq 0) {
            $EmptyCount++
            continue
        }

        # New folder -- process it
        $NewCount++
        $timestamp = Get-Date -Format "HH:mm:ss"
        Write-Host ""
        Write-Host "[$timestamp] NEW: $($dir.Name) ($($dcmFiles.Count) files)" -ForegroundColor Green

        try {
            $output = & python $Dicompressor -j --skip-if-done -f $dir.FullName 2>&1
            $output | ForEach-Object { Write-Host "  $_" }
            Write-Host "  Done!" -ForegroundColor Green
        }
        catch {
            Write-Host "  FAILED: $_" -ForegroundColor Red
        }
    }

    $Total = $NewCount + $DoneCount + $EmptyCount
    $timestamp = Get-Date -Format "HH:mm:ss"

    if ($NewCount -eq 0) {
        Write-Host "`r[$timestamp] $Total folders ($DoneCount done, $EmptyCount empty). Next scan in ${IntervalSeconds}s..." -NoNewline
    }
    else {
        Write-Host ""
        Write-Host "[$timestamp] Processed $NewCount new folder(s). Total: $Total ($DoneCount done)" -ForegroundColor Yellow
    }

    Start-Sleep -Seconds $IntervalSeconds
}
