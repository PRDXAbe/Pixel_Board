#!/usr/bin/env python3
"""
configure_board.py
==================
Interactive tool to set Magic Board dimensions and detection tuning.
No ROS required — runs standalone.

Usage:
    python3 configure_board.py
"""

import json
import pathlib
import sys

# ─── paths ────────────────────────────────────────────────────────────────────
_HERE       = pathlib.Path(__file__).parent.resolve()
CONFIG_PATH = _HERE / "board_config.json"

_DEFAULTS = {
    "board_min_x":    0.050,
    "board_max_x":    0.860,
    "board_min_y":   -0.190,
    "board_max_y":    0.190,
    "cluster_dist":   0.08,
    "min_pts":        2,
    "match_radius":   0.20,
    "forget_frames":  25,
    "recount_frames": 8,
}

_RAW_EDIT_KEYS = {
    "board_min_x",
    "board_max_x",
    "board_min_y",
    "board_max_y",
    "cluster_dist",
    "min_pts",
    "match_radius",
    "forget_frames",
    "recount_frames",
}

# ─── ANSI colour helpers ───────────────────────────────────────────────────────
_USE_COLOUR = sys.stdout.isatty()
def _c(code, t): return f"\033[{code}m{t}\033[0m" if _USE_COLOUR else t
def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def cyan(t):   return _c("36", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)
def red(t):    return _c("31", t)


# ─── config I/O ───────────────────────────────────────────────────────────────
def load_config() -> dict:
    cfg = dict(_DEFAULTS)
    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text())
        cfg.update({k: v for k, v in raw.items() if k != "_comment"})
    else:
        print(yellow(f"  ⚠  {CONFIG_PATH.name} not found — using defaults."))
    return cfg


def save_config(cfg: dict) -> None:
    out = {"_comment": "Magic Board — edit via: python3 configure_board.py"}
    out.update(cfg)
    CONFIG_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(green(f"  ✔  Saved → {CONFIG_PATH}"))


# ─── derived user-friendly values ─────────────────────────────────────────────
def to_user(cfg: dict) -> dict:
    """Convert raw config to the 3+5 values the user actually sees."""
    return {
        "length_cm":         (cfg["board_max_x"] - cfg["board_min_x"]) * 100,
        "breadth_cm":        (cfg["board_max_y"] - cfg["board_min_y"]) * 100,
        "lidar_offset_cm":   cfg["board_min_x"] * 100,
        "cluster_dist_cm":   cfg["cluster_dist"] * 100,
        "min_pts":           cfg["min_pts"],
        "match_radius_cm":   cfg["match_radius"] * 100,
        "forget_frames":     cfg["forget_frames"],
        "recount_frames":    cfg["recount_frames"],
    }


def from_user(u: dict) -> dict:
    """Convert user-friendly values back to raw config (metres)."""
    min_x = u["lidar_offset_cm"] / 100
    max_x = min_x + u["length_cm"] / 100
    half  = u["breadth_cm"] / 100 / 2
    return {
        "board_min_x":    round(min_x, 5),
        "board_max_x":    round(max_x, 5),
        "board_min_y":    round(-half, 5),
        "board_max_y":    round( half, 5),
        "cluster_dist":   round(u["cluster_dist_cm"] / 100, 5),
        "min_pts":        int(u["min_pts"]),
        "match_radius":   round(u["match_radius_cm"] / 100, 5),
        "forget_frames":  int(u["forget_frames"]),
        "recount_frames": int(u["recount_frames"]),
    }


# ─── validation ───────────────────────────────────────────────────────────────
def validate(u: dict) -> list[str]:
    errs = []
    if u["length_cm"] <= 0:
        errs.append("Board length must be > 0 cm")
    if u["breadth_cm"] <= 0:
        errs.append("Board breadth must be > 0 cm")
    if u["lidar_offset_cm"] < 0:
        errs.append("LIDAR offset must be ≥ 0 cm")
    if u["cluster_dist_cm"] <= 0:
        errs.append("Cluster gap must be > 0 cm")
    if u["min_pts"] < 1:
        errs.append("Min scan points must be ≥ 1")
    if u["match_radius_cm"] <= 0:
        errs.append("Tracking radius must be > 0 cm")
    if u["forget_frames"] < 1:
        errs.append("Track memory must be ≥ 1 frame")
    if u["recount_frames"] < 1:
        errs.append("Recount delay must be ≥ 1 frame")
    return errs


