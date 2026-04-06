# Real-World LD19 Integration — Required Changes

> **Goal**: Replace the Gazebo simulation with the physical LD19 LIDAR, keep the
> `scan_tracker` counting logic unchanged, and add a standalone Python
> visualization (matplotlib) that draws the live scan, the board rectangle, ball
> centroids, and an incrementing counter.  No Kotlin UI is required.

---

## 0 — Physical Setup & Coordinate System

```
                     ← 41 cm →
     ┌─────────────────────────┐  ─┐
     │         BOARD           │   │
     │                         │   │
     │                         │  90 cm
     │                         │   │
     │                         │   │
     │  ┌────────────────┐     │   │
     │  │ LIDAR (LD19)   │     │   │
     └──┤   46.29×34.8mm ├─────┘  ─┘
        │   [scan origin]│
        └────────────────┘
              cable (below board, invisible to sensor)
```

The LD19 is placed **flat on the board surface**, centered on one of the 41 cm
short edges, with its forward face looking into the board.  The USB cable exits
from the bottom and is routed under the board, so the sensor's field of view is
a **forward-facing 180° semicircle** covering the full 90 × 41 cm surface.

### Sensor-frame axes (used everywhere below)

| Axis | Direction | Description |
|------|-----------|-------------|
| +X   | into board (90 cm direction) | depth down the board |
| +Y   | left across board (41 cm direction) | lateral |
| Origin | LD19 scan centre | approx. geometric centre of LD19 body |

### Board boundary derivation

| Dimension | Raw value | Buffer | Final param |
|-----------|-----------|--------|-------------|
| LD19 depth | 34.8 mm | — | — |
| Scan centre from near edge | 17.4 mm | — | — |
| Near board bound (avoid LIDAR body reflections) | 17.4 mm + 32.6 mm buffer | +32.6 mm | **`board_min_x = 0.050 m`** |
| Far board bound | 900 mm − 17.4 mm = 882.6 mm | −22.6 mm | **`board_max_x = 0.860 m`** |
| Half board width | 410 / 2 = 205 mm | −15 mm both sides | **`board_min_y = −0.190 m`** |
| Half board width | 205 mm | −15 mm | **`board_max_y = +0.190 m`** |

These are the numbers already used in `Bridge.kt → startTrackerRealWorld()`.  They
trim 1.5 cm inward on all four sides so the board's wooden edges never register
as phantom clusters.

---

## 1 — Change: `src/adapt_display/src/scan_tracker.cpp`

The existing node logs ball detections only to `RCLCPP_INFO` (i.e. stderr).  The
new Python visualizer needs the same data as ROS 2 topics so it can subscribe
directly without parsing log text.

Two new publishers must be added:

| Topic | Message type | Description |
|-------|-------------|-------------|
| `/ball_count` | `std_msgs/msg/Int32` | Running total; published every scan frame |
| `/ball_positions` | `std_msgs/msg/Float32MultiArray` | Flat array `[x1,y1, x2,y2, …]` of all centroids currently visible in this frame |

### 1.1 — Add header includes

Near the top of the file, alongside the existing includes, add:

```cpp
#include <std_msgs/msg/int32.hpp>
#include <std_msgs/msg/float32_multi_array.hpp>
```

### 1.2 — Add publisher member variables

Inside the `private:` section of `ScanTrackerNode`, after the existing
`scan_subscriber_` declaration, add:

```cpp
rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr             count_publisher_;
rclcpp::Publisher<std_msgs::msg::Float32MultiArray>::SharedPtr positions_publisher_;
```

### 1.3 — Initialise publishers in the constructor

Inside `ScanTrackerNode()`, after the `scan_subscriber_` initialisation line, add:

```cpp
count_publisher_ = this->create_publisher<std_msgs::msg::Int32>(
    "/ball_count", 10);

positions_publisher_ = this->create_publisher<std_msgs::msg::Float32MultiArray>(
    "/ball_positions", 10);
```

### 1.4 — Publish at the end of `scan_callback`

At the very bottom of `scan_callback`, just before the closing `}`, add:

```cpp
// Publish running count
std_msgs::msg::Int32 count_msg;
count_msg.data = total_count_;
count_publisher_->publish(count_msg);

// Publish current-frame centroid list as flat [x1,y1, x2,y2, ...] array
std_msgs::msg::Float32MultiArray pos_msg;
pos_msg.data.reserve(clusters.size() * 2);
for (const auto& c : clusters) {
    pos_msg.data.push_back(static_cast<float>(c.centroid_x));
    pos_msg.data.push_back(static_cast<float>(c.centroid_y));
}
positions_publisher_->publish(pos_msg);
```

