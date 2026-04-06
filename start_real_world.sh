#!/usr/bin/env bash
# start_real_world.sh
# Usage:  bash start_real_world.sh
#
# Starts the RPLIDAR A1-M8 driver then opens the live visualization.
# Edit magic_board_live.py (top section) to change board dimensions.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RW="$SCRIPT_DIR/rw"

echo "[magic_board] Sourcing workspaces..."
source "$RW/install/setup.bash"

echo "[magic_board] Starting RPLIDAR A1-M8 driver..."
ros2 run sllidar_ros2 sllidar_node \
    --ros-args \
    -p serial_port:=/dev/ttyUSB0 \
    -p serial_baudrate:=115200 \
    -p frame_id:=laser_frame \
    -p inverted:=false \
    -p angle_compensate:=true &

LIDAR_PID=$!
echo "[magic_board] LIDAR driver PID: $LIDAR_PID"

# Give the driver 3 seconds to connect and start publishing
echo "[magic_board] Waiting for driver to start..."
sleep 3

echo "[magic_board] Opening live visualization..."
python3 "$SCRIPT_DIR/magic_board_live.py"

# When the visualization window is closed, also stop the driver
echo "[magic_board] Visualization closed — stopping LIDAR driver..."
kill $LIDAR_PID 2>/dev/null || true
wait $LIDAR_PID 2>/dev/null || true
echo "[magic_board] Done."
