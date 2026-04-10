#!/usr/bin/env python3
"""
touch_output.py
===============
Detects finger touches on the Magic Board via LIDAR and prints the
corresponding screen pixel coordinate to stdout.

How to run:
  # Terminal 1 — LIDAR driver
  source rw/install/setup.bash
  ros2 launch ldlidar_stl_ros2 ld19.launch.py

  # Terminal 2 — this script
  source rw/install/setup.bash
  python3 touch_output.py

Output format (one line per touch detected per scan):
  TOUCH  finger=1  pixel=(960, 540)  physical=(0.550m, 0.000m)
"""

import json
import math
import pathlib
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import LaserScan

# ══════════════════════════════════════════════════════════════════════════════
#  BOARD CONFIG  (mirrors board_config.json)
# ══════════════════════════════════════════════════════════════════════════════
_CONFIG_PATH = pathlib.Path(__file__).parent / "board_config.json"

_DEFAULTS = {
    "board_min_x":    0.050,
    "board_max_x":    1.050,
    "board_min_y":   -0.250,
    "board_max_y":    0.250,
    "board_width_mm":  1000,
    "board_height_mm":  500,
    "cluster_dist":   0.08,
    "min_pts":        2,
    "match_radius":   0.20,
    "forget_frames":  25,
    "recount_frames": 8,
}


def _load_config() -> dict:
    cfg = dict(_DEFAULTS)
    if _CONFIG_PATH.exists():
        raw = json.loads(_CONFIG_PATH.read_text())
        raw.pop("_comment", None)
        cfg.update({k: v for k, v in raw.items() if k in _DEFAULTS})
    return cfg


_cfg = _load_config()

BOARD_MIN_X    = _cfg["board_min_x"]
BOARD_MAX_X    = _cfg["board_max_x"]
BOARD_MIN_Y    = _cfg["board_min_y"]
BOARD_MAX_Y    = _cfg["board_max_y"]
BOARD_W_MM     = int(_cfg["board_width_mm"])   # pixel width  = board width in mm
BOARD_H_MM     = int(_cfg["board_height_mm"])  # pixel height = board height in mm
CLUSTER_DIST   = _cfg["cluster_dist"]
MIN_PTS        = _cfg["min_pts"]
MATCH_RADIUS   = _cfg["match_radius"]
FORGET_FRAMES  = _cfg["forget_frames"]
RECOUNT_FRAMES = _cfg["recount_frames"]

# ══════════════════════════════════════════════════════════════════════════════


def physical_to_pixel(x: float, y: float) -> tuple[int, int]:
    """
    Map physical LIDAR coordinate (metres) to board pixel coordinate (mm).
    Output: (0,0) = board top-left, (BOARD_W_MM, BOARD_H_MM) = bottom-right.
    """
    board_w_m = BOARD_MAX_X - BOARD_MIN_X
    board_h_m = BOARD_MAX_Y - BOARD_MIN_Y
    nx = (x - BOARD_MIN_X) / board_w_m
    ny = 1.0 - (y - BOARD_MIN_Y) / board_h_m   # flip Y
    px = int(round(nx * BOARD_W_MM))
    py = int(round(ny * BOARD_H_MM))
    px = max(0, min(BOARD_W_MM, px))
    py = max(0, min(BOARD_H_MM, py))
    return px, py


# ── Helpers (same logic as magic_board_live.py) ───────────────────────────────

def filter_to_board(xs, ys):
    bxs, bys = [], []
    for x, y in zip(xs, ys):
        if BOARD_MIN_X <= x <= BOARD_MAX_X and BOARD_MIN_Y <= y <= BOARD_MAX_Y:
            bxs.append(x)
            bys.append(y)
    return bxs, bys


