# Agent Interface — adapt_display ROS 2 Package

> **Last updated**: 2026-03-05  
> **Target reader**: Any AI agent working on the Kotlin UI or ROS 2 layer  
> **ROS 2 Distro**: Humble | **Simulator**: Gazebo Classic  
> **Workspace root**: `/home/xanta/big_boulder`

---

## 1. System Overview

A **stationary 2D lidar** on a platform at z≈0.65m scans 360° at 100Hz (720 samples) with a 6.0m range. Balls (r=0.05m) are spawned above it and fall through the scan plane. A C++ node (`scan_tracker`) detects, clusters, and **counts** them using frame-to-frame centroid matching.

The **AdaptBoard** Kotlin UI at `/home/xanta/big_boulder/AdaptBoard/` drives the simulation via shell subprocess calls. It does NOT use ROS libraries directly.

---

## 2. Executable Nodes & Parameters

**Always source first**: `source /home/xanta/big_boulder/install/setup.bash`

### 2.1 Launch Simulation (run first)
```bash
ros2 launch adapt_display launch_simulation.launch.py
```
Starts Gazebo, spawns the lidar platform, begins `/scan` topic.

### 2.2 Spawn Single Ball
```bash
ros2 run adapt_display spawn_single_ball.py --ros-args \
  -p board_width:=6.0 -p board_height:=4.0 \
  -p margin_width:=10.0 -p margin_height:=8.0 \
  -p spawn_height:=2.0
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `board_width` | double | 6.0 | Board width in meters (80% of balls land here) |
| `board_height` | double | 4.0 | Board height in meters |
| `margin_width` | double | 10.0 | Margin width in meters (max spawn extent) |
| `margin_height` | double | 8.0 | Margin height in meters |
| `spawn_height` | double | 2.0 | Drop height (meters above ground) |
| `offset_x` | double | 0.0 | X offset to shift spawn center (meters) |
| `offset_y` | double | 0.0 | Y offset to shift spawn center (meters) |

**Spawn distribution**: 80% uniform within `board_width × board_height`, 20% in the margin strip between board edge and margin edge. 0% outside margin. The offset shifts the entire spawn region so balls land relative to the board/margin center rather than the lidar position.

### 2.3 Spawn Multiple Balls
Same params as above, plus:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `num_balls` | int | 10 | Number of balls to spawn sequentially |

### 2.4 Remove Balls
```bash
ros2 run adapt_display remove_balls.py --ros-args -p num_balls:=5  # remove last 5
ros2 run adapt_display remove_balls.py                              # remove ALL
```

### 2.5 Scan Tracker (long-running)
```bash
ros2 run adapt_display scan_tracker --ros-args \
  -p distance_threshold:=0.15 \
  -p min_points_per_cluster:=1 \
  -p match_radius:=0.5 \
  -p absent_frames_to_forget:=30
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `distance_threshold` | double | 0.15 | Max gap between adjacent scan points to cluster them |
| `min_points_per_cluster` | int | 1 | Min hits for a valid cluster |
| `match_radius` | double | 0.5 | Max centroid-to-centroid distance to match across frames |
| `absent_frames_to_forget` | int | 30 | Frames without seeing a track before forgetting it |

**Counting logic**:
- **New cluster** (no match) → `total_count++`
- **Reappearing** (was absent, then matched again) → `total_count++`
- **Continuous** (present in consecutive frames) → no re-count
- A big ball sitting still = exactly 1 count

### 2.6 scan_tracker Output Format (stderr)

> [!IMPORTANT]
> All output goes to **stderr** via `RCLCPP_INFO`. Read `process.errorStream` in Kotlin.

```
[scan_tracker]: Ball NEW at (1.234, -0.567) | Total: 1
[scan_tracker]: --- Detected 2 Balls --- | Total Count: 3
[scan_tracker]: Ball 1: Centroid X (1.234), Y (-0.567) | Points: 4
[scan_tracker]: Ball 2: Centroid X (-0.100), Y (0.800) | Points: 3
```

Key lines for parsing:
- `--- Detected N Balls --- | Total Count: M` — frame header, M = total unique events
- `Ball N: Centroid X (x), Y (y) | Points: P` — centroid position per cluster
- `Ball NEW at (x, y) | Total: M` — first appearance
- `Ball REAPPEARED at (x, y) | Total: M` — re-entry after absence

---

## 3. Physical Constraints

| Property | Value | Impact |
|---|---|---|
| Lidar max range | **6.0 m** | Balls beyond 6m are invisible |
| Lidar min range | 0.12 m | Dead zone within 12cm |
| Lidar update rate | 100 Hz | ~10ms between scans |
| Scan plane height | ~0.65 m | Balls on ground (z=0) are below scan |
| Lidar samples | 720 | Per revolution, 0.5° angular resolution |
| Ball radius | 0.05 m | Ball transit through scan plane ≈ 19.4ms |
| Ball naming | `ball_<uuid8>` | `remove_balls.py` filters by `ball_` prefix |
| Coordinate origin | Lidar center | (0,0) in scan_tracker output |

---

## 4. Build & Rebuild

```bash
cd /home/xanta/big_boulder
source /opt/ros/humble/setup.bash
colcon build --packages-select adapt_display
source install/setup.bash
```

**Requires rebuild**: Any change to `.cpp`, `.py`, `CMakeLists.txt`, `package.xml`, `.urdf`, `.xacro`, `.launch.py`

**Does NOT require rebuild**: Runtime parameter changes via `--ros-args`

---

## 5. Rules for Agents

### DO
- Source the workspace before any `ros2` command
- Always launch the simulation before running spawners or tracker
- Read `errorStream` (stderr) for ROS node output, not `inputStream` (stdout)
- Kill the full process tree (use `ProcessHandle.descendants()`) when stopping Gazebo
- Read both stdout and stderr on separate threads to avoid pipe deadlock
- Rebuild after modifying any source file

### DO NOT
- Pass UI abstract units as raw meter values — the UI's board/margin values ARE meters
- Assume `Process.destroyForcibly()` kills child processes — it only kills the bash shell
- Read `process.inputStream` for ROS logging — it goes to stderr
- Spawn balls before the simulation is running — requires `/spawn_entity` service
- Change the `ball_` entity naming prefix — `remove_balls.py` depends on it