# ─── display ──────────────────────────────────────────────────────────────────
PARAMS = [
    # key                label                               unit   kind
    ("length_cm",       "Board length  (long axis)",        "cm",  "float"),
    ("breadth_cm",      "Board breadth (short axis)",       "cm",  "float"),
    ("lidar_offset_cm", "LIDAR offset  (gap to near edge)", "cm",  "float"),
    ("cluster_dist_cm", "Ball cluster gap",                 "cm",  "float"),
    ("min_pts",         "Min scan points per ball",         "pts", "int"),
    ("match_radius_cm", "Ball tracking radius",             "cm",  "float"),
    ("forget_frames",   "Track memory",                     "fr",  "int"),
    ("recount_frames",  "Recount delay",                    "fr",  "int"),
]


def print_table(u: dict) -> None:
    print()
    print(bold("  Board & Detection Settings"))
    print(f"  {'─'*52}")
    print(f"  {'#':>3}  {'Parameter':<30}  {'Value':>12}")
    print(f"  {'─'*52}")

    print(f"  {dim('  Board size:')}")
    for i, (key, label, unit, _) in enumerate(PARAMS[:3], 1):
        val = u[key]
        print(f"  {cyan(str(i)):>6}  {label:<30}  {val:>8.1f} {unit}")

    print(f"  {dim('  Ball detection:')}")
    for i, (key, label, unit, kind) in enumerate(PARAMS[3:], 4):
        val = u[key]
        if kind == "float":
            print(f"  {cyan(str(i)):>6}  {label:<30}  {val:>8.1f} {unit}")
        else:
            print(f"  {cyan(str(i)):>6}  {label:<30}  {int(val):>8d} {unit}")

    print(f"  {'─'*52}")
    print()


def print_diagram(u: dict) -> None:
    L = u["length_cm"]
    B = u["breadth_cm"]
    O = u["lidar_offset_cm"]
    print()
    print(cyan("  Board layout (top view):"))
    print()
    print(f"    ◄─────────── {B:.0f} cm wide ───────────►")
    print(f"    ┌─────────────────────────────────────┐")
    print(f"    │                                     │  ▲")
    print(f"    │            board surface            │  │  {L:.0f} cm")
    print(f"    │                                     │  │  long")
    print(f"    └──────────────┬──────────────────────┘  ▼")
    print(f"    {dim(f'◄── {O:.0f} cm gap ──►')} LIDAR ▲")
    print()


# ─── edit ─────────────────────────────────────────────────────────────────────
def edit_param(u: dict, idx: int) -> dict:
    key, label, unit, kind = PARAMS[idx]
    cur = u[key]

    print(f"\n  Editing: {bold(label)}")
    if kind == "float":
        print(f"  Current: {yellow(f'{cur:.1f} {unit}')}   (enter new value in {unit}, or Enter to keep)")
    else:
        print(f"  Current: {yellow(f'{int(cur)} {unit}')}   (enter new integer, or Enter to keep)")

    while True:
        raw = input("  > ").strip()
        if raw == "":
            print(dim("  (no change)"))
            return u
        try:
            new_val = float(raw) if kind == "float" else int(raw)
            break
        except ValueError:
            print(red(f"  ✗  Please enter a {'number' if kind=='float' else 'whole number'}."))

    test = dict(u)
    test[key] = new_val
    errs = validate(test)
    if errs:
        for e in errs:
            print(red(f"  ✗  {e}"))
        print(yellow("  Change not applied."))
        return u

    u[key] = new_val
    print(green(f"  ✔  {key} → {new_val} {unit}"))
    return u


# ─── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print()
    print(bold(cyan("  ╔════════════════════════════════════════╗")))
    print(bold(cyan("  ║   Magic Board — Board Configuration    ║")))
    print(bold(cyan("  ╚════════════════════════════════════════╝")))

    cfg     = load_config()
    passthrough = {k: v for k, v in cfg.items() if k not in _RAW_EDIT_KEYS}
    u       = to_user(cfg)
    changed = False

    while True:
        print_diagram(u)
        print_table(u)
        print(dim("  [1–8] edit   [s] save & quit   [q] quit"))
        raw = input("  > ").strip().lower()
        print()

        if raw in ("q", "quit", "exit"):
            if changed:
                ans = input(yellow("  ⚠  Unsaved changes. Quit anyway? [y/N] ")).strip().lower()
                if ans not in ("y", "yes"):
                    continue
            print(dim("  Bye!"))
            break

        if raw in ("s", "save"):
            errs = validate(u)
            if errs:
                for e in errs:
                    print(red(f"  ✗  {e}"))
                continue
            save_config({**passthrough, **from_user(u)})
            changed = False
            ans = input(dim("  Press Enter to continue or [q] to quit: ")).strip().lower()
            if ans in ("q", "quit"):
                break
            continue

        if raw.isdigit() and 1 <= int(raw) <= len(PARAMS):
            u       = edit_param(u, int(raw) - 1)
            changed = True
            continue

        print(red(f"  ✗  Unknown command '{raw}'"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted — no changes saved.")
        sys.exit(0)
