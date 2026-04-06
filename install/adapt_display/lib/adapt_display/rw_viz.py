#!/usr/bin/env python3
"""
rw_viz.py — Real-world LD19 visualizer
=======================================
Displays a live top-down view of the board with:
• raw LIDAR scan points (white dots)
• board boundary rectangle (green dashed line)
• detected ball centroids (red filled circles)
• incrementing ball counter (top-right overlay)

Topics consumed
/scan sensor_msgs/LaserScan — raw LD19 data
/ball_count std_msgs/Int32 — running total from scan_tracker
/ball_positions std_msgs/Float32MultiArray — centroid flat array [x1,y1,…]

Run after sourcing both workspaces (see start_real_world.sh).
"""

import math
import threading

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Int32, Float32MultiArray

import matplotlib
matplotlib.use("TkAgg") # use TkAgg so the window runs on the main thread
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation

# ── Plot limits (see VIZ_ORIENTATION_FIX.md) ────────────────────────────────
# sensor-X → horizontal (board width), -sensor-Y → vertical (board depth, inverted)
PLOT_X_MIN = -0.28   # horizontal: just past board right (sensor X)
PLOT_X_MAX = 0.28    # horizontal: just past board left (sensor X)
PLOT_Y_MIN = -0.05   # vertical: small gap above LIDAR (-sensor Y)
PLOT_Y_MAX = 0.95    # vertical: small gap past far board edge

# ── Board rectangle in plot coordinates (x=sensor_X, y=-sensor_Y) ──────────
BOARD_MIN_X = -0.19           # left edge of board (sensor X)
BOARD_MAX_X = 0.19            # right edge of board (sensor X)
BOARD_MIN_Y_NEG = 0.00      # near edge of board (-sensor Y, i.e. -0 = 0)
BOARD_MAX_Y_NEG = 0.86        # far edge of board (-sensor Y, i.e. -(-0.86) = 0.86)


class RwVizNode(Node):

    def __init__(self):
        super().__init__("rw_viz")

        # Shared state written by ROS callbacks, read by matplotlib main thread.
        # Use a simple lock to avoid torn reads on CPython (belt-and-suspenders).
        self._lock = threading.Lock()
        self._scan_xs: list[float] = []
        self._scan_ys: list[float] = []
        self._ball_xs: list[float] = []
        self._ball_ys: list[float] = []
        self._ball_count: int = 0

        # ── Subscriptions ────────────────────────────────────────────────────
        self.create_subscription(LaserScan, "/scan",
                                 self._on_scan, 10)
        self.create_subscription(Int32, "/ball_count",
                                 self._on_count, 10)
        self.create_subscription(Float32MultiArray, "/ball_positions",
                                 self._on_positions, 10)

    # ── Callbacks ──────────────────────────────────────────────────────────

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
        with self._lock:
            self._scan_xs = xs
            self._scan_ys = ys

    def _on_count(self, msg: Int32):
        with self._lock:
            self._ball_count = msg.data

    def _on_positions(self, msg: Float32MultiArray):
        data = msg.data
        # flat [x1, y1, x2, y2, ...]
        xs, ys = [], []
        for i in range(0, len(data) - 1, 2):
            xs.append(float(data[i]))
            ys.append(float(data[i + 1]))
        with self._lock:
            self._ball_xs = xs
            self._ball_ys = ys

    # ── Snapshot for the drawing thread ──────────────────────────────────────

    def snapshot(self):
        with self._lock:
            return (
                list(self._scan_xs),
                list(self._scan_ys),
                list(self._ball_xs),
                list(self._ball_ys),
                self._ball_count,
            )


def build_figure():
    """Create and return the matplotlib figure and artist objects to update."""
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#111111")
    ax.set_facecolor("#111111")

    ax.set_xlim(PLOT_X_MIN, PLOT_X_MAX)  # sensor X on horizontal (board width)
    ax.set_ylim(PLOT_Y_MIN, PLOT_Y_MAX)  # -sensor Y on vertical (board depth, inverted)
    ax.invert_yaxis()  # Y=0 (LIDAR) at TOP, -Y=0.86 at BOTTOM
    ax.set_aspect("equal")
    ax.set_xlabel("← board right X (m) board left →", color="#888888")
    ax.set_ylabel("board depth (m)\n← near (LIDAR) far →", color="#888888")
    ax.set_title("LD19 Real-World View (top-down)", color="white", fontsize=12)
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444444")

    # Board boundary rectangle (dashed green) — (x=sensor_X, y=-sensor_Y)
    board_rect = mpatches.FancyBboxPatch(
        (BOARD_MIN_X, BOARD_MIN_Y_NEG),  # (x=sensor_X, y=-sensor_Y)
        BOARD_MAX_X - BOARD_MIN_X,  # width = X span
        BOARD_MAX_Y_NEG - BOARD_MIN_Y_NEG,  # height = negated-Y span
        boxstyle="square,pad=0",
        linewidth=1.5, edgecolor="#00cc44", facecolor="none",
        linestyle="--", label="Board boundary",
    )
    ax.add_patch(board_rect)

    # LIDAR origin marker — downward triangle (pointing into board)
    ax.plot(0, 0, marker="v", color="#ffcc00", markersize=10, zorder=5,
            label="LIDAR origin")

    # Scan point scatter (white)
    scan_scatter = ax.scatter([], [], s=2, color="white", alpha=0.6,
                              label="Scan points", zorder=3)

    # Ball centroid scatter (red)
    ball_scatter = ax.scatter([], [], s=120, color="#ff3333", alpha=0.9,
                              edgecolors="white", linewidths=0.8,
                              label="Ball centroids", zorder=6)

    # Counter text (top-right corner of the axes)
    counter_text = ax.text(
        0.98, 0.95, "Balls: 0",
        transform=ax.transAxes,
        fontsize=18, color="#ffcc00",
        ha="right", va="top",
        fontweight="bold",
    )

    ax.legend(loc="upper left", facecolor="#222222", edgecolor="#555555",
              labelcolor="white", fontsize=8)

    return fig, scan_scatter, ball_scatter, counter_text


def main(args=None):
    rclpy.init(args=args)
    node = RwVizNode()

    # Spin ROS in a background thread so matplotlib can own the main thread
    ros_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    ros_thread.start()

    fig, scan_scatter, ball_scatter, counter_text = build_figure()

    def update(_frame):
        scan_xs, scan_ys, ball_xs, ball_ys, count = node.snapshot()

        if scan_xs:
            scan_scatter.set_offsets(list(zip(scan_xs, [-y for y in scan_ys])))  # (sensor_X, -sensor_Y)
        else:
            scan_scatter.set_offsets([])

        if ball_xs:
            ball_scatter.set_offsets(list(zip(ball_xs, [-y for y in ball_ys])))  # (sensor_X, -sensor_Y)
        else:
            ball_scatter.set_offsets([])

        counter_text.set_text(f"Balls: {count}")
        return scan_scatter, ball_scatter, counter_text

    # Animate at ~25 fps; blit=True redraws only changed artists
    _anim = FuncAnimation(fig, update, interval=40, blit=True, cache_frame_data=False)

    plt.tight_layout()
    plt.show()

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
