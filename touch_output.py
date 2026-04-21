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
TOUCH_CONTINUITY_REPEAT_FRAMES = 2
SHORT_GAP_VISIBLE_FRAMES = max(TOUCH_HOLD_FRAMES, 3)

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
            cluster_span_y = 0.0
            if len(member_pts) > 1:
                cluster_span_y = max(y for _, y in member_pts) - min(y for _, y in member_pts)
            if MOUNT_MODE == "bottom_center":
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
        track["last_evidence"] = detection
        track["stable_frames"] = max(1, track.get("stable_frames", 0))
        self._reset_outlier_state(track)
        self._reset_continuity_candidate(track)

    def _update_weak_confirmed_track(self, track: dict, detection: dict):
        hold_x, hold_y = self._strong_position_or_anchor(track)
        self._set_track_position(track, hold_x, hold_y)
        self._set_anchor(track, hold_x, hold_y)
        track["last_evidence"] = detection
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

    def update(self, centroids: list[tuple]) -> list[tuple]:
        """Returns list of (cx, cy) for currently visible stable touches."""
        normalized_detections = [self._normalize_detection(detection) for detection in centroids]
        for t in self.tracks:
            t["present"] = False

        for detection in normalized_detections:
            cx = detection["x"]
            cy = detection["y"]
            best_d, best_t = MATCH_RADIUS, None
            for t in self.tracks:
                match_x = t.get("anchor_x", t["x"])
                match_y = t.get("anchor_y", t["y"])
                d = math.hypot(cx - match_x, cy - match_y)
                if d < best_d:
                    best_d, best_t = d, t
            if best_t is not None:
                if best_t["absent"] > 0 and self._has_strong_ridge(detection):
                    if (
                        best_t.get("state") == "moving"
                        and best_t.get("hits", 0) >= TOUCH_CONFIRM_FRAMES
                        and best_t["absent"] <= SHORT_GAP_VISIBLE_FRAMES
                    ):
                        self._resume_moving_reacquire(best_t, detection)
                    else:
                        self._reacquire_track(best_t, detection)
                else:
                    self._update_track(best_t, detection)
                best_t["present"] = True
                best_t["absent"]  = 0
                best_t["hits"] = min(best_t["hits"] + 1, TOUCH_CONFIRM_FRAMES)
            else:
                continuity_track = self._eligible_continuity_track(len(normalized_detections))
                if continuity_track is not None:
                    if self._register_continuity_candidate(continuity_track, detection):
                        if (
                            continuity_track.get("state") == "moving"
                            and continuity_track.get("hits", 0) >= TOUCH_CONFIRM_FRAMES
                            and continuity_track["absent"] <= SHORT_GAP_VISIBLE_FRAMES
                        ):
                            self._resume_moving_reacquire(continuity_track, detection)
                        else:
                            self._reacquire_track(continuity_track, detection)
                        continuity_track["present"] = True
                        continuity_track["absent"] = 0
                    continue
                self.tracks.append({
                    "x": cx,
                    "y": cy,
                    "anchor_x": cx,
                    "anchor_y": cy,
                    "present": True,
                    "absent": 0,
                    "hits": 1,
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
                })

        for t in self.tracks:
            if not t["present"]:
                t["absent"] += 1
                if t["absent"] > SHORT_GAP_VISIBLE_FRAMES:
                    self._reset_continuity_candidate(t)
                if t["absent"] > SHORT_GAP_VISIBLE_FRAMES and t["absent"] >= RECOUNT_FRAMES:
                    t["hits"] = 0
        self.tracks = [t for t in self.tracks if t["absent"] < FORGET_FRAMES]

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
            (t["x"], t["y"])
            for t in visible_tracks
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
