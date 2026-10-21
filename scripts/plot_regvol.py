"""Cross-sections of the car parts against the Appendix 1 reference volumes
(cad/regvol.py), to see where `build_car.py`'s volume checks fail.

    python scripts/plot_regvol.py            # G1 with wake boards -> docs/figures/regvol_sections_g1.png
    python scripts/plot_regvol.py --g0       # G0 baseline
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cad import car2026, regvol  # noqa: E402
from cad.car2026 import CarParams  # noqa: E402

plt.rcParams.update({"font.family": "serif", "font.size": 9, "xtick.direction": "in",
                     "ytick.direction": "in", "xtick.top": True, "ytick.right": True})


def section(shape, x):
    """Triangles of the X = x section of `shape`, projected on (Y, Z)."""
    s = shape.intersect(car2026._box(x - 0.25, x + 0.25, -10, 2000, -100, 2000))
    if not s.Solids():
        return []
    v, f = s.tessellate(0.3, 0.2)
    v = np.array([[q.y, q.z] for q in v])
    return [v[list(t)] for t in f]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--g0", action="store_true", help="G0 baseline instead of G1")
    args = ap.parse_args()
    lvl = "G0" if args.g0 else "G1"
    p = CarParams().with_(geom_level=lvl, wake_boards=not args.g0)
    xr, xc = p.xr, p.xc
    sp = car2026.sprung_parts(p)
    floor = car2026._fuse(*car2026.floor_parts(p))
    fwv = list(regvol.front_wing_volumes().values())
    rwv = list(regvol.rear_wing_volumes(xr).values())
    flv = list(regvol.floor_volumes(xr, xc).values())
    panels = [("Front wing, XF = -900", -900, fwv, [sp["front_wing"]]),
              ("Floor board area, XF = 900", 900, flv, [floor] + ([sp["wake_boards"]] if "wake_boards" in sp else [])),
              ("Floor, XR = -1500", xr - 1500, flv, [floor]),
              ("Diffuser, XR = 0", xr, flv, [floor]),
              ("Rear wing, XR = 450", xr + 450, rwv, [sp["rear_wing"]])]
    fig, axs = plt.subplots(len(panels), 1, figsize=(7, 2.3 * len(panels)))
    for ax, (title, x, vols, parts) in zip(axs, panels):
        for v in vols:
            ax.add_collection(PolyCollection(section(v, x), facecolor="#c9d3e6", edgecolor="none"))
        for s in parts:
            ax.add_collection(PolyCollection(section(s, x), facecolor="#b0413e", edgecolor="none",
                                             alpha=0.85))
        ax.autoscale()
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("Y [mm]")
        ax.set_ylabel("Z [mm]")
    fig.suptitle(f"{lvl} parts (red) vs App.1 reference volumes (blue), Y >= 0 half", fontsize=10)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / f"regvol_sections_{lvl.lower()}.png"
    fig.savefig(out, dpi=130)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
