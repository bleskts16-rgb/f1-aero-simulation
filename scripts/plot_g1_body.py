"""Plot the G1 body (spine) keyframes and sections before lofting (clean-cad step 3).

    python scripts/plot_g1_body.py
Output: docs/figures/g1_body_2d.png
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


def main():
    plt.rcParams.update({"font.family": "serif", "xtick.direction": "in", "ytick.direction": "in",
                         "xtick.top": True, "ytick.right": True, "font.size": 8})
    navy, red, grey, green = "#1f3a68", "#a23b3b", "#8a8a8a", "#3b6e4a"
    p = c.CarParams(geom_level="G1")
    k = c.g1_body_table(p)
    secs = c.g1_body_sections(p)
    g0 = np.array([s[:4] for s in c._spine_sections(c.CarParams())], dtype=float)
    counts = sorted({len(s) for _, s in secs})
    print("points per section:", counts)

    fig = plt.figure(figsize=(12, 8))
    a = fig.add_subplot(2, 2, 1)
    xs = np.array([x for x, _ in secs])
    zb = [s[0, 1] for _, s in secs]
    zc = [s[-1, 1] for _, s in secs]
    i_sh = 2 * c.G1_BODY_N_RUN + c.G1_BODY_N_ARC + c.G1_BODY_N_ARC // 2   # shoulder arc mid index
    zsh = [s[i_sh, 1] for _, s in secs]
    a.plot(xs, zc, color=navy, lw=1.2, label="crown")
    a.plot(xs, zsh, color=red, lw=1.2, label="shoulder crease")
    a.plot(xs, zb, color=navy, lw=0.8, ls="--", label="bottom")
    a.plot(k[:, 0], k[:, 7], "o", color=navy, ms=3)
    a.plot(k[:, 0], k[:, 3], "o", color=red, ms=3)
    a.plot(g0[:, 0], g0[:, 3], color=grey, lw=0.8, label="G0 spine top")
    a.plot(g0[:, 0], g0[:, 2], color=grey, lw=0.8, ls=":", label="G0 spine bottom")
    a.set_title("side view (keyframes = dots)"); a.set_xlabel("X [mm]"); a.set_ylabel("Z [mm]")
    a.legend(frameon=False, fontsize=6.5, ncol=2)

    a = fig.add_subplot(2, 2, 2)
    ash = [s[:, 0].max() for _, s in secs]
    a.plot(xs, ash, color=red, lw=1.2, label="max half width (shoulder)")
    a.plot(k[:, 0], k[:, 2], "--", color=navy, lw=0.8, label="bottom half width")
    a.plot(k[:, 0], k[:, 6], ":", color=navy, lw=0.8, label="roof edge half width")
    a.plot(g0[:, 0], g0[:, 1], color=grey, lw=0.8, label="G0 half width")
    a.set_title("plan view (Y >= 0)"); a.set_xlabel("X [mm]"); a.set_ylabel("Y [mm]")
    a.legend(frameon=False, fontsize=6.5)

    a = fig.add_subplot(2, 1, 2)
    cmap = plt.get_cmap("viridis")
    for i, (x, s) in enumerate(secs):
        off = (x - xs[0]) * 0.32                 # spread the sections along the plot
        a.plot(off + s[:, 0], s[:, 1], "-", color=cmap(i / (len(secs) - 1)), lw=0.8)
        a.plot(off + s[i_sh, 0], s[i_sh, 1], ".", color=red, ms=3)
        if i % 3 == 0:
            a.text(off, s[0, 1] - 35, f"{x:.0f}", fontsize=6, ha="left")
    a.set_title(f"half sections nose -> tail, spread by X (red dot = shoulder crease, same index; "
                f"{counts[0]} points each)")
    a.set_xlabel("spread X + Y [mm]"); a.set_ylabel("Z [mm]"); a.set_aspect("equal")
    fig.suptitle("G1 body: keyframe table and sections before lofting", fontsize=9)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / "g1_body_2d.png"
    fig.savefig(out, dpi=140)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