---

## 2 — Change: `src/adapt_display/CMakeLists.txt`

Three edits are required.

### 2.1 — Add `std_msgs` to `find_package`

After the existing `find_package(sensor_msgs REQUIRED)` line, add:

```cmake
find_package(std_msgs REQUIRED)
```

### 2.2 — Add `std_msgs` to scan_tracker's `ament_target_dependencies`

The existing line reads:

```cmake
ament_target_dependencies(scan_tracker rclcpp sensor_msgs)
```

Change it to:

```cmake
ament_target_dependencies(scan_tracker rclcpp sensor_msgs std_msgs)
```

### 2.3 — Register the new Python scripts

The existing `install(PROGRAMS …)` block lists Python scripts.  Add the two new
files (created in sections 3 and 4 below) to that block:

```cmake
install(PROGRAMS
  scripts/py_node.py
  scripts/spawn_single_ball.py
  scripts/spawn_multiple_balls.py
  scripts/remove_balls.py
  scripts/rw_viz.py          # ← add this
  DESTINATION lib/${PROJECT_NAME}
)
```

Also add the new launch directory content (the new launch file goes into the
existing `launch/` directory so the existing `install(DIRECTORY launch …)` block
already covers it — no extra change needed there).

---

## 3 — New File: `src/adapt_display/scripts/rw_viz.py`

Create this file at the path above.  It is a standalone ROS 2 Python node that
subscribes to `/scan`, `/ball_count`, and `/ball_positions`, and renders a live
matplotlib window.

```python
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
  /scan             sensor_msgs/LaserScan   — raw LD19 data
  /ball_count       std_msgs/Int32          — running total from scan_tracker
  /ball_positions   std_msgs/Float32MultiArray — centroid flat array [x1,y1,…]

Run after sourcing both workspaces (see start_real_world.sh).
"""

import math
import threading

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Int32, Float32MultiArray

import matplotlib
matplotlib.use("TkAgg")          # use TkAgg so the window runs on the main thread
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation

# ── Board boundary constants (sensor-frame, metres) ─────────────────────────
# These must match the params passed to scan_tracker (see real_world.launch.py)
BOARD_MIN_X =  0.050
BOARD_MAX_X =  0.860
BOARD_MIN_Y = -0.190
BOARD_MAX_Y =  0.190

# ── Plot axis limits (give a small margin around the board) ──────────────────
AXIS_MIN_X = -0.10
AXIS_MAX_X =  1.00
AXIS_MIN_Y = -0.30
AXIS_MAX_Y =  0.30


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
        self.create_subscription(LaserScan,           "/scan",
                                 self._on_scan, 10)
        self.create_subscription(Int32,               "/ball_count",
                                 self._on_count, 10)
        self.create_subscription(Float32MultiArray,   "/ball_positions",
                                 self._on_positions, 10)

    # ── Callbacks ────────────────────────────────────────────────────────────

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

    ax.set_xlim(AXIS_MIN_X, AXIS_MAX_X)
    ax.set_ylim(AXIS_MIN_Y, AXIS_MAX_Y)
    ax.set_aspect("equal")
    ax.set_xlabel("X — along board length (m)", color="white")
    ax.set_ylabel("Y — across board width (m)", color="white")
    ax.set_title("LD19 Real-World View", color="white", fontsize=12)
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#444444")

    # Board boundary rectangle (dashed green)
    board_rect = mpatches.FancyBboxPatch(
        (BOARD_MIN_X, BOARD_MIN_Y),
        BOARD_MAX_X - BOARD_MIN_X,
        BOARD_MAX_Y - BOARD_MIN_Y,
        boxstyle="square,pad=0",
        linewidth=1.5, edgecolor="#00cc44", facecolor="none",
        linestyle="--", label="Board boundary",
    )
    ax.add_patch(board_rect)

    # LIDAR origin marker
    ax.plot(0, 0, marker="^", color="#ffcc00", markersize=10, zorder=5,
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
            scan_scatter.set_offsets(list(zip(scan_xs, scan_ys)))
        else:
            scan_scatter.set_offsets([])

        if ball_xs:
            ball_scatter.set_offsets(list(zip(ball_xs, ball_ys)))
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
```

### Dependencies note

`matplotlib` must be installed in the system Python used by ROS 2:

```bash
pip install matplotlib --break-system-packages
# OR, if the above conflicts:
sudo apt install python3-matplotlib
```

