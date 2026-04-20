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
import statistics
import sys
import time
from collections import defaultdict

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
    "mount_mode":     "side_edge",
    "invert_scan_x":  False,
    "invert_scan_y":  True,
    "touch_bias_radial_m": 0.00,
    "touch_bias_x_m": 0.03,
    "touch_bias_y_m": 0.00,
    "touch_detection_margin_near_m": 0.00,
    "touch_detection_margin_far_m": 0.00,
    "touch_detection_margin_y_m": 0.00,
    "background_calibration_frames": 20,
    "background_cell_size": 0.010,
    "background_neighbor_cells": 0,
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
    "dynamic_persist_frames": 3,
    "dynamic_point_limit": 120,
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
MOUNT_MODE      = str(_cfg["mount_mode"]).lower()
INVERT_SCAN_X   = bool(_cfg["invert_scan_x"])
INVERT_SCAN_Y   = bool(_cfg["invert_scan_y"])
TOUCH_BIAS_RADIAL_M = float(_cfg["touch_bias_radial_m"])
TOUCH_BIAS_X_M  = float(_cfg["touch_bias_x_m"])
TOUCH_BIAS_Y_M  = float(_cfg["touch_bias_y_m"])
TOUCH_MARGIN_NEAR_M = float(_cfg["touch_detection_margin_near_m"])
TOUCH_MARGIN_FAR_M  = float(_cfg["touch_detection_margin_far_m"])
TOUCH_MARGIN_Y_M    = float(_cfg["touch_detection_margin_y_m"])
BACKGROUND_CAL_FRAMES = max(0, int(_cfg["background_calibration_frames"]))
BACKGROUND_CELL_SIZE  = float(_cfg["background_cell_size"])
BACKGROUND_NEIGHBOR_CELLS = max(0, int(_cfg["background_neighbor_cells"]))
CLUSTER_DIST    = _cfg["cluster_dist"]
MIN_PTS         = _cfg["min_pts"]
MATCH_RADIUS    = _cfg["match_radius"]
FORGET_FRAMES   = _cfg["forget_frames"]
RECOUNT_FRAMES  = _cfg["recount_frames"]
TOUCH_SMOOTHING_ALPHA = max(0.0, min(1.0, float(_cfg["touch_smoothing_alpha"])))
TOUCH_FAST_ALPHA = max(TOUCH_SMOOTHING_ALPHA, min(1.0, float(_cfg["touch_fast_alpha"])))
TOUCH_HOLD_FRAMES = max(0, int(_cfg["touch_hold_frames"]))
TOUCH_CONFIRM_FRAMES = max(1, int(_cfg["touch_confirm_frames"]))
TOUCH_HISTORY_FRAMES = max(1, int(_cfg["touch_history_frames"]))
TOUCH_MAX_STEP_M = max(0.001, float(_cfg["touch_max_step_m"]))
TOUCH_STATIONARY_RADIUS_M = max(0.0, float(_cfg["touch_stationary_radius_m"]))
DYNAMIC_PERSIST_FRAMES = max(1, int(_cfg["dynamic_persist_frames"]))
DYNAMIC_POINT_LIMIT = max(1, int(_cfg["dynamic_point_limit"]))

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
    if MOUNT_MODE == "bottom_center":
        board_depth_m = BOARD_MAX_X - BOARD_MIN_X   # bottom edge -> top edge
        board_width_m = BOARD_MAX_Y - BOARD_MIN_Y   # left edge   -> right edge

        # Positive LiDAR Y is treated as board-left for this mount, so
        # pixel X decreases as Y increases.
        nx = (BOARD_MAX_Y - y) / board_width_m      # 0..1 left -> right
        ny = 1.0 - (x - BOARD_MIN_X) / board_depth_m  # 0..1 top -> bottom
    else:
        board_w_m = BOARD_MAX_X - BOARD_MIN_X  # board width  in metres
        board_h_m = BOARD_MAX_Y - BOARD_MIN_Y  # board height in metres

        nx = (x - BOARD_MIN_X) / board_w_m          # 0..1 along width
        ny = 1.0 - (y - BOARD_MIN_Y) / board_h_m    # 0..1 along height (flip Y)

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

