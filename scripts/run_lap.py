"""Simulate one lap and plot the speed map and speed trace.

    python scripts/run_lap.py Monza
    python scripts/run_lap.py Suzuka --cla 7.0 --cda 1.6
    python scripts/run_lap.py Budapest --calibrated
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lapsim import load_track, simulate, Vehicle  # noqa: E402


def fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:06.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("track")
    ap.add_argument("--cla", type=float)
    ap.add_argument("--cda", type=float)
    ap.add_argument("--calibrated", action="store_true",
                    help="use CL*A / CD*A fitted to telemetry (data/aero_calibration.json)")
    args = ap.parse_args()

    veh = Vehicle()
    if args.calibrated:
        cal = json.loads((ROOT / "data" / "aero_calibration.json").read_text(encoding="utf-8"))
        veh = veh.with_aero(cal[args.track]["cla"], cal[args.track]["cda"])
    veh = veh.with_aero(args.cla, args.cda)

    res = simulate(load_track(args.track), veh)
    tr = res.track
    print(f"{args.track}: lap {fmt(res.lap_time)}  top {res.top_speed_kph:.1f} km/h  "
          f"min {res.min_speed_kph:.1f} km/h  CL*A={veh.cla:.2f} CD*A={veh.cda:.2f}")

    fig = plt.figure(figsize=(13, 5.5))
    ax0 = fig.add_subplot(1, 2, 1)
    pts = np.column_stack([tr.x, tr.y])
    segs = np.stack([pts, np.roll(pts, -1, axis=0)], axis=1)
    lc = LineCollection(segs, cmap="plasma", linewidths=3)
    lc.set_array(res.v * 3.6)
    ax0.add_collection(lc)
    ax0.autoscale()
    ax0.set_aspect("equal")
    ax0.axis("off")
    fig.colorbar(lc, ax=ax0, label="speed [km/h]", shrink=0.7)
    ax0.set_title(f"{args.track}  {fmt(res.lap_time)}")

    ax1 = fig.add_subplot(1, 2, 2)
    ax1.plot(tr.s, res.v * 3.6, "r-", lw=1, label="speed")
    ax1.plot(tr.s, np.minimum(res.v_corner, veh.v_max) * 3.6, "k:", lw=0.6, label="corner limit")
    ax1.set_ylim(0, 380)
    ax1.set_xlabel("distance [m]")
    ax1.set_ylabel("speed [km/h]")
    ax1.legend(loc="lower right")
    fig.tight_layout()

    out = ROOT / "docs" / "figures" / f"lap_{args.track}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
