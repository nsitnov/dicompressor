#!/usr/bin/env python3
"""
DicomPressor - Cross-platform DICOM CLI tool
Analogous to Sante Dicommander
Works on: macOS, Windows (PowerShell), WSL/Linux

Usage: python dicompressor.py [action] [options] -f/-F <folder_or_file>

Actions match Sante Dicommander switches where applicable.
"""

import argparse
import os
import sys
import time
import logging
from pathlib import Path

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
    merge_to_multiframe, split_multiframe, split_multiframe_folder,
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

VERSION = "1.0.0"
PROGRAM_NAME = "DicomPressor"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("dicompressor")

# Marker file for --skip-if-done / --watch
DONE_MARKER = ".dicompressor_done"

def is_already_done(folder: str) -> bool:
    """Check if a folder has already been processed (marker file exists)."""
    return os.path.isfile(os.path.join(folder, DONE_MARKER))

def mark_as_done(folder: str, action: str, results: list):
    """Create a marker file after successful processing."""
    marker_path = os.path.join(folder, DONE_MARKER)
    import json
    from datetime import datetime
    info = {
        "processed_at": datetime.now().isoformat(),
        "action": action,
        "results": [os.path.basename(r) if isinstance(r, str) else str(r) for r in results],
        "dicompressor_version": VERSION,
    }
    with open(marker_path, "w") as f:
        json.dump(info, f, indent=2)
    logger.info(f"Marked as done: {marker_path}")


def copy_to_output_dir(result_files: list, output_dir: str):
    """Copy result files to the specified output directory."""
    import shutil
    os.makedirs(output_dir, exist_ok=True)
    for src in result_files:
        if isinstance(src, str) and os.path.isfile(src):
            dst = os.path.join(output_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            size_mb = os.path.getsize(dst) / 1024 / 1024
            logger.info(f"Copied to output: {dst} ({size_mb:.1f} MB)")


def print_banner():
    """Print program banner."""
    print(f"""
╔══════════════════════════════════════════════════════╗
║  {PROGRAM_NAME} v{VERSION}                              ║
║  Cross-platform DICOM CLI Tool                       ║
║  Compatible with: macOS, Windows, WSL/Linux          ║
╚══════════════════════════════════════════════════════╝
""")


def print_help_detailed():
    """Print detailed help matching Sante Dicommander switch reference."""
    print_banner()
    print("""
SWITCHES (compatible with Sante Dicommander):
═══════════════════════════════════════════════

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
  --watch N       Watch mode: re-scan subfolders every N seconds,
                  process only new (unmarked) ones. Ctrl+C to stop.
  --output-dir D  Copy merged result files to directory D.
                  Works with -j, --skip-if-done, and --watch.
                  Directory is created automatically if it doesn't exist.

EXAMPLES:
═════════

  # Merge 400 single-frame CT files into one multi-frame DICOM:
  python dicompressor.py -j -f /path/to/patient_folder

  # Merge, but skip if already done (safe to run repeatedly):
  python dicompressor.py -j --skip-if-done -f /path/to/patient_folder

  # Watch a folder with patient subfolders, auto-merge every 5 min:
  python dicompressor.py -j --watch 300 -f /path/to/patients/

  # Watch + copy merged files to a central output folder:
  python dicompressor.py -j --watch 300 --output-dir /data/merged -f /data/patients/

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

    args = parser.parse_args()

    # Setup logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

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

    start_time = time.time()

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
                # Prepare output dir if specified
                out_dir = None
                if args.output_dir:
                    out_dir = os.path.abspath(args.output_dir)
                    os.makedirs(out_dir, exist_ok=True)
                    print(f"Output directory: {out_dir}")

                # --watch mode: loop and scan subfolders
                if args.watch_interval:
                    args.skip_if_done = True  # --watch implies --skip-if-done
                    print(f"Watch mode: scanning every {args.watch_interval}s (Ctrl+C to stop)")
                    try:
                        while True:
                            subdirs = [os.path.join(target_path, d) for d in sorted(os.listdir(target_path))
                                       if os.path.isdir(os.path.join(target_path, d))]
                            new_count = 0
                            for subdir in subdirs:
                                if is_already_done(subdir):
                                    continue
                                # Check if folder has DICOM files
                                dcm_files = find_dicom_files(subdir, False)
                                if not dcm_files:
                                    continue
                                new_count += 1
                                folder_name = os.path.basename(subdir)
                                print(f"\n[NEW] {folder_name} ({len(dcm_files)} files)")
                                try:
                                    results = merge_to_multiframe(subdir, False)
                                    print(f"  Merged into {len(results)} multi-frame file(s)")
                                    for r in results:
                                        size_mb = os.path.getsize(r) / 1024 / 1024
                                        print(f"  -> {os.path.basename(r)} ({size_mb:.1f} MB)")
                                    if out_dir:
                                        copy_to_output_dir(results, out_dir)
                                    mark_as_done(subdir, "merge", results)
                                except Exception as e:
                                    logger.error(f"  Failed: {e}")
                            if new_count == 0:
                                print(f"[{time.strftime('%H:%M:%S')}] No new folders. Waiting {args.watch_interval}s...", end='\r')
                            time.sleep(args.watch_interval)
                    except KeyboardInterrupt:
                        print("\nWatch mode stopped.")
                        return 0

                # --skip-if-done: check marker
                elif args.skip_if_done and is_already_done(target_path):
                    print(f"SKIPPED (already processed): {target_path}")
                    print(f"  Marker: {os.path.join(target_path, DONE_MARKER)}")
                    print(f"  Delete the marker file to re-process.")
                    return 0

                else:
                    results = merge_to_multiframe(target_path, include_subfolders)
                    print(f"Created {len(results)} multi-frame file(s)")
                    for r in results:
                        size_mb = os.path.getsize(r) / 1024 / 1024
                        print(f"  -> {r} ({size_mb:.1f} MB)")
                    if out_dir:
                        copy_to_output_dir(results, out_dir)
                    if args.skip_if_done and results:
                        mark_as_done(target_path, "merge", results)
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
    return 0


if __name__ == '__main__':
    sys.exit(main())