---

## 4 — New File: `src/adapt_display/launch/real_world.launch.py`

This launch file starts three things in order:
1. The physical LD19 driver (from the `rw` workspace / `ldlidar_stl_ros2` package)
2. `scan_tracker` (from `big_boulder`) with the real-world board boundary params
3. The `rw_viz.py` visualizer

```python
#!/usr/bin/env python3
"""
real_world.launch.py
====================
Launches the full real-world pipeline:
  1. ldlidar_stl_ros2 LD19 driver  → publishes /scan
  2. adapt_display scan_tracker    → detects balls, publishes /ball_count and /ball_positions
  3. adapt_display rw_viz          → live matplotlib window

Pre-requisites
  • Both workspaces sourced (see start_real_world.sh)
  • LD19 connected via USB → /dev/ttyUSB0 (or update port_name below)
  • adapt_display rebuilt after the scan_tracker changes described in this doc
"""

from launch import LaunchDescription
from launch.actions import TimerAction
from launch_ros.actions import Node


# ── Board boundary (sensor-frame, metres) ────────────────────────────────────
# Derived from 90 × 41 cm board with LD19 centred on the short edge.
# Trim 1.5 cm inward on all sides to avoid detecting the wooden board edges.
BOARD_MIN_X =  0.050
BOARD_MAX_X =  0.860
BOARD_MIN_Y = -0.190
BOARD_MAX_Y =  0.190


def generate_launch_description():

    # ── 1. LD19 hardware driver ───────────────────────────────────────────────
    # Publishes sensor_msgs/LaserScan on /scan at ~10 Hz.
    # angle_crop hides the 45° cone directly behind the sensor (cable side)
    # so the board surface receives a clean 180° forward scan.
    ld19_driver = Node(
        package="ldlidar_stl_ros2",
        executable="ldlidar_stl_ros2_node",
        name="LD19",
        parameters=[
            {"product_name":          "LDLiDAR_LD19"},
            {"topic_name":            "scan"},
            {"frame_id":              "laser_frame"},
            {"port_name":             "/dev/ttyUSB0"},
            {"port_baudrate":         230400},
            {"laser_scan_dir":        True},
            # Mask 157.5°–202.5° (the 45° cone behind the sensor / cable side).
            # NOTE: these are the HIDDEN angles, not the visible ones.
            {"enable_angle_crop_func": True},
            {"angle_crop_min":        157.5},
            {"angle_crop_max":        202.5},
            {"bins":                  455},
        ],
        output="screen",
    )

    # ── 2. scan_tracker: ball detection + counting ────────────────────────────
    # Give the LD19 driver 2 s to start publishing /scan before scan_tracker
    # tries to subscribe to it.  Without this delay scan_tracker logs a warning
    # every frame about "no publisher" and the first few frames may be dropped.
    scan_tracker = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="adapt_display",
                executable="scan_tracker",
                name="scan_tracker",
                output="screen",
                parameters=[
                    # Clustering: 10 cm gap between points → separate cluster
                    {"distance_threshold":    0.10},
                    # A single LIDAR hit is enough to register a ball
                    {"min_points_per_cluster": 1},
                    # Track matching: centroids within 50 cm = same ball
                    {"match_radius":           0.50},
                    # Forget a track after 30 consecutive missed frames (~3 s)
                    {"absent_frames_to_forget": 30},
                    # Board filtering ON — ignore everything outside the board
                    {"enable_board_filtering": True},
                    {"board_min_x": BOARD_MIN_X},
                    {"board_max_x": BOARD_MAX_X},
                    {"board_min_y": BOARD_MIN_Y},
                    {"board_max_y": BOARD_MAX_Y},
                ],
            )
        ],
    )

    # ── 3. Live visualizer ────────────────────────────────────────────────────
    # Starts 3 s after driver launch so the first frames are already populated
    # before the matplotlib window opens.
    rw_viz = TimerAction(
        period=3.0,
        actions=[
            Node(
                package="adapt_display",
                executable="rw_viz.py",
                name="rw_viz",
                output="screen",
            )
        ],
    )

    return LaunchDescription([
        ld19_driver,
        scan_tracker,
        rw_viz,
    ])
```

---

## 5 — New File: `start_real_world.sh`  (workspace root, i.e. beside `big_boulder/` and `rw/`)

A single shell script that chains both workspace setups and then fires the launch
file.  This is the **only** script you need to run.

