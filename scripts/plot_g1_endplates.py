"""Plot the G1 endplate design sections before lofting (clean-cad step 3).

    python scripts/plot_g1_endplates.py
Output: docs/figures/g1_endplates_2d.png

Rear: side view (X-Z) with the rear tyre and the diffuser, and rear view (Y-Z) of
how the endplate turns inboard into the diffuser outer wall.
Front: endplate side outline with the wheel-clearance cut, and the footplate J section.
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
    xr, s = p.xr, p.rw_span_half
    secs = c.rw_endplate_sections(p)
    # rear tyre in the car frame (approximate: pitch ignored), and the diffuser
    rz = p.tyre_r_diameter / 2 - p.tyre_squash - p.ride_height_rear
    th = np.linspace(0, 2 * np.pi, 200)
    R = p.tyre_r_diameter / 2

    fig, ax = plt.subplots(2, 2, figsize=(10, 8.4))
    a = ax[0, 0]
    up = np.array(c._rounded_outline(c.G1_RW_EP_UPPER))
    a.fill(xr + up[:, 0], up[:, 1], color=navy, alpha=0.25, lw=0)
    a.plot(xr + up[:, 0], up[:, 1], color=navy, lw=1, label="endplate beside the wing")
    for z, ring in secs:
        r = np.array(ring)
        a.plot([r[:, 0].min(), r[:, 0].max()], [z, z], color=red, lw=1)
    a.plot([], [], color=red, label="lower endplate sections (loft)")
    lk = np.array(c._rounded_outline([(xr + dx, z, rr) for dx, z, rr in c.G1_RW_DIFF_LINK]))
    a.fill(lk[:, 0], lk[:, 1], color=green, alpha=0.3, lw=0)
    a.plot(lk[:, 0], lk[:, 1], color=green, lw=1, label="diffuser wall extension")
    a.plot(xr + R * np.cos(th), rz + R * np.sin(th), color=grey, lw=1, ls="--", label="rear tyre")
    xd = xr + p.diffuser_start
    a.plot([xd, xr + 165, xr + 165], [p.floor_thickness, p.diffuser_exit_height + p.floor_thickness, 0],
           color="k", lw=0.8, label="diffuser ramp / exit")
    a.set_title("rear, side view (car frame)")
    a.set_xlabel("X [mm]"); a.set_ylabel("Z [mm]"); a.set_aspect("equal")
    a.set_xlim(xr - 450, xr + 750); a.set_ylim(-50, 950); a.legend(frameon=False, fontsize=7, loc="upper left")

    a = ax[0, 1]
    z = np.array([q[0] for q in secs])
    yc = np.array([np.mean(np.array(r)[:, 1]) for _, r in secs])
    h = c.G1_RW_EP_THICK / 2
    a.fill_betweenx(z, yc - h, yc + h, color=red, alpha=0.5, lw=0, label="lower endplate")
    a.fill_between([s - 7, s + 8], [470, 470], [878, 878], color=navy, alpha=0.3, lw=0, label="endplate beside wing")
    y0, y1 = c.G1_RW_DIFF_LINK_Y
    a.fill_between([y0, y1], [40, 40], [232, 232], color=green, alpha=0.35, lw=0, label="diffuser wall extension")
    a.fill_between([375, 390], [0, 0], [190, 190], color="k", alpha=0.25, lw=0, label="diffuser fence (body)")
    a.axvline(p.half_width - p.tyre_r_width, color=grey, ls="--", lw=1, label="rear tyre inner face")
    a.plot(yc, z, ".", color=red, ms=3)
    a.set_title("rear, view from behind (Y >= 0)")
    a.set_xlabel("Y [mm]"); a.set_ylabel("Z [mm]"); a.set_xlim(300, 700); a.set_ylim(0, 950)
    a.legend(frameon=False, fontsize=7, loc="upper left")

    a = ax[1, 0]
    ep = np.array(c._rounded_outline(c.G1_FW_EP_SIDE))
    a.plot(ep[:, 0], ep[:, 1], color=navy, lw=1, label="endplate outline (before wheel cut)")
    a.plot(412.5 * np.cos(th), 360 + 412.5 * np.sin(th), color=grey, ls="--", lw=1, label="wheel clearance cut R412.5")
    fs = c.fw_foot_sections()
    fx = np.array([x for x, _ in fs])
    ftop = np.array([np.array(r)[:, 1].max() for _, r in fs])
    a.fill_between(fx, 40, ftop, color=red, alpha=0.3, lw=0, label="footplate (curl top along X)")
    a.plot(fx, ftop, ".", color=red, ms=3)
    a.set_title("front, side view"); a.set_xlabel("X [mm]"); a.set_ylabel("Z [mm]"); a.set_aspect("equal")
    a.set_xlim(-1300, -200); a.set_ylim(0, 500); a.legend(frameon=False, fontsize=7, loc="upper right")

    a = ax[1, 1]
    for i, (x, ring) in enumerate(fs):
        ft = np.array(ring)
        a.plot(np.r_[ft[:, 0], ft[0, 0]], np.r_[ft[:, 1], ft[0, 1]], color=red, lw=0.7, alpha=0.4 + 0.5 * (i == 5),
               label="footplate J sections" if i == 0 else None)
    print("footplate points per section:", sorted({len(r) for _, r in fs}))
    a.fill_between([p.fw_span_half - 10, p.fw_span_half + 2], [40, 40], [410, 410], color=navy, alpha=0.3,
                   lw=0, label="endplate")
    a.axvline(680, color="k", ls=":", lw=1, label="RV-FWEP-BODY |Y| = 680")
    a.set_title("front, view from ahead (Y >= 0)"); a.set_xlabel("Y [mm]"); a.set_ylabel("Z [mm]")
    a.set_aspect("equal"); a.set_xlim(590, 700); a.set_ylim(20, 220); a.legend(frameon=False, fontsize=7)

    fig.suptitle("G1 endplates: design sections before lofting", fontsize=9)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / "g1_endplates_2d.png"
    fig.savefig(out, dpi=140)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
