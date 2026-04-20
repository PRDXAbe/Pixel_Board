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


class TouchTrackerRegressionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
