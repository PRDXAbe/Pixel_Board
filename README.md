# Magic Board

Real-time ball detection and counting system using an RPLIDAR A1-M8. A LIDAR sensor mounted at the edge of a physical drawing board scans across the surface and detects balls as they land, maintaining a running total count.

## Hardware

- **LIDAR**: RPLIDAR A1-M8 connected via USB (`/dev/ttyUSB0`)
- **Board**: 90 cm × 41 cm drawing board
- **Mounting**: LIDAR centered on one 41 cm edge, scanning into the board surface

## Requirements

- ROS 2 Humble
- Python 3 with `matplotlib` and `numpy`
- User must be in the `dialout` group for USB serial access

```bash
sudo usermod -aG dialout $USER   # re-login after this
```

## Build

Build the RPLIDAR driver (only needed once):

```bash
cd rw
source /opt/ros/humble/setup.bash
colcon build --packages-select sllidar_ros2
```

## Run

```bash
bash start_real_world.sh
```

This will:
1. Kill any stale LIDAR processes from previous runs
2. Start the RPLIDAR A1-M8 driver on `/dev/ttyUSB0`
3. Open the live top-down visualization with ball counter

Close the visualization window to stop everything.

## Configuration

Board dimensions and detection parameters are set at the top of `magic_board_live.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BOARD_MIN_X` | 0.050 m | Near edge (avoids LIDAR body) |
| `BOARD_MAX_X` | 0.860 m | Far edge |
| `BOARD_MIN_Y` | -0.190 m | Left edge |
| `BOARD_MAX_Y` | 0.190 m | Right edge |
| `DISTANCE_THRESHOLD` | 0.10 m | Cluster gap for ball detection |
| `MATCH_RADIUS` | 0.50 m | Max centroid movement between frames |

## Project Structure

```
Magic_Board/
├── start_real_world.sh       # Entry point
├── magic_board_live.py       # Live visualizer + ball counter
├── rw/                       # Real-world ROS 2 workspace
│   └── src/
│       ├── sllidar_ros2-main/  # RPLIDAR A1/A2/A3 driver
│       └── ldlidar_stl_ros2/   # LD19/LD06 driver (alternative)
└── big_boulder/              # Simulation workspace + Kotlin UI
    └── src/
        └── adapt_display/    # Ball detection node (scan_tracker) + launch files
```

## Simulation Mode

A Gazebo-based simulation and Kotlin desktop UI are available for development without physical hardware:

```bash
# Terminal 1
cd big_boulder
source /opt/ros/humble/setup.bash
colcon build --packages-select adapt_display
source install/setup.bash
ros2 launch adapt_display launch_simulation.launch.py

# Terminal 2
cd big_boulder/AdaptBoard
./gradlew run
```
