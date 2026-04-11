<#
.SYNOPSIS
    DicomPressor - Cross-platform DICOM CLI Tool (PowerShell Wrapper)

.DESCRIPTION
    PowerShell wrapper for DicomPressor Python CLI.
    Works on Windows PowerShell and PowerShell Core.
    Passes all arguments to the Python script.

.EXAMPLE
    .\dicompressor.ps1 -j -f "C:\DICOM\Patient1"
    Merges single-frame DICOM files into multi-frame

.EXAMPLE
    .\dicompressor.ps1 -x -f "C:\DICOM\Patient1"
    Compresses DICOM files with JPEG lossless

.EXAMPLE
    .\dicompressor.ps1 --summary -f "C:\DICOM\Patient1"
    Shows folder summary
#>

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

# Find Python
$pythonCmd = $null
$pythonCandidates = @("python3", "python", "py")

foreach ($candidate in $pythonCandidates) {
    try {
        $version = & $candidate --version 2>&1
        if ($version -match "Python 3") {
            $pythonCmd = $candidate
            break
        }
    } catch {
        continue
    }
}

if (-not $pythonCmd) {
    Write-Host "ERROR: Python 3 is required but not found in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3 from https://python.org" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "On Windows: winget install Python.Python.3.12" -ForegroundColor Cyan
    Write-Host "On macOS:   brew install python3" -ForegroundColor Cyan
    exit 1
}

# Check for pydicom
$pydicomCheck = & $pythonCmd -c "import pydicom" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing required packages..." -ForegroundColor Yellow
    & $pythonCmd -m pip install pydicom numpy Pillow --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install required packages." -ForegroundColor Red
        Write-Host "Please run: $pythonCmd -m pip install pydicom numpy Pillow" -ForegroundColor Yellow
        exit 1
    }
}

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "dicompressor.py"

if (-not (Test-Path $pythonScript)) {
    Write-Host "ERROR: Cannot find dicompressor.py in $scriptDir" -ForegroundColor Red
    exit 1
}

# Run the Python script with all arguments
if ($Arguments) {
    & $pythonCmd $pythonScript @Arguments
} else {
    & $pythonCmd $pythonScript
}

exit $LASTEXITCODE
