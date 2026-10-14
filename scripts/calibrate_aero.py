"""Fit per-circuit aero level (CL*A, CD*A) to real qualifying speed traces.

Teams trim the car differently per circuit (low-drag Monza vs high-downforce
Suzuka), so the fitted values should show that spread.

    python scripts/calibrate_aero.py Monza Budapest Suzuka Silverstone
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lapsim import load_track, simulate, Vehicle  # noqa: E402
from lapsim.reference import load_reference, align  # noqa: E402

logging.getLogger("fastf1").setLevel(logging.WARNING)


def speed_rms(track, ref, veh):
    res = simulate(track, veh)
    _, vs, vr = align(track.s, res.v, ref.distance, ref.speed)
    return float(np.sqrt(np.mean((vs - vr) ** 2))), res.lap_time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", nargs="+")
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()

    base = Vehicle()
    out = {}
    print(f"{'track':12s} {'CL*A':>6s} {'CD*A':>6s} {'L/D':>5s} {'rms km/h':>9s} {'lap err':>8s}")
    for name in args.tracks:
        track = load_track(name)
        ref = load_reference(name, args.year)

        def cost(p):
            cla, cda = p
            if not (1.0 < cla < 12.0 and 0.6 < cda < 2.5):
                return 1e3
            return speed_rms(track, ref, base.with_aero(cla, cda))[0]

        fit = minimize(cost, x0=[base.cla, base.cda], method="Nelder-Mead",
                       options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 200})
        cla, cda = fit.x
        rms, lap = speed_rms(track, ref, base.with_aero(cla, cda))
        out[name] = {"cla": round(cla, 3), "cda": round(cda, 3),
                     "speed_rms_kph": round(rms * 3.6, 2),
                     "lap_sim": round(lap, 3), "lap_real": round(ref.lap_time, 3),
                     "driver": ref.driver, "year": ref.year}
        print(f"{name:12s} {cla:6.2f} {cda:6.2f} {cla / cda:5.2f} {rms * 3.6:9.1f} "
              f"{lap - ref.lap_time:+8.2f}s")

    dst = ROOT / "data" / "aero_calibration.json"
    dst.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
