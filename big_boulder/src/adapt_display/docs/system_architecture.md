# System Architecture — adapt_display + AdaptBoard

> **Last updated**: 2026-03-05  
> **ROS 2 Distro**: Humble  
> **Simulator**: Gazebo Classic (`gazebo_ros`)  
> **UI**: Compose Desktop (Kotlin/JVM) at `/home/xanta/big_boulder/AdaptBoard/`

---

## High-Level Overview

A **stationary 2D lidar** sits on a platform in Gazebo. Balls are spawned above it and fall through its horizontal scan plane. A C++ node (`scan_tracker`) detects, clusters, and **counts** them in real-time. A Kotlin desktop UI (`AdaptBoard`) manages the simulation lifecycle, spawning, and visualizes detections on a 2D canvas.

```mermaid
graph TD
    subgraph "AdaptBoard (Kotlin Desktop UI)"
        M[Main.kt — App shell + Canvas]
        SM[SimulationManager — Process lifecycle]
        TP[TrackerParser — Parse scan_tracker stderr]
        PS[ProcessScope — Async subprocess runner]
        BR[Bridge.kt — ROS CLI wrappers]
        IP[InfoPanel — Status + Nodes + Logs + Count]
        BO[BallOverlay — Draw detections on canvas]
        SC[SimulationConfig — Board/Margin/Lidar/Ball params]
        ST[Settings.kt — Editable param fields]
    end

    subgraph "adapt_display (ROS 2 Package)"
        LS[launch_simulation.launch.py]
        SSB[spawn_single_ball.py]
        SMB[spawn_multiple_balls.py]
        RMB[remove_balls.py]
        SCT[scan_tracker — C++ detection + counting]
    end

    subgraph "Gazebo Classic"
        GS[/spawn_entity service]
        GD[/delete_entity service]
        GL[/get_model_list service]
        SCAN[/scan topic — 30Hz LaserScan]
    end

    M --> SM
    M --> TP
    M --> IP
    M --> BO
    SM --> BR
    TP --> BR
    PS --> BR
    BR -->|"bash -c ros2 ..."| LS
    BR -->|"bash -c ros2 ..."| SSB
    BR -->|"bash -c ros2 ..."| SMB
    BR -->|"bash -c ros2 ..."| RMB
    BR -->|"bash -c ros2 ..."| SCT
    TP -.->|"reads stderr"| SCT
    SSB --> GS
    SMB --> GS
    RMB --> GD
    RMB --> GL
    SCT -->|"subscribes"| SCAN
    IP -.->|"ros2 node list"| LS
```

---

## Directory Layout

```
/home/xanta/big_boulder/
├── src/adapt_display/              # ROS 2 package (C++/Python)
│   ├── CMakeLists.txt
│   ├── package.xml
│   ├── description/
│   │   ├── robot.urdf.xacro        # Lidar platform (scan plane at z≈0.65m)
│   │   └── ball.urdf               # Ball model (r=0.05m, m=0.1kg)
│   ├── src/
│   │   ├── scan_tracker.cpp        # Detection + counting node
│   │   └── display_node.cpp        # (minimal placeholder)
│   ├── scripts/
│   │   ├── spawn_single_ball.py    # Spawn 1 ball within board/margin
│   │   ├── spawn_multiple_balls.py # Spawn N balls
│   │   ├── remove_balls.py         # Remove N or all balls
│   │   └── py_node.py              # (minimal placeholder)
│   ├── launch/
│   │   ├── launch_simulation.launch.py
│   │   └── display.launch.py
│   ├── config/
│   │   └── gazebo_params.yaml
│   └── docs/                       # ← YOU ARE HERE
│       ├── system_architecture.md
│       ├── AGENT_INTERFACE.md
│       └── KOTLIN_UI.md
├── AdaptBoard/                     # Kotlin Desktop UI
│   ├── build.gradle.kts
│   └── app/src/desktopMain/kotlin/
│       ├── Main.kt                 # Entry point, canvas, action buttons
│       ├── AppTheme.kt             # Colors, drawer, nav
│       ├── Bridge.kt               # All ROS CLI subprocess wrappers
│       ├── ProcessScope.kt         # Async dual-stream subprocess runner
│       ├── SimulationManager.kt    # Gazebo process lifecycle
│       ├── SimulationConfig.kt     # Data classes + state management
│       ├── Settings.kt             # Editable parameter fields + save/rebuild
│       ├── TrackerParser.kt        # Parse scan_tracker stderr for detections
│       ├── BallOverlay.kt          # Draw detected balls on canvas
│       ├── InfoPanel.kt            # Right sidebar: status, nodes, logs, counts
│       ├── Board.kt                # Draw board rectangle
│       ├── Support.kt              # Draw dashed margin rectangle
│       ├── Lidar.kt                # Draggable lidar dot + gestures
│       └── About.kt                # About page
└── install/                        # colcon build output (source setup.bash)
```

---

## Physical Constants

| Property | Value | Notes |
|---|---|---|
| Lidar max range | **6.0 m** | URDF `robot.urdf.xacro` line 75 |
| Lidar min range | 0.12 m | Below this = dead zone |
| Lidar update rate | 100 Hz | ~10ms per scan |
| Lidar scan plane height | ~0.65 m | z-offset of `cylinder0` |
| Lidar scan arc | 0 → 6.28 rad | Full 360° |
| Lidar samples | 720 | Per revolution (0.5° resolution) |
| Ball radius | 0.05 m | URDF `ball.urdf` |
| Ball mass | 0.1 kg | URDF `ball.urdf` |
| Default spawn height | 2.0 m | Runtime param |
| Board default | 6 × 4 m | SimulationConfig |
| Margin default | 10 × 8 m | SimulationConfig |

---

## Communication Protocol

The Kotlin UI does NOT use ROS libraries. All communication is via **shell subprocesses**:

1. `Bridge.kt` builds bash commands (`source install/setup.bash && ros2 ...`)
2. `ProcessScope.kt` runs them on `Dispatchers.IO` with dual-thread stdout/stderr reading
3. `SimulationManager.kt` manages the long-running Gazebo process
4. `TrackerParser.kt` reads the long-running `scan_tracker` process **stderr** (ROS2 logs to stderr)

> [!CAUTION]
> ROS 2 `RCLCPP_INFO` and all ROS logging macros write to **stderr**, not stdout.
> Any code parsing ROS node output must read `process.errorStream`, not `process.inputStream`.

---

## Known Gotchas

1. **stderr vs stdout**: ROS logging → stderr. TrackerParser reads errorStream.
2. **Process tree kill**: `Process.destroyForcibly()` only kills the bash shell, not Gazebo/ROS children. Must use `ProcessHandle.descendants()` to kill the tree.
3. **URDF changes require rebuild**: Any edit to `robot.urdf.xacro` or `ball.urdf` requires `colcon build` + simulation restart.
4. **Scan plane height**: The lidar scans at z≈0.65m. Balls resting on the ground (z=0) are below the scan plane and invisible to the lidar. Only balls currently falling through or intersecting the plane are detected. At 100Hz, a ball with r=0.05m falling from 2m has ≈19.4ms transit time — guaranteed at least 1 scan hit.
5. **Pipe deadlock**: When reading both stdout and stderr from a process, both must be consumed concurrently (on separate threads) to avoid the OS pipe buffer filling up and blocking the process.
