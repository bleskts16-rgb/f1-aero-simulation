"""Data for the dashboard prototype (site/index.html) -> site/data.js.

For every circuit of data/aero_sensitivity_2026.json: the qualifying lap of the fitted
2026 car (data/aero_2026.json) with lapsim.rules2026 - racing line, speed and where the
straight mode is open - plus the lap-time sensitivities to the four aero numbers and the
real 2026 qualifying time. Written as a JS file (window.SITE_DATA = ...) so the page also
opens straight from disk (file://), where fetch() of a JSON file is blocked.

    python scripts/build_site.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lapsim import load_track  # noqa: E402
from lapsim.rules2026 import Car2026, simulate_2026  # noqa: E402

STEP_M = 10.0          # station spacing kept for the page [m]
KEYS = ("cla", "cda", "cla_x", "cda_x")


def git_commit():
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def track_entry(name, car, sens, ref):
    tr = load_track(name)
    lap = simulate_2026(tr, car)
    k = max(1, int(round(STEP_M / tr.ds)))
    idx = np.arange(0, len(tr.s), k)
    x, y = tr.x[idx], tr.y[idx]
    x0, y0 = x.min(), y.min()
    s_pct = {key: sens[key]["s_per_pct"] for key in KEYS}
    drag = s_pct["cda"] + s_pct["cda_x"]
    return {
        "name": name,
        "length_m": round(float(tr.length), 1),
        "lap_sim_s": round(float(lap.lap_time), 3),
        "lap_real_2026_s": ref.get("2026"),
        "lap_real_2024_s": ref.get("2024"),
        "s_per_pct": s_pct,
        # +1 % corner CL*A pays for this many % of total CD*A (both modes) at equal lap time
        "breakeven_drag_pct": round(-s_pct["cla"] / drag, 3) if drag > 0 else None,
        "x_mode_share": round(float(lap.x_mode.mean()), 3),
        "v_max_kmh": round(float(lap.v.max() * 3.6), 1),
        "v_min_kmh": round(float(lap.v.min() * 3.6), 1),
        "line": {
            "s": np.round(tr.s[idx], 1).tolist(),
            "x": np.round(x - x0, 1).tolist(),
            "y": np.round(y - y0, 1).tolist(),
            "v": np.round(lap.v[idx] * 3.6, 1).tolist(),
            "xm": lap.x_mode[idx].astype(int).tolist(),
        },
    }


def main():
    fit = json.loads((ROOT / "data/aero_2026.json").read_text(encoding="utf-8"))
    sens = json.loads((ROOT / "data/aero_sensitivity_2026.json").read_text(encoding="utf-8"))
    ref = json.loads((ROOT / "data/quali_best_2024_2026.json").read_text(encoding="utf-8"))["laps"]
    car = Car2026(cla=fit["cla_z"], cda=fit["cda_z"], cla_x=fit["cla_x"], cda_x=fit["cda_x"])
    tracks = []
    for name, row in sens["per_track"].items():
        tracks.append(track_entry(name, car, row, ref.get(name, {})))
        t = tracks[-1]
        print(f"{name:12s} lap {t['lap_sim_s']:7.3f} s  straight mode {100 * t['x_mode_share']:4.1f} %  "
              f"break-even {t['breakeven_drag_pct']:.2f} % drag per 1 % downforce", flush=True)
    out = {
        "generated": date.today().isoformat(),
        "commit": git_commit(),
        "car": {"cla": car.cla, "cda": car.cda, "cla_x": car.cla_x, "cda_x": car.cda_x,
                "rms_lap_error_s": fit.get("rms_lap_error_s")},
        "sensitivity_step": sens["step"],
        # CFD reference car (simplified G1 v4, grid2 L2, docs/results/g1v4/summary.md)
        "cfd_reference": {"geometry": "G1 v4", "grid": "grid2 L2", "cells": 2390309,
                          "zmode": {"cla": 1.560, "cda": 1.004},
                          "xmode": {"cla": 1.001, "cda": 0.827}},
        "tracks": tracks,
    }
    path = ROOT / "site" / "data.js"
    path.parent.mkdir(exist_ok=True)
    path.write_text("window.SITE_DATA = " + json.dumps(out, ensure_ascii=False, separators=(",", ":"))
                    + ";\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
