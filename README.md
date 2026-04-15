# DicomPressor

Cross-platform DICOM CLI tool for the generic workflow: merge, split, compress, anonymize, export, and more.

Use this version for machines that already export many single-frame `.dcm` slices into folders. If the machine exports `DCM_FILE.CT` archives, use the separate Vatech workflow instead:

- GitHub: `https://github.com/nsitnov/dicompressor-vatech`
- Local docs: `README-vatech.md`

## Requirements

- Python 3.8+
- pydicom
- numpy
- Pillow

## Quick Install

```bash
pip install pydicom numpy Pillow
```

If you downloaded the ZIP package, unzip it first and run the commands from that folder.

## Usage

### macOS / Linux / WSL

```bash
./dicompressor.sh [action] [options] -f /path/to/folder_or_file

# or directly
python3 dicompressor.py [action] [options] -f /path/to/folder_or_file
```

### Windows PowerShell

Recommended for most Windows users: install the requirements once, then run Python directly.

```powershell
python -m pip install -r .\requirements.txt
python .\dicompressor.py [action] [options] -f "C:\path\to\folder"
```

If `python` is missing, use:

```powershell
py -3 -m pip install -r .\requirements.txt
py -3 .\dicompressor.py [action] [options] -f "C:\path\to\folder"
```

## Recommended Generic Watch Mode

If new patient studies appear under one parent folder and each study has its own subfolder:

```powershell
python .\dicompressor.py -j --watch 300 --output-dir "D:\Merged" -f "D:\DICOM\Patients"
```

That command:

- scans recursively every 300 seconds
- starts processing matching study folders as soon as they are found during the scan
- writes `.dicompressor_done` after each successful folder
- copies merged outputs to `D:\Merged`
- writes a rotating log file named `dicompressor.log` next to the script by default

### Optional Custom Log File

```powershell
python .\dicompressor.py -j --watch 300 --log-file "D:\DICOM\Logs\dicompressor.log" --output-dir "D:\Merged" -f "D:\DICOM\Patients"
```

### Optional Windows Auto-Start Service Installer

If you want the generic watcher to start automatically with Windows and run hidden in the background, use the interactive NSSM installer:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Unblock-File .\dicompressor-install-service.ps1
.\dicompressor-install-service.ps1
```

The installer prompts for:

- `nssm.exe` path
- `python.exe` path
- source/watch directory
- output directory
- log file path
- watch interval in seconds
- service name and display name

It creates a Windows service that runs at startup, restarts automatically if it exits, and keeps the watcher hidden from normal users.

### Optional Windows PowerShell Wrapper

If you want to use the wrapper script instead of calling Python directly:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Unblock-File .\dicompressor.ps1
.\dicompressor.ps1 -j -F "C:\path\to\patient_folder"
```

The direct `python .\dicompressor.py ...` command is still the safest Windows option when troubleshooting.

## Core Switches

| Switch | Description |
|--------|-------------|
| `-h` | Display help |
| `-c` | Display version info |
| `-f PATH` | Working folder/file, include subfolders |
| `-F PATH` | Working folder/file, do not include subfolders |
| `-a PARAMS` / `-A PARAMS` | Anonymize DICOM files |
| `-m PARAMS` / `-M PARAMS` | Modify DICOM tags |
| `-w` / `-W` | Convert images to DICOM |
| `-v` | Convert video to DICOM |
| `-i TYPE` / `-I TYPE` | Export DICOM to images |
| `-e` / `-E` | Export DICOM to video |
| `-d` / `-D` | Create DICOMDIR |
| `-j` | Merge single-frame DICOM to multi-frame |
| `-s` | Split multi-frame to single-frame |
| `-p` / `-P` | Convert NEMA2 to DICOM 3 |
| `-n` / `-N` | Convert DICOM 3 to NEMA2 |
| `-l` / `-L` | Convert Big Endian to Little Endian |
| `-b` / `-B` | Convert Little Endian to Big Endian |
| `-x` / `-X` | JPEG lossless compression |
| `-z` / `-Z` | JPEG lossy compression |
| `-u` / `-U` | Decompress to uncompressed |
| `-t` | Export headers to text |
| `--info` | Display DICOM file info |
| `--summary` | Display folder summary |
| `--skip-if-done` | Skip folders that already contain `.dicompressor_done` |
| `--watch N` | Re-scan every `N` seconds and process only new folders |
| `--output-dir DIR` | Copy merged outputs to `DIR` |
| `--log-file FILE` | Write a rotating log file to `FILE` |
| `--scan-state-file FILE` | Persistent per-folder mtime cache used by `--watch` to skip folders whose contents haven't changed. Pass an empty string to disable. |
| `--verbose` | Debug logging |
| `--quiet` | Warnings/errors only |

Lowercase usually saves with a suffix. Uppercase usually overwrites the original.

## Examples

