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
import statistics
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
    "mount_mode":     "side_edge",
    "invert_scan_x":  False,
    "invert_scan_y":  True,
    "touch_bias_radial_m": 0.00,
    "touch_bias_x_m": 0.03,
    "touch_bias_y_m": 0.00,
    "touch_detection_margin_near_m": 0.00,
    "touch_detection_margin_far_m": 0.00,
    "touch_detection_margin_y_m": 0.00,
    "cluster_dist":   0.055,
    "min_pts":        2,
    "match_radius":   0.075,
    "forget_frames":  12,
    "recount_frames": 5,
    "touch_smoothing_alpha": 0.12,
    "touch_fast_alpha": 0.30,
    "touch_hold_frames": 4,
    "touch_confirm_frames": 2,
    "touch_history_frames": 5,
    "touch_max_step_m": 0.024,
    "touch_stationary_radius_m": 0.006,
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
MOUNT_MODE     = str(_cfg["mount_mode"]).lower()
INVERT_SCAN_X  = bool(_cfg["invert_scan_x"])
INVERT_SCAN_Y  = bool(_cfg["invert_scan_y"])
TOUCH_BIAS_RADIAL_M = float(_cfg["touch_bias_radial_m"])
TOUCH_BIAS_X_M = float(_cfg["touch_bias_x_m"])
TOUCH_BIAS_Y_M = float(_cfg["touch_bias_y_m"])
TOUCH_MARGIN_NEAR_M = float(_cfg["touch_detection_margin_near_m"])
TOUCH_MARGIN_FAR_M  = float(_cfg["touch_detection_margin_far_m"])
TOUCH_MARGIN_Y_M    = float(_cfg["touch_detection_margin_y_m"])
CLUSTER_DIST   = _cfg["cluster_dist"]
MIN_PTS        = _cfg["min_pts"]
MATCH_RADIUS   = _cfg["match_radius"]
FORGET_FRAMES  = _cfg["forget_frames"]
RECOUNT_FRAMES = _cfg["recount_frames"]
TOUCH_SMOOTHING_ALPHA = max(0.0, min(1.0, float(_cfg["touch_smoothing_alpha"])))
TOUCH_FAST_ALPHA = max(TOUCH_SMOOTHING_ALPHA, min(1.0, float(_cfg["touch_fast_alpha"])))
TOUCH_HOLD_FRAMES = max(0, int(_cfg["touch_hold_frames"]))
TOUCH_CONFIRM_FRAMES = max(1, int(_cfg["touch_confirm_frames"]))
TOUCH_HISTORY_FRAMES = max(1, int(_cfg["touch_history_frames"]))
TOUCH_MAX_STEP_M = max(0.001, float(_cfg["touch_max_step_m"]))
TOUCH_STATIONARY_RADIUS_M = max(0.0, float(_cfg["touch_stationary_radius_m"]))

# ══════════════════════════════════════════════════════════════════════════════


def physical_to_pixel(x: float, y: float) -> tuple[int, int]:
    """
    Map physical LIDAR coordinate (metres) to board pixel coordinate (mm).
    Output: (0,0) = board top-left, (BOARD_W_MM, BOARD_H_MM) = bottom-right.
    """
    if MOUNT_MODE == "bottom_center":
        board_depth_m = BOARD_MAX_X - BOARD_MIN_X
        board_width_m = BOARD_MAX_Y - BOARD_MIN_Y
        nx = (BOARD_MAX_Y - y) / board_width_m
        ny = 1.0 - (x - BOARD_MIN_X) / board_depth_m
    else:
        board_w_m = BOARD_MAX_X - BOARD_MIN_X
        board_h_m = BOARD_MAX_Y - BOARD_MIN_Y
        nx = (x - BOARD_MIN_X) / board_w_m
        ny = 1.0 - (y - BOARD_MIN_Y) / board_h_m   # flip Y
    px = int(round(nx * BOARD_W_MM))
    py = int(round(ny * BOARD_H_MM))
    px = max(0, min(BOARD_W_MM, px))
    py = max(0, min(BOARD_H_MM, py))
    return px, py


def polar_to_xy(r: float, theta: float) -> tuple[float, float]:
    x = r * math.cos(theta)
    y = r * math.sin(theta)
    if INVERT_SCAN_X:
        x = -x
    if INVERT_SCAN_Y:
        y = -y
    return x, y


