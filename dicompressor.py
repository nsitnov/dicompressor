#!/usr/bin/env python3
"""
DicomPressor - Cross-platform DICOM CLI tool
Analogous to Sante Dicommander
Works on: macOS, Windows (PowerShell), WSL/Linux

Usage: python dicompressor.py [action] [options] -f/-F <folder_or_file>

Actions match Sante Dicommander switches where applicable.
"""

import argparse
import builtins
import json
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

try:
    import pydicom
except ImportError:
    print("ERROR: pydicom is required. Install with: pip install pydicom")
    sys.exit(1)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dicom_utils import (
    # Anonymize
    anonymize_folder, anonymize_file,
    # Modify tags
    modify_folder, modify_file,
    # Image/Video conversion
    images_to_dicom_folder, image_to_dicom,
    videos_to_dicom_folder, video_to_dicom,
    # Export
    export_images_folder, dicom_to_images,
    export_video_folder, dicom_to_video,
    # DICOMDIR
    create_dicomdir,
    # Merge/Split
    merge_files_to_multiframe, merge_to_multiframe, split_multiframe, split_multiframe_folder,
    # NEMA2 conversion
    convert_nema2_folder, nema2_to_dicom3, dicom3_to_nema2,
    # Endian
    convert_endian_folder,
    # Compression
    compress_folder, decompress_folder,
    compress_dicom, decompress_dicom,
    # Header export
    export_headers_folder, export_header,
    # Info
    get_dicom_info, get_folder_summary,
    # Utilities
    find_dicom_files, is_dicom_file,
)

VERSION = "1.0.3"
PROGRAM_NAME = "DicomPressor"
DONE_MARKER = ".dicompressor_done"
DEFAULT_LOG_FILENAME = "dicompressor.log"
DEFAULT_SCAN_STATE_FILENAME = "dicompressor-scan-state.json"
SCAN_STATE_VERSION = 1
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
SCAN_PROGRESS_EVERY_FOLDERS = 250
SCAN_PROGRESS_EVERY_SECONDS = 15.0

logger = logging.getLogger("dicompressor")


def console_print(*args, **kwargs) -> None:
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        file = kwargs.get("file", sys.stdout)
        flush = kwargs.get("flush", False)
        text = sep.join("" if arg is None else str(arg) for arg in args) + end
        encoding = getattr(file, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        builtins.print(safe_text, end="", file=file, flush=flush)


print = console_print


def default_log_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_LOG_FILENAME)


def default_scan_state_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_SCAN_STATE_FILENAME)


def supports_unicode_output(stream=None) -> bool:
    stream = stream or sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        "╔═║╝".encode(encoding)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def configure_logging(verbose: bool, quiet: bool, log_file: str = "") -> str:
    console_level = logging.INFO
    if verbose:
        console_level = logging.DEBUG
    elif quiet:
        console_level = logging.WARNING

    effective_log_file = os.path.abspath(log_file) if log_file else default_log_path()
    log_dir = os.path.dirname(effective_log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.DEBUG)

    console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = RotatingFileHandler(
        effective_log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    logging.captureWarnings(True)
    logger.debug(
        "Logging configured: console=%s file=%s",
        logging.getLevelName(console_level),
        effective_log_file,
    )
    return effective_log_file


def marker_path(folder: str) -> str:
    return os.path.join(folder, DONE_MARKER)

def is_already_done(folder: str) -> bool:
    """Check if a folder has already been processed (marker file exists)."""
    return os.path.isfile(marker_path(folder))

def mark_as_done(folder: str, action: str, results: list):
    """Create a marker file after successful processing."""
    info = {
        "processed_at": datetime.now().isoformat(),
        "action": action,
        "results": [os.path.basename(r) if isinstance(r, str) else str(r) for r in results],
        "dicompressor_version": VERSION,
    }
    with open(marker_path(folder), "w", encoding="utf-8") as handle:
        json.dump(info, handle, indent=2)
    logger.info("Marked as done: %s", marker_path(folder))


# ---------------------------------------------------------------------------
# Persistent per-folder scan state.
#
# Caches os.stat(folder).st_mtime_ns so subsequent watch passes can skip
# folders whose direct-child list hasn't changed since they were last
# scanned. This avoids re-opening thousands of DICOM headers every cycle on
# large trees that only change near the edges.
# ---------------------------------------------------------------------------


def empty_scan_state(root: str = "") -> Dict[str, object]:
    return {
        "version": SCAN_STATE_VERSION,
        "root": os.path.abspath(root) if root else "",
        "folders": {},
    }


def load_scan_state(path: str, root: str) -> Dict[str, object]:
    if not path:
        return empty_scan_state(root)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        logger.info("Scan state file not found, starting fresh: %s", path)
        return empty_scan_state(root)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Scan state file %s is unreadable (%s); starting fresh",
            path,
            exc,
        )
        return empty_scan_state(root)

    if not isinstance(data, dict) or data.get("version") != SCAN_STATE_VERSION:
        logger.warning(
            "Scan state file %s has unexpected format; starting fresh",
            path,
        )
        return empty_scan_state(root)

    folders = data.get("folders")
    if not isinstance(folders, dict):
        folders = {}
    data["folders"] = folders

    cached_root = data.get("root") or ""
    if root and cached_root and os.path.abspath(cached_root) != os.path.abspath(root):
        logger.warning(
            "Scan state file %s is for root %s but current root is %s; starting fresh",
            path,
            cached_root,
            root,
        )
        return empty_scan_state(root)
    data["root"] = os.path.abspath(root) if root else cached_root

    logger.info(
        "Loaded scan state from %s: %d folder entries",
        path,
        len(folders),
    )
    return data


