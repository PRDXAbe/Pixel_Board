import importlib
import sys
import types
import unittest


def _install_ros_stubs():
    rclpy = types.ModuleType("rclpy")
    rclpy.init = lambda: None
    rclpy.shutdown = lambda: None
    rclpy.ok = lambda: False
    sys.modules.setdefault("rclpy", rclpy)

    executors = types.ModuleType("rclpy.executors")
    executors.SingleThreadedExecutor = object
    sys.modules.setdefault("rclpy.executors", executors)

    node_mod = types.ModuleType("rclpy.node")
    node_mod.Node = object
    sys.modules.setdefault("rclpy.node", node_mod)

    qos_mod = types.ModuleType("rclpy.qos")
    qos_mod.QoSHistoryPolicy = object
    qos_mod.QoSProfile = object
    qos_mod.QoSReliabilityPolicy = object
    sys.modules.setdefault("rclpy.qos", qos_mod)

    sensor_msgs = types.ModuleType("sensor_msgs")
    msg_mod = types.ModuleType("sensor_msgs.msg")
    msg_mod.LaserScan = object
    sensor_msgs.msg = msg_mod
    sys.modules.setdefault("sensor_msgs", sensor_msgs)
    sys.modules.setdefault("sensor_msgs.msg", msg_mod)


_install_ros_stubs()
ros_bridge = importlib.import_module("ros_bridge")


def _track_positions(points):
    tracker = ros_bridge.TouchTracker()
    positions = []
    for point in points:
        touches = tracker.update([point])
        if touches:
            _, x, y = touches[0]
            positions.append((x, y))
    return positions


def _track_frames(frames):
    tracker = ros_bridge.TouchTracker()
    outputs = []
    for frame in frames:
        outputs.append(tracker.update(frame))
    return outputs


def _strong_detection(x, y, confidence=0.9, localization_quality=0.9):
    return {
        "x": x,
        "y": y,
        "confidence": confidence,
        "localization_quality": localization_quality,
        "point_count": 4,
        "edge_point_count": 2,
        "ridge_point_count": 2,
        "cluster_span_y": 0.004,
    }


def _single_point_detection(x, y, confidence=0.7, localization_quality=0.35):
    return {
        "x": x,
        "y": y,
        "confidence": confidence,
        "localization_quality": localization_quality,
        "point_count": 3,
        "edge_point_count": 1,
        "ridge_point_count": 1,
        "cluster_span_y": 0.008,
    }


def _strong_ridge_detection(x, y, ridge_points, confidence=0.9, localization_quality=0.9):
    return {
        "x": x,
        "y": y,
        "confidence": confidence,
        "localization_quality": localization_quality,
        "point_count": 4,
        "edge_point_count": len(ridge_points),
        "ridge_point_count": len(ridge_points),
        "ridge_points": [[float(px), float(py)] for px, py in ridge_points],
        "cluster_span_y": 0.004,
    }