def depth_scaled_touch_bias_x(x: float) -> float:
    if MOUNT_MODE != "bottom_center":
        return TOUCH_BIAS_X_M

    board_depth_m = max(1e-6, BOARD_MAX_X - BOARD_MIN_X)
    depth_t = (x - BOARD_MIN_X) / board_depth_m
    depth_t = max(0.0, min(1.0, depth_t))

    # Near the LiDAR we want very little push; near the far edge we need more
    # because the laser usually hits the near face of the finger.
    return TOUCH_BIAS_X_M * (0.1 + 1.4 * depth_t)


def estimate_touch_contact(x: float, y: float) -> tuple[float, float]:
    if TOUCH_BIAS_RADIAL_M:
        radius = math.hypot(x, y)
        if radius > 1e-6:
            scale = TOUCH_BIAS_RADIAL_M / radius
            x += x * scale
            y += y * scale
    return x + depth_scaled_touch_bias_x(x), y + TOUCH_BIAS_Y_M


# ── Helpers (same logic as magic_board_live.py) ───────────────────────────────

def is_inside_board(x: float, y: float) -> bool:
    return BOARD_MIN_X <= x <= BOARD_MAX_X and BOARD_MIN_Y <= y <= BOARD_MAX_Y

def filter_to_board(xs, ys):
    bxs, bys = [], []
    for x, y in zip(xs, ys):
        if is_inside_board(x, y):
            bxs.append(x)
            bys.append(y)
    return bxs, bys


def filter_to_touch_zone(xs, ys):
    min_x = BOARD_MIN_X - TOUCH_MARGIN_NEAR_M
    max_x = BOARD_MAX_X + TOUCH_MARGIN_FAR_M
    min_y = BOARD_MIN_Y - TOUCH_MARGIN_Y_M
    max_y = BOARD_MAX_Y + TOUCH_MARGIN_Y_M

    zxs, zys = [], []
    for x, y in zip(xs, ys):
        if min_x <= x <= max_x and min_y <= y <= max_y:
            zxs.append(x)
            zys.append(y)
    return zxs, zys


def cluster_points(xs, ys):
    """Single-pass Euclidean clustering. Returns list of (cx, cy) centroids."""
    if not xs:
        return []
    pts  = list(zip(xs, ys))
    used = [False] * len(pts)
    clusters = []
    for i in range(len(pts)):
        if used[i]:
            continue
        stack = [i]
        members = []
        used[i] = True
        while stack:
            idx = stack.pop()
            members.append(idx)
            px, py = pts[idx]
            for j, (qx, qy) in enumerate(pts):
                if used[j]:
                    continue
                if math.hypot(qx - px, qy - py) < CLUSTER_DIST:
                    used[j] = True
                    stack.append(j)
        if len(members) >= MIN_PTS:
            member_pts = [pts[k] for k in members]
            if MOUNT_MODE == "bottom_center":
                far_x = max(x for x, _ in member_pts)
                edge_band = max(0.012, CLUSTER_DIST * 0.25)
                edge_pts = [(x, y) for x, y in member_pts if far_x - x <= edge_band]
                touch_x = float(statistics.median(x for x, _ in edge_pts))
                touch_y = float(statistics.median(y for _, y in edge_pts))
                clusters.append((touch_x, touch_y))
            else:
                touch_x = float(statistics.median(x for x, _ in member_pts))
                touch_y = float(statistics.median(y for _, y in member_pts))
                clusters.append((touch_x, touch_y))
    return clusters


