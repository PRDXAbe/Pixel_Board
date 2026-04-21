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
import os
import pathlib
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass

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
    "min_pts":        3,
    "match_radius":   0.075,
    "forget_frames":  6,
    "recount_frames": 3,
    "touch_smoothing_alpha": 0.12,
    "touch_fast_alpha": 0.30,
    "touch_hold_frames": 2,
    "touch_confirm_frames": 3,
    "touch_history_frames": 5,
    "touch_max_step_m": 0.024,
    "touch_stationary_radius_m": 0.006,
    "touch_hover_settle_frames": 3,
    "touch_hover_soft_radius_m": 0.003,
    "touch_hover_breakout_radius_m": 0.008,
    "touch_hover_soft_alpha": 0.10,
    "touch_hover_outlier_frames": 2,
    "touch_hover_min_confidence": 0.45,
    "touch_edge_band_m": 0.010,
    "touch_edge_max_points": 3,
    "touch_ridge_points": 2,
    "touch_ridge_max_span_y_m": 0.004,
    "touch_single_point_repeat_radius_m": 0.004,
    "touch_single_point_glide_alpha": 0.12,
    "touch_localize_min_quality": 0.55,
    "touch_weak_update_alpha": 0.07,
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
TOUCH_HOVER_SETTLE_FRAMES = max(1, int(_cfg["touch_hover_settle_frames"]))
TOUCH_HOVER_SOFT_RADIUS_M = max(0.0, float(_cfg["touch_hover_soft_radius_m"]))
TOUCH_HOVER_BREAKOUT_RADIUS_M = max(
    TOUCH_HOVER_SOFT_RADIUS_M,
    float(_cfg["touch_hover_breakout_radius_m"]),
)
TOUCH_HOVER_SOFT_ALPHA = max(0.0, min(1.0, float(_cfg["touch_hover_soft_alpha"])))
TOUCH_HOVER_OUTLIER_FRAMES = max(1, int(_cfg["touch_hover_outlier_frames"]))
TOUCH_HOVER_MIN_CONFIDENCE = max(0.0, min(1.0, float(_cfg["touch_hover_min_confidence"])))
TOUCH_EDGE_BAND_M = max(0.001, float(_cfg["touch_edge_band_m"]))
TOUCH_EDGE_MAX_POINTS = max(2, int(_cfg["touch_edge_max_points"]))
TOUCH_RIDGE_POINTS = max(2, int(_cfg["touch_ridge_points"]))
TOUCH_RIDGE_MAX_SPAN_Y_M = max(0.001, float(_cfg["touch_ridge_max_span_y_m"]))
TOUCH_SINGLE_POINT_REPEAT_RADIUS_M = max(0.001, float(_cfg["touch_single_point_repeat_radius_m"]))
TOUCH_SINGLE_POINT_GLIDE_ALPHA = max(0.0, min(1.0, float(_cfg["touch_single_point_glide_alpha"])))
TOUCH_LOCALIZE_MIN_QUALITY = max(0.0, min(1.0, float(_cfg["touch_localize_min_quality"])))
TOUCH_WEAK_UPDATE_ALPHA = max(0.0, min(1.0, float(_cfg["touch_weak_update_alpha"])))
DYNAMIC_PERSIST_FRAMES = max(1, int(_cfg["dynamic_persist_frames"]))
DYNAMIC_POINT_LIMIT = max(1, int(_cfg["dynamic_point_limit"]))
DIAGNOSTIC_LOG_PATH = os.environ.get("PIXELBOARD_DIAG_LOG_PATH", "").strip()
TOUCH_CONTINUITY_REPEAT_FRAMES = 2
SHORT_GAP_VISIBLE_FRAMES = max(TOUCH_HOLD_FRAMES, 3)

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
            cluster_span_y = 0.0
            if len(member_pts) > 1:
                cluster_span_y = max(y for _, y in member_pts) - min(y for _, y in member_pts)
            if MOUNT_MODE == "bottom_center":
                # For a bottom-mounted sensor, the visible front edge of the
                # finger is closer to the actual contact point than the rest of
                # the cluster. Use a tight front subset so nearby trailing
                # returns do not pull the touch estimate sideways.
                sorted_pts = sorted(member_pts, key=lambda pt: pt[0], reverse=True)
                far_x = sorted_pts[0][0]
                edge_pts = [(x, y) for x, y in sorted_pts if far_x - x <= TOUCH_EDGE_BAND_M]
                if not edge_pts:
                    edge_pts = [sorted_pts[0]]

                ridge_pts = [edge_pts[0]]
                for x, y in edge_pts[1:]:
                    next_min_y = min(pt[1] for pt in ridge_pts + [(x, y)])
                    next_max_y = max(pt[1] for pt in ridge_pts + [(x, y)])
                    if next_max_y - next_min_y <= TOUCH_RIDGE_MAX_SPAN_Y_M:
                        ridge_pts.append((x, y))
                    if len(ridge_pts) >= TOUCH_RIDGE_POINTS:
                        break

                position_pts = ridge_pts[: min(len(ridge_pts), TOUCH_RIDGE_POINTS)]
                edge_floor_x = min(x for x, _ in position_pts)
                edge_depth_span = far_x - edge_floor_x
                if edge_depth_span <= 1e-6:
                    edge_weights = [1.0] * len(position_pts)
                else:
                    edge_weights = [
                        1.0 + ((x - edge_floor_x) / edge_depth_span)
                        for x, _ in position_pts
                    ]
                weight_total = sum(edge_weights)
                touch_x = float(
                    sum(x * w for (x, _), w in zip(position_pts, edge_weights)) / max(weight_total, 1e-6)
                )
                touch_y = float(sum(y for _, y in position_pts) / max(len(position_pts), 1))
                edge_point_count = len(edge_pts)
                ridge_point_count = len(position_pts)
                edge_span_y = 0.0
                if len(edge_pts) > 1:
                    edge_span_y = max(y for _, y in edge_pts) - min(y for _, y in edge_pts)
                ridge_span_y = 0.0
                if len(position_pts) > 1:
                    ridge_span_y = max(y for _, y in position_pts) - min(y for _, y in position_pts)
            else:
                touch_x = float(statistics.median(x for x, _ in member_pts))
                touch_y = float(statistics.median(y for _, y in member_pts))
                edge_point_count = len(member_pts)
                edge_span_y = cluster_span_y
                edge_depth_span = 0.0
                ridge_point_count = len(member_pts)
                ridge_span_y = cluster_span_y

            point_score = min(1.0, len(member_pts) / float(max(MIN_PTS + 2, 4)))
            edge_score = min(1.0, edge_point_count / float(max(2, TOUCH_EDGE_MAX_POINTS)))
            span_score = min(1.0, cluster_span_y / max(0.006, CLUSTER_DIST * 0.20))
            edge_tightness_score = 1.0 - min(1.0, edge_depth_span / max(TOUCH_EDGE_BAND_M, 1e-6))
            edge_compact_score = 1.0 - min(1.0, edge_span_y / max(0.018, CLUSTER_DIST * 0.35))
            ridge_score = min(1.0, ridge_point_count / float(TOUCH_RIDGE_POINTS))
            ridge_compact_score = 1.0 - min(1.0, ridge_span_y / max(TOUCH_RIDGE_MAX_SPAN_Y_M, 1e-6))
            confidence = max(0.0, min(1.0, 0.5 * point_score + 0.3 * edge_score + 0.2 * span_score))
            if ridge_point_count >= TOUCH_RIDGE_POINTS:
                localization_quality = max(
                    0.0,
                    min(1.0, 0.45 * ridge_score + 0.30 * edge_tightness_score + 0.25 * ridge_compact_score),
                )
            else:
                localization_quality = max(
                    0.0,
                    min(0.49, 0.25 * ridge_score + 0.15 * edge_tightness_score + 0.10 * edge_compact_score),
                )
            clusters.append(
                {
                    "x": touch_x,
                    "y": touch_y,
                    "point_count": len(member_pts),
                    "edge_point_count": edge_point_count,
                    "ridge_point_count": ridge_point_count,
                    "ridge_points": [[float(x), float(y)] for x, y in position_pts],
                    "cluster_span_y": cluster_span_y,
                    "confidence": confidence,
                    "localization_quality": localization_quality,
                }
            )
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


