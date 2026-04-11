#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# DicomPressor Watch Script (Linux/macOS/WSL)
# ═══════════════════════════════════════════════════════════════
#
# Watches a parent folder containing patient subfolders.
# Every INTERVAL seconds, scans for new (unprocessed) subfolders
# and automatically merges their DICOM files into multi-frame.
#
# Usage:
#   ./dicompressor-watch.sh /path/to/patients [interval_seconds]
#
# Example folder structure:
#   /data/patients/
#     patient_001/        <- contains 400 single-frame .dcm files
#     patient_002/        <- new patient, will be auto-merged
#     patient_003/        <- already has .dicompressor_done, skipped
#
# The script creates a .dicompressor_done marker file in each
# folder after successful processing. This is how it knows
# which folders are already done.
#
# To re-process a folder, simply delete its .dicompressor_done file.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# Config
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DICOMPRESSOR="$SCRIPT_DIR/dicompressor.py"
MARKER=".dicompressor_done"
WATCH_DIR="${1:?Usage: $0 /path/to/patients [interval_seconds]}"
INTERVAL="${2:-300}"  # default 5 minutes

# Validate
if [ ! -d "$WATCH_DIR" ]; then
    echo "ERROR: Directory not found: $WATCH_DIR"
    exit 1
fi

if [ ! -f "$DICOMPRESSOR" ]; then
    echo "ERROR: dicompressor.py not found at: $DICOMPRESSOR"
    exit 1
fi

echo "═══════════════════════════════════════════════════"
echo " DicomPressor Watch Mode"
echo " Watching: $WATCH_DIR"
echo " Interval: ${INTERVAL}s"
echo " Marker:   $MARKER"
echo " Press Ctrl+C to stop"
echo "═══════════════════════════════════════════════════"
echo ""

# Main loop
while true; do
    NEW_COUNT=0
    DONE_COUNT=0
    EMPTY_COUNT=0

    for dir in "$WATCH_DIR"/*/; do
        [ -d "$dir" ] || continue
        FOLDER_NAME=$(basename "$dir")

        # Already processed?
        if [ -f "$dir/$MARKER" ]; then
            DONE_COUNT=$((DONE_COUNT + 1))
            continue
        fi

        # Has DICOM files?
        DCM_COUNT=$(find "$dir" -maxdepth 1 -name "*.dcm" -o -name "*.DCM" 2>/dev/null | wc -l)
        if [ "$DCM_COUNT" -eq 0 ]; then
            EMPTY_COUNT=$((EMPTY_COUNT + 1))
            continue
        fi

        # New folder — process it!
        NEW_COUNT=$((NEW_COUNT + 1))
        echo ""
        echo "[$(date '+%H:%M:%S')] NEW: $FOLDER_NAME ($DCM_COUNT files)"
        echo "  Processing..."

        if python3 "$DICOMPRESSOR" -j --skip-if-done -f "$dir"; then
            echo "  Done!"
        else
            echo "  FAILED (see log above)"
        fi
    done

    TOTAL=$((NEW_COUNT + DONE_COUNT + EMPTY_COUNT))
    if [ "$NEW_COUNT" -eq 0 ]; then
        echo -ne "\r[$(date '+%H:%M:%S')] $TOTAL folders ($DONE_COUNT done, $EMPTY_COUNT empty). Next scan in ${INTERVAL}s...  "
    else
        echo ""
        echo "[$(date '+%H:%M:%S')] Processed $NEW_COUNT new folder(s). Total: $TOTAL ($DONE_COUNT done)"
    fi

    sleep "$INTERVAL"
done
