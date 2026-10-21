"""Plot the G1 endplate design sections before lofting (clean-cad step 3).

    python scripts/plot_g1_endplates.py
Output: docs/figures/g1_endplates_2d.png

Rear: side view (X-Z) with the rear tyre and the diffuser, and rear view (Y-Z) of
how the lower endplate folds inboard along the RV-RWEP-BODY band (§26).
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
    py = np.array(c._rounded_outline(c.G1_RW_PYLON))
    a.fill(xr + py[:, 0], py[:, 1], color=green, alpha=0.3, lw=0)
    a.plot(xr + py[:, 0], py[:, 1], color=green, lw=1, label="twin pylon (Y 28..43)")
    a.plot(xr + R * np.cos(th), rz + R * np.sin(th), color=grey, lw=1, ls="--", label="rear tyre")
    roof = np.array([(xr + x, z + 1) for x, z in c.G1_DIFF_ROOF])
    a.plot(roof[:, 0], roof[:, 1], color="k", lw=0.8, label="diffuser roof underside (tunnel roof)")
    sh = np.array([(xr + x, z + 1) for x, z in c.G1_DIFF_SHEET])
    a.plot(sh[:, 0], sh[:, 1], color="k", lw=0.8, ls="--", label="diffuser fence lower edge")
    rs = np.array(c.RS_RWEP + (c.RS_RWEP[0],))
    a.plot(xr + rs[:, 0], rs[:, 1], color="k", ls=":", lw=1.2, label="RS-RWEP (must be covered)")
    a.set_title("rear, side view (car frame)")
    a.set_xlabel("X [mm]"); a.set_ylabel("Z [mm]"); a.set_aspect("equal")
    a.set_xlim(xr - 450, xr + 750); a.set_ylim(-50, 950); a.legend(frameon=False, fontsize=7, loc="upper left")

    a = ax[0, 1]
    z = np.array([q[0] for q in secs])
    yc = np.array([np.mean(np.array(r)[:, 1]) for _, r in secs])
    h = c.G1_RW_EP_THICK / 2
    band = np.array([(350, 250), (350, 425), (540, 700), (540, 880), (575, 880), (575, 675),
                     (375, 375), (375, 250), (350, 250)])
    a.plot(band[:, 0], band[:, 1], color="k", ls=":", lw=1.2, label="RV-RWEP-BODY section (§26.1)")
    a.fill_betweenx(z, yc - h, yc + h, color=red, alpha=0.5, lw=0, label="lower endplate")
    uy0, uy1 = c.G1_RW_EP_UPPER_Y
    a.fill_between([uy0, uy1], [712, 712], [878, 878], color=navy, alpha=0.3, lw=0, label="endplate beside wing")
    fy0, fy1 = c.G1_DIFF_FENCE_Y
    a.fill_between([fy0, fy1], [101, 101], [174, 174], color="k", alpha=0.25, lw=0,
                   label="diffuser fence at the exit (body)")
    a.axvline(p.half_width - p.tyre_r_width, color=grey, ls="--", lw=1, label="rear tyre inner face")
    a.plot(yc, z, ".", color=red, ms=3)
    a.set_title("rear, view from behind (Y >= 0)")
    a.set_xlabel("Y [mm]"); a.set_ylabel("Z [mm]"); a.set_xlim(300, 700); a.set_ylim(0, 950)
    a.legend(frameon=False, fontsize=7, loc="upper left")

    a = ax[1, 0]
    body = np.array(c._rounded_outline(c.G1_FW_EP_BODY))
    fence = np.array(c._rounded_outline(c.G1_FW_FENCE))
    a.plot(np.r_[body[:, 0], body[0, 0]], np.r_[body[:, 1], body[0, 1]], color=navy, lw=1,
           label="endplate body (before wheel cut)")
    a.plot(np.r_[fence[:, 0], fence[0, 0]], np.r_[fence[:, 1], fence[0, 1]], color=red, lw=1, label="fence")
    for (y0, y1, z0, z1), col, lab in ((c.G1_FW_IFP, green, "inboard footplate"),
                                       (c.G1_FW_OFP, red, "outboard footplate")):
        a.fill_between([c.fw_section_x(y1) + 3, c.G1_FW_FP_REAR], z0, z1, color=col, alpha=0.3, lw=0, label=lab)
    rs = np.array(c.RS_FWEP_SIDE + (c.RS_FWEP_SIDE[0],))
    a.plot(rs[:, 0], rs[:, 1], color="k", ls=":", lw=1.2, label="RS-FWEP-SIDE (must be covered)")
    a.plot(412.5 * np.cos(th), 360 + 412.5 * np.sin(th), color=grey, ls="--", lw=1, label="wheel cut D825")
    a.set_title("front endplate, side view"); a.set_xlabel("XF [mm]"); a.set_ylabel("Z [mm]"); a.set_aspect("equal")
    a.set_xlim(-1300, -200); a.set_ylim(0, 450); a.legend(frameon=False, fontsize=6.5, loc="upper left")

    a = ax[1, 1]
    for (y0, y1, z0, z1), col, lab in ((c.G1_FW_IFP, green, "inboard footplate"),
                                       (c.G1_FW_OFP, red, "outboard footplate")):
        o = np.array(c.fw_footplate_outline(y0, y1))
        a.fill(o[:, 0], o[:, 1], color=col, alpha=0.3, lw=0, label=lab)
    by0, by1 = c.G1_FW_EP_BODY_Y
    a.fill_between([-980, -412], by0, by1, color=navy, alpha=0.5, lw=0, label="endplate body")
    fy0, fy1 = c.G1_FW_FENCE_Y
    a.fill_between([-820, -300], fy0, fy1, color=red, alpha=0.6, lw=0, label="fence")
    ys = np.linspace(0, c.FW_SPAN_G1, 60)
    a.plot([p.fw_le[0] + c.fw_sweep(p, y) for y in ys], ys, color=navy, lw=1, label="wing leading edge (swept)")
    a.plot([c.fw_section_x(0), c.fw_section_x(900)], [0, 900], color="k", lw=0.8, label="RS-FW-SECTION (front limit)")
    rt = np.array(c.RS_FWEP_TOP + (c.RS_FWEP_TOP[0],))
    a.plot(rt[:, 0], rt[:, 1], color="k", ls=":", lw=1.2, label="RS-FWEP-TOP (must be covered)")
    a.fill_between([-352, 352], p.half_width - p.tyre_f_width, p.half_width, color=grey, alpha=0.25, lw=0,
                   label="front tyre")
    a.set_title("front wing, top view (Y >= 0)"); a.set_xlabel("XF [mm]"); a.set_ylabel("Y [mm]")
    a.set_aspect("equal"); a.set_xlim(-1300, 400); a.set_ylim(0, 1000)
    a.legend(frameon=False, fontsize=6.5, loc="lower right")

    fig.suptitle("G1 endplates: design sections before lofting", fontsize=9)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / "g1_endplates_2d.png"
    fig.savefig(out, dpi=140)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