def save_scan_state(path: str, state: Dict[str, object]) -> None:
    if not path:
        return
    try:
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning("Failed to save scan state to %s: %s", path, exc)


def get_folder_state(state: Optional[Dict[str, object]], folder: str) -> Optional[Dict[str, object]]:
    if not state:
        return None
    folders = state.get("folders")
    if not isinstance(folders, dict):
        return None
    entry = folders.get(os.path.abspath(folder))
    if isinstance(entry, dict):
        return entry
    return None


def update_folder_state(
    state: Optional[Dict[str, object]],
    folder: str,
    mtime_ns: Optional[int],
    *,
    empty: Optional[bool] = None,
    done: Optional[bool] = None,
) -> None:
    if not state:
        return
    folders = state.setdefault("folders", {})
    key = os.path.abspath(folder)
    entry = folders.get(key)
    if not isinstance(entry, dict):
        entry = {}
    if mtime_ns is not None:
        entry["mtime_ns"] = mtime_ns
    if empty is not None:
        entry["empty"] = bool(empty)
    if done is not None:
        entry["done"] = bool(done)
    folders[key] = entry


def folder_cache_is_fresh(
    state: Optional[Dict[str, object]],
    folder: str,
    current_mtime_ns: Optional[int],
) -> Tuple[bool, Optional[Dict[str, object]]]:
    entry = get_folder_state(state, folder)
    if entry is None or current_mtime_ns is None:
        return False, entry
    cached_mtime = entry.get("mtime_ns")
    if not isinstance(cached_mtime, int):
        return False, entry
    return cached_mtime == current_mtime_ns, entry


def _safe_dir_mtime_ns(path: str) -> Optional[int]:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def copy_to_output_dir(result_files: list, output_dir: str):
    """Copy result files to the specified output directory."""
    import shutil

    os.makedirs(output_dir, exist_ok=True)
    for src in result_files:
        if isinstance(src, str) and os.path.isfile(src):
            dst = os.path.join(output_dir, os.path.basename(src))
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            if os.path.exists(dst):
                stem, ext = os.path.splitext(os.path.basename(src))
                counter = 1
                while True:
                    candidate = os.path.join(output_dir, f"{stem}_{counter}{ext}")
                    if not os.path.exists(candidate):
                        dst = candidate
                        break
                    counter += 1
            shutil.copy2(src, dst)
            size_mb = os.path.getsize(dst) / 1024 / 1024
            logger.info("Copied to output: %s (%.1f MB)", dst, size_mb)


def print_banner():
    """Print program banner."""
    if supports_unicode_output():
        print(f"""
╔══════════════════════════════════════════════════════╗
║  {PROGRAM_NAME} v{VERSION:<31}║
║  Cross-platform DICOM CLI Tool                       ║
║  Compatible with: macOS, Windows, WSL/Linux          ║
╚══════════════════════════════════════════════════════╝
""")
        return

    print(f"""
+------------------------------------------------------+
|  {PROGRAM_NAME} v{VERSION:<31}|
|  Cross-platform DICOM CLI Tool                       |
|  Compatible with: macOS, Windows, WSL/Linux          |
+------------------------------------------------------+
""")