# ── Processing helpers ─────────────────────────────────────────────────────────

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
                # For a bottom-mounted sensor, the visible finger surface sits
                # closer to the LiDAR than the actual contact point. Using the
                # leading edge of the cluster is more stable than the centroid
                # when the finger angle changes.
                far_x = max(x for x, _ in member_pts)
                edge_band = max(0.018, CLUSTER_DIST * 0.35)
                edge_pts = [(x, y) for x, y in member_pts if far_x - x <= edge_band]
                touch_x = float(statistics.median(x for x, _ in edge_pts))
                touch_y = float(statistics.median(y for _, y in edge_pts))
                clusters.append((touch_x, touch_y))
            else:
                touch_x = float(statistics.median(x for x, _ in member_pts))
                touch_y = float(statistics.median(y for _, y in member_pts))
                clusters.append((touch_x, touch_y))
    return clusters


def sample_points(xs, ys, limit: int):
    if limit <= 0 or len(xs) <= limit:
        return [[round(x, 4), round(y, 4)] for x, y in zip(xs, ys)]

    if limit == 1:
        mid = len(xs) // 2
        return [[round(xs[mid], 4), round(ys[mid], 4)]]

    step = (len(xs) - 1) / float(limit - 1)
    sampled = []
    last_idx = -1
    for i in range(limit):
        idx = int(round(i * step))
        if idx == last_idx:
            continue
        sampled.append([round(xs[idx], 4), round(ys[idx], 4)])
        last_idx = idx
    return sampled


class BackgroundModel:
    """
    Learns the empty-board scan for the first few frames and suppresses those
    static returns afterward. This keeps the board surface from being mistaken
    for touch clusters when nothing is on the board.
    """

    def __init__(self):
        self.frames_seen = 0
        self._counts: dict[tuple[int, int], int] = defaultdict(int)
        self._background_cells: set[tuple[int, int]] = set()

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return (
            int(round(x / BACKGROUND_CELL_SIZE)),
            int(round(y / BACKGROUND_CELL_SIZE)),
        )

    @property
    def ready(self) -> bool:
        return self.frames_seen >= BACKGROUND_CAL_FRAMES

    def update(self, xs, ys):
        if self.ready:
            return
        self.frames_seen += 1
        for x, y in zip(xs, ys):
            self._counts[self._cell(x, y)] += 1
        if self.ready:
            min_hits = max(2, int(BACKGROUND_CAL_FRAMES * 0.35))
            self._background_cells = {
                cell for cell, hits in self._counts.items() if hits >= min_hits
            }

    def filter_dynamic(self, xs, ys):
        if not self.ready:
            return [], []

        dxs, dys = [], []
        for x, y in zip(xs, ys):
            cx, cy = self._cell(x, y)
            is_background = False
            for ox in range(-BACKGROUND_NEIGHBOR_CELLS, BACKGROUND_NEIGHBOR_CELLS + 1):
                for oy in range(-BACKGROUND_NEIGHBOR_CELLS, BACKGROUND_NEIGHBOR_CELLS + 1):
                    if (cx + ox, cy + oy) in self._background_cells:
                        is_background = True
                        break
                if is_background:
                    break
            if not is_background:
                dxs.append(x)
                dys.append(y)
        return dxs, dys


class DynamicPointTrail:
    """
    Keeps recent dynamic board returns alive for a few frames so single-frame
    transients remain visible on the canvas.
    """

    def __init__(self):
        self.points: list[dict] = []

    def update(self, xs, ys):
        kept = []
        for p in self.points:
            p["ttl"] -= 1
            if p["ttl"] > 0:
                kept.append(p)

        for x, y in zip(xs, ys):
            kept.append({"x": x, "y": y, "ttl": DYNAMIC_PERSIST_FRAMES})

        if len(kept) > DYNAMIC_POINT_LIMIT:
            kept = kept[-DYNAMIC_POINT_LIMIT:]

        self.points = kept
        return [(p["x"], p["y"]) for p in self.points]


