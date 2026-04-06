#!/usr/bin/env python3
"""
rw_viz.py — Real-world RPLIDAR visualizer
==========================================
Displays a live top-down view of the board with:
  • raw LIDAR scan points (white dots)
  • board boundary rectangle (green dashed line)
  • detected ball centroids (red filled circles)
  • incrementing ball counter and scan-receive diagnostic

Topics consumed
  /scan             sensor_msgs/LaserScan        — raw scan data
  /ball_count       std_msgs/Int32               — running total from scan_tracker
  /ball_positions   std_msgs/Float32MultiArray   — centroid flat array [x1,y1,…]

ROS2 parameters (set from real_world.launch.py — edit there, not here)
  board_min_x / board_max_x / board_min_y / board_max_y  (metres, sensor frame)
  lidar_offset_x / lidar_offset_y  (metres, default 0,0)

Coordinate frame (sensor frame, same as scan_tracker)
  +X  → into the board (depth, long axis, away from LIDAR)
  +Y  → left across the board (lateral, short axis)
  Origin = LIDAR scan centre
"""

import math

import numpy as np

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Int32, Float32MultiArray

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation


class RwVizNode(Node):

    def __init__(self):
        super().__init__("rw_viz")

        # ── Board / LIDAR geometry params ──────────────────────────────────────
        self.declare_parameter("board_min_x",    0.050)
        self.declare_parameter("board_max_x",    0.860)
        self.declare_parameter("board_min_y",   -0.190)
        self.declare_parameter("board_max_y",    0.190)
        self.declare_parameter("lidar_offset_x", 0.0)
        self.declare_parameter("lidar_offset_y", 0.0)

        # ── Scan data (updated by ROS callbacks, read by animation) ───────────
        self.scan_xs: list[float] = []
        self.scan_ys: list[float] = []
        self.ball_xs: list[float] = []
        self.ball_ys: list[float] = []
        self.ball_count: int = 0
        self.scan_msg_count: int = 0   # diagnostic counter

        # ── Subscriptions ──────────────────────────────────────────────────────
        # BEST_EFFORT matches what sllidar_node sends on the wire.
        scan_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.create_subscription(LaserScan,         "/scan",           self._on_scan,      scan_qos)
        self.create_subscription(Int32,             "/ball_count",     self._on_count,     10)
        self.create_subscription(Float32MultiArray, "/ball_positions", self._on_positions, 10)

        self.get_logger().info("rw_viz ready — waiting for /scan …")

    # ── ROS callbacks ──────────────────────────────────────────────────────────
    # These run on the main thread via spin_once() inside the animation update.

    def _on_scan(self, msg: LaserScan):
        xs, ys = [], []
        for i, r in enumerate(msg.ranges):
            if math.isnan(r) or math.isinf(r):
                continue
            if r < msg.range_min or r > msg.range_max:
                continue
            theta = msg.angle_min + i * msg.angle_increment
            xs.append(r * math.cos(theta))
            ys.append(r * math.sin(theta))
        self.scan_xs = xs
        self.scan_ys = ys
        self.scan_msg_count += 1

    def _on_count(self, msg: Int32):
        self.ball_count = msg.data

    def _on_positions(self, msg: Float32MultiArray):
        data = msg.data
        xs, ys = [], []
        for i in range(0, len(data) - 1, 2):
            xs.append(float(data[i]))
            ys.append(float(data[i + 1]))
        self.ball_xs = xs
        self.ball_ys = ys

    def board_params(self):
        return (
            self.get_parameter("board_min_x").value,
            self.get_parameter("board_max_x").value,
            self.get_parameter("board_min_y").value,
            self.get_parameter("board_max_y").value,
            self.get_parameter("lidar_offset_x").value,
            self.get_parameter("lidar_offset_y").value,
        )


