# Handover

This file replaces `tasks.md`.

The project is being handed off with one main goal:

- attain true interactive projection on real hardware, meaning the physical LiDAR interaction plane maps reliably onto the intended system/projector display with stable hover, usable single click, and predictable double click behavior

## 1. Current Target Behavior

The current intended interaction model is:

- hover should feel stable and not visibly wobble or teleport
- single click should still work from a tap/release gesture
- single click currently dispatches after about `1s`
- double click is no longer based on a second tap
- double click is currently a dwell gesture:
  stay within about `8 px` of one stabilized screen point for `2000 ms`
  then a system `doubleClick()` is fired at that anchored point
- if the touch releases before `2000 ms`, the dwell state resets
- after a dwell-triggered double click fires, the dwell state resets and can fire again after another full stable dwell

## 2. Current Architecture

The runtime stack is:

1. Hardware / OS session
   - LiDAR device on `/dev/ttyUSB*`
   - Desktop session must support Java `Robot` injection
   - Wayland is currently not supported for desktop input injection
2. Driver
   - `rw/src/ldlidar_stl_ros2/launch/ld19.launch.py`
   - `rw/src/ldlidar_stl_ros2/src/demo.cpp`
3. Bridge / touch tracking
   - `ros_bridge.py`
   - `touch_output.py`
4. UI orchestration and input injection
   - `pixel_board_ui/src/main/kotlin/AppViewModel.kt`
   - `pixel_board_ui/src/main/kotlin/InteractiveGestureHeuristics.kt`
   - `pixel_board_ui/src/main/kotlin/DesktopInputController.kt`
5. Calibration / mapping
   - `board_config.json`
   - `configure_board.py`

Startup entrypoints:

- `run_app.sh`
  starts the Kotlin UI; the UI starts/stops the driver and bridge
- `start_real_world.sh`
  starts the LD19 driver and raw visualization path for lower-level real-world inspection

## 3. Important Findings Already Made

These findings matter before any new tuning work:

- A major root cause of instability was upstream:
  LD19 was previously publishing partial rolling scans with internal filtering disabled.
- The LD19 launch is now intentionally configured for full scans with filtering:
  `enable_internal_filter = True`
  `rolling_publish_hz = 0.0`
- The board is small relative to the screen mapping:
  `344 x 193 mm` mapped to `1920 x 1080`
  so small physical jitter becomes large pixel motion.
- Bridge-side motion tracking was updated so coherent motion can move faster while stationary touches stay more locked.
- UI-side pointer stabilization and prediction were added to reduce visible wobble and latency.
- PixelBoard self-click suppression was narrowed so it only suppresses clicks while the PixelBoard window is the active foreground window.
- The current double-click logic has been redesigned from tap-based promotion to dwell-based triggering.

## 4. Current Config / Gesture Baseline

As of handoff, these values are important:

- board size:
  `board_width_mm = 344`
  `board_height_mm = 193`
- reference screen:
  `screen_width_px = 1920`
  `screen_height_px = 1080`
- LD19 launch:
  `enable_internal_filter = True`
  `rolling_publish_hz = 0.0`
- current UI gesture heuristics:
  `SINGLE_CLICK_DELAY_MS = 1000`
  `DWELL_DOUBLE_CLICK_DURATION_MS = 2000`
  `DWELL_DOUBLE_CLICK_RADIUS_PX = 8.0`

## 5. Read These Files In Order

If a new engineer needs to understand the system quickly, this is the most efficient reading order:

1. `run_app.sh`
2. `pixel_board_ui/src/main/kotlin/ProcessManager.kt`
3. `rw/src/ldlidar_stl_ros2/launch/ld19.launch.py`
4. `rw/src/ldlidar_stl_ros2/src/demo.cpp`
5. `ros_bridge.py`
6. `touch_output.py`
7. `pixel_board_ui/src/main/kotlin/AppViewModel.kt`
8. `pixel_board_ui/src/main/kotlin/InteractiveGestureHeuristics.kt`
9. `pixel_board_ui/src/main/kotlin/DesktopInputController.kt`
10. `board_config.json`
11. `tests/test_ros_bridge_touch_tracker.py`
12. `pixel_board_ui/src/test/kotlin/InteractiveGestureHeuristicsTest.kt`

## 6. Ordered Discovery And Checks To Reach True Interactive Projection

The next engineer should work in this order, not by jumping straight to projector tuning.

### Step 1: Verify Environment And Desktop Preconditions

Check these first:

- the machine is on X11, not Wayland
- the projector is connected in extended-desktop mode
- the correct display is selected in the PixelBoard UI
- the PixelBoard app window is not itself occupying the target area being evaluated
- the LiDAR serial device is present and writable

Why this comes first:

- if desktop injection is unavailable or the wrong display is selected, all higher-level gesture tuning will give misleading results

### Step 2: Verify Driver Baseline

Inspect and confirm:

- `rw/src/ldlidar_stl_ros2/launch/ld19.launch.py`
- `rw/src/ldlidar_stl_ros2/src/demo.cpp`

Checks:

- confirm `enable_internal_filter` is still `True`
- confirm `rolling_publish_hz` is still `0.0`
- if those files changed, rebuild the package and confirm the installed launch matches the source launch

Why this matters:

- partial rolling scans were previously a major source of hover wobble and tracking instability

### Step 3: Verify Bridge / Tracker Baseline

Inspect:

- `ros_bridge.py`
- `touch_output.py`
- `tests/test_ros_bridge_touch_tracker.py`

Checks:

- stationary touches should stay locked enough to avoid obvious drift
- coherent movement should not lag badly behind the real motion
- touch IDs should not churn excessively during normal use

Why this matters:

- if the bridge is unstable in board coordinates, projector alignment and UI tuning will only mask symptoms

### Step 4: Verify UI Gesture Baseline On The System Display

Inspect:

- `pixel_board_ui/src/main/kotlin/AppViewModel.kt`
- `pixel_board_ui/src/main/kotlin/InteractiveGestureHeuristics.kt`
- `pixel_board_ui/src/main/kotlin/DesktopInputController.kt`

Checks:

- hover uses the stabilized screen point
- single click delay is still about `1s`
- dwell double click is still the active double-click path
- the dwell logic resets on release before `2000 ms`
- the PixelBoard self-click guard only applies when the PixelBoard window is active in the foreground

Why this matters:

- true projection should only be pursued after the system-screen interaction path is behaving correctly

### Step 5: Verify Calibration And Mapping

Inspect:

- `board_config.json`
- `configure_board.py`

Checks:

- confirm physical board width and height still match the actual setup
- confirm the board min/max geometry matches the actual mounted LiDAR arrangement
- confirm the selected display resolution used by the app matches the intended target display

Why this matters:

- calibration mismatch can look like jitter, drift, or projection misalignment even when tracking code is correct

### Step 6: Only Then Move To Projector Validation

Once Steps 1-5 are clean, test on the actual projector/display target.

Manual checks to perform in order:

1. Hover over a fixed projected point and watch for visible wobble.
2. Hold at one point for several seconds and estimate stationary drift.
3. Move slowly in straight horizontal and vertical lines and watch for lag or oscillation.
4. Perform a tap/release and confirm single click arrives after about `1s`.
5. Hover over a native app target and remain stable for about `2s`; confirm the dwell double click fires.
6. Release before `2s`; confirm no double click fires.
7. Continue hovering after a dwell-triggered double click; confirm it can re-arm and fire again after another full dwell.
8. Move outside the `8 px` stability zone and verify the dwell timer resets.
9. Minimize or background the PixelBoard window and repeat the click/dwell tests to confirm the app is no longer blocking its own targets.
10. Confirm the projected target position and actual system cursor destination match closely enough for real use.

## 7. Ordered Verification Commands

Run these in roughly this order:

1. Python syntax / bridge sanity

```bash
python3 -m py_compile ros_bridge.py touch_output.py tests/test_ros_bridge_touch_tracker.py
```

2. Bridge regression tests

```bash
python3 -m unittest tests.test_ros_bridge_touch_tracker
```

3. Kotlin gesture regressions

```bash
cd pixel_board_ui
GRADLE_USER_HOME=/tmp/pixelboard-gradle ./gradlew test --tests com.pixelboard.InteractiveGestureHeuristicsTest
```

4. LD19 launch syntax

```bash
python3 -m py_compile rw/src/ldlidar_stl_ros2/launch/ld19.launch.py
```

5. Rebuild LD19 package when launch/driver changes

```bash
cd rw
colcon build --packages-select ldlidar_stl_ros2
```

After any LD19 launch or driver rebuild:

- restart the app and/or driver before trusting runtime behavior

## 8. Where The Most Likely Remaining Problems Are

If true interactive projection is still not good enough, the most likely remaining areas are:

1. Physical calibration mismatch
   - board geometry, mounting assumptions, or display selection mismatch
2. Residual stationary jitter from the sensor / bridge
   - especially because the board-to-screen mapping amplifies small error strongly
3. Projector/display scaling mismatch
   - OS scaling, projector scaling, or resolution mismatch with app assumptions
4. Dwell gesture tuning
   - `8 px / 2000 ms` may still need adjustment after real projector testing
5. Real hardware repeatability
   - some remaining problems may only be observable on the live LiDAR + projector path, not in unit tests

## 9. Current Verified Status At Handoff

The following checks were already passing before handoff:

- `python3 -m unittest tests.test_ros_bridge_touch_tracker`
- `python3 -m py_compile ros_bridge.py touch_output.py tests/test_ros_bridge_touch_tracker.py`
- `GRADLE_USER_HOME=/tmp/pixelboard-gradle ./gradlew test --tests com.pixelboard.InteractiveGestureHeuristicsTest`
- `python3 -m py_compile rw/src/ldlidar_stl_ros2/launch/ld19.launch.py`
- `colcon build --packages-select ldlidar_stl_ros2`

What remains unverified in this repo-only environment:

- live hardware feel on the real projector path
- final projector mapping accuracy
- whether the current dwell gesture is the best UX on the real installed setup

## 10. Final Recommendation To The Next Engineer

Do not start by changing projector math.

First prove:

1. the driver is still on full filtered scans
2. the bridge is stable enough in board coordinates
3. the UI hover path is stable on the system display
4. the current dwell double-click works reliably on the system display
5. the board calibration matches the physical installation

Only after those pass should projector-specific mapping or projector-only tuning begin.