```bash
#!/usr/bin/env bash
# start_real_world.sh
# Usage:  bash start_real_world.sh
# Place this file alongside the big_boulder/ and rw/ directories.

set -e

# Absolute paths — adjust if your workspace root is different
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIG_BOULDER="$SCRIPT_DIR/big_boulder"
RW="$SCRIPT_DIR/rw"

echo "[start_real_world] Sourcing workspaces..."
# shellcheck disable=SC1091
source "$RW/install/setup.bash"
# shellcheck disable=SC1091
source "$BIG_BOULDER/install/setup.bash"

echo "[start_real_world] Launching real_world pipeline..."
exec ros2 launch adapt_display real_world.launch.py
```

Make it executable once:

```bash
chmod +x start_real_world.sh
```

---

## 6 — Build Instructions

After making all changes above, rebuild only `adapt_display` (the `rw` workspace
does not change):

```bash
cd big_boulder
colcon build --packages-select adapt_display
```

If `colcon` complains about `std_msgs` not being found, ensure it is installed:

```bash
sudo apt install ros-humble-std-msgs
```

---

## 7 — Run Order

```
Terminal 1 (or just run this):
  bash start_real_world.sh

This single command:
  1. Sources rw/install/setup.bash          (makes ldlidar_stl_ros2 visible)
  2. Sources big_boulder/install/setup.bash (makes adapt_display visible)
  3. ros2 launch adapt_display real_world.launch.py
       ├── t=0 s   → LD19 driver starts, /scan begins publishing
       ├── t=2 s   → scan_tracker starts subscribing to /scan
       └── t=3 s   → rw_viz.py opens the matplotlib window
```

---

## 8 — How the Counter Works (End-to-End)

```
Physical LD19
  │  USB serial @ 230400 baud
  ▼
ldlidar_stl_ros2_node
  │  publishes sensor_msgs/LaserScan on /scan  (~10 Hz)
  │  angle_crop hides cable-side cone (157.5°–202.5°)
  ▼
scan_tracker (C++ node)
  │  converts polar → Cartesian
  │  filters points outside board rect (board_min/max_x/y)
  │  clusters by 10 cm Euclidean gap
  │  matches clusters to previous-frame tracks
  │  NEW cluster (no match) → total_count_++
  │  publishes /ball_count  (Int32, running total)
  │  publishes /ball_positions (Float32MultiArray, current centroids)
  ▼
rw_viz.py (Python node)
  │  /scan → white scatter points
  │  /ball_positions → red circles at centroid locations
  │  /ball_count → "Balls: N" text overlay
  ▼
matplotlib window (live, ~25 fps)
```

A ball that lands on the board increments the counter by exactly 1.  A ball that
lands outside the board boundary rect produces LIDAR hits that are discarded by
the board-filtering step in `scan_tracker`, so the counter stays unchanged.

---

## 9 — Tuning the Board Boundary

If test drops show the counter triggering for objects placed outside the board
(or missing objects placed on the board edge), adjust the four `board_*` params.
They live in **two** places that must stay in sync:

| File | Location |
|------|----------|
| `src/adapt_display/launch/real_world.launch.py` | `parameters=[…]` block in `scan_tracker` Node |
| `big_boulder/AdaptBoard/app/src/desktopMain/kotlin/Bridge.kt` | `startTrackerRealWorld()` method (for future Kotlin UI use) |

Values are in **metres, sensor-frame**.  With the LIDAR at the origin:
- Increase `board_min_x` if the LIDAR body itself is being detected as a ball at startup.
- Decrease `board_max_x` if the far board edge registers phantom clusters.
- Tighten `board_min_y` / `board_max_y` symmetrically if the side edges produce noise.

---

## 10 — File Change Summary

| File | Action | What changed |
|------|--------|-------------|
| `src/adapt_display/src/scan_tracker.cpp` | **Modify** | Add `#include` for `std_msgs`, two publisher members, publisher init in ctor, publish calls at end of `scan_callback` |
| `src/adapt_display/CMakeLists.txt` | **Modify** | `find_package(std_msgs)`, add `std_msgs` to `ament_target_dependencies`, register `rw_viz.py` in `install(PROGRAMS)` |
| `src/adapt_display/scripts/rw_viz.py` | **New** | Matplotlib-based live visualizer node |
| `src/adapt_display/launch/real_world.launch.py` | **New** | Orchestrates LD19 driver + scan_tracker + rw_viz |
| `start_real_world.sh` | **New** | Sources both workspaces, fires the launch file |

No changes are needed to `rw/` — the LD19 driver and its launch file are used
as-is from that workspace.