def build_figure(board_min_x, board_max_x, board_min_y, board_max_y,
                 lidar_offset_x, lidar_offset_y):
    board_w  = board_max_x - board_min_x
    board_h  = board_max_y - board_min_y
    margin_x = board_w * 0.14
    margin_y = board_h * 0.28

    fig, ax = plt.subplots(figsize=(11, 6))
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    ax.set_xlim(board_min_x - margin_x, board_max_x + margin_x)
    ax.set_ylim(board_min_y - margin_y, board_max_y + margin_y)
    ax.set_aspect("equal")
    ax.set_xlabel("X — depth into board (m)", color="#888888", fontsize=9)
    ax.set_ylabel("Y — lateral across board (m)", color="#888888", fontsize=9)
    ax.set_title("RPLIDAR A1-M8 — Live Board View (top-down)", color="white", fontsize=12, pad=10)
    ax.tick_params(colors="#666666", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")

    # Board boundary
    board_rect = mpatches.FancyBboxPatch(
        (board_min_x, board_min_y), board_w, board_h,
        boxstyle="square,pad=0",
        linewidth=1.8, edgecolor="#00e64d", facecolor="#00e64d08",
        linestyle="--", label="Board boundary", zorder=2,
    )
    ax.add_patch(board_rect)

    # Dimension annotations
    ax.annotate(f"{board_w*100:.0f} cm",
                xy=((board_min_x + board_max_x) / 2, board_max_y),
                xytext=(0, 8), textcoords="offset points",
                ha="center", va="bottom", color="#00e64d", fontsize=8)
    ax.annotate(f"{board_h*100:.0f} cm",
                xy=(board_max_x, (board_min_y + board_max_y) / 2),
                xytext=(6, 0), textcoords="offset points",
                ha="left", va="center", color="#00e64d", fontsize=8, rotation=90)

    # LIDAR marker
    ax.plot(lidar_offset_x, lidar_offset_y,
            marker="^", color="#ffcc00", markersize=11, zorder=7,
            label="LIDAR origin", markeredgecolor="#000000", markeredgewidth=0.8)

    # Scan points
    scan_scatter = ax.scatter([], [], s=2, color="white", alpha=0.55,
                              label="Scan points", zorder=3)
    # Ball centroids
    ball_scatter = ax.scatter([], [], s=140, color="#ff3333", alpha=0.95,
                              edgecolors="white", linewidths=1.0,
                              label="Ball centroids", zorder=6)

    # Ball counter
    counter_text = ax.text(
        0.98, 0.97, "Balls: 0",
        transform=ax.transAxes, fontsize=20, color="#ffcc00",
        ha="right", va="top", fontweight="bold",
    )

    # Diagnostic counter (shows whether /scan is being received)
    diag_text = ax.text(
        0.98, 0.04, "Scans: 0",
        transform=ax.transAxes, fontsize=8, color="#555555",
        ha="right", va="bottom",
    )

    ax.legend(loc="upper left", facecolor="#1a1a1a", edgecolor="#444444",
              labelcolor="white", fontsize=8, framealpha=0.85)
    fig.tight_layout()
    return fig, scan_scatter, ball_scatter, counter_text, diag_text


def main(args=None):
    rclpy.init(args=args)
    node = RwVizNode()

    # Use a SingleThreadedExecutor — spin_once() will be called directly
    # inside the matplotlib animation update, on the main thread.
    # This avoids all background-thread issues when launched via ros2 launch.
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    board_min_x, board_max_x, board_min_y, board_max_y, \
        lidar_offset_x, lidar_offset_y = node.board_params()

    node.get_logger().info(
        f"rw_viz: board X[{board_min_x:.3f}, {board_max_x:.3f}]  "
        f"Y[{board_min_y:.3f}, {board_max_y:.3f}]  "
        f"LIDAR offset ({lidar_offset_x:.3f}, {lidar_offset_y:.3f})"
    )

    fig, scan_scatter, ball_scatter, counter_text, diag_text = build_figure(
        board_min_x, board_max_x, board_min_y, board_max_y,
        lidar_offset_x, lidar_offset_y,
    )

    def update(_frame):
        # Process any pending ROS callbacks right here in the main thread.
        # timeout_sec=0 means: handle whatever is ready now, return immediately.
        executor.spin_once(timeout_sec=0)

        # Draw scan points
        if node.scan_xs:
            scan_scatter.set_offsets(np.column_stack([node.scan_xs, node.scan_ys]))
        else:
            scan_scatter.set_offsets(np.empty((0, 2)))

        # Draw ball centroids
        if node.ball_xs:
            ball_scatter.set_offsets(np.column_stack([node.ball_xs, node.ball_ys]))
        else:
            ball_scatter.set_offsets(np.empty((0, 2)))

        counter_text.set_text(f"Balls: {node.ball_count}")

        # Diagnostic: colour changes green once data flows, stays red if not
        if node.scan_msg_count > 0:
            diag_text.set_text(f"Scans: {node.scan_msg_count}")
            diag_text.set_color("#00cc66")
        else:
            diag_text.set_text("Scans: 0 — waiting for /scan …")
            diag_text.set_color("#cc3333")

    _anim = FuncAnimation(fig, update, interval=40, blit=False, cache_frame_data=False)

    plt.show()

    executor.shutdown()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
