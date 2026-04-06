#!/usr/bin/env python3
"""
real_world.launch.py
====================
Launches the full real-world pipeline:
1. ldlidar_stl_ros2 LD19 driver → publishes /scan
2. adapt_display scan_tracker → detects balls, publishes /ball_count and /ball_positions
3. adapt_display rw_viz → live matplotlib window

Pre-requisites
• Both workspaces sourced (see start_real_world.sh)
• LD19 connected via USB → /dev/ttyUSB0 (or update port_name below)
• adapt_display rebuilt after the scan_tracker changes described in this doc
"""

from launch import LaunchDescription
from launch_ros.actions import Node


# ── Board boundary (sensor-frame, metres) ────────────────────────────────────
# Derived from 90 × 41 cm board with LD19 centred on the short edge.
# Trim 1.5 cm inward on all four sides to avoid detecting wooden board edges.
BOARD_MIN_X = 0.050
BOARD_MAX_X = 0.860
BOARD_MIN_Y = -0.190
BOARD_MAX_Y = 0.190


def generate_launch_description():

    # ── 1. LD19 hardware driver ───────────────────────────────────────────────
    # Publishes sensor_msgs/LaserScan on /scan at ~10 Hz.
    # angle_crop hides the 45° cone directly behind the sensor (cable side)
    # so the board surface receives a clean 180° forward scan.
    ld19_driver = Node(
        package="ldlidar_stl_ros2",
        executable="ldlidar_stl_ros2_node",
        name="LD19",
        parameters=[
            {"product_name": "LDLiDAR_LD19"},
            {"topic_name": "scan"},
            {"frame_id": "laser_frame"},
            {"port_name": "/dev/ttyUSB0"},
            {"port_baudrate": 230400},
            {"laser_scan_dir": True},
            # Mask 157.5°–202.5° (the 45° cone behind the sensor / cable side).
            # NOTE: these are the HIDDEN angles, not the visible ones.
            {"enable_angle_crop_func": True},
            {"angle_crop_min": 157.5},
            {"angle_crop_max": 202.5},
            {"bins": 455},
        ],
        output="screen",
    )

    # ── 2. scan_tracker: ball detection + counting ────────────────────────────
    scan_tracker = Node(
        package="adapt_display",
        executable="scan_tracker",
        name="scan_tracker",
        output="screen",
        parameters=[
            {"distance_threshold": 0.10},
            {"min_points_per_cluster": 1},
            {"match_radius": 0.50},
            {"absent_frames_to_forget": 30},
            {"enable_board_filtering": True},
            {"board_min_x": BOARD_MIN_X},
            {"board_max_x": BOARD_MAX_X},
            {"board_min_y": BOARD_MIN_Y},
            {"board_max_y": BOARD_MAX_Y},
        ],
    )

    # ── 3. Live visualizer ───────────────────────────────────────────────────
    rw_viz = Node(
        package="adapt_display",
        executable="rw_viz.py",
        name="rw_viz",
        output="screen",
    )

    return LaunchDescription([
        ld19_driver,
        scan_tracker,
        rw_viz,
    ])
