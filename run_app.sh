#!/usr/bin/env bash
# run.sh — Launch the PixelBoard UI
# Usage: bash run.sh
#
# This single script starts everything:
#   1. Fixes serial port permissions for the LD19 LiDAR
#   2. Launches the Kotlin Compose desktop UI
#
# The UI itself handles starting/stopping the LiDAR driver
# and ROS bridge via the Start/Stop button.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$SCRIPT_DIR/pixel_board_ui"

# ── Sanity checks ─────────────────────────────────────────────────────────────

if ! command -v java &>/dev/null; then
    echo "❌  Java not found. Install with: sudo apt install -y openjdk-21-jdk"
    exit 1
fi

if [ ! -f "$UI_DIR/gradlew" ]; then
    echo "❌  Gradle wrapper not found at $UI_DIR/gradlew"
    echo "    Re-run the project setup first."
    exit 1
fi

# ── Serial port permission ────────────────────────────────────────────────────

if ls /dev/ttyUSB* &>/dev/null; then
    PORT=$(ls /dev/ttyUSB* 2>/dev/null | head -1)
    if [ ! -w "$PORT" ]; then
        echo "🔑  Fixing serial port permission for $PORT ..."
        sudo chmod a+rw "$PORT"
    fi
    echo "✅  Serial port: $PORT"
else
    echo "⚠️   No /dev/ttyUSB* found — is the LD19 plugged in?"
fi

# ── Launch UI ─────────────────────────────────────────────────────────────────

echo ""
echo "🚀  Launching PixelBoard UI..."
echo "    Click  [Start Driver]  in the app to activate the LiDAR."
echo ""

cd "$UI_DIR"
./gradlew run
