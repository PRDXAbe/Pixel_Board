#!/usr/bin/env python3
"""
real_world.launch.py
====================
Launches the full real-world pipeline for the Magic Board:
  1. sllidar_node (RPLIDAR A1-M8 driver)  → publishes /scan
  2. scan_tracker                           → detects balls, publishes /ball_count and /ball_positions
  3. rw_viz                                 → live matplotlib top-down view

Pre-requisites
  • Both workspaces sourced (see start_real_world.sh):
        source rw/install/setup.bash
        source big_boulder/install/setup.bash
  • RPLIDAR A2-M12 connected via USB
  • adapt_display rebuilt after any changes here

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CHANGE YOUR SETUP HERE — all tunable values in one place
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from launch import LaunchDescription
from launch.actions import TimerAction
from launch_ros.actions import Node

# ── USB port ─────────────────────────────────────────────────────────────────
# Check with: ls /dev/ttyUSB*  (usually /dev/ttyUSB0)
SERIAL_PORT = "/dev/ttyUSB0"

# ── Board boundary (metres, sensor frame) ─────────────────────────────────────
#
#   Sensor frame axes:
#     +X  →  depth into board (long axis, away from LIDAR)
#     +Y  →  left across board (short axis / lateral)
#     Origin = LIDAR scan centre
#
#   Default values are for a 90 × 41 cm board with the LIDAR centred on
#   one short edge. Trim 1–2 cm inward to avoid detecting the board edges.
#
#                     ┌───────────── board far edge (board_max_x) ──────────────┐
#                     │                                                          │
#         board_min_y ├─────────────────────────────────────────────────────────┤ board_max_y
#                     │                                                          │
#                     └──────────── board near edge (board_min_x) ──────────────┘
#                                     ▲
#                              LIDAR origin (0, 0)
#
BOARD_MIN_X =  0.050   # near edge  (m) — increase if LIDAR body is detected as a ball
BOARD_MAX_X =  0.860   # far  edge  (m) — decrease if far edge produces phantom clusters
BOARD_MIN_Y = -0.190   # left  edge (m) — tighten symmetrically if side edges are noisy
BOARD_MAX_Y =  0.190   # right edge (m)

# ── LIDAR position offset (metres) ────────────────────────────────────────────
# Leave at 0,0 when the LIDAR is at the board corner / origin.
# Set if the sensor is mounted at a non-zero position relative to the board.
LIDAR_OFFSET_X = 0.0
LIDAR_OFFSET_Y = 0.0

# ─────────────────────────────────────────────────────────────────────────────


def generate_launch_description():

    # ── 1. RPLIDAR A1-M8 hardware driver ─────────────────────────────────────
    # Publishes sensor_msgs/LaserScan on /scan.
    # Baudrate 115200 is correct for A1-M8.
    # angle_compensate=True gives evenly-spaced angle buckets.
    # NOTE: scan_mode is intentionally NOT set — A1-M8 only supports
    # "Standard" mode. Passing "Sensitivity" causes the driver to log
    # an error and never start the scan (motor spins but no data published).
    # Leaving it unset makes the driver auto-select its default typical mode.
    sllidar_driver = Node(
        package="sllidar_ros2",
        executable="sllidar_node",
        name="sllidar_a1m8",
        parameters=[{
            "channel_type":     "serial",
            "serial_port":      SERIAL_PORT,
            "serial_baudrate":  115200,
            "frame_id":         "laser_frame",
            "inverted":         False,
            "angle_compensate": True,
        }],
        output="screen",
    )

    # ── 2. scan_tracker: ball detection + counting ────────────────────────────
    # Give the driver 2 s to start publishing /scan before scan_tracker
    # subscribes, so the first frames are not missed.
    scan_tracker = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="adapt_display",
                executable="scan_tracker",
                name="scan_tracker",
                output="screen",
                parameters=[{
                    # Clustering: points > 10 cm apart → separate cluster
                    "distance_threshold":      0.10,
                    # One LIDAR hit is enough to register a ball
                    "min_points_per_cluster":  1,
                    # Centroids within 50 cm = same ball across frames
                    "match_radius":            0.50,
                    # Forget a track after 30 consecutive missed frames (~3 s)
                    "absent_frames_to_forget": 30,
                    # Board filtering ON — discard everything outside the board
                    "enable_board_filtering":  True,
                    "board_min_x": BOARD_MIN_X,
                    "board_max_x": BOARD_MAX_X,
                    "board_min_y": BOARD_MIN_Y,
                    "board_max_y": BOARD_MAX_Y,
                }],
            )
        ],
    )

    # ── 3. Live visualizer ────────────────────────────────────────────────────
    # Starts 3 s after driver launch so the matplotlib window opens with
    # data already flowing. Board/LIDAR geometry is passed as params so
    # rw_viz draws the correct rectangle and marker position automatically.
    rw_viz = TimerAction(
        period=3.0,
        actions=[
            Node(
                package="adapt_display",
                executable="rw_viz.py",
                name="rw_viz",
                output="screen",
                parameters=[{
                    "board_min_x":    BOARD_MIN_X,
                    "board_max_x":    BOARD_MAX_X,
                    "board_min_y":    BOARD_MIN_Y,
                    "board_max_y":    BOARD_MAX_Y,
                    "lidar_offset_x": LIDAR_OFFSET_X,
                    "lidar_offset_y": LIDAR_OFFSET_Y,
                }],
            )
        ],
    )

    return LaunchDescription([
        sllidar_driver,
        scan_tracker,
        rw_viz,
    ])
