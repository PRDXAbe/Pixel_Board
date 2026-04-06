#!/usr/bin/env python3
"""
scan_debug.py — Standalone LIDAR diagnostic visualizer
=======================================================
Run this script standalone (without the full launch file) to verify:
  1. Is /scan data flowing at all?
  2. Where are the scan points in the coordinate frame?
  3. Are plot limits the problem?

Usage (source workspaces first):
  source rw/install/setup.bash
  source big_boulder/install/setup.bash
  python3 big_boulder/src/adapt_display/scripts/scan_debug.py

No scan_tracker or ball detection needed — just the LIDAR driver.
"""

import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import LaserScan

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


class ScanDebugNode(Node):
    def __init__(self):
        super().__init__("scan_debug")
        self._lock = threading.Lock()
        self._xs: list[float] = []
        self._ys: list[float] = []
        self._msg_count = 0
        self._last_msg_time = 0.0
        self._range_min = 0.0
        self._range_max = 0.0
        self._num_ranges = 0
        self._angle_min = 0.0
        self._angle_max = 0.0

        # Try RELIABLE QoS first (matches sllidar_node default)
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.create_subscription(LaserScan, "/scan", self._on_scan, qos)
        self.get_logger().info("scan_debug: subscribed to /scan (BEST_EFFORT QoS)")

    def _on_scan(self, msg: LaserScan):
        xs, ys = [], []
        valid = 0
        for i, r in enumerate(msg.ranges):
            if math.isnan(r) or math.isinf(r):
                continue
            if r < msg.range_min or r > msg.range_max:
                continue
            valid += 1
            theta = msg.angle_min + i * msg.angle_increment
            xs.append(r * math.cos(theta))
            ys.append(r * math.sin(theta))

        with self._lock:
            self._xs = xs
            self._ys = ys
            self._msg_count += 1
            self._last_msg_time = time.time()
            self._range_min = msg.range_min
            self._range_max = msg.range_max
            self._num_ranges = len(msg.ranges)
            self._angle_min = math.degrees(msg.angle_min)
            self._angle_max = math.degrees(msg.angle_max)

        if self._msg_count % 10 == 1:
            self.get_logger().info(
                f"  scan #{self._msg_count}: {valid}/{len(msg.ranges)} valid pts | "
                f"angles [{self._angle_min:.1f}° … {self._angle_max:.1f}°] | "
                f"range [{msg.range_min:.2f} … {msg.range_max:.2f} m]"
            )

    def snapshot(self):
        with self._lock:
            return list(self._xs), list(self._ys), self._msg_count, self._last_msg_time


def main():
    rclpy.init()
    node = ScanDebugNode()

    ros_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    ros_thread.start()

    # ── Full 360° wide-view figure ────────────────────────────────────────────
    LIMIT = 3.0   # metres — show everything within 3 m
    fig, ax = plt.subplots(figsize=(8, 8))
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    ax.set_xlim(-LIMIT, LIMIT)
    ax.set_ylim(-LIMIT, LIMIT)
    ax.set_aspect("equal")
    ax.set_xlabel("X (m)", color="white")
    ax.set_ylabel("Y (m)", color="white")
    ax.set_title("LIDAR Debug — Full 360° Raw Scan\n(all data within 3 m visible)", color="white")
    ax.tick_params(colors="#888888")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444444")

    # Grid lines for orientation reference
    for v in [-2, -1, 0, 1, 2]:
        ax.axhline(v, color="#333333", linewidth=0.5)
        ax.axvline(v, color="#333333", linewidth=0.5)

    # Axes labels to identify positive half-space
    ax.text(LIMIT - 0.1, 0.05, "+X →", color="#ffcc00", ha="right", fontsize=9)
    ax.text(0.05, LIMIT - 0.1, "+Y ↑", color="#ffcc00", ha="left", fontsize=9)

    # Board boundary reference (expected location of the board)
    import matplotlib.patches as mpatches
    board_rect = mpatches.FancyBboxPatch(
        (0.050, -0.190), 0.810, 0.380,
        boxstyle="square,pad=0",
        linewidth=1.5, edgecolor="#00e64d", facecolor="none",
        linestyle="--", label="Expected board (0.05–0.86 m in X)",
    )
    ax.add_patch(board_rect)

    # LIDAR origin
    ax.plot(0, 0, marker="^", color="#ffcc00", markersize=12, zorder=7, label="LIDAR origin")

    scatter = ax.scatter([], [], s=3, color="white", alpha=0.7, label="Scan points", zorder=3)

    status_text = ax.text(
        0.02, 0.97, "Waiting for /scan …",
        transform=ax.transAxes, fontsize=9,
        color="#ffaa00", ha="left", va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a1a1a", edgecolor="#555555"),
    )

    ax.legend(loc="lower right", facecolor="#1a1a1a", edgecolor="#444444",
              labelcolor="white", fontsize=8)

    fig.tight_layout()

    def update(_frame):
        xs, ys, count, last_t = node.snapshot()
        age = time.time() - last_t if last_t > 0 else 999

        if xs:
            scatter.set_offsets(list(zip(xs, ys)))
            status_text.set_text(
                f"msgs received: {count} | points this scan: {len(xs)}\n"
                f"last msg: {age:.1f}s ago | X range: [{min(xs):.2f} … {max(xs):.2f}]\n"
                f"Y range: [{min(ys):.2f} … {max(ys):.2f}]"
            )
            status_text.set_color("#00ff88")
        else:
            scatter.set_offsets([])
            if count == 0:
                status_text.set_text("NO DATA — /scan not received yet.\nCheck: ros2 topic list")
                status_text.set_color("#ff4444")
            else:
                status_text.set_text(f"msgs received: {count}, but 0 valid points\n(all ranges NaN/inf or out of range_min/max)")
                status_text.set_color("#ffaa00")

        return scatter, status_text

    _anim = FuncAnimation(fig, update, interval=50, blit=True, cache_frame_data=False)
    plt.show()

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