class TouchTrackerRegressionTests(unittest.TestCase):
    def test_bottom_center_contact_ignores_trailing_cluster_y_bias(self):
        original_mount_mode = ros_bridge.MOUNT_MODE
        try:
            ros_bridge.MOUNT_MODE = "bottom_center"
            clusters = ros_bridge.cluster_points(
                [0.200, 0.199, 0.198, 0.190, 0.188, 0.187],
                [0.000, 0.004, -0.003, 0.030, 0.028, 0.026],
            )
        finally:
            ros_bridge.MOUNT_MODE = original_mount_mode

        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster["ridge_point_count"], 2)
        self.assertAlmostEqual(cluster["x"], 0.199, delta=0.003)
        self.assertAlmostEqual(cluster["y"], 0.000, delta=0.006)

    def test_bottom_center_touch_uses_only_two_strong_front_points(self):
        original_mount_mode = ros_bridge.MOUNT_MODE
        try:
            ros_bridge.MOUNT_MODE = "bottom_center"
            clusters = ros_bridge.cluster_points(
                [0.200, 0.199, 0.198, 0.190, 0.188, 0.187],
                [0.000, 0.002, 0.017, 0.030, 0.028, 0.026],
            )
        finally:
            ros_bridge.MOUNT_MODE = original_mount_mode

        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster["ridge_point_count"], 2)
        self.assertAlmostEqual(cluster["y"], 0.001, delta=0.003)
        self.assertEqual(len(cluster["ridge_points"]), 2)
        ridge_ys = [pt[1] for pt in cluster["ridge_points"]]
        self.assertLessEqual(max(ridge_ys) - min(ridge_ys), 0.0041)

    def test_stationary_noise_stays_locked(self):
        base_x = 0.14
        base_y = 0.0
        noisy_points = []
        for index in range(40):
            dx = [0.0, 0.006, -0.006, 0.008, -0.008, 0.0, 0.004, -0.004][index % 8]
            noisy_points.append((base_x + dx, base_y))

        positions = _track_positions(noisy_points)

        self.assertGreater(len(positions), 30)
        xs = [x for x, _ in positions]
        self.assertLessEqual(max(xs) - min(xs), 0.002)

    def test_coherent_motion_does_not_fall_far_behind(self):
        moving_points = [(0.10 + index * 0.003, 0.0) for index in range(14)]

        positions = _track_positions(moving_points)

        self.assertGreaterEqual(len(positions), 10)
        last_x, _ = positions[-1]
        last_raw_x, _ = moving_points[-1]
        lag_m = last_raw_x - last_x

        self.assertLessEqual(lag_m, 0.009)

    def test_single_outlier_does_not_pull_locked_hover_far_off_target(self):
        stable_then_outlier = [
            (0.140, 0.0),
            (0.142, 0.0),
            (0.138, 0.0),
            (0.141, 0.0),
            (0.139, 0.0),
            (0.140, 0.0),
            (0.141, 0.0),
            (0.139, 0.0),
            (0.140, 0.0),
            (0.160, 0.0),
            (0.140, 0.0),
            (0.141, 0.0),
            (0.139, 0.0),
        ]

        positions = _track_positions(stable_then_outlier)

        self.assertGreaterEqual(len(positions), 10)
        locked_x = positions[7][0]
        jump_x = positions[8][0]
        self.assertLessEqual(abs(jump_x - locked_x), 0.0025)

    def test_repeated_displacement_breaks_out_of_soft_lock_quickly(self):
        stable_then_move = [
            (0.140, 0.0),
            (0.142, 0.0),
            (0.138, 0.0),
            (0.141, 0.0),
            (0.139, 0.0),
            (0.140, 0.0),
            (0.141, 0.0),
            (0.139, 0.0),
            (0.152, 0.0),
            (0.155, 0.0),
            (0.158, 0.0),
            (0.160, 0.0),
        ]

        positions = _track_positions(stable_then_move)

        self.assertGreaterEqual(len(positions), 9)
        last_x = positions[-1][0]
        self.assertGreaterEqual(last_x, 0.154)

    def test_soft_lock_does_not_freeze_smooth_motion_until_breakout(self):
        smooth_motion = [
            (0.140, 0.0),
            (0.141, 0.0),
            (0.139, 0.0),
            (0.140, 0.0),
            (0.141, 0.0),
            (0.140, 0.0),
            (0.144, 0.0),
            (0.146, 0.0),
            (0.148, 0.0),
        ]

        positions = _track_positions(smooth_motion)

        self.assertGreaterEqual(len(positions), 7)
        self.assertGreater(positions[5][0], positions[4][0])
        self.assertGreater(positions[6][0], positions[5][0])
        self.assertLess(positions[6][0] - positions[5][0], 0.0065)

    def test_moving_state_damps_incoherent_nearby_strong_jitter(self):
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.150, 0.000)],
            [_strong_detection(0.152, 0.000)],
            [_strong_detection(0.150, 0.009)],
            [_strong_detection(0.150, 0.000)],
            [_strong_detection(0.150, 0.009)],
            [_strong_detection(0.150, 0.000)],
            [_strong_detection(0.150, 0.009)],
        ]

        outputs = _track_frames(frames)

        moving_positions = [(x, y) for frame in outputs[3:] if frame for _, x, y in frame]
        ys = [y for _, y in moving_positions]
        self.assertGreaterEqual(len(ys), 6)
        self.assertLessEqual(max(ys) - min(ys), 0.0041)

    def test_moving_state_damps_orthogonal_spike_during_smooth_motion(self):
        frames = [
            [_strong_detection(0.150, 0.000)],
            [_strong_detection(0.150, 0.000)],
            [_strong_detection(0.150, 0.000)],
            [_strong_detection(0.150, 0.004, localization_quality=0.82)],
            [_strong_detection(0.150, 0.008, localization_quality=0.82)],
            [_strong_detection(0.150, 0.012, localization_quality=0.82)],
            [_strong_detection(0.168, 0.016, localization_quality=0.82)],
            [_strong_detection(0.150, 0.020, localization_quality=0.82)],
            [_strong_detection(0.150, 0.024, localization_quality=0.82)],
        ]

        outputs = _track_frames(frames)

        moving_positions = [(x, y) for frame in outputs[2:] if frame for _, x, y in frame]
        self.assertGreaterEqual(len(moving_positions), 6)

        spike_x, spike_y = moving_positions[4]
        final_x, final_y = moving_positions[-1]

        self.assertLessEqual(spike_x, 0.154)
        self.assertGreater(spike_y, 0.010)
        self.assertGreater(final_y, spike_y)
        self.assertLessEqual(final_x, 0.153)

    def test_moving_relocks_after_stationary_hold(self):
        tracker = ros_bridge.TouchTracker()
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.152, 0.000)],
            [_strong_detection(0.156, 0.000)],
            [_strong_detection(0.1562, 0.0002)],
            [_strong_detection(0.1561, -0.0001)],
            [_strong_detection(0.1560, 0.0001)],
            [_strong_detection(0.1561, 0.0000)],
            [_strong_detection(0.1560, -0.0001)],
            [_strong_detection(0.1561, 0.0001)],
        ]

        for frame in frames:
            tracker.update(frame)

        track = tracker.tracks[0]
        self.assertEqual(track["state"], "soft_locked")
        self.assertGreater(track["x"], 0.152)

    def test_confirmed_new_touch_hides_absent_ghost_touch(self):
        frames = [
            [(0.140, 0.0)],
            [(0.140, 0.0)],
            [(0.140, 0.0)],
            [(0.140, 0.0)],
            [(0.240, 0.0)],
            [(0.240, 0.0)],
            [(0.240, 0.0)],
        ]

        outputs = _track_frames(frames)

        final_touches = outputs[-1]
        self.assertEqual(len(final_touches), 1)
        _, final_x, final_y = final_touches[0]
        self.assertAlmostEqual(final_x, 0.240, delta=0.01)
        self.assertAlmostEqual(final_y, 0.0, delta=0.001)

    def test_single_strong_point_requires_repeat_before_tiny_glide(self):
        tracker = ros_bridge.TouchTracker()
        tracker.update([_strong_detection(0.140, 0.0)])
        anchor_x = tracker.tracks[0]["x"]

        tracker.update([_single_point_detection(0.146, 0.0)])
        first_single_x = tracker.tracks[0]["x"]

        tracker.update([_single_point_detection(0.1465, 0.0003)])
        repeated_single_x = tracker.tracks[0]["x"]

        self.assertAlmostEqual(first_single_x, anchor_x, delta=0.0005)
        self.assertGreater(repeated_single_x, first_single_x)
        self.assertLess(repeated_single_x - first_single_x, 0.002)

    def test_build_diagnostic_entry_summarizes_live_frame(self):
        tracker = ros_bridge.TouchTracker()
        detection = _strong_detection(0.140, 0.0)
        tracker.update([detection])
        tracker.update([detection])
        touches = tracker.update([detection])

        self.assertEqual(len(touches), 1)
        touch_id, touch_x, touch_y = touches[0]

        entry = ros_bridge.build_diagnostic_entry(
            scan_count=12,
            rate_hz=10.0,
            raw_scan_point_count=360,
            touch_zone_point_count=42,
            dynamic_point_count=9,
            board_dynamic_point_count=5,
            visible_dynamic_point_count=7,
            centroids=[detection],
            tracker=tracker,
            visible_touches=[
                {
                    "id": touch_id,
                    "px": 100,
                    "py": 50,
                    "mx": round(touch_x, 4),
                    "my": round(touch_y, 4),
                    "control_pts": [[0.1400, 0.0000], [0.1395, 0.0005]],
                }
            ],
        )

        self.assertEqual(entry["scan_count"], 12)
        self.assertEqual(entry["rate_hz"], 10.0)
        self.assertEqual(entry["counts"]["scan_points"], 360)
        self.assertEqual(entry["counts"]["touch_zone_points"], 42)
        self.assertEqual(entry["counts"]["dynamic_points"], 9)
        self.assertEqual(entry["counts"]["board_dynamic_points"], 5)
        self.assertEqual(entry["counts"]["visible_dynamic_points"], 7)
        self.assertEqual(entry["counts"]["centroids"], 1)
        self.assertEqual(entry["counts"]["visible_touches"], 1)
        self.assertEqual(entry["centroids"][0]["ridge_point_count"], 2)
        self.assertEqual(entry["tracks"][0]["state"], "soft_locked")
        self.assertEqual(entry["tracks"][0]["hits"], 3)
        self.assertEqual(entry["tracks"][0]["last_evidence"]["ridge_point_count"], 2)
        self.assertEqual(entry["visible_touches"][0]["id"], touch_id)

    def test_repeated_far_centroid_reuses_existing_touch_id(self):
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.200, 0.090)],
            [_strong_detection(0.201, 0.091)],
        ]

        outputs = _track_frames(frames)

        first_id = outputs[2][0][0]
        self.assertEqual(len(outputs[4]), 1)
        final_id, final_x, final_y = outputs[4][0]
        self.assertEqual(final_id, first_id)
        self.assertAlmostEqual(final_x, 0.201, delta=0.02)
        self.assertAlmostEqual(final_y, 0.091, delta=0.02)

    def test_repeated_far_centroid_does_not_churn_to_new_visible_id(self):
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.200, 0.090)],
            [_strong_detection(0.201, 0.091)],
            [_strong_detection(0.202, 0.092)],
        ]

        outputs = _track_frames(frames)

        visible_ids = [frame[0][0] for frame in outputs if frame]
        self.assertGreaterEqual(len(visible_ids), 4)
        self.assertEqual(len(set(visible_ids)), 1)

    def test_confirmed_touch_stays_visible_through_three_frame_gap(self):
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [],
            [],
            [],
            [_strong_detection(0.141, 0.001)],
        ]

        outputs = _track_frames(frames)

        visible_ids = [frame[0][0] for frame in outputs if frame]
        self.assertEqual(visible_ids, [1, 1, 1, 1, 1])

    def test_weak_nearby_evidence_keeps_touch_alive_without_dragging_position(self):
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_single_point_detection(0.1490, 0.0120, localization_quality=0.28)],
            [_single_point_detection(0.1493, 0.0123, localization_quality=0.28)],
            [_single_point_detection(0.1496, 0.0126, localization_quality=0.28)],
            [_single_point_detection(0.1499, 0.0129, localization_quality=0.28)],
            [_single_point_detection(0.1502, 0.0132, localization_quality=0.28)],
            [_single_point_detection(0.1505, 0.0135, localization_quality=0.28)],
            [_single_point_detection(0.1508, 0.0138, localization_quality=0.28)],
            [_single_point_detection(0.1511, 0.0141, localization_quality=0.28)],
        ]

        outputs = _track_frames(frames)

        anchor_id, anchor_x, anchor_y = outputs[2][0]
        final_id, final_x, final_y = outputs[-1][0]
        self.assertEqual(final_id, anchor_id)
        self.assertLessEqual(abs(final_x - anchor_x), 0.002)
        self.assertLessEqual(abs(final_y - anchor_y), 0.002)

    def test_latest_measurement_remains_separate_from_held_visible_position(self):
        tracker = ros_bridge.TouchTracker()
        tracker.update([_strong_detection(0.140, 0.000)])
        tracker.update([_strong_detection(0.140, 0.000)])
        anchor_frame = tracker.update([_strong_detection(0.140, 0.000)])

        self.assertEqual(len(anchor_frame), 1)
        anchor_id, anchor_x, anchor_y = anchor_frame[0]

        held_frame = tracker.update([
            _single_point_detection(0.1490, 0.0120, localization_quality=0.28)
        ])

        self.assertEqual(len(held_frame), 1)
        held_id, held_x, held_y = held_frame[0]
        self.assertEqual(held_id, anchor_id)
        self.assertLessEqual(abs(held_x - anchor_x), 0.002)
        self.assertLessEqual(abs(held_y - anchor_y), 0.002)

        measurements = tracker.latest_measurements()
        self.assertEqual(len(measurements), 1)
        measurement = measurements[0]
        self.assertEqual(measurement.touch_id, anchor_id)
        self.assertEqual(measurement.mode, "weak_ridge")
        self.assertAlmostEqual(measurement.x, 0.1490, delta=0.0001)
        self.assertAlmostEqual(measurement.y, 0.0120, delta=0.0001)
        self.assertGreater(abs(measurement.x - held_x), 0.005)
        self.assertGreater(abs(measurement.y - held_y), 0.005)

    def test_measurement_tracker_preserves_identity_through_short_gap(self):
        tracker = ros_bridge.TouchMeasurementTracker()
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [],
            [],
            [_strong_detection(0.141, 0.001)],
        ]

        outputs = [tracker.update(frame) for frame in frames]

        confirmed = outputs[2][0]
        held_gap = outputs[3][0]
        held_gap_2 = outputs[4][0]
        reacquired = outputs[5][0]

        self.assertEqual(confirmed.touch_id, 1)
        self.assertTrue(confirmed.present)
        self.assertFalse(confirmed.gap_held)
        self.assertTrue(confirmed.confirmed)

        self.assertEqual(held_gap.touch_id, 1)
        self.assertFalse(held_gap.present)
        self.assertTrue(held_gap.gap_held)
        self.assertEqual(held_gap.absent_frames, 1)

        self.assertEqual(held_gap_2.touch_id, 1)
        self.assertFalse(held_gap_2.present)
        self.assertTrue(held_gap_2.gap_held)
        self.assertEqual(held_gap_2.absent_frames, 2)

        self.assertEqual(reacquired.touch_id, 1)
        self.assertTrue(reacquired.present)
        self.assertFalse(reacquired.gap_held)
        self.assertAlmostEqual(reacquired.x, 0.141, delta=0.0001)
        self.assertAlmostEqual(reacquired.y, 0.001, delta=0.0001)

    def test_measurement_tracker_ignores_extra_unmatched_detection_when_touch_is_confirmed(self):
        tracker = ros_bridge.TouchMeasurementTracker()
        tracker.update([_strong_detection(0.140, 0.000)])
        tracker.update([_strong_detection(0.140, 0.000)])
        tracker.update([_strong_detection(0.140, 0.000)])

        measurements = tracker.update([
            _strong_detection(0.141, 0.001),
            _strong_detection(0.220, 0.090),
        ])

        self.assertEqual([measurement.touch_id for measurement in measurements], [1])
        self.assertEqual(len(tracker.tracks), 1)
        self.assertEqual(tracker.tracks[0]["id"], 1)
        self.assertAlmostEqual(measurements[0].x, 0.141, delta=0.0001)
        self.assertAlmostEqual(measurements[0].y, 0.001, delta=0.0001)

    def test_confirmed_track_keeps_last_strong_control_ridge_through_weak_measurement(self):
        tracker = ros_bridge.TouchTracker()
        strong = _strong_ridge_detection(
            0.140,
            0.000,
            ridge_points=[(0.1400, 0.0000), (0.1396, 0.0004)],
        )
        tracker.update([strong])
        tracker.update([strong])
        tracker.update([strong])

        tracker.update([_single_point_detection(0.1490, 0.0120, localization_quality=0.28)])

        track = tracker.tracks[0]
        self.assertEqual(track["last_evidence"]["ridge_point_count"], 2)
        self.assertEqual(len(track["last_evidence"]["ridge_points"]), 2)

        measurements = tracker.latest_measurements()
        self.assertEqual(len(measurements), 1)
        self.assertEqual(measurements[0].mode, "weak_ridge")
        self.assertEqual(measurements[0].ridge_point_count, 1)
        self.assertAlmostEqual(measurements[0].x, 0.1490, delta=0.0001)
        self.assertAlmostEqual(measurements[0].y, 0.0120, delta=0.0001)

    def test_confirmed_settling_ignores_single_moderate_strong_jump(self):
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [],
            [],
            [_strong_detection(0.141, 0.001)],
            [_strong_detection(0.190, 0.040)],
            [_strong_detection(0.142, 0.001)],
        ]

        outputs = _track_frames(frames)

        anchor_id, anchor_x, anchor_y = outputs[5][0]
        jumped_id, jumped_x, jumped_y = outputs[6][0]
        final_id, final_x, final_y = outputs[7][0]
        self.assertEqual(jumped_id, anchor_id)
        self.assertLessEqual(abs(jumped_x - anchor_x), 0.005)
        self.assertLessEqual(abs(jumped_y - anchor_y), 0.005)
        self.assertEqual(final_id, anchor_id)
        self.assertLessEqual(abs(final_x - anchor_x), 0.005)
        self.assertLessEqual(abs(final_y - anchor_y), 0.005)

    def test_confirmed_settling_accepts_repeated_moderate_strong_motion(self):
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [],
            [],
            [_strong_detection(0.141, 0.001)],
            [_strong_detection(0.190, 0.040)],
            [_strong_detection(0.191, 0.041)],
        ]

        outputs = _track_frames(frames)

        anchor_x = outputs[5][0][1]
        final_x = outputs[7][0][1]
        final_y = outputs[7][0][2]
        self.assertGreater(final_x - anchor_x, 0.02)
        self.assertGreater(final_y, 0.015)

    def test_short_gap_reacquire_resumes_moving_without_resetting_track(self):
        tracker = ros_bridge.TouchTracker()
        frames = [
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.140, 0.000)],
            [_strong_detection(0.150, 0.005)],
            [_strong_detection(0.155, 0.010)],
            [],
            [_strong_detection(0.180, 0.015)],
            [_strong_detection(0.181, 0.016)],
        ]

        outputs = []
        for frame in frames:
            outputs.append(tracker.update(frame))

        self.assertEqual(tracker.tracks[0]["id"], 1)
        self.assertEqual(outputs[5][0][0], 1)

        resumed_id, resumed_x, resumed_y = outputs[6][0]
        self.assertEqual(resumed_id, 1)
        self.assertEqual(tracker.tracks[0]["state"], "moving")
        self.assertLess(resumed_x, 0.175)
        self.assertGreater(resumed_x, outputs[5][0][1])
        self.assertGreater(resumed_y, outputs[5][0][2])

        final_id, final_x, final_y = outputs[7][0]
        self.assertEqual(final_id, 1)
        self.assertEqual(tracker.tracks[0]["state"], "moving")
        self.assertGreater(final_x, resumed_x)
        self.assertGreater(final_y, resumed_y)


if __name__ == "__main__":
    unittest.main()
