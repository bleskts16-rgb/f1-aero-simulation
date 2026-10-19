"""Fit one global 2026 aero level to real 2026 qualifying lap times.

Only lap times are public for 2026 here (no speed traces), so two global numbers are
fitted: corner-mode CL*A and CD*A. Straight-mode (X) aero follows fixed ratios to the
corner mode (assumption, see --x-cla / --x-cda). Per-track residuals show how far each
circuit's real wing level sits from this one-trim car.

    python scripts/fit_2026.py
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lapsim import load_track  # noqa: E402
from lapsim.rules2026 import Car2026, simulate_2026  # noqa: E402


def make_car(cla, cda, rx_cla, rx_cda):
    return Car2026(cla=cla, cda=cda, cla_x=rx_cla * cla, cda_x=rx_cda * cda)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x-cla", type=float, default=0.50, help="X-mode CL*A / Z-mode CL*A (assumed)")
    ap.add_argument("--x-cda", type=float, default=0.55, help="X-mode CD*A / Z-mode CD*A (assumed)")
    # the track database (TUMFTM, ~2020) predates these layout changes:
    # Albert Park 2022 (chicane removed), Catalunya 2023 (final chicane removed)
    ap.add_argument("--exclude", nargs="*", default=["Melbourne", "Catalunya"])
    args = ap.parse_args()

    ref = json.loads((ROOT / "data" / "quali_best_2024_2026.json").read_text(encoding="utf-8"))["laps"]
    names = [n for n in ref if n not in args.exclude]
    tracks = {n: load_track(n) for n in names}
    real = np.array([ref[n]["2026"] for n in names])

    def laps(p):
        car = make_car(p[0], p[1], args.x_cla, args.x_cda)
        return np.array([simulate_2026(tracks[n], car).lap_time for n in names])

    def cost(p):
        if not (2.0 < p[0] < 10.0 and 0.6 < p[1] < 2.5):
            return 1e3
        return float(np.sqrt(np.mean((laps(p) - real) ** 2)))

    fit = minimize(cost, x0=[4.8, 1.45], method="Nelder-Mead",
                   options={"xatol": 0.01, "fatol": 0.005, "maxiter": 80})
    cla, cda = fit.x
    sim = laps(fit.x)
    car = make_car(cla, cda, args.x_cla, args.x_cda)
    print(f"global fit: CL*A_Z = {cla:.3f}, CD*A_Z = {cda:.3f}, CL*A_X = {car.cla_x:.3f}, "
          f"CD*A_X = {car.cda_x:.3f}  (rms lap error {fit.fun:.3f} s, {fit.nfev} evaluations)")
    print(f"{'track':12s} {'real':>8s} {'sim':>8s} {'err':>7s}")
    per = {}
    for n, r, s in zip(names, real, sim):
        print(f"{n:12s} {r:8.3f} {s:8.3f} {s - r:+7.3f}")
        per[n] = {"real": float(r), "sim": round(float(s), 3), "err": round(float(s - r), 3)}
    out = {"cla_z": round(cla, 3), "cda_z": round(cda, 3), "cla_x": round(car.cla_x, 3),
           "cda_x": round(car.cda_x, 3), "x_ratio_cla": args.x_cla, "x_ratio_cda": args.x_cda,
           "rms_lap_error_s": round(float(fit.fun), 3), "tracks": per,
           "excluded": args.exclude,
           "note": "global one-trim fit to 2026 qualifying best laps (Jolpica); X-mode ratios assumed"}
    dst = ROOT / "data" / "aero_2026.json"
    dst.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"saved {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