def cluster_points(xs, ys):
    """Single-pass Euclidean clustering. Returns list of (cx, cy) centroids."""
    if not xs:
        return []
    pts  = list(zip(xs, ys))
    used = [False] * len(pts)
    clusters = []
    for i, (px, py) in enumerate(pts):
        if used[i]:
            continue
        members = [i]
        used[i] = True
        for j in range(i + 1, len(pts)):
            if used[j]:
                continue
            if math.hypot(pts[j][0] - px, pts[j][1] - py) < CLUSTER_DIST:
                members.append(j)
                used[j] = True
        if len(members) >= MIN_PTS:
            mx = sum(pts[k][0] for k in members) / len(members)
            my = sum(pts[k][1] for k in members) / len(members)
            clusters.append((mx, my))
    return clusters


class TouchTracker:
    """
    Wraps the same absent/present logic as BallTracker so that we only
    print a TOUCH line when a *stable* cluster is visible (not fleeting noise).
    """

    def __init__(self):
        self.tracks: list[dict] = []

    def update(self, centroids: list[tuple]) -> list[tuple]:
        """Returns list of (cx, cy) for currently visible stable touches."""
        for t in self.tracks:
            t["present"] = False

        for cx, cy in centroids:
            best_d, best_t = MATCH_RADIUS, None
            for t in self.tracks:
                d = math.hypot(cx - t["x"], cy - t["y"])
                if d < best_d:
                    best_d, best_t = d, t
            if best_t is not None:
                best_t["x"], best_t["y"] = cx, cy
                best_t["present"] = True
                best_t["absent"]  = 0
            else:
                self.tracks.append({"x": cx, "y": cy, "present": True, "absent": 0})

        for t in self.tracks:
            if not t["present"]:
                t["absent"] += 1
        self.tracks = [t for t in self.tracks if t["absent"] < FORGET_FRAMES]

        return [(t["x"], t["y"]) for t in self.tracks if t["present"]]


# ── ROS2 scan subscriber ───────────────────────────────────────────────────────

class TouchNode(Node):
    def __init__(self):
        super().__init__("touch_output")
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.scan_xs: list[float] = []
        self.scan_ys: list[float] = []
        self.create_subscription(LaserScan, "/scan", self._on_scan, qos)
        self.get_logger().info(
            f"touch_output: board={BOARD_W_MM}x{BOARD_H_MM} mm  "
            f"LIDAR X:[{BOARD_MIN_X:.3f},{BOARD_MAX_X:.3f}] Y:[{BOARD_MIN_Y:.3f},{BOARD_MAX_Y:.3f}] m"
        )

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


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    rclpy.init()
    node    = TouchNode()
    exec_   = SingleThreadedExecutor()
    tracker = TouchTracker()
    exec_.add_node(node)

    print()
    print(f"  Magic Board Touch Output  |  Board {BOARD_W_MM}×{BOARD_H_MM} mm")
    print(f"  LIDAR: X[{BOARD_MIN_X:.3f}…{BOARD_MAX_X:.3f}]  "
          f"Y[{BOARD_MIN_Y:.3f}…{BOARD_MAX_Y:.3f}]  (metres)")
    print("-" * 60)

    last_pixels: list[tuple] = []

    try:
        while rclpy.ok():
            exec_.spin_once(timeout_sec=0.02)

            bxs, bys = filter_to_board(node.scan_xs, node.scan_ys)
            centroids = cluster_points(bxs, bys)
            touches   = tracker.update(centroids)

            # Only reprint when the touch state actually changes
            current_pixels = [physical_to_pixel(cx, cy) for cx, cy in touches]
            if current_pixels != last_pixels:
                if current_pixels:
                    for i, ((cx, cy), (px, py)) in enumerate(
                        zip(touches, current_pixels), start=1
                    ):
                        print(
                            f"TOUCH  finger={i}"
                            f"  pixel=({px:4d}, {py:4d})"
                            f"  physical=({cx:.3f}m, {cy:+.3f}m)"
                        )
                else:
                    print("(no touch)")
                last_pixels = current_pixels

    except KeyboardInterrupt:
        pass
    finally:
        exec_.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
