# Visualization Orientation Fix — `rw_viz.py`

## The Problem

The original `rw_viz.py` plotted scan data as `scatter(sensor_X, sensor_Y)`,
mapping sensor-frame X onto the horizontal axis and sensor-frame Y onto the
vertical axis. This produces two compounding errors:

1. **90° rotation** — sensor-X (board depth, running *into* the board) ends up
   going left→right on screen. But in reality the board extends *downward* from
   the LIDAR. The whole picture is rotated 90° clockwise from what you see
   standing in front of the board.

2. **Left/right mirror** — sensor-Y is positive to the *left* of the sensor.
   Matplotlib's vertical axis is positive *upward*. Putting sensor-Y on that
   axis means a ball on the physical left of the board appears at the top of the
   plot, and a ball on the right appears at the bottom — the lateral axis is
   effectively mirrored relative to the top-down reference image.

The net result is a visualization that feels inverted/wrong compared to reality.

---

## The Fix

Map the axes so the plot matches the physical top-down view:

```
Sensor frame              →   Matplotlib plot
─────────────────────────     ──────────────────────────────────────
Y  (board width, ±0.19 m) →   horizontal axis   (+Y = left on screen)
X  (board depth, 0→0.86m) →   vertical axis,    increases DOWNWARD
                               achieved with ax.invert_yaxis()
```

This puts the LIDAR at the **top centre** and the board extending **downward**,
matching the reference top-down diagram exactly.

---

## Exact Code Changes

### 1. `build_figure()` — axis limits and board rectangle

**Before:**
```python
ax.set_xlim(AXIS_MIN_X, AXIS_MAX_X)   # sensor X on horizontal
ax.set_ylim(AXIS_MIN_Y, AXIS_MAX_Y)   # sensor Y on vertical
ax.set_aspect("equal")
ax.set_xlabel("X — along board length (m)", color="white")
ax.set_ylabel("Y — across board width (m)", color="white")

board_rect = mpatches.FancyBboxPatch(
    (BOARD_MIN_X, BOARD_MIN_Y),        # (x=sensor_X, y=sensor_Y)
    BOARD_MAX_X - BOARD_MIN_X,
    BOARD_MAX_Y - BOARD_MIN_Y,
    ...
)

ax.plot(0, 0, marker="^", ...)        # LIDAR marker (upward triangle)
```

**After:**
```python
ax.set_xlim(PLOT_Y_MIN, PLOT_Y_MAX)   # sensor Y on horizontal  (board width)
ax.set_ylim(PLOT_X_MIN, PLOT_X_MAX)   # sensor X on vertical    (board depth)
ax.invert_yaxis()                      # X=0 (LIDAR) at TOP, X=0.86 at BOTTOM
ax.set_aspect("equal")
ax.set_xlabel("← board right     Y (m)     board left →", color="#888888")
ax.set_ylabel("board depth (m)\n← near (LIDAR)     far →", color="#888888")

board_rect = mpatches.FancyBboxPatch(
    (BOARD_MIN_Y, BOARD_MIN_X),        # swapped: (x=sensor_Y, y=sensor_X)
    BOARD_MAX_Y - BOARD_MIN_Y,         # width  = Y span
    BOARD_MAX_X - BOARD_MIN_X,         # height = X span
    ...
)

ax.plot(0, 0, marker="v", ...)        # LIDAR marker (downward triangle — points into board)
```

Replace the two `AXIS_MIN/MAX` constants with these four:

```python
PLOT_Y_MIN = -0.28    # horizontal: just past board right edge
PLOT_Y_MAX =  0.28    # horizontal: just past board left  edge
PLOT_X_MIN = -0.05    # vertical:   small gap above LIDAR
PLOT_X_MAX =  0.95    # vertical:   small gap past far board edge
```

---

### 2. `update()` — scatter data

This is the single most important line change. Every call to `set_offsets` must
pass **(sensor_Y, sensor_X)** — Y first, X second — so the swap is applied to
live data on every frame.

**Before:**
```python
scan_scatter.set_offsets(list(zip(scan_xs, scan_ys)))   # (sensor_X, sensor_Y)
ball_scatter.set_offsets(list(zip(ball_xs, ball_ys)))   # (sensor_X, sensor_Y)
```

**After:**
```python
scan_scatter.set_offsets(list(zip(scan_ys, scan_xs)))   # (sensor_Y, sensor_X)
ball_scatter.set_offsets(list(zip(ball_ys, ball_xs)))   # (sensor_Y, sensor_X)
```

---

## Result

| | Before | After |
|---|---|---|
| LIDAR position in window | Left edge | Top centre |
| Board extends toward | Right | Downward |
| Ball on physical left of board | Appears at top of plot | Appears on left of plot |
| Ball on physical right of board | Appears at bottom of plot | Appears on right of plot |
| LIDAR marker | `▲` (upward triangle) | `▼` (downward triangle, pointing into board) |
