#!/usr/bin/env bash
# start_real_world.sh
# Usage: bash start_real_world.sh
# Place this file alongside the big_boulder/ and rw/ directories.

set -e

# Absolute paths — adjust if your workspace root is different
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIG_BOULDER="$SCRIPT_DIR/big_boulder"
RW="$SCRIPT_DIR/rw"

echo "[start_real_world] Sourcing workspaces..."
# shellcheck disable=SC1091
source "$RW/install/setup.bash"
# shellcheck disable=SC1091
source "$BIG_BOULDER/install/setup.bash"

echo "[start_real_world] Launching real_world pipeline..."
exec ros2 launch adapt_display real_world.launch.py