```bash
# Merge one folder
python3 dicompressor.py -j -F /path/to/patient_folder

# Merge recursively
python3 dicompressor.py -j -f /path/to/patients

# Skip if already processed
python3 dicompressor.py -j --skip-if-done -f /path/to/patients

# Watch mode
python3 dicompressor.py -j --watch 300 -f /path/to/patients

# Watch + output dir
python3 dicompressor.py -j --watch 300 --output-dir /data/merged -f /data/patients

# Custom log file
python3 dicompressor.py -j --watch 300 --log-file /data/logs/dicompressor.log -f /data/patients

# JPEG lossless compression
python3 dicompressor.py -x -f /path/to/folder

# Export DICOM to PNG
python3 dicompressor.py -I png -f /path/to/folder

# Folder summary
python3 dicompressor.py --summary -f /path/to/folder

# Anonymize using parameter file
python3 dicompressor.py -a params.txt -f /path/to/folder
```

## Watch Scripts

### Linux / macOS / WSL

```bash
./dicompressor-watch.sh /path/to/patients 300 /data/merged /data/logs/dicompressor.log
```

### Windows PowerShell

```powershell
.\dicompressor-watch.ps1 -WatchDir "D:\DICOM\Patients" -IntervalSeconds 300 -OutputDir "D:\Merged" -LogFile "D:\DICOM\Logs\dicompressor.log" -ScanStateFile "D:\DICOM\Logs\dicompressor.scan-state.json"
```

Both watch scripts are thin wrappers around the Python watch mode. They use the same marker logic, the same rotating log file support, the same streaming scan behavior, and the same incremental `--scan-state-file` cache as the main CLI.

If you pass a custom log path but omit a scan-state path, the watch wrappers automatically place the cache next to the log as `<log-stem>.scan-state.json`. If you want the built-in default instead, call `python .\dicompressor.py ...` directly and omit `--scan-state-file`.

## Watch Behavior

The current generic watch loop is serial but streaming:

- it scans recursively
- it starts processing a folder as soon as it is found
- it writes `.dicompressor_done` only after a successful merge
- it skips done-marked folders before deep re-inspection on later passes
- it writes scan progress to the console and the rotating log file
- after each pass, it sleeps only for the remaining part of the interval
- if a pass takes longer than the interval, the next pass starts immediately

This means there is no overlapping second scan while the first one is still running. New folders are not lost; they are simply picked up during the current pass or the next one.

## Output Filenames

Merged output names come from the DICOM metadata, usually `PatientName + SeriesNumber`.

Examples:

```text
Stamenov_Enco_series31_multiframe.dcm
Sitnov_Nedelcho_series31_multiframe.dcm
```

If `--output-dir` already contains the same filename, DicomPressor keeps both files by adding `_1`, `_2`, and so on instead of overwriting the existing file.

## Common Windows Problems

### PowerShell says scripts are disabled

Error example:

```text
File ... cannot be loaded because running scripts is disabled on this system.
```

Fix:

- use the direct Python command instead of the `.ps1` wrapper
- or allow scripts only for the current terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

If you want to use the interactive Windows service installer, run the same command first and then start:

```powershell
Unblock-File .\dicompressor-install-service.ps1
.\dicompressor-install-service.ps1
```

### `python` is not recognized

Try:

```powershell
py -3 -m pip install -r .\requirements.txt
py -3 .\dicompressor.py -j --watch 300 --output-dir "D:\Merged" -f "D:\DICOM\Patients"
```

If neither `python` nor `py` exists, install Python 3 and make sure it is added to `PATH`.

### `Expected implicit VR, but found explicit VR`

This message is usually a warning from `pydicom`, not a fatal error. In most cases the files are still read correctly and the merge continues.

### Nothing appears immediately in the output folder

The watch logic now starts processing folders during the scan instead of waiting for a full candidate list first.

If the output folder is still empty:

- check the console for lines like `Found processable folder`, `[OK]`, or `[FAILED]`
- open the log file `dicompressor.log` in the script folder, or your custom `--log-file` path
- remember that the first pass can still take time on very large historical archives

### Help text looks broken in an older Windows console

The CLI now falls back to plain ASCII banners and separators when the console code page cannot print box-drawing Unicode characters.

## Marker File

After a successful merge with `--skip-if-done` or `--watch`, the script writes:

```text
.dicompressor_done
```

Delete that marker if you need to force a re-run for the same folder.

## Parameter File Formats

### Anonymization (`params.txt`)

```text
# Rectangles: [type] [left] [top] [right] [bottom]
# r=both, ri=single-frame, rv=multi-frame
r 10 10 20 20
ri 150 150 250 350

# Tags: [group] [element] [VR] [Value]
0010 0010 PN ANONYMIZED
0010 0020
```

### Tag Modification (`modify_params.txt`)

```text
# [action] [group] [element] [VR] [Value]
# i=insert, m=modify, r=remove
m 0010 0010 PN ANONYMIZED
r 0010 0020
i 0011 0030 FD 3.14159
```
