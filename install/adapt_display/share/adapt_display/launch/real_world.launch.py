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
from launch.actions import TimerAction
from launch_ros.actions import Node


# ── Board boundary (sensor-frame, metres) ────────────────────────────────────
# Derived from 90 × 41 cm board with LD19 centred on the short edge.
# Trim 1.5 cm inward on all sides to avoid detecting the wooden board edges.
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
    # Give the LD19 driver 2 s to start publishing /scan before scan_tracker
    # tries to subscribe to it. Without this delay scan_tracker logs a warning
    # every frame about "no publisher" and the first few frames may be dropped.
    scan_tracker = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="adapt_display",
                executable="scan_tracker",
                name="scan_tracker",
                output="screen",
                parameters=[
                    # Clustering: 10 cm gap between points → separate cluster
                    {"distance_threshold": 0.10},
                    # A single LIDAR hit is enough to register a ball
                    {"min_points_per_cluster": 1},
                    # Track matching: centroids within 50 cm = same ball
                    {"match_radius": 0.50},
                    # Forget a track after 30 consecutive missed frames (~3 s)
                    {"absent_frames_to_forget": 30},
                    # Board filtering ON — ignore everything outside the board
                    {"enable_board_filtering": True},
                    {"board_min_x": BOARD_MIN_X},
                    {"board_max_x": BOARD_MAX_X},
                    {"board_min_y": BOARD_MIN_Y},
                    {"board_max_y": BOARD_MAX_Y},
                ],
            )
        ],
    )

    # ── 3. Live visualizer ───────────────────────────────────────────────────
    # Starts 3 s after driver launch so the first frames are already populated
    # before the matplotlib window opens.
    rw_viz = TimerAction(
        period=3.0,
        actions=[
            Node(
                package="adapt_display",
                executable="rw_viz.py",
                name="rw_viz",
                output="screen",
            )
        ],
    )

    return LaunchDescription([
        ld19_driver,
        scan_tracker,
        rw_viz,
    ])
