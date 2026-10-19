"""Plot the G1 helmet sections before lofting (clean-cad step 3).

    python scripts/plot_g1_helmet.py
Output: docs/figures/g1_helmet_2d.png
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cad import car2026 as c  # noqa: E402


def superellipse(a, z0, z1, n, npts=13):
    """Same half section as car2026._superellipse, as (y, z) points."""
    zc, b = 0.5 * (z0 + z1), 0.5 * (z1 - z0)
    t = np.linspace(-np.pi / 2, np.pi / 2, npts)
    return a * np.abs(np.cos(t)) ** (2 / n), zc + b * np.sign(np.sin(t)) * np.abs(np.sin(t)) ** (2 / n)


def main():
    plt.rcParams.update({"font.family": "serif", "xtick.direction": "in", "ytick.direction": "in",
                         "xtick.top": True, "ytick.right": True, "font.size": 8})
    navy, red, grey = "#1f3a68", "#a23b3b", "#8a8a8a"
    p = c.CarParams(geom_level="G1")
    secs = np.array(c.helmet_sections(p))
    hx, r, hz = p.xc - 450, 125.0, 720.0
    th = np.linspace(0, 2 * np.pi, 200)
    spine = np.array([s[:4] for s in c._spine_sections(p)], dtype=float)
    xs = np.linspace(1150, 1650, 100)
    body_top = np.interp(xs, spine[:, 0], spine[:, 3])

    fig, ax = plt.subplots(1, 3, figsize=(12, 4.2))
    a = ax[0]
    a.plot(secs[:, 0], secs[:, 3], "-", color=navy, lw=1.2, label="G1 top")
    a.plot(secs[:, 0], secs[:, 2], "--", color=navy, lw=0.8, label="G1 bottom (inside body)")
    a.plot(secs[:, 0], secs[:, 3], ".", color=navy, ms=3)
    a.plot(hx + r * np.cos(th), hz + r * np.sin(th), color=red, lw=0.8, label="G0 sphere")
    a.plot(xs, body_top, color="k", lw=0.8, label="chassis top")
    a.axhline(800, color=grey, ls=":", lw=0.8, label="halo hoop height")
    a.set_title("side view"); a.set_xlabel("X [mm]"); a.set_ylabel("Z [mm]"); a.set_aspect("equal")
    a.set_xlim(1150, 1650); a.set_ylim(560, 900); a.legend(frameon=False, fontsize=6.5, loc="lower center")

    a = ax[1]
    a.plot(secs[:, 0], secs[:, 1], "-", color=navy, lw=1.2, label="G1 half width")
    a.plot(secs[:, 0], -secs[:, 1], "-", color=navy, lw=1.2)
    a.plot(hx + r * np.cos(th), r * np.sin(th), color=red, lw=0.8, label="G0 sphere")
    a.set_title("plan view"); a.set_xlabel("X [mm]"); a.set_ylabel("Y [mm]"); a.set_aspect("equal")
    a.set_xlim(1150, 1650); a.set_ylim(-200, 200); a.legend(frameon=False, fontsize=6.5)

    a = ax[2]
    cmap = plt.get_cmap("viridis")
    for i, (x, w, z0, z1, e) in enumerate(secs):
        y, z = superellipse(w, z0, z1, e)
        a.plot(y, z, "-", color=cmap(i / (len(secs) - 1)), lw=0.8)
    a.set_title("sections front (dark) to rear (light), Y >= 0")
    a.set_xlabel("Y [mm]"); a.set_ylabel("Z [mm]"); a.set_aspect("equal"); a.set_xlim(-10, 140); a.set_ylim(620, 860)
    fig.suptitle("G1 helmet: design sections before lofting", fontsize=9)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / "g1_helmet_2d.png"
    fig.savefig(out, dpi=140)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