def _diagnostic_point(x: float, y: float) -> list[float]:
    return [round(float(x), 4), round(float(y), 4)]


def _diagnostic_detection(detection) -> dict:
    if isinstance(detection, dict):
        ridge_points = detection.get("ridge_points", [])
        return {
            "x": round(float(detection.get("x", 0.0)), 4),
            "y": round(float(detection.get("y", 0.0)), 4),
            "confidence": round(float(detection.get("confidence", 0.0)), 3),
            "localization_quality": round(float(detection.get("localization_quality", 0.0)), 3),
            "point_count": int(detection.get("point_count", 0)),
            "edge_point_count": int(detection.get("edge_point_count", 0)),
            "ridge_point_count": int(detection.get("ridge_point_count", 0)),
            "cluster_span_y": round(float(detection.get("cluster_span_y", 0.0)), 4),
            "ridge_points": [
                _diagnostic_point(point[0], point[1])
                for point in ridge_points
                if len(point) >= 2
            ],
        }

    x, y = detection
    return {
        "x": round(float(x), 4),
        "y": round(float(y), 4),
        "confidence": 1.0,
        "localization_quality": 1.0,
        "point_count": 0,
        "edge_point_count": 0,
        "ridge_point_count": 0,
        "cluster_span_y": 0.0,
        "ridge_points": [_diagnostic_point(x, y)],
    }


@dataclass(frozen=True)
class TouchMeasurement:
    touch_id: int
    x: float
    y: float
    confidence: float
    localization_quality: float
    point_count: int
    edge_point_count: int
    ridge_point_count: int
    cluster_span_y: float
    ridge_points: tuple[tuple[float, float], ...]
    mode: str
    present: bool
    absent_frames: int
    confirmed: bool
    gap_held: bool
    hits: int


def _diagnostic_track(track: dict) -> dict:
    pending = track.get("pending_single_point")
    history = track.get("history", [])
    return {
        "id": int(track["id"]),
        "state": track.get("state", "settling"),
        "present": bool(track.get("present", False)),
        "absent": int(track.get("absent", 0)),
        "hits": int(track.get("hits", 0)),
        "stable_frames": int(track.get("stable_frames", 0)),
        "outlier_streak": int(track.get("outlier_streak", 0)),
        "x": round(float(track.get("x", 0.0)), 4),
        "y": round(float(track.get("y", 0.0)), 4),
        "anchor_x": round(float(track.get("anchor_x", track.get("x", 0.0))), 4),
        "anchor_y": round(float(track.get("anchor_y", track.get("y", 0.0))), 4),
        "history": [_diagnostic_point(x, y) for x, y in history],
        "pending_single_point": (
            None if pending is None else _diagnostic_point(pending["x"], pending["y"])
        ),
        "last_evidence": _diagnostic_detection(track["last_evidence"])
        if track.get("last_evidence") is not None
        else None,
    }


