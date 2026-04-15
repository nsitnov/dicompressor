#!/bin/bash
# Thin watch wrapper for the generic DicomPressor workflow.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER="$SCRIPT_DIR/dicompressor.sh"
WATCH_DIR="${1:?Usage: $0 /path/to/patients [interval_seconds] [output_dir] [log_file] [scan_state_file]}"
INTERVAL="${2:-300}"
OUTPUT_DIR="${3:-}"
HAS_CUSTOM_LOG=0
if [ "$#" -ge 4 ]; then
    LOG_FILE="${4:-}"
    HAS_CUSTOM_LOG=1
else
    LOG_FILE="$SCRIPT_DIR/dicompressor.log"
fi
HAS_SCAN_STATE=0
if [ "$#" -ge 5 ]; then
    SCAN_STATE_FILE="${5-}"
    HAS_SCAN_STATE=1
else
    SCAN_STATE_FILE=""
fi

derive_scan_state_path() {
    local log_path="$1"
    local dir base stem
    dir="$(dirname "$log_path")"
    base="$(basename "$log_path")"
    stem="${base%.*}"
    if [ "$stem" = "$base" ]; then
        stem="$base"
    fi
    printf '%s/%s.scan-state.json' "$dir" "$stem"
}

if [ ! -d "$WATCH_DIR" ]; then
    echo "ERROR: Directory not found: $WATCH_DIR"
    exit 1
fi

if [ ! -f "$WRAPPER" ]; then
    echo "ERROR: dicompressor.sh not found at: $WRAPPER"
    exit 1
fi

if [ -n "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR"
fi

mkdir -p "$(dirname "$LOG_FILE")"

EFFECTIVE_SCAN_STATE="$SCAN_STATE_FILE"
if [ "$HAS_SCAN_STATE" -eq 0 ] && [ "$HAS_CUSTOM_LOG" -eq 1 ] && [ -n "$LOG_FILE" ]; then
    EFFECTIVE_SCAN_STATE="$(derive_scan_state_path "$LOG_FILE")"
fi

if [ -n "$EFFECTIVE_SCAN_STATE" ]; then
    mkdir -p "$(dirname "$EFFECTIVE_SCAN_STATE")"
fi

echo "═══════════════════════════════════════════════════"
echo " DicomPressor Watch Mode"
echo " Watching:    $WATCH_DIR"
echo " Interval:    ${INTERVAL}s"
if [ -n "$OUTPUT_DIR" ]; then
echo " Output dir:  $OUTPUT_DIR"
fi
echo " Log file:    $LOG_FILE"
if [ -n "$EFFECTIVE_SCAN_STATE" ]; then
echo " Scan state:  $EFFECTIVE_SCAN_STATE"
fi
echo " Press Ctrl+C to stop"
echo "═══════════════════════════════════════════════════"
echo ""

CMD=("$WRAPPER" -j --watch "$INTERVAL" --log-file "$LOG_FILE" -f "$WATCH_DIR")
if [ -n "$OUTPUT_DIR" ]; then
    CMD+=(--output-dir "$OUTPUT_DIR")
fi
if [ "$HAS_SCAN_STATE" -eq 1 ]; then
    CMD+=(--scan-state-file "$EFFECTIVE_SCAN_STATE")
elif [ -n "$EFFECTIVE_SCAN_STATE" ]; then
    CMD+=(--scan-state-file "$EFFECTIVE_SCAN_STATE")
fi

exec "${CMD[@]}"
