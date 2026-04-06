# Adapt Board

A Kotlin Compose Desktop application for the **adapt_display** ROS 2 Simulation System.

## Architecture

```mermaid
graph TD
    M[Main.kt<br/>Entry + Nav + Splash] --> S[Settings.kt]
    M --> AB[About.kt]
    M --> MBP[MainBoardPage]

    SC[SimulationConfigState] -.->|boardSettings| MBP
    SC -.->|simState| S

    MBP --> L[Lidar.kt<br/>LidarState + LidarDot]
    MBP --> B[Board.kt<br/>BoardConfig + drawBoard]
    MBP --> SP[Support.kt<br/>SupportConfig + drawSupport]
    MBP --> BO[BallOverlay.kt<br/>drawDetectedBalls]
    MBP --> IP[InfoPanel.kt<br/>Status + Nodes + Logs + Detection]

    SM[SimulationManager] -.->|status| MBP
    SM -.->|status| IP
    TP[TrackerParser] -.->|detections| BO
    TP -.->|count| IP

    RB[Bridge.kt<br/>RosBridge] --> SM
    RB --> TP
    PS[ProcessScope.kt] --> RB

    AT[AppTheme.kt<br/>Colors + Drawer] --> M
    AT -.-> S
    AT -.-> AB
    AT -.-> MBP
```

## Module Summary

| File | Responsibility |
|---|---|
| `Main.kt` | Entry point, splash screen, navigation, page composition |
| `AppTheme.kt` | Shared colors, `Page` enum, drawer composables |
| `Settings.kt` | Settings page with ROS 2 parameter cards |
| `About.kt` | About page |
| `Lidar.kt` | `LidarState` data class, `LidarDot` composable, `clampToGap()` |
| `Board.kt` | `BoardConfig` data class, `drawBoard()` DrawScope extension |
| `Support.kt` | `SupportConfig` data class, `drawSupport()` DrawScope extension |
| `InfoPanel.kt` | Right sidebar showing live sensor coordinates and status |
| `Bridge.kt` | `RosBridge` object — ROS 2 subprocess integration layer |

## Build & Run

```bash
cd /home/xanta/big_boulder/AdaptBoard
./gradlew build   # compile
./gradlew run     # launch
```