def print_help_detailed():
    """Print detailed help matching Sante Dicommander switch reference."""
    print_banner()
    rule = "===============================================" if not supports_unicode_output() else "═══════════════════════════════════════════════"
    rule_short = "=========" if not supports_unicode_output() else "═════════"
    print(f"""
SWITCHES (compatible with Sante Dicommander):
{rule}

  -h            Display this help text
  -c            Display version and copyright information
  -f PATH       Specify working folder (include subfolders) or file
  -F PATH       Specify working folder (subfolders ignored) or file

  --- Anonymize ---
  -a PARAMS     Anonymize DICOM files, save with different name (suffix)
  -A PARAMS     Anonymize DICOM files, overwrite original

  --- Modify Tags ---
  -m PARAMS     Modify DICOM tags, save with different name (suffix)
  -M PARAMS     Modify DICOM tags, overwrite original

  --- Convert Images to DICOM ---
  -w            Convert plain images to DICOM (one file per image)
  -W            Convert plain images to single multi-frame DICOM

  --- Convert Videos to DICOM ---
  -v            Convert video files to compressed DICOM

  --- Export to Images ---
  -i TYPE       Export DICOM to images with annotations (jpeg/png/bmp/tiff)
  -I TYPE       Export DICOM to images without annotations

  --- Export to Video ---
  -e            Export multi-frame DICOM to video with annotations
  -E            Export multi-frame DICOM to video without annotations

  --- DICOMDIR ---
  -d            Create DICOMDIR in selected folder
  -D            Create DICOMDIR in parent folder

  --- Merge / Split ---
  -j            Merge single-frame DICOM files to multi-frame
  -s            Split multi-frame DICOM files to single-frame

  --- Format Conversion ---
  -p            Convert NEMA2 to DICOM 3 Part 10 (save with suffix)
  -P            Convert NEMA2 to DICOM 3 Part 10 (overwrite)
  -n            Convert DICOM 3 Part 10 to NEMA2 (save with suffix)
  -N            Convert DICOM 3 Part 10 to NEMA2 (overwrite)

  --- Endian Conversion ---
  -l            Convert Big Endian to Little Endian (save with suffix)
  -L            Convert Big Endian to Little Endian (overwrite)
  -b            Convert Little Endian to Big Endian (save with suffix)
  -B            Convert Little Endian to Big Endian (overwrite)

  --- Compression ---
  -x            Compress to JPEG lossless (save with suffix)
  -X            Compress to JPEG lossless (overwrite)
  -z            Compress to JPEG lossy (save with suffix)
  -Z            Compress to JPEG lossy (overwrite)
  -u            Decompress to uncompressed (save with suffix)
  -U            Decompress to uncompressed (overwrite)

  --- Header Export ---
  -t            Export DICOM headers to text files

  --- Info ---
  --info        Display info about DICOM file(s) in folder
  --summary     Display folder summary

  --- Scheduler / Watch ---
  --skip-if-done  Skip if .dicompressor_done marker exists in folder.
                  Creates the marker after successful processing.
  --watch N       Watch mode: re-scan recursively every N seconds,
                  process mergeable folders as soon as they are found.
                  Implies --skip-if-done. Ctrl+C to stop.
  --output-dir D  Copy merged result files to directory D.
                  Works with -j, --skip-if-done, and --watch.
                  Directory is created automatically if it doesn't exist.
  --log-file FILE Write a rotating log file. Default:
                  {default_log_path()}
  --scan-state-file FILE
                  Persistent per-folder mtime cache used by --watch.
                  Default: {default_scan_state_path()}
                  Pass an empty string to disable the cache.

EXAMPLES:
{rule_short}

  # Merge 400 single-frame CT files into one multi-frame DICOM:
  python dicompressor.py -j -f /path/to/patient_folder

  # Merge, but skip if already done (safe to run repeatedly):
  python dicompressor.py -j --skip-if-done -f /path/to/patient_folder

  # Watch a folder with patient subfolders, auto-merge every 5 min:
  python dicompressor.py -j --watch 300 -f /path/to/patients/

  # Watch + copy merged files to a central output folder:
  python dicompressor.py -j --watch 300 --output-dir /data/merged -f /data/patients/

  # Windows watch example:
  python dicompressor.py -j --watch 300 --output-dir "D:\\Merged" -f "D:\\DICOM\\Patients"

  # Custom log file:
  python dicompressor.py -j --watch 300 --log-file /data/logs/dicompressor.log -f /data/patients

  # Custom scan-state file:
  python dicompressor.py -j --watch 300 --log-file /data/logs/dicompressor.log \
    --scan-state-file /data/logs/dicompressor.scan-state.json -f /data/patients

  # Compress all DICOM files with JPEG lossless:
  python dicompressor.py -x -f /path/to/folder

  # Anonymize files using parameter file:
  python dicompressor.py -a params.txt -f /path/to/folder

  # Export DICOM to PNG images:
  python dicompressor.py -I png -f /path/to/folder

  # Modify DICOM tags:
  python dicompressor.py -m modify_params.txt -f /path/to/folder

  # Get folder summary:
  python dicompressor.py --summary -f /path/to/folder
""")


def parse_num_frames(dataset) -> int:
    num_frames = getattr(dataset, "NumberOfFrames", 1)
    if isinstance(num_frames, str):
        try:
            num_frames = int(num_frames)
        except ValueError:
            num_frames = 1
    return int(num_frames)


def _list_folder_files(folder: str) -> List[str]:
    """Return sorted basenames of regular files directly in ``folder`` using os.scandir."""
    names: List[str] = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        names.append(entry.name)
                except OSError:
                    continue
    except OSError as exc:
        logger.warning("Cannot list folder %s: %s", folder, exc)
        return []
    names.sort()
    return names


def find_mergeable_dicom_files(
    folder: str,
    scan_state: Optional[Dict[str, object]] = None,
    folder_mtime_ns: Optional[int] = None,
) -> List[str]:
    # Skip the expensive pydicom parse when mtime matches the cached value
    # and last time we recorded this folder as empty. Saves one dcmread per
    # file per pass on large unchanged trees.
    is_fresh, entry = folder_cache_is_fresh(scan_state, folder, folder_mtime_ns)
    if is_fresh and entry is not None and entry.get("empty"):
        return []

    results: List[str] = []
    for name in _list_folder_files(folder):
        path = os.path.join(folder, name)
        if not is_dicom_file(path):
            continue
        try:
            dataset = pydicom.dcmread(path, stop_before_pixels=True)
        except Exception:
            continue
        if parse_num_frames(dataset) <= 1:
            results.append(path)
    return results


