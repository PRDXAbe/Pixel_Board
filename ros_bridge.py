#!/usr/bin/env python3
"""
ros_bridge.py
=============
Subscribes to /scan, processes touch detections, and emits one
newline-delimited JSON object per scan frame to stdout.

This is the data bridge between ROS2 and the Kotlin Compose UI.

JSON schema (one line per scan):
  {
    "scan_pts":  [[x, y], ...],     // all valid scan points, metres
    "board_pts": [[x, y], ...],     // board-filtered points, metres
    "touches":   [{"px":960,"py":540,"mx":0.55,"my":0.00}, ...],
    "scan_count": 1042,
    "rate_hz":    9.8,
    "board_min_x": 0.05,
    "board_max_x": 1.05,
    "board_min_y": -0.25,
    "board_max_y":  0.25
  }
"""

import json
import math
import pathlib
import sys
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import LaserScan

# ── Config ────────────────────────────────────────────────────────────────────

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

BOARD_MIN_X     = _cfg["board_min_x"]
BOARD_MAX_X     = _cfg["board_max_x"]
BOARD_MIN_Y     = _cfg["board_min_y"]
BOARD_MAX_Y     = _cfg["board_max_y"]
BOARD_W_MM      = int(_cfg["board_width_mm"])   # pixel width  = board width in mm
BOARD_H_MM      = int(_cfg["board_height_mm"])  # pixel height = board height in mm
CLUSTER_DIST    = _cfg["cluster_dist"]
MIN_PTS         = _cfg["min_pts"]
MATCH_RADIUS    = _cfg["match_radius"]
FORGET_FRAMES   = _cfg["forget_frames"]
RECOUNT_FRAMES  = _cfg["recount_frames"]

# ── Coordinate mapping ────────────────────────────────────────────────────────

def physical_to_pixel(x: float, y: float) -> tuple[int, int]:
    """
    Map a physical LIDAR coordinate (metres) to a board pixel coordinate (mm).

    Output range:
      px  in [0, BOARD_W_MM]   — 0 = left edge, BOARD_W_MM = right edge
      py  in [0, BOARD_H_MM]   — 0 = top edge,  BOARD_H_MM = bottom edge

    LIDAR X (depth) maps to board width.
    LIDAR Y (lateral) maps to board height; Y is flipped so positive LIDAR Y
    = left side of board = low pixel Y.
    """
    board_w_m = BOARD_MAX_X - BOARD_MIN_X  # board width  in metres
    board_h_m = BOARD_MAX_Y - BOARD_MIN_Y  # board height in metres

    nx = (x - BOARD_MIN_X) / board_w_m          # 0..1 along width
    ny = 1.0 - (y - BOARD_MIN_Y) / board_h_m    # 0..1 along height (flip Y)

    px = int(round(nx * BOARD_W_MM))
    py = int(round(ny * BOARD_H_MM))

    px = max(0, min(BOARD_W_MM, px))
    py = max(0, min(BOARD_H_MM, py))
    return px, py

# ── Processing helpers ─────────────────────────────────────────────────────────

def filter_to_board(xs, ys):
    bxs, bys = [], []
    for x, y in zip(xs, ys):
        if BOARD_MIN_X <= x <= BOARD_MAX_X and BOARD_MIN_Y <= y <= BOARD_MAX_Y:
            bxs.append(x)
            bys.append(y)
    return bxs, bys


def cluster_points(xs, ys):
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
    def __init__(self):
        self.tracks: list[dict] = []

    def update(self, centroids):
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


# ── ROS2 node ─────────────────────────────────────────────────────────────────

class BridgeNode(Node):
    def __init__(self):
        super().__init__("ros_bridge")
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.scan_xs: list[float] = []
        self.scan_ys: list[float] = []
        self.scan_count = 0
        self._last_time = time.monotonic()
        self._rate_hz   = 0.0
        self.new_frame  = False
        self.create_subscription(LaserScan, "/scan", self._on_scan, qos)

    def _on_scan(self, msg: LaserScan):
        now = time.monotonic()
        dt  = now - self._last_time
        if dt > 0:
            self._rate_hz = 0.8 * self._rate_hz + 0.2 * (1.0 / dt)
        self._last_time = now

        xs, ys = [], []
        for i, r in enumerate(msg.ranges):
            if math.isnan(r) or math.isinf(r):
                continue
            if r < msg.range_min or r > msg.range_max:
                continue
            theta = msg.angle_min + i * msg.angle_increment
            xs.append(r * math.cos(theta))
            ys.append(r * math.sin(theta))

        self.scan_xs    = xs
        self.scan_ys    = ys
        self.scan_count += 1
        self.new_frame  = True

    @property
    def rate_hz(self):
        return self._rate_hz


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    rclpy.init()
    node    = BridgeNode()
    exec_   = SingleThreadedExecutor()
    tracker = TouchTracker()
    exec_.add_node(node)

    # Flush stdout immediately (important for pipe to Kotlin)
    sys.stdout.reconfigure(line_buffering=True)

    try:
        while rclpy.ok():
            exec_.spin_once(timeout_sec=0.02)

            if not node.new_frame:
                continue
            node.new_frame = False

            xs, ys = node.scan_xs, node.scan_ys
            bxs, bys = filter_to_board(xs, ys)
            centroids = cluster_points(bxs, bys)
            touches   = tracker.update(centroids)

            out = {
                "scan_pts":   [[round(x, 4), round(y, 4)] for x, y in zip(xs, ys)],
                "board_pts":  [[round(x, 4), round(y, 4)] for x, y in zip(bxs, bys)],
                "touches": [
                    {
                        "px": physical_to_pixel(cx, cy)[0],
                        "py": physical_to_pixel(cx, cy)[1],
                        "mx": round(cx, 4),
                        "my": round(cy, 4),
                    }
                    for cx, cy in touches
                ],
                "scan_count":      node.scan_count,
                "rate_hz":         round(node.rate_hz, 1),
                "board_min_x":     BOARD_MIN_X,
                "board_max_x":     BOARD_MAX_X,
                "board_min_y":     BOARD_MIN_Y,
                "board_max_y":     BOARD_MAX_Y,
                "board_width_mm":  BOARD_W_MM,
                "board_height_mm": BOARD_H_MM,
            }
            print(json.dumps(out), flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        exec_.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
