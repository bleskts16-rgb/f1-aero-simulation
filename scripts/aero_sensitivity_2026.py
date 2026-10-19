"""Lap-time sensitivity to the four 2026 aero numbers and the CFD accuracy it implies.

For each circuit, central differences (+-5 %) of the qualifying lap time with respect to
corner-mode CL*A / CD*A and straight-mode CL*A / CD*A of the fitted 2026 car
(data/aero_2026.json). The allowed CFD error for a lap-time tolerance eps is
eps / |dT/dp| per quantity, and eps / (2 |dT/dp|) when the four errors share the budget
(independent errors, root-sum-square).

    python scripts/aero_sensitivity_2026.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lapsim import load_track  # noqa: E402
from lapsim.rules2026 import Car2026, simulate_2026  # noqa: E402

PARAMS = [("cla", "CL·A Z (corner)"), ("cda", "CD·A Z (corner)"),
          ("cla_x", "CL·A X (straight)"), ("cda_x", "CD·A X (straight)")]
EPS = (0.10, 0.20, 0.50, 1.00)
REL = 0.05


def main():
    fit = json.loads((ROOT / "data" / "aero_2026.json").read_text(encoding="utf-8"))
    ref = json.loads((ROOT / "data" / "quali_best_2024_2026.json").read_text(encoding="utf-8"))["laps"]
    car = Car2026(cla=fit["cla_z"], cda=fit["cda_z"], cla_x=fit["cla_x"], cda_x=fit["cda_x"])
    names = [n for n in ref if n in fit["tracks"]]      # same circuits as the fit
    res = {}
    for n in names:
        tr = load_track(n)
        t0 = simulate_2026(tr, car).lap_time
        row = {"lap": round(t0, 3)}
        for key, _ in PARAMS:
            p = getattr(car, key)
            tp = simulate_2026(tr, car.with_modes(**{key: p * (1 + REL)})).lap_time
            tm = simulate_2026(tr, car.with_modes(**{key: p * (1 - REL)})).lap_time
            d = (tp - tm) / (2 * REL * p)                   # s per m^2
            row[key] = {"s_per_m2": round(d, 4), "s_per_pct": round(d * p / 100, 4)}
        res[n] = row
        print(f"{n:12s} lap {t0:7.3f}  " + "  ".join(f"{k} {row[k]['s_per_pct']:+.4f}" for k, _ in PARAMS)
              + "  (s per 1 %)", flush=True)

    # worst case over circuits (largest |sensitivity|) and the median
    summary = {}
    for key, lab in PARAMS:
        pct = np.array([abs(res[n][key]["s_per_pct"]) for n in names])
        m2 = np.array([abs(res[n][key]["s_per_m2"]) for n in names])
        summary[key] = {"label": lab, "nominal": getattr(car, key),
                        "median_s_per_pct": float(np.median(pct)), "max_s_per_pct": float(pct.max()),
                        "max_track": names[int(pct.argmax())], "max_s_per_m2": float(m2.max()),
                        "allowed_pct_single": {str(e): float(e / pct.max()) for e in EPS},
                        "allowed_pct_shared": {str(e): float(e / (2 * pct.max())) for e in EPS},
                        "allowed_m2_shared": {str(e): float(e / (2 * m2.max())) for e in EPS}}
    out = {"car": {k: getattr(car, k) for k, _ in PARAMS}, "step": REL, "per_track": res, "summary": summary}
    (ROOT / "data" / "aero_sensitivity_2026.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                                             encoding="utf-8")
    write_md(out, names)
    plot(out, names)


def write_md(out, names):
    s = out["summary"]
    lines = ["# 2026 aero sensitivity and CFD accuracy target", "",
             "Qualifying lap time of the fitted one-trim 2026 car (`data/aero_2026.json`), central differences of ±5 %.",
             "Sensitivity is lap-time change for a 1 % change of each aero number (positive = slower).", "",
             "| circuit | lap [s] | " + " | ".join(lab for _, lab in PARAMS) + " |",
             "|---|---|" + "---|" * len(PARAMS)]
    for n in names:
        r = out["per_track"][n]
        lines.append(f"| {n} | {r['lap']:.3f} | " + " | ".join(f"{r[k]['s_per_pct']:+.4f}" for k, _ in PARAMS) + " |")
    lines += ["", "## Allowed CFD error (worst circuit, four errors sharing the budget)", "",
              "| quantity | nominal [m²] | worst s / 1 % (circuit) | " + " | ".join(f"lap ±{e:.2f} s" for e in EPS) + " |",
              "|---|---|---|" + "---|" * len(EPS)]
    for k, lab in PARAMS:
        v = s[k]
        cells = " | ".join(f"±{v['allowed_pct_shared'][str(e)]:.1f} % (±{v['allowed_m2_shared'][str(e)]:.3f} m²)"
                           for e in EPS)
        lines.append(f"| {lab} | {v['nominal']:.3f} | {v['max_s_per_pct']:.4f} ({v['max_track']}) | {cells} |")
    (ROOT / "docs" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "results" / "aero_sensitivity_2026.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot(out, names):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 9, "xtick.direction": "in",
                         "ytick.direction": "in", "xtick.top": False, "ytick.right": True})
    colors = ["#1f3b73", "#6b84b5", "#b0413e", "#d9908c"]
    fig, ax = plt.subplots(figsize=(10, 3.8))
    w = 0.2
    x = np.arange(len(names))
    for j, ((k, lab), c) in enumerate(zip(PARAMS, colors)):
        y = [out["per_track"][n][k]["s_per_pct"] for n in names]
        ax.bar(x + (j - 1.5) * w, y, w, color=c, label=lab, edgecolor="none")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x, names, rotation=30, ha="right")
    ax.set_ylabel("lap-time change per +1 % [s]")
    ax.legend(frameon=False, ncol=4, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / "aero_sensitivity_2026.png", dpi=150)


if __name__ == "__main__":
    main()