def iter_scan_roots(
    root: str,
    recursive: bool,
    prune_done: bool = False,
) -> Iterator[Tuple[int, str, Optional[int]]]:
    """Yield (scanned_count, folder_path, folder_mtime_ns).

    Uses an explicit os.scandir-based DFS rather than os.walk, which cuts
    the per-directory syscall count roughly in half.
    """
    root = os.path.abspath(root)

    if not recursive:
        yield 1, root, _safe_dir_mtime_ns(root)
        return

    logger.info("Starting recursive scan under %s", root)
    scanned_count = 0
    scan_started = time.time()
    last_progress_time = scan_started

    stack: List[Tuple[str, Optional[int]]] = [(root, _safe_dir_mtime_ns(root))]

    while stack:
        current_root, current_mtime_ns = stack.pop()

        scanned_count += 1
        yield scanned_count, current_root, current_mtime_ns

        now = time.time()
        if (
            scanned_count % SCAN_PROGRESS_EVERY_FOLDERS == 0
            or now - last_progress_time >= SCAN_PROGRESS_EVERY_SECONDS
        ):
            logger.info(
                "Scan progress: scanned %d folder(s). Current=%s",
                scanned_count,
                current_root,
            )
            last_progress_time = now

        if prune_done and is_already_done(current_root):
            logger.debug("Pruning already processed subtree: %s", current_root)
            continue

        children: List[Tuple[str, Optional[int]]] = []
        try:
            with os.scandir(current_root) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    try:
                        child_mtime = entry.stat(follow_symlinks=False).st_mtime_ns
                    except OSError:
                        child_mtime = None
                    children.append((entry.path, child_mtime))
        except OSError as exc:
            logger.warning("Cannot scan %s: %s", current_root, exc)
            continue

        children.sort(key=lambda item: item[0])
        for child in reversed(children):
            stack.append(child)

    logger.info(
        "Finished recursive scan under %s: scanned %d folder(s) in %.1fs",
        root,
        scanned_count,
        time.time() - scan_started,
    )


