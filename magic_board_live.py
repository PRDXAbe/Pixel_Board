#!/usr/bin/env python3
"""
magic_board_live.py
===================
Standalone real-time LIDAR visualizer + ball counter for Magic Board.

What it does:
  • Shows all raw scan points in a live top-down view
  • Detects balls from clusters in the scan data
  • Increments a ball counter each time a new ball lands on the board

How to run:
  # Terminal 1 — start the LIDAR driver:
  source /path/to/rw/install/setup.bash
  ros2 run sllidar_ros2 sllidar_node \
      --ros-args -p serial_baudrate:=115200 -p angle_compensate:=true

  # Terminal 2 — run this script:
  source /path/to/rw/install/setup.bash
  python3 magic_board_live.py

Configure your board dimensions below (only place you need to edit).
"""

import math
import time

import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import LaserScan

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ══════════════════════════════════════════════════════════════════════════════
#   CONFIGURE YOUR SETUP HERE
# ══════════════════════════════════════════════════════════════════════════════

# Board dimensions in metres (sensor frame)
# +X = depth into board (long axis, away from LIDAR)
# +Y = lateral across board (short axis)
#
#   LIDAR is at origin, board stretches in front of it:
#
#        board_min_y ──────────────────────── board_max_y
#                │                                 │
#     LIDAR →   │   ←──────── board ──────────→   │
#                │                                 │
#        ────── board_min_x ─────── board_max_x ───
#
BOARD_MIN_X = 0.050   # near edge  (m) – just past the LIDAR body
BOARD_MAX_X = 0.860   # far  edge  (m)
BOARD_MIN_Y = -0.190  # left  edge (m)
BOARD_MAX_Y = 0.190   # right edge (m)

# Ball detection tuning
CLUSTER_DIST   = 0.08   # (m) max gap between points to be in the same cluster
MIN_PTS        = 2      # minimum points for a cluster to count as a ball
MATCH_RADIUS   = 0.20   # (m) max centroid movement to match same ball across frames
FORGET_FRAMES  = 25     # frames without a match before a track is removed

# ══════════════════════════════════════════════════════════════════════════════


class BallTracker:
    """Simple frame-to-frame ball tracker. Increments counter on new tracks."""

    def __init__(self):
        self.tracks  = []   # list of {'x', 'y', 'absent'}
        self.count   = 0

    def update(self, centroids):
        """Update tracks with new centroids. Returns current visible centroids."""
        for t in self.tracks:
            t['present'] = False

        unmatched = []
        for cx, cy in centroids:
            best_d, best_t = MATCH_RADIUS, None
            for t in self.tracks:
                d = math.hypot(cx - t['x'], cy - t['y'])
                if d < best_d:
                    best_d, best_t = d, t
            if best_t is not None:
                best_t['x'], best_t['y'] = cx, cy
                best_t['present'] = True
                best_t['absent']  = 0
            else:
                unmatched.append((cx, cy))

        # New clusters → new balls
        for cx, cy in unmatched:
            self.count += 1
            self.tracks.append({'x': cx, 'y': cy, 'present': True, 'absent': 0})

        # Age out absent tracks
        for t in self.tracks:
            if not t['present']:
                t['absent'] += 1
        self.tracks = [t for t in self.tracks if t['absent'] < FORGET_FRAMES]

        return [(t['x'], t['y']) for t in self.tracks if t['present']]


class ScanNode(Node):
    def __init__(self):
        super().__init__('mb_live')
        self.scan_xs   = []
        self.scan_ys   = []
        self.msg_count = 0

        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.create_subscription(LaserScan, '/scan', self._on_scan, qos)
        self.get_logger().info('mb_live: subscribed to /scan (BEST_EFFORT)')

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
        self.scan_xs   = xs
        self.scan_ys   = ys
        self.msg_count += 1


def cluster_points(xs, ys):
    """Simple single-pass Euclidean clustering. Returns list of (cx, cy)."""
    if not xs:
        return []
    pts = list(zip(xs, ys))
    clusters = []
    used = [False] * len(pts)
    for i, (px, py) in enumerate(pts):
        if used[i]:
            continue
        members = [i]
        used[i] = True
        for j in range(i + 1, len(pts)):
            if used[j]:
                continue
            dx = pts[j][0] - px
            dy = pts[j][1] - py
            if math.hypot(dx, dy) < CLUSTER_DIST:
                members.append(j)
                used[j] = True
        if len(members) >= MIN_PTS:
            mx = sum(pts[k][0] for k in members) / len(members)
            my = sum(pts[k][1] for k in members) / len(members)
            clusters.append((mx, my))
    return clusters


