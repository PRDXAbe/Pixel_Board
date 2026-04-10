# PixelBoard

A LIDAR-powered smart board that turns any physical board into a touchscreen. The LD19 LiDAR detects finger/object positions on the board surface and outputs exact pixel coordinates in real time — displayed through a clean Kotlin Compose desktop UI.

## How It Works

```
LD19 LiDAR  →  ROS2 /scan topic  →  ros_bridge.py  →  Kotlin UI
                                         │
                                   filter → cluster → map to mm
                                         │
                                   pixel (x, y) on the board
```

The LiDAR mounts at the edge of the board. When a finger touches the surface, it appears as a new cluster of scan points. The system maps that cluster's physical position to a pixel coordinate where `(0, 0)` is the board's top-left corner and `(width_mm, height_mm)` is the bottom-right — matching the board's real physical dimensions exactly.

## Quick Start

```bash
bash run_app.sh
```

This will:
1. Automatically fix serial port permissions for the LD19
2. Launch the Kotlin Compose desktop UI

Then click **▶ Start Driver** in the app. The LiDAR driver and scan bridge start automatically.

> **First-time permission fix** (permanent — do once, then `run_app.sh` needs no sudo):
> ```bash
> sudo usermod -aG dialout $USER   # log out and back in after
> ```

## Requirements

- **OS**: Ubuntu 22.04 (Jammy)
- **ROS 2**: Humble
- **Java**: JDK 21 (`sudo apt install -y openjdk-21-jdk`)
- **Python**: 3.10+ with `rclpy` (comes with ROS 2)
- **Hardware**: LDROBOT LD19 LiDAR on `/dev/ttyUSB0` at 230400 baud

## Build the LiDAR Driver (once)

```bash
cd rw
source /opt/ros/humble/setup.bash
colcon build --packages-select ldlidar_stl_ros2 --symlink-install
```

## Configuration

### Board Dimensions (in the UI)

Enter your board's exact physical size in the **Control Panel** → **Board Dimensions** fields (width and height in mm). Hit **Save** — the system immediately updates both the scan boundary and the pixel coordinate space.

**Example:** A 150 cm × 90 cm board → enter `1500` × `900`. Touching the center outputs pixel `(750, 450)`.

### Direct config edit

`board_config.json` is the single source of truth:

| Key | Default | Description |
|-----|---------|-------------|
| `board_min_x` | 0.05 m | LIDAR boundary — near edge |
| `board_max_x` | 1.05 m | LIDAR boundary — far edge |
| `board_min_y` | -0.25 m | LIDAR boundary — left edge |
| `board_max_y` | 0.25 m | LIDAR boundary — right edge |
| `board_width_mm` | 1000 | Physical board width → pixel X range |
| `board_height_mm` | 500 | Physical board height → pixel Y range |
| `cluster_dist` | 0.08 m | Max point gap within a touch cluster |
| `min_pts` | 2 | Minimum points to count as a touch |

Run `python3 configure_board.py` for an interactive LIDAR boundary calibrator.

## Project Structure

```
Pixel_Board/
├── run_app.sh              ← Single entry point — run this
├── board_config.json       ← Board + detection parameters
├── ros_bridge.py           ← ROS2 bridge: /scan → JSON → Kotlin UI
├── touch_output.py         ← Standalone terminal touch output (no UI)
├── magic_board_live.py     ← Matplotlib live visualizer (standalone)
├── configure_board.py      ← Interactive LIDAR boundary calibrator
├── start_real_world.sh     ← Manual driver launch (without UI)
├── pixel_board_ui/         ← Kotlin Compose desktop app
│   ├── src/main/kotlin/
│   │   ├── Main.kt
│   │   ├── AppState.kt
│   │   ├── AppViewModel.kt
│   │   ├── ProcessManager.kt
│   │   └── ui/
│   │       ├── MainScreen.kt
│   │       ├── LidarCanvas.kt   ← Top-down LIDAR visualization
│   │       ├── TouchPanel.kt    ← Live pixel coordinate display
│   │       ├── ControlPanel.kt  ← Start/stop + board config
│   │       ├── TopBar.kt
│   │       └── StatusBar.kt
│   └── build.gradle.kts
└── rw/                     ← ROS 2 workspace
    └── src/
        ├── ldlidar_stl_ros2/   ← LD19/LD06 LiDAR driver
        └── sllidar_ros2-main/  ← RPLIDAR driver (unused, kept for reference)
```

## UI Overview

| Panel | Content |
|-------|---------|
| **Left — Control** | Start/Stop driver, board dimensions editor (save to JSON) |
| **Centre — Canvas** | Live top-down LIDAR scan with touch markers and board boundary |
| **Right — Touch** | Real-time pixel coordinates per finger, mini 2D position map |
| **Top bar** | Connection status, scan rate, board dimensions |
| **Status bar** | Scan count, Hz, board mm range, serial port |