def build_diagnostic_entry(
    *,
    scan_count: int,
    rate_hz: float,
    raw_scan_point_count: int,
    touch_zone_point_count: int,
    dynamic_point_count: int,
    board_dynamic_point_count: int,
    visible_dynamic_point_count: int,
    centroids,
    tracker,
    visible_touches,
) -> dict:
    return {
        "timestamp_monotonic_s": round(time.monotonic(), 3),
        "scan_count": int(scan_count),
        "rate_hz": round(float(rate_hz), 1),
        "counts": {
            "scan_points": int(raw_scan_point_count),
            "touch_zone_points": int(touch_zone_point_count),
            "dynamic_points": int(dynamic_point_count),
            "board_dynamic_points": int(board_dynamic_point_count),
            "visible_dynamic_points": int(visible_dynamic_point_count),
            "centroids": len(centroids),
            "visible_touches": len(visible_touches),
            "tracks": len(tracker.tracks),
        },
        "centroids": [_diagnostic_detection(detection) for detection in centroids],
        "tracks": [_diagnostic_track(track) for track in tracker.tracks],
        "visible_touches": visible_touches,
    }


class DiagnosticLogger:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8", buffering=1)

    @classmethod
    def from_env(cls):
        if not DIAGNOSTIC_LOG_PATH:
            return None
        try:
            return cls(pathlib.Path(DIAGNOSTIC_LOG_PATH))
        except OSError as exc:
            print(
                f"ros_bridge: warning: unable to open diagnostic log at {DIAGNOSTIC_LOG_PATH}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return None

    def log_frame(
        self,
        *,
        scan_count: int,
        rate_hz: float,
        raw_scan_point_count: int,
        touch_zone_point_count: int,
        dynamic_point_count: int,
        board_dynamic_point_count: int,
        visible_dynamic_point_count: int,
        centroids,
        tracker,
        visible_touches,
    ):
        entry = build_diagnostic_entry(
            scan_count=scan_count,
            rate_hz=rate_hz,
            raw_scan_point_count=raw_scan_point_count,
            touch_zone_point_count=touch_zone_point_count,
            dynamic_point_count=dynamic_point_count,
            board_dynamic_point_count=board_dynamic_point_count,
            visible_dynamic_point_count=visible_dynamic_point_count,
            centroids=centroids,
            tracker=tracker,
            visible_touches=visible_touches,
        )
        self._handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def close(self):
        self._handle.close()


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


class TouchMeasurementTracker:
    def __init__(self):
        self.tracks: list[dict] = []
        self._next_id = 1

    def _has_strong_ridge(self, detection: dict) -> bool:
        return int(detection.get("ridge_point_count", 0)) >= TOUCH_RIDGE_POINTS

    def _measurement_mode(self, detection: dict) -> str:
        return "strong_ridge" if self._has_strong_ridge(detection) else "weak_ridge"

    def _normalize_detection(self, detection) -> dict:
        if isinstance(detection, dict):
            return {
                "x": float(detection["x"]),
                "y": float(detection["y"]),
                "confidence": max(0.0, min(1.0, float(detection.get("confidence", 1.0)))),
                "localization_quality": max(
                    0.0,
                    min(1.0, float(detection.get("localization_quality", detection.get("confidence", 1.0)))),
                ),
                "point_count": int(detection.get("point_count", 0)),
                "edge_point_count": int(detection.get("edge_point_count", 0)),
                "ridge_point_count": int(detection.get("ridge_point_count", detection.get("edge_point_count", 0))),
                "ridge_points": [
                    [float(pt[0]), float(pt[1])]
                    for pt in detection.get("ridge_points", [])
                    if len(pt) >= 2
                ],
                "cluster_span_y": float(detection.get("cluster_span_y", 0.0)),
            }
        cx, cy = detection
        return {
            "x": float(cx),
            "y": float(cy),
            "confidence": 1.0,
            "localization_quality": 1.0,
            "point_count": 0,
            "edge_point_count": 0,
            "ridge_point_count": TOUCH_RIDGE_POINTS,
            "ridge_points": [[float(cx), float(cy)]],
            "cluster_span_y": 0.0,
        }

    def _measurement_from_track(self, track: dict) -> TouchMeasurement | None:
        detection = track.get("last_evidence")
        if not detection:
            return None

        ridge_points = tuple(
            (float(point[0]), float(point[1]))
            for point in detection.get("ridge_points", [])
            if len(point) >= 2
        )
        return TouchMeasurement(
            touch_id=int(track["id"]),
            x=float(detection["x"]),
            y=float(detection["y"]),
            confidence=float(detection.get("confidence", 1.0)),
            localization_quality=float(
                detection.get("localization_quality", detection.get("confidence", 1.0))
            ),
            point_count=int(detection.get("point_count", 0)),
            edge_point_count=int(detection.get("edge_point_count", 0)),
            ridge_point_count=int(detection.get("ridge_point_count", 0)),
            cluster_span_y=float(detection.get("cluster_span_y", 0.0)),
            ridge_points=ridge_points,
            mode=self._measurement_mode(detection),
            present=bool(track.get("present", False)),
            absent_frames=int(track.get("absent", 0)),
            confirmed=int(track.get("hits", 0)) >= TOUCH_CONFIRM_FRAMES,
            gap_held=bool(track.get("gap_held", False)),
            hits=int(track.get("hits", 0)),
        )

    def latest_measurements(self) -> list[TouchMeasurement]:
        measurements = []
        for track in self.tracks:
            measurement = self._measurement_from_track(track)
            if measurement is not None:
                measurements.append(measurement)
        measurements.sort(key=lambda measurement: measurement.touch_id)
        return measurements

    def _eligible_continuity_track(self, detection_count: int) -> dict | None:
        if detection_count != 1:
            return None

        candidates = [
            track for track in self.tracks
            if track.get("hits", 0) >= TOUCH_CONFIRM_FRAMES and track.get("absent", 0) <= TOUCH_HOLD_FRAMES
        ]
        if len(candidates) != 1:
            return None
        return candidates[0]

    def _register_continuity_candidate(self, track: dict, detection: dict) -> bool:
        cx = detection["x"]
        cy = detection["y"]
        pending = track.get("pending_reacquire")
        repeated = False
        if pending is not None:
            repeated = math.hypot(cx - pending["x"], cy - pending["y"]) <= MATCH_RADIUS

        streak = int(pending.get("streak", 1)) + 1 if repeated else 1
        track["pending_reacquire"] = {"x": cx, "y": cy, "streak": streak}
        return streak >= TOUCH_CONTINUITY_REPEAT_FRAMES

    def _accept_detection(self, track: dict, detection: dict):
        track["x"] = detection["x"]
        track["y"] = detection["y"]
        track["present"] = True
        track["gap_held"] = False
        track["absent"] = 0
        track["hits"] = min(int(track.get("hits", 0)) + 1, TOUCH_CONFIRM_FRAMES)
        track["last_evidence"] = detection
        track["pending_reacquire"] = None

    def update(self, centroids) -> list[TouchMeasurement]:
        normalized_detections = [self._normalize_detection(detection) for detection in centroids]
        for track in self.tracks:
            track["present"] = False
            track["gap_held"] = False

        for detection in normalized_detections:
            cx = detection["x"]
            cy = detection["y"]
            best_d, best_t = MATCH_RADIUS, None
            for track in self.tracks:
                d = math.hypot(cx - track["x"], cy - track["y"])
                if d < best_d:
                    best_d, best_t = d, track

            if best_t is not None:
                self._accept_detection(best_t, detection)
                continue

            continuity_track = self._eligible_continuity_track(len(normalized_detections))
            if continuity_track is not None:
                if self._register_continuity_candidate(continuity_track, detection):
                    self._accept_detection(continuity_track, detection)
                continue

            if any(
                track.get("present", False) and track.get("hits", 0) >= TOUCH_CONFIRM_FRAMES
                for track in self.tracks
            ):
                continue

            self.tracks.append(
                {
                    "id": self._next_id,
                    "x": cx,
                    "y": cy,
                    "present": True,
                    "gap_held": False,
                    "absent": 0,
                    "hits": 1,
                    "pending_reacquire": None,
                    "last_evidence": detection,
                }
            )
            self._next_id += 1

        for track in self.tracks:
            if track["present"]:
                continue
            track["absent"] += 1
            track["gap_held"] = (
                track.get("hits", 0) >= TOUCH_CONFIRM_FRAMES
                and track["absent"] <= SHORT_GAP_VISIBLE_FRAMES
            )
            if track["absent"] > SHORT_GAP_VISIBLE_FRAMES:
                track["pending_reacquire"] = None
            if track["absent"] > SHORT_GAP_VISIBLE_FRAMES and track["absent"] >= RECOUNT_FRAMES:
                track["hits"] = 0

        self.tracks = [track for track in self.tracks if track["absent"] < FORGET_FRAMES]
        return self.latest_measurements()


class TouchTracker:
    def __init__(self):
        self.measurement_tracker = TouchMeasurementTracker()
        self.tracks: list[dict] = []

    def _append_history(self, track: dict, cx: float, cy: float):
        history = track.setdefault("history", [])
        history.append((cx, cy))
        if len(history) > TOUCH_HISTORY_FRAMES:
            del history[:-TOUCH_HISTORY_FRAMES]
        return history

    def _normalize_detection(self, detection) -> dict:
        if isinstance(detection, dict):
            return {
                "x": float(detection["x"]),
                "y": float(detection["y"]),
                "confidence": max(0.0, min(1.0, float(detection.get("confidence", 1.0)))),
                "localization_quality": max(
                    0.0,
                    min(1.0, float(detection.get("localization_quality", detection.get("confidence", 1.0)))),
                ),
                "point_count": int(detection.get("point_count", 0)),
                "edge_point_count": int(detection.get("edge_point_count", 0)),
                "ridge_point_count": int(detection.get("ridge_point_count", detection.get("edge_point_count", 0))),
                "ridge_points": [
                    [float(pt[0]), float(pt[1])]
                    for pt in detection.get("ridge_points", [])
                    if len(pt) >= 2
                ],
                "cluster_span_y": float(detection.get("cluster_span_y", 0.0)),
            }
        cx, cy = detection
        return {
            "x": float(cx),
            "y": float(cy),
            "confidence": 1.0,
            "localization_quality": 1.0,
            "point_count": 0,
            "edge_point_count": 0,
            "ridge_point_count": TOUCH_RIDGE_POINTS,
            "ridge_points": [[float(cx), float(cy)]],
            "cluster_span_y": 0.0,
        }

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

    def _history_direction(self, track: dict, *, include_latest: bool = True) -> tuple[float, float] | None:
        history = track.get("history") or [(track["x"], track["y"])]
        if not include_latest and len(history) > 1:
            history = history[:-1]
        if len(history) < 2:
            return None

        start_x, start_y = history[0]
        end_x, end_y = history[-1]
        dx = end_x - start_x
        dy = end_y - start_y
        dist = math.hypot(dx, dy)
        if dist <= 1e-6:
            return None
        return dx / dist, dy / dist

    def _blend(self, current: float, target: float, alpha: float) -> float:
        return (1.0 - alpha) * current + alpha * target

    def _effective_detection_quality(self, detection: dict) -> float:
        return min(detection["confidence"], detection.get("localization_quality", detection["confidence"]))

    def _has_strong_ridge(self, detection: dict) -> bool:
        return int(detection.get("ridge_point_count", 0)) >= TOUCH_RIDGE_POINTS

    def _measurement_mode(self, detection: dict) -> str:
        return "strong_ridge" if self._has_strong_ridge(detection) else "weak_ridge"

    def _measurement_from_track(self, track: dict) -> TouchMeasurement | None:
        detection = track.get("last_evidence")
        if not detection:
            return None

        ridge_points = tuple(
            (float(point[0]), float(point[1]))
            for point in detection.get("ridge_points", [])
            if len(point) >= 2
        )
        return TouchMeasurement(
            touch_id=int(track["id"]),
            x=float(detection["x"]),
            y=float(detection["y"]),
            confidence=float(detection.get("confidence", 1.0)),
            localization_quality=float(
                detection.get("localization_quality", detection.get("confidence", 1.0))
            ),
            point_count=int(detection.get("point_count", 0)),
            edge_point_count=int(detection.get("edge_point_count", 0)),
            ridge_point_count=int(detection.get("ridge_point_count", 0)),
            cluster_span_y=float(detection.get("cluster_span_y", 0.0)),
            ridge_points=ridge_points,
            mode=self._measurement_mode(detection),
            present=bool(track.get("present", False)),
            absent_frames=int(track.get("absent", 0)),
            confirmed=int(track.get("hits", 0)) >= TOUCH_CONFIRM_FRAMES,
        )

    def latest_measurements(self) -> list[TouchMeasurement]:
        return self.measurement_tracker.latest_measurements()

    def _detection_from_measurement(self, measurement: TouchMeasurement) -> dict:
        return {
            "x": float(measurement.x),
            "y": float(measurement.y),
            "confidence": float(measurement.confidence),
            "localization_quality": float(measurement.localization_quality),
            "point_count": int(measurement.point_count),
            "edge_point_count": int(measurement.edge_point_count),
            "ridge_point_count": int(measurement.ridge_point_count),
            "ridge_points": [[float(x), float(y)] for x, y in measurement.ridge_points],
            "cluster_span_y": float(measurement.cluster_span_y),
        }

    def _move_track_towards(self, track: dict, tx: float, ty: float, alpha: float):
        dx = tx - track["x"]
        dy = ty - track["y"]
        dist = math.hypot(dx, dy)
        if dist > TOUCH_MAX_STEP_M:
            scale = TOUCH_MAX_STEP_M / dist
            tx = track["x"] + dx * scale
            ty = track["y"] + dy * scale
        track["x"] = self._blend(track["x"], tx, alpha)
        track["y"] = self._blend(track["y"], ty, alpha)

    def _reset_outlier_state(self, track: dict):
        track["outlier_streak"] = 0
        track["last_outlier_dx"] = 0.0
        track["last_outlier_dy"] = 0.0

    def _reset_single_point_state(self, track: dict):
        track["pending_single_point"] = None

    def _reset_continuity_candidate(self, track: dict):
        track["pending_reacquire"] = None

    def _remember_strong_position(self, track: dict, detection: dict):
        track["last_strong_x"] = float(track["x"])
        track["last_strong_y"] = float(track["y"])
        track["last_strong_detection"] = detection

    def _strong_position_or_anchor(self, track: dict) -> tuple[float, float]:
        return (
            float(track.get("last_strong_x", track.get("anchor_x", track["x"]))),
            float(track.get("last_strong_y", track.get("anchor_y", track["y"]))),
        )

    def _reacquire_track(self, track: dict, detection: dict):
        cx = detection["x"]
        cy = detection["y"]
        track["history"] = [(cx, cy)]
        self._set_track_position(track, cx, cy)
        self._set_anchor(track, cx, cy)
        track["state"] = "settling"
        track["stable_frames"] = 1
        track["last_evidence"] = detection
        track["hits"] = max(track.get("hits", 0), TOUCH_CONFIRM_FRAMES)
        self._reset_outlier_state(track)
        self._reset_single_point_state(track)
        self._reset_continuity_candidate(track)
        if self._has_strong_ridge(detection):
            self._remember_strong_position(track, detection)

    def _resume_moving_reacquire(self, track: dict, detection: dict):
        cx = detection["x"]
        cy = detection["y"]
        quality = self._effective_detection_quality(detection)
        self._append_history(track, cx, cy)
        track["last_evidence"] = detection
        track["state"] = "moving"
        track["stable_frames"] = 0
        self._follow_moving(track, cx, cy, quality)
        if self._has_strong_ridge(detection):
            self._remember_strong_position(track, detection)

    def _eligible_continuity_track(self, centroid_count: int) -> dict | None:
        if centroid_count != 1:
            return None

        candidates = [
            track for track in self.tracks
            if track.get("hits", 0) >= TOUCH_CONFIRM_FRAMES and track.get("absent", 0) <= TOUCH_HOLD_FRAMES
        ]
        if len(candidates) != 1:
            return None
        return candidates[0]

    def _register_continuity_candidate(self, track: dict, detection: dict) -> bool:
        cx = detection["x"]
        cy = detection["y"]
        pending = track.get("pending_reacquire")
        repeated = False
        if pending is not None:
            repeated = math.hypot(cx - pending["x"], cy - pending["y"]) <= MATCH_RADIUS

        if repeated:
            streak = int(pending.get("streak", 1)) + 1
        else:
            streak = 1
        track["pending_reacquire"] = {"x": cx, "y": cy, "streak": streak}
        return streak >= TOUCH_CONTINUITY_REPEAT_FRAMES

    def _register_outlier(self, track: dict, dx: float, dy: float) -> int:
        prev_dx = track.get("last_outlier_dx", 0.0)
        prev_dy = track.get("last_outlier_dy", 0.0)
        aligned = prev_dx * dx + prev_dy * dy > 0.0
        if track.get("outlier_streak", 0) > 0 and aligned:
            track["outlier_streak"] += 1
        else:
            track["outlier_streak"] = 1
        track["last_outlier_dx"] = dx
        track["last_outlier_dy"] = dy
        return track["outlier_streak"]

    def _set_anchor(self, track: dict, x: float, y: float):
        track["anchor_x"] = x
        track["anchor_y"] = y

    def _set_track_position(self, track: dict, x: float, y: float):
        track["x"] = x
        track["y"] = y

    def _continuous_follow_alpha(
        self,
        dist: float,
        quality: float,
        motion_coherence: float,
        *,
        prefer_fast: bool = False,
    ) -> float:
        fast_alpha = max(TOUCH_FAST_ALPHA, 0.45)
        low_alpha = max(0.05, TOUCH_HOVER_SOFT_ALPHA * 0.6)
        mid_alpha = max(low_alpha, min(fast_alpha, 0.34 if prefer_fast else 0.24))

        if dist <= TOUCH_HOVER_SOFT_RADIUS_M:
            alpha = low_alpha
        elif dist >= TOUCH_HOVER_BREAKOUT_RADIUS_M:
            over = min(
                1.0,
                (dist - TOUCH_HOVER_BREAKOUT_RADIUS_M) / max(TOUCH_HOVER_BREAKOUT_RADIUS_M, 1e-6),
            )
            alpha = mid_alpha + (fast_alpha - mid_alpha) * over
        else:
            blend_t = (dist - TOUCH_HOVER_SOFT_RADIUS_M) / max(
                1e-6,
                TOUCH_HOVER_BREAKOUT_RADIUS_M - TOUCH_HOVER_SOFT_RADIUS_M,
            )
            alpha = low_alpha + (mid_alpha - low_alpha) * (0.15 + 0.85 * blend_t)

        coherence_scale = 0.10 + 0.90 * max(0.0, min(1.0, motion_coherence))
        alpha *= coherence_scale

        if prefer_fast and dist >= TOUCH_HOVER_BREAKOUT_RADIUS_M and motion_coherence >= 0.60:
            alpha = max(alpha, fast_alpha * (0.80 + 0.20 * max(0.0, min(1.0, motion_coherence))))

        if quality < TOUCH_LOCALIZE_MIN_QUALITY:
            alpha = max(TOUCH_WEAK_UPDATE_ALPHA, alpha * 0.7)

        return min(1.0, max(low_alpha * 0.75, alpha))

    def _enter_soft_locked(self, track: dict):
        track["state"] = "soft_locked"
        track["stable_frames"] = TOUCH_HOVER_SETTLE_FRAMES
        self._set_track_position(track, track["anchor_x"], track["anchor_y"])
        self._reset_outlier_state(track)
        self._reset_single_point_state(track)
        self._reset_continuity_candidate(track)
    def _damp_moving_orthogonal_target(
        self,
        track: dict,
        cx: float,
        cy: float,
        motion_direction: tuple[float, float] | None,
        quality: float,
    ) -> tuple[float, float]:
        if motion_direction is None:
            return cx, cy

        dir_x, dir_y = motion_direction
        dx = cx - track["x"]
        dy = cy - track["y"]
        parallel = dx * dir_x + dy * dir_y
        perp_x = dx - parallel * dir_x
        perp_y = dy - parallel * dir_y
        perp_mag = math.hypot(perp_x, perp_y)

        if perp_mag <= TOUCH_HOVER_SOFT_RADIUS_M:
            return cx, cy
        if perp_mag <= abs(parallel) + (TOUCH_HOVER_SOFT_RADIUS_M * 0.5):
            return cx, cy

        perp_scale = 0.25 + 0.25 * max(0.0, min(1.0, quality))
        return (
            track["x"] + (parallel * dir_x) + (perp_x * perp_scale),
            track["y"] + (parallel * dir_y) + (perp_y * perp_scale),
        )

    def _follow_moving(self, track: dict, cx: float, cy: float, quality: float):
        self._reset_outlier_state(track)
        self._reset_single_point_state(track)
        self._reset_continuity_candidate(track)
        residual = math.hypot(cx - track["x"], cy - track["y"])
        motion_span, motion_coherence = self._history_motion_metrics(track)
        prior_motion_direction = self._history_direction(track, include_latest=False)
        if motion_coherence >= 0.45:
            cx, cy = self._damp_moving_orthogonal_target(
                track,
                cx,
                cy,
                prior_motion_direction,
                quality,
            )
            residual = math.hypot(cx - track["x"], cy - track["y"])
        follow_alpha = self._continuous_follow_alpha(
            max(residual, motion_span),
            quality,
            motion_coherence,
            prefer_fast=True,
        )
        self._move_track_towards(track, cx, cy, follow_alpha)
        self._set_anchor(track, track["x"], track["y"])

    def _enter_moving(self, track: dict, cx: float, cy: float, quality: float):
        track["state"] = "moving"
        track["stable_frames"] = 0
        self._follow_moving(track, cx, cy, quality)

    def _update_single_point(self, track: dict, detection: dict):
        cx = detection["x"]
        cy = detection["y"]
        pending = track.get("pending_single_point")
        repeated = False
        if pending is not None:
            repeated = math.hypot(cx - pending["x"], cy - pending["y"]) <= TOUCH_SINGLE_POINT_REPEAT_RADIUS_M

        if repeated:
            self._move_track_towards(track, cx, cy, TOUCH_SINGLE_POINT_GLIDE_ALPHA)
            self._set_anchor(track, track["x"], track["y"])

        track["pending_single_point"] = {"x": cx, "y": cy}
        track["last_measurement"] = detection
        if track.get("last_evidence") is None:
            track["last_evidence"] = detection
        track["stable_frames"] = max(1, track.get("stable_frames", 0))
        self._reset_outlier_state(track)
        self._reset_continuity_candidate(track)

    def _update_weak_confirmed_track(self, track: dict, detection: dict):
        hold_x, hold_y = self._strong_position_or_anchor(track)
        self._set_track_position(track, hold_x, hold_y)
        self._set_anchor(track, hold_x, hold_y)
        track["last_measurement"] = detection
        track["stable_frames"] = max(1, track.get("stable_frames", 0))
        self._reset_outlier_state(track)
        self._reset_single_point_state(track)
        self._reset_continuity_candidate(track)

    def _hold_confirmed_settling_jump(self, track: dict, detection: dict) -> bool:
        if track.get("hits", 0) < TOUCH_CONFIRM_FRAMES:
            return False

        hold_x, hold_y = self._strong_position_or_anchor(track)
        dx = detection["x"] - hold_x
        dy = detection["y"] - hold_y
        dist = math.hypot(dx, dy)
        if dist < TOUCH_HOVER_BREAKOUT_RADIUS_M:
            self._reset_outlier_state(track)
            return False

        if len(track.get("history", [])) > 2 and track.get("outlier_streak", 0) == 0:
            return False

        streak = self._register_outlier(track, dx, dy)
        if streak >= TOUCH_HOVER_OUTLIER_FRAMES:
            return False

        self._set_track_position(track, hold_x, hold_y)
        self._set_anchor(track, hold_x, hold_y)
        track["last_evidence"] = detection
        track["stable_frames"] = 1
        return True

    def _update_settling(self, track: dict, detection: dict):
        quality = self._effective_detection_quality(detection)
        target_x, target_y = self._history_target(track)
        motion_span, motion_coherence = self._history_motion_metrics(track)
        target_dist = math.hypot(detection["x"] - target_x, detection["y"] - target_y)
        history_len = len(track.get("history", []))
        coherent_motion = history_len >= 3 and motion_span >= TOUCH_HOVER_BREAKOUT_RADIUS_M and motion_coherence >= 0.60
        responsive_settling = history_len >= 3 and motion_coherence >= 0.85 and max(target_dist, motion_span) >= TOUCH_HOVER_SOFT_RADIUS_M * 1.5

        if self._hold_confirmed_settling_jump(track, detection):
            return

        follow_x, follow_y = (detection["x"], detection["y"]) if (coherent_motion or responsive_settling) else (target_x, target_y)

        anchor_alpha = self._continuous_follow_alpha(
            max(target_dist, motion_span),
            quality,
            motion_coherence,
            prefer_fast=coherent_motion or responsive_settling,
        )
        if responsive_settling:
            anchor_alpha = max(anchor_alpha, 0.35)
        track["anchor_x"] = self._blend(track["anchor_x"], follow_x, anchor_alpha)
        track["anchor_y"] = self._blend(track["anchor_y"], follow_y, anchor_alpha)

        if target_dist <= TOUCH_HOVER_SOFT_RADIUS_M and not coherent_motion:
            track["stable_frames"] += 1
        elif target_dist <= TOUCH_HOVER_BREAKOUT_RADIUS_M and motion_coherence < 0.45:
            track["stable_frames"] = max(1, track["stable_frames"] - 1)
        else:
            track["stable_frames"] = 1

        self._set_track_position(track, track["anchor_x"], track["anchor_y"])
        if track["stable_frames"] >= TOUCH_HOVER_SETTLE_FRAMES and quality >= TOUCH_HOVER_MIN_CONFIDENCE:
            self._enter_soft_locked(track)

    def _update_soft_locked(self, track: dict, detection: dict):
        cx = detection["x"]
        cy = detection["y"]
        quality = self._effective_detection_quality(detection)
        dx = cx - track["anchor_x"]
        dy = cy - track["anchor_y"]
        dist = math.hypot(dx, dy)
        motion_span, motion_coherence = self._history_motion_metrics(track)

        if dist <= TOUCH_HOVER_SOFT_RADIUS_M:
            creep_alpha = TOUCH_HOVER_SOFT_ALPHA * max(0.4, quality)
            track["anchor_x"] = self._blend(track["anchor_x"], cx, creep_alpha)
            track["anchor_y"] = self._blend(track["anchor_y"], cy, creep_alpha)
            self._set_track_position(track, track["anchor_x"], track["anchor_y"])
            track["stable_frames"] = min(track["stable_frames"] + 1, TOUCH_HOVER_SETTLE_FRAMES)
            self._reset_outlier_state(track)
            return

        large_jump = dist >= max(TOUCH_HOVER_BREAKOUT_RADIUS_M * 1.6, TOUCH_MAX_STEP_M * 0.75)
        if large_jump:
            streak = self._register_outlier(track, dx, dy)
            if streak < TOUCH_HOVER_OUTLIER_FRAMES:
                self._set_track_position(track, track["anchor_x"], track["anchor_y"])
                return

        breakout_ready = (
            dist >= TOUCH_HOVER_BREAKOUT_RADIUS_M or motion_span >= TOUCH_HOVER_BREAKOUT_RADIUS_M
        ) and motion_coherence >= 0.45
        if not breakout_ready:
            blend_t = (dist - TOUCH_HOVER_SOFT_RADIUS_M) / max(
                1e-6,
                TOUCH_HOVER_BREAKOUT_RADIUS_M - TOUCH_HOVER_SOFT_RADIUS_M,
            )
            medium_alpha = TOUCH_HOVER_SOFT_ALPHA + (
                max(TOUCH_FAST_ALPHA, 0.45) - TOUCH_HOVER_SOFT_ALPHA
            ) * (0.30 + 0.45 * max(0.0, min(1.0, blend_t)))
            medium_alpha *= 0.15 + 0.85 * max(0.0, min(1.0, motion_coherence))
            if quality < TOUCH_LOCALIZE_MIN_QUALITY:
                medium_alpha = max(TOUCH_WEAK_UPDATE_ALPHA, medium_alpha * 0.6)
            self._move_track_towards(track, cx, cy, medium_alpha)
            self._set_anchor(track, track["x"], track["y"])
            track["stable_frames"] = max(1, track["stable_frames"] - 1)
            self._reset_outlier_state(track)
            return

        self._reset_outlier_state(track)
        self._enter_moving(track, cx, cy, quality)

    def _update_moving(self, track: dict, detection: dict):
        cx = detection["x"]
        cy = detection["y"]
        quality = self._effective_detection_quality(detection)
        self._follow_moving(track, cx, cy, quality)
        motion_span, motion_coherence = self._history_motion_metrics(track)
        residual = math.hypot(cx - track["x"], cy - track["y"])
        if residual <= TOUCH_HOVER_SOFT_RADIUS_M and motion_span <= TOUCH_HOVER_BREAKOUT_RADIUS_M and motion_coherence < 0.55:
            track["stable_frames"] += 1
        else:
            track["stable_frames"] = 0
        if track["stable_frames"] >= TOUCH_HOVER_SETTLE_FRAMES:
            self._enter_soft_locked(track)

    def _update_track(self, track: dict, detection: dict):
        cx = detection["x"]
        cy = detection["y"]
        if not self._has_strong_ridge(detection):
            if track.get("hits", 0) >= TOUCH_CONFIRM_FRAMES:
                self._update_weak_confirmed_track(track, detection)
            else:
                self._update_single_point(track, detection)
            return

        self._reset_single_point_state(track)
        self._reset_continuity_candidate(track)
        self._append_history(track, cx, cy)
        track["last_evidence"] = detection
        state = track.get("state", "settling")
        if state == "soft_locked":
            self._update_soft_locked(track, detection)
        elif state == "moving":
            self._update_moving(track, detection)
        else:
            self._update_settling(track, detection)
        self._remember_strong_position(track, detection)

    def update(self, centroids):
        measurements = self.measurement_tracker.update(centroids)
        measurements_by_id = {measurement.touch_id: measurement for measurement in measurements}

        for track in self.tracks:
            track["present"] = False

        for measurement in measurements:
            if not measurement.present:
                continue

            detection = self._detection_from_measurement(measurement)
            track = next(
                (candidate for candidate in self.tracks if candidate["id"] == measurement.touch_id),
                None,
            )
            if track is None:
                cx = detection["x"]
                cy = detection["y"]
                self.tracks.append(
                    {
                        "id": measurement.touch_id,
                        "x": cx,
                        "y": cy,
                        "anchor_x": cx,
                        "anchor_y": cy,
                        "present": True,
                        "absent": 0,
                        "hits": measurement.hits,
                        "state": "settling",
                        "stable_frames": 1,
                        "outlier_streak": 0,
                        "last_outlier_dx": 0.0,
                        "last_outlier_dy": 0.0,
                        "pending_single_point": None,
                        "pending_reacquire": None,
                        "last_evidence": detection,
                        "last_strong_x": cx,
                        "last_strong_y": cy,
                        "last_strong_detection": detection,
                        "history": [(cx, cy)],
                    }
                )
                continue

            previous_absent = int(track.get("absent", 0))
            if previous_absent > 0 and self._has_strong_ridge(detection):
                if (
                    track.get("state") == "moving"
                    and measurement.confirmed
                    and previous_absent <= SHORT_GAP_VISIBLE_FRAMES
                ):
                    self._resume_moving_reacquire(track, detection)
                else:
                    self._reacquire_track(track, detection)
            else:
                self._update_track(track, detection)

            track["present"] = True
            track["absent"] = 0
            track["hits"] = measurement.hits

        active_measurement_ids = set(measurements_by_id)
        for track in self.tracks:
            measurement = measurements_by_id.get(track["id"])
            if measurement is None:
                continue
            if not track["present"]:
                track["absent"] = measurement.absent_frames
                track["hits"] = measurement.hits
                if track["absent"] > SHORT_GAP_VISIBLE_FRAMES:
                    self._reset_continuity_candidate(track)
                if track["absent"] > SHORT_GAP_VISIBLE_FRAMES and track["absent"] >= RECOUNT_FRAMES:
                    track["hits"] = 0

        self.tracks = [track for track in self.tracks if track["id"] in active_measurement_ids]
        present_confirmed = [
            t for t in self.tracks
            if t["present"] and t["hits"] >= TOUCH_CONFIRM_FRAMES
        ]
        visible_tracks = present_confirmed
        if not visible_tracks:
            visible_tracks = [
                t for t in self.tracks
                if t["hits"] >= TOUCH_CONFIRM_FRAMES and (t["present"] or t["absent"] <= SHORT_GAP_VISIBLE_FRAMES)
            ]
        return [
            (t["id"], t["x"], t["y"])
            for t in visible_tracks
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
    diagnostic_logger = DiagnosticLogger.from_env()
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
                track = next((candidate for candidate in tracker.tracks if candidate["id"] == touch_id), None)
                raw_control_points = []
                if track is not None:
                    raw_control_points = track.get("last_evidence", {}).get("ridge_points", [])
                adjusted_control_points = []
                for point in raw_control_points:
                    if len(point) < 2:
                        continue
                    control_x, control_y = estimate_touch_contact(float(point[0]), float(point[1]))
                    if is_inside_board(control_x, control_y):
                        adjusted_control_points.append([round(control_x, 4), round(control_y, 4)])
                px, py = physical_to_pixel(tx, ty)
                visible_touches.append(
                    {
                        "id": touch_id,
                        "px": px,
                        "py": py,
                        "mx": round(tx, 4),
                        "my": round(ty, 4),
                        "control_pts": adjusted_control_points,
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
            if diagnostic_logger is not None:
                diagnostic_logger.log_frame(
                    scan_count=node.scan_count,
                    rate_hz=node.rate_hz,
                    raw_scan_point_count=len(xs),
                    touch_zone_point_count=len(zxs),
                    dynamic_point_count=len(dyn_xs),
                    board_dynamic_point_count=len(dyn_bxs),
                    visible_dynamic_point_count=len(visible_dyn_pts),
                    centroids=centroids,
                    tracker=tracker,
                    visible_touches=visible_touches,
                )
            print(json.dumps(out, separators=(",", ":")), flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        if diagnostic_logger is not None:
            diagnostic_logger.close()
        exec_.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
