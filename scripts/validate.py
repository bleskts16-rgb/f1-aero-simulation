"""Compare simulated laps against real F1 qualifying laps (FastF1).

    python scripts/validate.py Monza Silverstone Budapest
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lapsim import load_track, simulate, Vehicle  # noqa: E402
from lapsim.reference import load_reference, align  # noqa: E402


def fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:06.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--out", default=str(ROOT / "docs" / "figures"))
    ap.add_argument("--calibrated", action="store_true",
                    help="use per-track CL*A / CD*A from data/aero_calibration.json")
    args = ap.parse_args()

    cal = {}
    if args.calibrated:
        cal = json.loads((ROOT / "data" / "aero_calibration.json").read_text(encoding="utf-8"))
    rows = []
    fig, axes = plt.subplots(len(args.tracks), 1, figsize=(12, 3.2 * len(args.tracks)),
                             squeeze=False)
    for ax, name in zip(axes[:, 0], args.tracks):
        veh = Vehicle()
        if name in cal:
            veh = veh.with_aero(cal[name]["cla"], cal[name]["cda"])
        res = simulate(load_track(name), veh)
        ref = load_reference(name, args.year)
        f, vs, vr = align(res.track.s, res.v, ref.distance, ref.speed)
        err = res.lap_time - ref.lap_time
        rows.append((name, ref.driver, ref.lap_time, res.lap_time, err))

        ax.plot(f * ref.distance[-1], vr * 3.6, "k-", lw=1, label=f"{ref.year} Q {ref.driver}  {fmt(ref.lap_time)}")
        ax.plot(f * ref.distance[-1], vs * 3.6, "r-", lw=1, label=f"QSS sim  {fmt(res.lap_time)}")
        ax.set_title(name)
        ax.set_ylabel("speed [km/h]")
        ax.legend(loc="lower right", fontsize=8)
    axes[-1, 0].set_xlabel("distance [m]")
    fig.tight_layout()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    suffix = "_calibrated" if args.calibrated else ""
    fig.savefig(out / f"validation_speed_traces{suffix}.png", dpi=110)

    print(f"{'track':12s} {'driver':6s} {'real':>9s} {'sim':>9s} {'err':>7s}")
    for name, drv, t_ref, t_sim, err in rows:
        print(f"{name:12s} {drv:6s} {fmt(t_ref):>9s} {fmt(t_sim):>9s} {err:+7.2f}s")


if __name__ == "__main__":
    main()