def filter_to_board(xs, ys):
    bxs, bys = [], []
    for x, y in zip(xs, ys):
        if BOARD_MIN_X <= x <= BOARD_MAX_X and BOARD_MIN_Y <= y <= BOARD_MAX_Y:
            bxs.append(x)
            bys.append(y)
    return bxs, bys


def build_figure():
    board_w  = BOARD_MAX_X - BOARD_MIN_X
    board_h  = BOARD_MAX_Y - BOARD_MIN_Y
    mx       = board_w * 0.22
    my       = board_h * 0.45

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#0a0a0a')
    ax.set_facecolor('#0a0a0a')
    ax.set_xlim(BOARD_MIN_X - mx, BOARD_MAX_X + mx)
    ax.set_ylim(BOARD_MIN_Y - my, BOARD_MAX_Y + my)
    ax.set_aspect('equal')
    ax.set_xlabel('X — depth into board (m)', color='#888', fontsize=9)
    ax.set_ylabel('Y — lateral (m)',           color='#888', fontsize=9)
    ax.set_title('Magic Board — Live LIDAR View', color='white', fontsize=13, pad=10)
    ax.tick_params(colors='#555', labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor('#2a2a2a')

    # Board boundary
    rect = mpatches.FancyBboxPatch(
        (BOARD_MIN_X, BOARD_MIN_Y), board_w, board_h,
        boxstyle='square,pad=0',
        linewidth=2, edgecolor='#00e64d', facecolor='#00e64d08',
        linestyle='--', label=f'Board  {board_w*100:.0f}×{board_h*100:.0f} cm', zorder=2,
    )
    ax.add_patch(rect)

    # LIDAR marker
    ax.plot(0, 0, '^', color='#ffcc00', ms=11, zorder=7, label='LIDAR',
            mec='#000', mew=0.8)

    # Scan — ALL points (grey, outside board)
    all_scan = ax.scatter([], [], s=1.5, color='#555555', alpha=0.6,
                          label='Scan (outside)', zorder=3)
    # Scan — board points (white)
    board_scan = ax.scatter([], [], s=2.5, color='white', alpha=0.75,
                            label='Scan (on board)', zorder=4)
    # Ball centroids
    ball_sc = ax.scatter([], [], s=160, color='#ff3333', alpha=0.95,
                         edgecolors='white', linewidths=1.2,
                         label='Ball detections', zorder=6)

    # Counter
    counter = ax.text(0.98, 0.96, 'Balls: 0', transform=ax.transAxes,
                      fontsize=22, color='#ffcc00', ha='right', va='top',
                      fontweight='bold')
    # Status
    status = ax.text(0.98, 0.04, 'Waiting for /scan…', transform=ax.transAxes,
                     fontsize=8, color='#cc3333', ha='right', va='bottom')

    ax.legend(loc='upper left', facecolor='#181818', edgecolor='#444',
              labelcolor='white', fontsize=8, framealpha=0.9)
    fig.tight_layout()
    return fig, all_scan, board_scan, ball_sc, counter, status


def main():
    rclpy.init()
    node    = ScanNode()
    exec_   = SingleThreadedExecutor()
    tracker = BallTracker()
    exec_.add_node(node)

    fig, all_scan, board_scan, ball_sc, counter, status = build_figure()

    def update(_frame):
        # Process any pending ROS messages on this thread
        exec_.spin_once(timeout_sec=0)

        xs, ys = node.scan_xs, node.scan_ys

        # All scan points
        if xs:
            all_scan.set_offsets(np.column_stack([xs, ys]))
        else:
            all_scan.set_offsets(np.empty((0, 2)))

        # Board-filtered scan points + ball detection
        bxs, bys = filter_to_board(xs, ys)
        if bxs:
            board_scan.set_offsets(np.column_stack([bxs, bys]))
            centroids = cluster_points(bxs, bys)
            visible   = tracker.update(centroids)
        else:
            board_scan.set_offsets(np.empty((0, 2)))
            tracker.update([])
            visible = []

        if visible:
            ball_sc.set_offsets(np.array(visible))
        else:
            ball_sc.set_offsets(np.empty((0, 2)))

        counter.set_text(f'Balls: {tracker.count}')

        # Status indicator
        if node.msg_count > 0:
            status.set_text(f'Scans received: {node.msg_count}')
            status.set_color('#00cc66')
        else:
            status.set_text('Waiting for /scan… (is sllidar_node running?)')
            status.set_color('#cc3333')

    _anim = FuncAnimation(fig, update, interval=40, blit=False,
                          cache_frame_data=False)
    plt.show()

    exec_.shutdown()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
