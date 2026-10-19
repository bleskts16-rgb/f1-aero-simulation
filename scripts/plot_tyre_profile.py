"""Plot the G1 wheel cross-sections (clean-cad step 3: check sections in 2D first).

    python scripts/plot_tyre_profile.py
Output: docs/figures/g1_tyre_profile.png
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cad.car2026 import CarParams, tyre_profile  # noqa: E402


def main():
    plt.rcParams.update({"font.family": "serif", "xtick.direction": "in", "ytick.direction": "in",
                         "xtick.top": True, "ytick.right": True, "font.size": 9})
    navy, red, grey = "#1f3a68", "#a23b3b", "#7a7a7a"
    p = CarParams(geom_level="G1")
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 4.4), width_ratios=[335, 420])
    for ax, (label, d, w) in zip(axes, (("front", p.tyre_f_diameter, p.tyre_f_width),
                                        ("rear", p.tyre_r_diameter, p.tyre_r_width))):
        curve, closing = tyre_profile(p, d, w)
        c = np.array(curve)
        k = np.array([curve[-1]] + closing + [curve[0]])
        ax.plot(c[:, 0], c[:, 1], "-", color=navy, lw=1.2, label="tyre (spline through points)")
        ax.plot(c[:, 0], c[:, 1], ".", color=navy, ms=2.5)
        ax.plot(k[:, 0], k[:, 1], "-", color=red, lw=1.0, label="rim / cover / inner face")
        ax.axhline(p.rim_diameter / 2, color=grey, lw=0.6, ls="--")
        ax.axvline(0, color=grey, lw=0.5, ls=":")
        ax.axvline(w, color=grey, lw=0.5, ls=":")
        ax.set_title(f"{label}: D {d:.0f} x W {w:.0f} mm")
        ax.set_xlabel("y from inner face [mm] (cover side right)")
        ax.set_xlim(-15, w + 15)
        ax.set_ylim(-15, 375)
        ax.set_aspect("equal")
    axes[0].set_ylabel("r from axle [mm]")
    axes[0].legend(frameon=False, loc="lower center", fontsize=7)
    fig.suptitle("G1 wheel cross-sections, revolved about the axle (rim 18 in = 462.6 mm)", fontsize=9)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / "g1_tyre_profile.png"
    fig.savefig(out, dpi=150)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
