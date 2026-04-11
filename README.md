# DicomPressor

Cross-platform DICOM CLI tool - full analogue of Sante Dicommander.
Works on **macOS**, **Windows (PowerShell)**, and **WSL/Linux**.

## Requirements

- Python 3.8+
- pydicom, numpy, Pillow (auto-installed by wrapper scripts)

## Quick Install

```bash
pip install pydicom numpy Pillow
```

## Usage

### macOS / Linux / WSL
```bash
./dicompressor.sh [action] [options] -f <folder_or_file>
# or directly:
python3 dicompressor.py [action] [options] -f <folder_or_file>
```

### Windows PowerShell
```powershell
.\dicompressor.ps1 [action] [options] -f "C:\path\to\folder"
# or directly:
python dicompressor.py [action] [options] -f "C:\path\to\folder"
```

## Switches

| Switch | Description |
|--------|-------------|
| `-h` | Display help |
| `-c` | Display version info |
| `-f PATH` | Working folder/file (include subfolders) |
| `-F PATH` | Working folder/file (subfolders ignored) |
| `-a PARAMS` | Anonymize DICOM files (save with suffix) |
| `-A PARAMS` | Anonymize DICOM files (overwrite original) |
| `-m PARAMS` | Modify DICOM tags (save with suffix) |
| `-M PARAMS` | Modify DICOM tags (overwrite original) |
| `-w` | Convert plain images to DICOM |
| `-W` | Convert images to single multi-frame DICOM |
| `-v` | Convert video files to DICOM |
| `-i TYPE` | Export DICOM to images with annotations |
| `-I TYPE` | Export DICOM to images without annotations |
| `-e` | Export DICOM to video with annotations |
| `-E` | Export DICOM to video without annotations |
| `-d` | Create DICOMDIR in selected folder |
| `-D` | Create DICOMDIR in parent folder |
| `-j` | Merge single-frame to multi-frame DICOM |
| `-s` | Split multi-frame to single-frame |
| `-p` / `-P` | Convert NEMA2 to DICOM 3 Part 10 |
| `-n` / `-N` | Convert DICOM 3 Part 10 to NEMA2 |
| `-l` / `-L` | Convert Big Endian to Little Endian |
| `-b` / `-B` | Convert Little Endian to Big Endian |
| `-x` / `-X` | JPEG lossless compression |
| `-z` / `-Z` | JPEG lossy compression |
| `-u` / `-U` | Decompress to uncompressed |
| `-t` | Export headers to text files |
| `--info` | Display DICOM file info |
| `--summary` | Display folder summary |
| `--skip-if-done` | Skip if .dicompressor_done marker exists; create after success |
| `--watch N` | Watch mode: re-scan every N seconds, process new subfolders |

Lowercase = save with suffix, Uppercase = overwrite original.

## Examples

```bash
# Merge 400 single-frame CT files into one multi-frame DICOM:
python3 dicompressor.py -j -f /path/to/patient_folder

# Merge, but skip if already processed (safe for cron/scheduler):
python3 dicompressor.py -j --skip-if-done -f /path/to/patient_folder

# Watch a folder with patient subfolders, auto-merge every 5 minutes:
python3 dicompressor.py -j --watch 300 -f /path/to/patients/

# Compress with JPEG lossless (85% size reduction):
python3 dicompressor.py -x -f /path/to/folder

# Export DICOM to PNG images:
python3 dicompressor.py -I png -f /path/to/folder

# Get folder summary:
python3 dicompressor.py --summary -f /path/to/folder

# Anonymize using parameter file:
python3 dicompressor.py -a params.txt -f /path/to/folder

# Modify DICOM tags:
python3 dicompressor.py -m modify_params.txt -f /path/to/folder
```

## Watch Scripts

For production use, standalone watch scripts are included:

### Linux / macOS / WSL
```bash
./dicompressor-watch.sh /path/to/patients [interval_seconds]
# Default interval: 300 seconds (5 minutes)
```

### Windows PowerShell
```powershell
.\dicompressor-watch.ps1 -WatchDir "D:\DICOM\Patients" -IntervalSeconds 300
```

Both scripts monitor a parent folder with patient subfolders, automatically merge new DICOM files, and skip already-processed folders using the `.dicompressor_done` marker file.

## Parameter File Formats

### Anonymization (params.txt)
```
# Rectangles: [type] [left] [top] [right] [bottom]
# r=both, ri=single-frame, rv=multi-frame
r 10 10 20 20
ri 150 150 250 350

# Tags: [group] [element] [VR] [Value]
0010 0010 PN ANONYMIZED
0010 0020
```

### Tag Modification (modify_params.txt)
```
# [action] [group] [element] [VR] [Value]
# i=insert, m=modify, r=remove
m 0010 0010 PN ANONYMIZED
r 0010 0020
i 0011 0030 FD 3.14159
```
