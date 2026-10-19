"""One 2026 qualifying lap with the fitted car: speed trace, active-aero zones, ERS use.

    python scripts/run_lap_2026.py Monza
    python scripts/run_lap_2026.py Silverstone --cla 6.0      # override corner-mode CL*A
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lapsim import load_track  # noqa: E402
from lapsim.rules2026 import Car2026, simulate_2026  # noqa: E402


def fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:06.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("track")
    for k in ("cla", "cda", "cla_x", "cda_x"):
        ap.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float)
    args = ap.parse_args()

    fit = json.loads((ROOT / "data" / "aero_2026.json").read_text(encoding="utf-8"))
    car = Car2026(cla=fit["cla_z"], cda=fit["cda_z"], cla_x=fit["cla_x"], cda_x=fit["cda_x"])
    car = car.with_modes(**{k: getattr(args, k) for k in ("cla", "cda", "cla_x", "cda_x")
                            if getattr(args, k) is not None})
    tr = load_track(args.track)
    r = simulate_2026(tr, car)
    r0 = simulate_2026(tr, car, active_aero=False)
    real = json.loads((ROOT / "data" / "quali_best_2024_2026.json").read_text(encoding="utf-8"))["laps"]
    real_t = real.get(args.track, {}).get("2026")
    print(f"{args.track}: {fmt(r.lap_time)}  (no active aero {fmt(r0.lap_time)}"
          + (f", real 2026 best {fmt(real_t)}" if real_t else "") + ")")
    print(f"  top {r.top_speed_kph:.1f} km/h, straight mode on {100 * r.x_mode.mean():.0f} % of the lap, "
          f"ERS deploy {r.e_deploy / 1e6:.2f} MJ = 4 MJ + harvest {r.e_harvest / 1e6:.2f} MJ, "
          f"deploy below {r.v_deploy * 3.6:.0f} km/h")

    plt.rcParams.update({"font.family": "serif", "font.size": 9, "xtick.direction": "in",
                         "ytick.direction": "in", "xtick.top": True, "ytick.right": True})
    fig, ax = plt.subplots(figsize=(10, 3.6))
    s = tr.s / 1000
    ax.fill_between(s, 0, 380, where=r.x_mode, color="#dfe6f2", lw=0, label="straight mode (X)")
    ax.plot(s, r0.v * 3.6, color="#999999", lw=0.8, label=f"no active aero  {fmt(r0.lap_time)}")
    ax.plot(s, r.v * 3.6, color="#1f3b73", lw=1.1, label=f"2026 model  {fmt(r.lap_time)}")
    if r.v_deploy < car.v_max:
        ax.axhline(r.v_deploy * 3.6, color="#b0413e", lw=0.8, ls="--",
                   label=f"ERS deployment limit {r.v_deploy * 3.6:.0f} km/h")
    ax.set_xlim(0, s[-1])
    ax.set_ylim(50, 360)
    ax.set_xlabel("distance [km]")
    ax.set_ylabel("speed [km/h]")
    ax.legend(frameon=False, loc="lower right", fontsize=8, ncol=2)
    ax.set_title(f"{args.track}: fitted 2026 car (CL·A {car.cla:.2f} / {car.cla_x:.2f}, "
                 f"CD·A {car.cda:.2f} / {car.cda_x:.2f} m², corner / straight)", fontsize=9)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / f"lap2026_{args.track}.png"
    fig.savefig(out, dpi=150)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