def process_merge_folder(
    folder: str,
    output_dir: str = "",
    dicom_files: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    folder = os.path.abspath(folder)
    if dicom_files is None:
        dicom_files = find_mergeable_dicom_files(folder)
    else:
        dicom_files = list(dicom_files)

    if not dicom_files:
        raise ValueError(f"No mergeable single-frame DICOM files found in {folder}")

    logger.info("Processing folder: %s (single-frame inputs=%d)", folder, len(dicom_files))
    results = merge_files_to_multiframe(list(dicom_files), folder, raise_on_error=True)
    if not results:
        raise ValueError(f"No multi-frame output was created for {folder}")

    if output_dir:
        copy_to_output_dir(results, output_dir)

    return {
        "folder": folder,
        "results": results,
        "direct_dicom_count": len(dicom_files),
    }


def print_folder_report(report: Dict[str, object], target_root: str) -> None:
    folder = os.path.abspath(str(report["folder"]))
    root = os.path.abspath(target_root)
    try:
        display_folder = os.path.relpath(folder, root)
    except ValueError:
        display_folder = folder
    if display_folder == ".":
        display_folder = os.path.basename(folder) or folder

    print(f"\n[OK] {display_folder}")
    print(f"  Single-frame inputs: {report['direct_dicom_count']}")
    for result in report["results"]:
        size_mb = os.path.getsize(result) / 1024 / 1024
        print(f"  -> {os.path.basename(result)} ({size_mb:.1f} MB)")


def print_failed_folder(folder: str, exc: Exception) -> None:
    print(f"\n[FAILED] {folder}")
    print(f"  {exc}")


def run_merge_once(
    target_path: str,
    include_subfolders: bool,
    skip_if_done: bool,
    output_dir: str = "",
) -> int:
    if skip_if_done and is_already_done(target_path):
        print(f"SKIPPED (already processed): {target_path}")
        print(f"  Marker: {marker_path(target_path)}")
        print("  Delete the marker file to re-process.")
        logger.info("Skipping already processed folder: %s", target_path)
        return 0

    results = merge_to_multiframe(
        target_path,
        include_subfolders,
        raise_on_error=skip_if_done,
    )
    print(f"Created {len(results)} multi-frame file(s)")
    for result in results:
        size_mb = os.path.getsize(result) / 1024 / 1024
        print(f"  -> {result} ({size_mb:.1f} MB)")
    if output_dir:
        copy_to_output_dir(results, output_dir)
    if skip_if_done and results:
        mark_as_done(target_path, "merge", results)
    logger.info(
        "Merge summary for %s: output_files=%d include_subfolders=%s",
        target_path,
        len(results),
        include_subfolders,
    )
    return 0


def run_merge_watch(
    target_path: str,
    recursive: bool,
    interval: int,
    output_dir: str = "",
    scan_state: Optional[Dict[str, object]] = None,
    scan_state_path: str = "",
) -> int:
    print(f"Watch mode: scanning every {interval}s (Ctrl+C to stop)", flush=True)
    if scan_state is not None:
        folders = scan_state.get("folders") or {}
        cached_done = sum(1 for e in folders.values() if isinstance(e, dict) and e.get("done"))
        cached_empty = sum(1 for e in folders.values() if isinstance(e, dict) and e.get("empty"))
        logger.info(
            "Scan state loaded: %d folders cached (%d done, %d empty)",
            len(folders),
            cached_done,
            cached_empty,
        )
    pass_number = 0
    try:
        while True:
            pass_number += 1
            pass_started = time.time()
            logger.info("Starting watch scan pass #%d under %s", pass_number, target_path)
            new_count = 0
            skipped_done = 0
            skipped_unchanged = 0
            failed_count = 0
            discovered_count = 0

            for scanned_count, folder, folder_mtime_ns in iter_scan_roots(
                target_path, recursive, prune_done=True
            ):
                if is_already_done(folder):
                    skipped_done += 1
                    update_folder_state(scan_state, folder, folder_mtime_ns, done=True)
                    logger.debug("Skipping already processed folder: %s", folder)
                    continue

                is_fresh, entry = folder_cache_is_fresh(scan_state, folder, folder_mtime_ns)
                if is_fresh and entry is not None and entry.get("empty"):
                    skipped_unchanged += 1
                    continue

                dicom_files = find_mergeable_dicom_files(
                    folder, scan_state=scan_state, folder_mtime_ns=folder_mtime_ns
                )
                if not dicom_files:
                    update_folder_state(scan_state, folder, folder_mtime_ns, empty=True)
                    continue

                discovered_count += 1
                logger.info(
                    "Found processable folder #%d after scanning %d folder(s): %s "
                    "(single-frame inputs=%d)",
                    discovered_count,
                    scanned_count,
                    folder,
                    len(dicom_files),
                )

                try:
                    report = process_merge_folder(
                        folder,
                        output_dir=output_dir,
                        dicom_files=dicom_files,
                    )
                    print_folder_report(report, target_path)
                    mark_as_done(folder, "merge", report["results"])
                    update_folder_state(
                        scan_state,
                        folder,
                        _safe_dir_mtime_ns(folder),
                        done=True,
                    )
                    save_scan_state(scan_state_path, scan_state or {})
                    new_count += 1
                except Exception as exc:
                    failed_count += 1
                    logger.error("Failed to process %s: %s", folder, exc)
                    print_failed_folder(folder, exc)

            pass_elapsed = time.time() - pass_started
            logger.info(
                "Completed watch scan pass #%d: discovered=%d new=%d skipped_done=%d "
                "skipped_unchanged=%d failed=%d elapsed=%.1fs",
                pass_number,
                discovered_count,
                new_count,
                skipped_done,
                skipped_unchanged,
                failed_count,
                pass_elapsed,
            )
            save_scan_state(scan_state_path, scan_state or {})

            sleep_seconds = max(0.0, interval - pass_elapsed)
            if new_count == 0 and failed_count == 0:
                if sleep_seconds > 0:
                    print(
                        f"[{time.strftime('%H:%M:%S')}] No new folders. "
                        f"Waiting {int(round(sleep_seconds))}s...",
                    )
                else:
                    print(
                        f"[{time.strftime('%H:%M:%S')}] No new folders. "
                        "Starting the next scan immediately.",
                    )
            else:
                print(
                    f"[{time.strftime('%H:%M:%S')}] Pass #{pass_number}: processed {new_count} "
                    f"new folder(s), skipped {skipped_done}, failed {failed_count}."
                )

            if sleep_seconds > 0:
                logger.info(
                    "Waiting %.1fs before watch scan pass #%d",
                    sleep_seconds,
                    pass_number + 1,
                )
                time.sleep(sleep_seconds)
            else:
                logger.info(
                    "Scan pass #%d took %.1fs which exceeded interval %ss; "
                    "starting the next pass immediately",
                    pass_number,
                    pass_elapsed,
                    interval,
                )
    except KeyboardInterrupt:
        print("\nWatch mode stopped.")
        logger.info("Watch mode stopped by user")
        return 0


def main():
    parser = argparse.ArgumentParser(
        prog='dicompressor',
        description=f'{PROGRAM_NAME} v{VERSION} - Cross-platform DICOM CLI Tool',
        add_help=False
    )

    # Path specification
    path_group = parser.add_mutually_exclusive_group()
    path_group.add_argument('-f', dest='path_with_sub', metavar='PATH',
                           help='Working folder/file (include subfolders)')
    path_group.add_argument('-F', dest='path_no_sub', metavar='PATH',
                           help='Working folder/file (subfolders ignored)')

    # Help and info
    parser.add_argument('-h', dest='show_help', action='store_true',
                       help='Display help text')
    parser.add_argument('-c', dest='show_version', action='store_true',
                       help='Display version info')

    # Anonymize
    parser.add_argument('-a', dest='anon_suffix', metavar='PARAMS',
                       help='Anonymize (save with suffix)')
    parser.add_argument('-A', dest='anon_overwrite', metavar='PARAMS',
                       help='Anonymize (overwrite)')

    # Modify
    parser.add_argument('-m', dest='modify_suffix', metavar='PARAMS',
                       help='Modify tags (save with suffix)')
    parser.add_argument('-M', dest='modify_overwrite', metavar='PARAMS',
                       help='Modify tags (overwrite)')

    # Image to DICOM
    parser.add_argument('-w', dest='img_to_dcm', action='store_true',
                       help='Convert images to DICOM (one per image)')
    parser.add_argument('-W', dest='img_to_dcm_multi', action='store_true',
                       help='Convert images to single multi-frame DICOM')

    # Video to DICOM
    parser.add_argument('-v', dest='vid_to_dcm', action='store_true',
                       help='Convert videos to DICOM')

    # Export images
    parser.add_argument('-i', dest='export_img_annot', metavar='TYPE',
                       help='Export DICOM to images with annotations')
    parser.add_argument('-I', dest='export_img_clean', metavar='TYPE',
                       help='Export DICOM to images without annotations')

    # Export video
    parser.add_argument('-e', dest='export_vid_annot', action='store_true',
                       help='Export DICOM to video with annotations')
    parser.add_argument('-E', dest='export_vid_clean', action='store_true',
                       help='Export DICOM to video without annotations')

    # DICOMDIR
    parser.add_argument('-d', dest='dicomdir_here', action='store_true',
                       help='Create DICOMDIR in folder')
    parser.add_argument('-D', dest='dicomdir_parent', action='store_true',
                       help='Create DICOMDIR in parent folder')

    # Merge / Split
    parser.add_argument('-j', dest='merge', action='store_true',
                       help='Merge single-frame to multi-frame')
    parser.add_argument('-s', dest='split', action='store_true',
                       help='Split multi-frame to single-frame')

    # NEMA2 conversion
    parser.add_argument('-p', dest='nema2_to_dcm3', action='store_true',
                       help='Convert NEMA2 to DICOM3 (suffix)')
    parser.add_argument('-P', dest='nema2_to_dcm3_ow', action='store_true',
                       help='Convert NEMA2 to DICOM3 (overwrite)')
    parser.add_argument('-n', dest='dcm3_to_nema2', action='store_true',
                       help='Convert DICOM3 to NEMA2 (suffix)')
    parser.add_argument('-N', dest='dcm3_to_nema2_ow', action='store_true',
                       help='Convert DICOM3 to NEMA2 (overwrite)')

    # Endian
    parser.add_argument('-l', dest='be_to_le', action='store_true',
                       help='Big Endian to Little Endian (suffix)')
    parser.add_argument('-L', dest='be_to_le_ow', action='store_true',
                       help='Big Endian to Little Endian (overwrite)')
    parser.add_argument('-b', dest='le_to_be', action='store_true',
                       help='Little Endian to Big Endian (suffix)')
    parser.add_argument('-B', dest='le_to_be_ow', action='store_true',
                       help='Little Endian to Big Endian (overwrite)')

    # Compression
    parser.add_argument('-x', dest='comp_lossless', action='store_true',
                       help='JPEG lossless compression (suffix)')
    parser.add_argument('-X', dest='comp_lossless_ow', action='store_true',
                       help='JPEG lossless compression (overwrite)')
    parser.add_argument('-z', dest='comp_lossy', action='store_true',
                       help='JPEG lossy compression (suffix)')
    parser.add_argument('-Z', dest='comp_lossy_ow', action='store_true',
                       help='JPEG lossy compression (overwrite)')
    parser.add_argument('-u', dest='decomp', action='store_true',
                       help='Decompress (suffix)')
    parser.add_argument('-U', dest='decomp_ow', action='store_true',
                       help='Decompress (overwrite)')

    # Header export
    parser.add_argument('-t', dest='export_header', action='store_true',
                       help='Export headers to text')

    # Extended options
    parser.add_argument('--info', dest='info', action='store_true',
                       help='Display DICOM file info')
    parser.add_argument('--summary', dest='summary', action='store_true',
                       help='Display folder summary')
    parser.add_argument('--verbose', dest='verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('--quiet', dest='quiet', action='store_true',
                       help='Suppress output')

    # Scheduler/watch support
    parser.add_argument('--skip-if-done', dest='skip_if_done', action='store_true',
                       help='Skip processing if .dicompressor_done marker exists in the folder. '
                            'Creates the marker after successful processing. '
                            'Useful for scheduled/cron jobs that re-scan the same folders.')
    parser.add_argument('--watch', dest='watch_interval', metavar='SECONDS', type=int,
                       help='Watch mode: re-scan folder every N seconds and process new subfolders. '
                            'Implies --skip-if-done. Press Ctrl+C to stop.')
    parser.add_argument('--output-dir', dest='output_dir', metavar='DIR',
                       help='Copy merged/processed result files to this directory. '
                            'Works with -j (merge), --skip-if-done, and --watch. '
                            'The directory is created automatically if it does not exist.')
    parser.add_argument('--log-file', dest='log_file', metavar='FILE',
                       help=f'Write logs to FILE (default: {default_log_path()})')
    parser.add_argument('--scan-state-file', dest='scan_state_file', metavar='FILE',
                       help='Persistent per-folder mtime cache used by --watch to skip '
                            'folders whose contents have not changed since the last pass. '
                            f'Default: {default_scan_state_path()}. '
                            'Pass an empty string to disable the cache.')

    args = parser.parse_args()

    # Help
    if args.show_help or len(sys.argv) == 1:
        print_help_detailed()
        return 0

    # Version
    if args.show_version:
        print(f"{PROGRAM_NAME} version {VERSION}")
        print(f"Copyright (c) 2026, DicomPressor")
        print(f"Cross-platform DICOM CLI Tool")
        print(f"Python {sys.version}")
        return 0

    # Determine path and subfolder inclusion
    if args.path_with_sub:
        target_path = os.path.abspath(args.path_with_sub)
        include_subfolders = True
    elif args.path_no_sub:
        target_path = os.path.abspath(args.path_no_sub)
        include_subfolders = False
    else:
        print("ERROR: You must specify a path with -f or -F")
        return 1

    if not os.path.exists(target_path):
        print(f"ERROR: Path does not exist: {target_path}")
        return 1

    is_file = os.path.isfile(target_path)
    is_folder = os.path.isdir(target_path)

    log_file = configure_logging(args.verbose, args.quiet, args.log_file or "")
    print(f"Log file: {log_file}", flush=True)
    logger.info("Starting %s v%s", PROGRAM_NAME, VERSION)
    logger.info("Log file: %s", log_file)

    start_time = time.time()
    exit_code = 0

    try:
        # ==========================================
        # ANONYMIZE
        # ==========================================
        if args.anon_suffix or args.anon_overwrite:
            param_file = args.anon_suffix or args.anon_overwrite
            overwrite = args.anon_overwrite is not None

            if not os.path.isfile(param_file):
                print(f"ERROR: Parameter file not found: {param_file}")
                return 1

            if is_folder:
                results = anonymize_folder(target_path, param_file, include_subfolders, overwrite)
                print(f"Anonymized {len(results)} file(s)")
            elif is_file:
                out = anonymize_file(target_path, param_file, overwrite)
                print(f"Anonymized: {out}")

        # ==========================================
        # MODIFY TAGS
        # ==========================================
        elif args.modify_suffix or args.modify_overwrite:
            param_file = args.modify_suffix or args.modify_overwrite
            overwrite = args.modify_overwrite is not None

            if not os.path.isfile(param_file):
                print(f"ERROR: Parameter file not found: {param_file}")
                return 1

            if is_folder:
                results = modify_folder(target_path, param_file, include_subfolders, overwrite)
                print(f"Modified {len(results)} file(s)")
            elif is_file:
                out = modify_file(target_path, param_file, overwrite)
                print(f"Modified: {out}")

        # ==========================================
        # CONVERT IMAGES TO DICOM
        # ==========================================
        elif args.img_to_dcm:
            if is_folder:
                results = images_to_dicom_folder(target_path, include_subfolders, False)
                print(f"Converted {len(results)} image(s) to DICOM")
            elif is_file:
                out = image_to_dicom(target_path)
                print(f"Converted: {out}")

        elif args.img_to_dcm_multi:
            if is_folder:
                results = images_to_dicom_folder(target_path, include_subfolders, True)
                print(f"Created {len(results)} multi-frame DICOM file(s)")

        # ==========================================
        # CONVERT VIDEOS TO DICOM
        # ==========================================
        elif args.vid_to_dcm:
            if is_folder:
                results = videos_to_dicom_folder(target_path, include_subfolders)
                print(f"Converted {len(results)} video(s) to DICOM")
            elif is_file:
                out = video_to_dicom(target_path)
                print(f"Converted: {out}")

        # ==========================================
        # EXPORT TO IMAGES
        # ==========================================
        elif args.export_img_annot:
            img_type = args.export_img_annot
            if is_folder:
                results = export_images_folder(target_path, img_type, include_subfolders, True)
                print(f"Exported {len(results)} image(s) with annotations")
            elif is_file:
                results = dicom_to_images(target_path, img_type, True)
                print(f"Exported {len(results)} image(s)")

        elif args.export_img_clean:
            img_type = args.export_img_clean
            if is_folder:
                results = export_images_folder(target_path, img_type, include_subfolders, False)
                print(f"Exported {len(results)} image(s)")
            elif is_file:
                results = dicom_to_images(target_path, img_type, False)
                print(f"Exported {len(results)} image(s)")

        # ==========================================
        # EXPORT TO VIDEO
        # ==========================================
        elif args.export_vid_annot:
            if is_folder:
                results = export_video_folder(target_path, include_subfolders, True)
                print(f"Exported {len(results)} video(s) with annotations")
            elif is_file:
                out = dicom_to_video(target_path, True)
                print(f"Exported: {out}")

        elif args.export_vid_clean:
            if is_folder:
                results = export_video_folder(target_path, include_subfolders, False)
                print(f"Exported {len(results)} video(s)")
            elif is_file:
                out = dicom_to_video(target_path, False)
                print(f"Exported: {out}")

        # ==========================================
        # DICOMDIR
        # ==========================================
        elif args.dicomdir_here:
            out = create_dicomdir(target_path, include_subfolders, False)
            print(f"Created DICOMDIR: {out}")

        elif args.dicomdir_parent:
            out = create_dicomdir(target_path, include_subfolders, True)
            print(f"Created DICOMDIR: {out}")

        # ==========================================
        # MERGE
        # ==========================================
        elif args.merge:
            if is_folder:
                out_dir = ""
                if args.output_dir:
                    out_dir = os.path.abspath(args.output_dir)
                    os.makedirs(out_dir, exist_ok=True)
                    print(f"Output directory: {out_dir}")

                if args.watch_interval:
                    args.skip_if_done = True
                    if args.scan_state_file is None:
                        scan_state_path = default_scan_state_path()
                    else:
                        scan_state_path = (
                            os.path.abspath(args.scan_state_file)
                            if args.scan_state_file
                            else ""
                        )
                    scan_state = (
                        load_scan_state(scan_state_path, target_path)
                        if scan_state_path
                        else None
                    )
                    if scan_state_path:
                        print(f"Scan state file: {scan_state_path}", flush=True)
                        logger.info("Scan state file: %s", scan_state_path)
                    else:
                        logger.info("Scan state cache disabled")
                    exit_code = run_merge_watch(
                        target_path=target_path,
                        recursive=include_subfolders,
                        interval=args.watch_interval,
                        output_dir=out_dir,
                        scan_state=scan_state,
                        scan_state_path=scan_state_path,
                    )
                else:
                    exit_code = run_merge_once(
                        target_path=target_path,
                        include_subfolders=include_subfolders,
                        skip_if_done=args.skip_if_done,
                        output_dir=out_dir,
                    )
            else:
                print("ERROR: -j (merge) requires a folder path")
                return 1

        # ==========================================
        # SPLIT
        # ==========================================
        elif args.split:
            if is_folder:
                results = split_multiframe_folder(target_path, include_subfolders)
                print(f"Split into {len(results)} single-frame file(s)")
            elif is_file:
                results = split_multiframe(target_path)
                print(f"Split into {len(results)} single-frame file(s)")

        # ==========================================
        # NEMA2 CONVERSION
        # ==========================================
        elif args.nema2_to_dcm3 or args.nema2_to_dcm3_ow:
            overwrite = args.nema2_to_dcm3_ow
            if is_folder:
                results = convert_nema2_folder(target_path, True, include_subfolders, overwrite)
                print(f"Converted {len(results)} file(s) from NEMA2 to DICOM3")
            elif is_file:
                out = nema2_to_dicom3(target_path, overwrite)
                print(f"Converted: {out}")

        elif args.dcm3_to_nema2 or args.dcm3_to_nema2_ow:
            overwrite = args.dcm3_to_nema2_ow
            if is_folder:
                results = convert_nema2_folder(target_path, False, include_subfolders, overwrite)
                print(f"Converted {len(results)} file(s) from DICOM3 to NEMA2")
            elif is_file:
                out = dicom3_to_nema2(target_path, overwrite)
                print(f"Converted: {out}")

        # ==========================================
        # ENDIAN CONVERSION
        # ==========================================
        elif args.be_to_le or args.be_to_le_ow:
            overwrite = args.be_to_le_ow
            if is_folder:
                results = convert_endian_folder(target_path, True, include_subfolders, overwrite)
                print(f"Converted {len(results)} file(s) to Little Endian")
            elif is_file:
                from dicom_utils import convert_endian
                out = convert_endian(target_path, True, overwrite)
                print(f"Converted: {out}")

        elif args.le_to_be or args.le_to_be_ow:
            overwrite = args.le_to_be_ow
            if is_folder:
                results = convert_endian_folder(target_path, False, include_subfolders, overwrite)
                print(f"Converted {len(results)} file(s) to Big Endian")
            elif is_file:
                from dicom_utils import convert_endian
                out = convert_endian(target_path, False, overwrite)
                print(f"Converted: {out}")

        # ==========================================
        # COMPRESSION
        # ==========================================
        elif args.comp_lossless or args.comp_lossless_ow:
            overwrite = args.comp_lossless_ow
            if is_folder:
                results = compress_folder(target_path, True, include_subfolders, overwrite)
                print(f"Compressed {len(results)} file(s) with JPEG lossless")
            elif is_file:
                out = compress_dicom(target_path, True, overwrite)
                print(f"Compressed: {out}")

        elif args.comp_lossy or args.comp_lossy_ow:
            overwrite = args.comp_lossy_ow
            if is_folder:
                results = compress_folder(target_path, False, include_subfolders, overwrite)
                print(f"Compressed {len(results)} file(s) with JPEG lossy")
            elif is_file:
                out = compress_dicom(target_path, False, overwrite)
                print(f"Compressed: {out}")

        elif args.decomp or args.decomp_ow:
            overwrite = args.decomp_ow
            if is_folder:
                results = decompress_folder(target_path, include_subfolders, overwrite)
                print(f"Decompressed {len(results)} file(s)")
            elif is_file:
                out = decompress_dicom(target_path, overwrite)
                print(f"Decompressed: {out}")

        # ==========================================
        # HEADER EXPORT
        # ==========================================
        elif args.export_header:
            if is_folder:
                results = export_headers_folder(target_path, include_subfolders)
                print(f"Exported {len(results)} header(s) to text")
            elif is_file:
                out = export_header(target_path)
                print(f"Exported header: {out}")

        # ==========================================
        # INFO / SUMMARY
        # ==========================================
        elif args.info:
            if is_file:
                info = get_dicom_info(target_path)
                print(f"\nDICOM File Info: {target_path}")
                print("=" * 60)
                for key, val in info.items():
                    print(f"  {key:25s}: {val}")
            elif is_folder:
                files = find_dicom_files(target_path, include_subfolders)
                for f in files[:5]:  # Show first 5
                    info = get_dicom_info(f)
                    print(f"\n{f}")
                    print(f"  Patient: {info['patient_name']} ({info['patient_id']})")
                    print(f"  Modality: {info['modality']}, Size: {info['rows']}x{info['columns']}")
                    print(f"  Frames: {info['num_frames']}, Compressed: {info['compressed']}")
                if len(files) > 5:
                    print(f"\n... and {len(files) - 5} more file(s)")

        elif args.summary:
            if is_folder:
                summary = get_folder_summary(target_path, include_subfolders)
                print(f"\nFolder Summary: {target_path}")
                print("=" * 60)
                print(f"  Total files:    {summary['total_files']}")
                print(f"  Total patients: {summary['total_patients']}")
                print(f"  Total series:   {summary['total_series']}")
                print(f"  Modalities:     {', '.join(summary['modalities'])}")
                print(f"  Total frames:   {summary['total_frames']}")
                print(f"  Total size:     {summary['total_size_mb']} MB")
                print(f"  Patients:       {', '.join(summary['patients'])}")
            else:
                info = get_dicom_info(target_path)
                for key, val in info.items():
                    print(f"  {key:25s}: {val}")

        else:
            print("ERROR: No action specified. Use -h for help.")
            return 1

    except Exception as e:
        print(f"\nERROR: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.2f} seconds")
    logger.info("Completed in %.2f seconds with exit code %d", elapsed, exit_code)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
