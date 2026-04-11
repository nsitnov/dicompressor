#!/usr/bin/env bash
#
# DicomPressor - Cross-platform DICOM CLI Tool (Bash Wrapper)
# Works on: macOS, Linux, WSL
#
# Usage: ./dicompressor.sh [options]
# Examples:
#   ./dicompressor.sh -j -f /path/to/patient_folder
#   ./dicompressor.sh -x -f /path/to/folder
#   ./dicompressor.sh --summary -f /path/to/folder
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/dicompressor.py"

# Find Python 3
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" --version 2>&1)
            if echo "$version" | grep -q "Python 3"; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_CMD=$(find_python)
if [ -z "$PYTHON_CMD" ]; then
    echo "ERROR: Python 3 is required but not found in PATH."
    echo ""
    echo "Install Python 3:"
    echo "  macOS:  brew install python3"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    echo "  WSL:    sudo apt install python3 python3-pip"
    exit 1
fi

# Check for pydicom
if ! "$PYTHON_CMD" -c "import pydicom" 2>/dev/null; then
    echo "Installing required packages..."
    "$PYTHON_CMD" -m pip install pydicom numpy Pillow --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON_CMD" -m pip install pydicom numpy Pillow --quiet 2>/dev/null || {
        echo "ERROR: Failed to install required packages."
        echo "Please run: $PYTHON_CMD -m pip install pydicom numpy Pillow"
        exit 1
    }
fi

# Check script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "ERROR: Cannot find dicompressor.py in $SCRIPT_DIR"
    exit 1
fi

# Run
exec "$PYTHON_CMD" "$PYTHON_SCRIPT" "$@"
