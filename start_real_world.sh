#!/usr/bin/env bash
# start_real_world.sh
# Usage:  bash start_real_world.sh
#
# Starts the LDROBOT LD19 LiDAR driver then opens the live visualization.
# Edit magic_board_live.py (top section) to change board dimensions.
# Driver settings (port, baud, angle-crop) live in:
#   rw/src/ldlidar_stl_ros2/launch/ld19.launch.py

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RW="$SCRIPT_DIR/rw"

echo "[magic_board] Sourcing workspaces..."
source "$RW/install/setup.bash"

# ── Kill any leftover LIDAR processes from previous runs ──────────────────────
echo "[magic_board] Cleaning up any leftover LIDAR processes..."
pkill -f ldlidar_stl_ros2_node 2>/dev/null && echo "  → killed stale ldlidar_stl_ros2_node" || true
pkill -f magic_board_live      2>/dev/null && echo "  → killed stale viz"                  || true

# Give the OS a moment to release the serial port
sleep 1

echo "[magic_board] Starting LD19 LiDAR driver..."
ros2 launch ldlidar_stl_ros2 ld19.launch.py &

LIDAR_PID=$!
echo "[magic_board] LIDAR driver PID: $LIDAR_PID"

# Wait for driver to start and confirm it's alive
echo "[magic_board] Waiting for driver to connect..."
sleep 3

if ! kill -0 $LIDAR_PID 2>/dev/null; then
    echo "[magic_board] ERROR: LD19 driver exited. Check that:"
    echo "  • LD19 LiDAR is plugged into USB"
    echo "  • Port is /dev/ttyUSB1  (check: ls /dev/ttyUSB*)"
    echo "  • Baud rate is 230400 (set in ld19.launch.py)"
    echo "  • You have permission  (check: groups | grep dialout)"
    exit 1
fi

echo "[magic_board] Driver is running — opening live visualization..."
python3 "$SCRIPT_DIR/magic_board_live.py"

# When the visualization window is closed, also stop the driver
echo "[magic_board] Visualization closed — stopping LIDAR driver..."
kill $LIDAR_PID 2>/dev/null || true
wait $LIDAR_PID 2>/dev/null || true
echo "[magic_board] Done."