class TouchTracker:
    """
    Wraps the same absent/present logic as BallTracker so that we only
    print a TOUCH line when a *stable* cluster is visible (not fleeting noise).
    """

    def __init__(self):
        self.tracks: list[dict] = []

    def _append_history(self, track: dict, cx: float, cy: float):
        history = track.setdefault("history", [])
        history.append((cx, cy))
        if len(history) > TOUCH_HISTORY_FRAMES:
            del history[:-TOUCH_HISTORY_FRAMES]
        return history

    def _history_target(self, track: dict) -> tuple[float, float]:
        history = track.get("history") or [(track["x"], track["y"])]
        return (
            float(statistics.median(x for x, _ in history)),
            float(statistics.median(y for _, y in history)),
        )

    def _history_motion_metrics(self, track: dict) -> tuple[float, float]:
        history = track.get("history") or [(track["x"], track["y"])]
        if len(history) < 2:
            return 0.0, 0.0

        path = 0.0
        for (ax, ay), (bx, by) in zip(history, history[1:]):
            path += math.hypot(bx - ax, by - ay)

        start_x, start_y = history[0]
        end_x, end_y = history[-1]
        net = math.hypot(end_x - start_x, end_y - start_y)
        coherence = net / path if path > 1e-9 else 0.0
        return net, coherence

    def _target_for_track(self, track: dict) -> tuple[float, float, bool, float]:
        history = track.get("history") or [(track["x"], track["y"])]
        motion_span, motion_coherence = self._history_motion_metrics(track)
        if motion_span >= TOUCH_STATIONARY_RADIUS_M and motion_coherence >= 0.65:
            tx, ty = history[-1]
            return tx, ty, True, motion_span

        tx, ty = self._history_target(track)
        return tx, ty, False, motion_span

    def _move_towards_target(self, track: dict, tx: float, ty: float, *, prefer_fast: bool, motion_span: float):
        dx = tx - track["x"]
        dy = ty - track["y"]
        raw_dist = math.hypot(dx, dy)
        dist = raw_dist
        if dist > TOUCH_MAX_STEP_M:
            scale = TOUCH_MAX_STEP_M / dist
            tx = track["x"] + dx * scale
            ty = track["y"] + dy * scale
            dx = tx - track["x"]
            dy = ty - track["y"]
            dist = math.hypot(dx, dy)

        if dist <= TOUCH_STATIONARY_RADIUS_M and not prefer_fast:
            return

        alpha = TOUCH_SMOOTHING_ALPHA
        if prefer_fast and TOUCH_FAST_ALPHA > alpha:
            accel_scale = max(TOUCH_STATIONARY_RADIUS_M * 2.0, 1e-6)
            motion_t = min(1.0, max(raw_dist, motion_span) / accel_scale)
            alpha = alpha + (TOUCH_FAST_ALPHA - alpha) * motion_t
        track["x"] = (1.0 - alpha) * track["x"] + alpha * tx
        track["y"] = (1.0 - alpha) * track["y"] + alpha * ty

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
                if best_t["absent"] > 0:
                    best_t["history"] = [(cx, cy)]
                    best_t["x"] = cx
                    best_t["y"] = cy
                else:
                    self._append_history(best_t, cx, cy)
                    target_x, target_y, prefer_fast, motion_span = self._target_for_track(best_t)
                    self._move_towards_target(
                        best_t,
                        target_x,
                        target_y,
                        prefer_fast=prefer_fast,
                        motion_span=motion_span,
                    )
                best_t["present"] = True
                best_t["absent"]  = 0
                best_t["hits"] = min(best_t["hits"] + 1, TOUCH_CONFIRM_FRAMES)
            else:
                self.tracks.append({
                    "x": cx,
                    "y": cy,
                    "present": True,
                    "absent": 0,
                    "hits": 1,
                    "history": [(cx, cy)],
                })

        for t in self.tracks:
            if not t["present"]:
                t["absent"] += 1
                if t["absent"] >= RECOUNT_FRAMES:
                    t["hits"] = 0
        self.tracks = [t for t in self.tracks if t["absent"] < FORGET_FRAMES]

        return [
            (t["x"], t["y"])
            for t in self.tracks
            if t["hits"] >= TOUCH_CONFIRM_FRAMES and (t["present"] or t["absent"] <= TOUCH_HOLD_FRAMES)
        ]


# ── ROS2 scan subscriber ───────────────────────────────────────────────────────

class TouchNode(Node):
    def __init__(self):
        super().__init__("touch_output")
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
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
            x, y = polar_to_xy(r, theta)
            xs.append(x)
            ys.append(y)
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

            zxs, zys = filter_to_touch_zone(node.scan_xs, node.scan_ys)
            bxs, bys = filter_to_board(zxs, zys)
            centroids = cluster_points(bxs, bys)
            touches   = tracker.update(centroids)

            # Only reprint when the touch state actually changes
            adjusted_touches = []
            for cx, cy in touches:
                tx, ty = estimate_touch_contact(cx, cy)
                if is_inside_board(tx, ty):
                    adjusted_touches.append((tx, ty))
            current_pixels = [physical_to_pixel(cx, cy) for cx, cy in adjusted_touches]
            if current_pixels != last_pixels:
                if current_pixels:
                    for i, ((cx, cy), (px, py)) in enumerate(
                        zip(adjusted_touches, current_pixels), start=1
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