class TouchTracker:
    def __init__(self):
        self.tracks: list[dict] = []
        self._next_id = 1

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
                if best_t["absent"] > 0:
                    # Reacquired tracks should not keep dragging stale samples
                    # forward; that is a major source of hover lag/teleporting
                    # on a 10 Hz sensor.
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
                    "id": self._next_id,
                    "x": cx,
                    "y": cy,
                    "present": True,
                    "absent": 0,
                    "hits": 1,
                    "history": [(cx, cy)],
                })
                self._next_id += 1

        for t in self.tracks:
            if not t["present"]:
                t["absent"] += 1
                if t["absent"] >= RECOUNT_FRAMES:
                    t["hits"] = 0
        self.tracks = [t for t in self.tracks if t["absent"] < FORGET_FRAMES]
        return [
            (t["id"], t["x"], t["y"])
            for t in self.tracks
            if t["hits"] >= TOUCH_CONFIRM_FRAMES and (t["present"] or t["absent"] <= TOUCH_HOLD_FRAMES)
        ]


# ── ROS2 node ─────────────────────────────────────────────────────────────────

class BridgeNode(Node):
    def __init__(self):
        super().__init__("ros_bridge")
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
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
            x, y = polar_to_xy(r, theta)
            xs.append(x)
            ys.append(y)

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
    background = BackgroundModel()
    dynamic_trail = DynamicPointTrail()
    exec_.add_node(node)

    # Flush stdout immediately (important for pipe to Kotlin)
    sys.stdout.reconfigure(line_buffering=True)

    try:
        while rclpy.ok():
            exec_.spin_once(timeout_sec=0.005)

            if not node.new_frame:
                continue
            node.new_frame = False

            xs, ys = node.scan_xs, node.scan_ys
            bxs, bys = filter_to_board(xs, ys)
            zxs, zys = filter_to_touch_zone(xs, ys)
            background.update(zxs, zys)
            dyn_xs, dyn_ys = background.filter_dynamic(zxs, zys)
            dyn_bxs, dyn_bys = filter_to_board(dyn_xs, dyn_ys)
            visible_dyn_pts = dynamic_trail.update(dyn_bxs, dyn_bys)
            centroids = cluster_points(dyn_bxs, dyn_bys)
            touches   = tracker.update(centroids)

            visible_touches = []
            for touch_id, cx, cy in touches:
                tx, ty = estimate_touch_contact(cx, cy)
                if not is_inside_board(tx, ty):
                    continue
                px, py = physical_to_pixel(tx, ty)
                visible_touches.append(
                    {
                        "id": touch_id,
                        "px": px,
                        "py": py,
                        "mx": round(tx, 4),
                        "my": round(ty, 4),
                    }
                )

            out = {
                "scan_pts":   sample_points(xs, ys, 360),
                "board_pts":  sample_points(
                    [x for x, _ in visible_dyn_pts],
                    [y for _, y in visible_dyn_pts],
                    DYNAMIC_POINT_LIMIT,
                ),
                "touches":    visible_touches,
                "scan_count":      node.scan_count,
                "rate_hz":         round(node.rate_hz, 1),
                "board_min_x":     BOARD_MIN_X,
                "board_max_x":     BOARD_MAX_X,
                "board_min_y":     BOARD_MIN_Y,
                "board_max_y":     BOARD_MAX_Y,
                "board_width_mm":  BOARD_W_MM,
                "board_height_mm": BOARD_H_MM,
                "mount_mode":      MOUNT_MODE,
            }
            print(json.dumps(out, separators=(",", ":")), flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        exec_.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
