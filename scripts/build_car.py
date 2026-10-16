"""Build the simplified 2026 car, check it against key regulation limits, export
STEP/STL and render a preview.

    python scripts/build_car.py                       # full car, default setup
    python scripts/build_car.py --half                # Y >= 0 half for a symmetry-plane case
    python scripts/build_car.py --rh-front 25 --rh-rear 90 --fw-flap-delta -10 --name low_drag

STL files are in metres (OpenFOAM), STEP in millimetres. Output: cad/out/<name>/.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cad.car2026 import CarParams, sprung_parts, build_car, _wing_stack  # noqa: E402

COLORS = {"body": "#3b4a6b", "front_wing": "#b0413e", "rear_wing": "#b0413e",
          "wheels_front": "#2b2b2b", "wheels_rear": "#2b2b2b"}


def regulation_checks(p, sprung, ground):
    """(description, value, limit, ok) for the limits this model is meant to respect."""
    bb = {k: v.BoundingBox() for k, v in sprung.items()}
    rows = []

    def add(desc, val, lim, ok):
        rows.append((desc, val, lim, bool(ok)))

    ymax = max(max(abs(b.ymin), abs(b.ymax)) for b in bb.values())
    add("2.8.1 bodywork |Y| max [mm]", ymax, "<= 950", ymax <= 950)
    add("2.8.2 wheelbase [mm]", p.wheelbase, "<= 3400", p.wheelbase <= 3400)
    add("2.8.3 XF - XA [mm]", p.xf_minus_xa, "0..150", 0 <= p.xf_minus_xa <= 150)
    add("2.8.4 XC - XA [mm]", p.xc_minus_xa, "1830..2030", 1830 <= p.xc_minus_xa <= 2030)
    add("App.1 s8/s13 body Z max [mm]", bb["body"].zmax, "<= 970", bb["body"].zmax <= 970)
    add("2.7a body Z min (car frame) [mm]", bb["body"].zmin, ">= 0", bb["body"].zmin >= -0.5)
    fw, rw = bb["front_wing"], bb["rear_wing"]
    add("App.1 s18 FW front X (XF) [mm]", fw.xmin, ">= -1250", fw.xmin >= -1250.5)
    add("App.1 s19 FW |Y| max [mm]", fw.ymax, "<= 680", fw.ymax <= 680)
    add("App.1 s25 RW profiles |Y| max [mm]", p.rw_span_half, "<= 575", p.rw_span_half <= 575)
    add("App.1 s25/26 RW Z max [mm]", rw.zmax, "<= 880", rw.zmax <= 880)
    add("App.1 s26 RW rear X (XR) [mm]", rw.xmax - p.xr, "<= 750", rw.xmax - p.xr <= 750)

    for tag, le, ch, an, gap, ov, dlt, lo, hi in (
            ("3.10.1e FW", p.fw_le, p.fw_chords, p.fw_angles, p.fw_gap, p.fw_overlap,
             p.fw_flap_delta, 5, 15),
            ("3.11.1d RW", (p.xr + p.rw_le[0], p.rw_le[1]), p.rw_chords, p.rw_angles,
             p.rw_gap, p.rw_overlap, p.rw_flap_delta, 10, 15)):
        el = _wing_stack(le, ch, an, -10, 10, gap, ov, dlt)
        gaps = [el[i].distance(el[i + 1]) for i in range(len(el) - 1)]
        add(f"{tag} slot gaps [mm]", ", ".join(f"{g:.1f}" for g in gaps), f"{lo}..{hi}",
            all(lo - 0.1 <= g <= hi + 0.1 for g in gaps))

    wheels = ground["wheels_front"].fuse(ground["wheels_rear"])
    clear = min(ground[k].distance(wheels) for k in ("body", "front_wing", "rear_wing"))
    add("body/wings to tyre clearance [mm]", round(clear, 1), "> 10", clear > 10)
    zmin = min(ground[k].BoundingBox().zmin for k in ("body", "front_wing", "rear_wing"))
    add("lowest bodywork above road [mm]", round(zmin, 1), "> 0", zmin > 0)
    return rows


def export(parts, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    asm = cq.Assembly()
    for name, shape in parts.items():
        asm.add(shape, name=name, color=cq.Color(COLORS[name]))
        cq.exporters.export(shape.scale(0.001), str(outdir / f"{name}.stl"),
                            tolerance=0.0005, angularTolerance=0.15)
    asm.export(str(outdir / "car.step"))


def render(parts, path, title):
    tris = {}
    for name, shape in parts.items():
        verts, faces = shape.tessellate(2.0, 0.3)
        v = np.array([[q.x, q.y, q.z] for q in verts])
        tris[name] = v[np.array(faces)]
    allv = np.concatenate([t.reshape(-1, 3) for t in tris.values()])
    lo, hi = allv.min(0), allv.max(0)
    light = np.array([-0.4, -0.6, 0.7]) / np.linalg.norm([-0.4, -0.6, 0.7])

    views = [("isometric", 22, -125), ("side", 0, -90), ("top", 90, -90), ("front", 0, 180)]
    fig = plt.figure(figsize=(16, 10))
    for i, (lbl, elev, azim) in enumerate(views):
        ax = fig.add_subplot(2, 2, i + 1, projection="3d")
        for name, t in tris.items():
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
            shade = 0.45 + 0.55 * np.abs(n @ light)
            base = np.array(matplotlib.colors.to_rgb(COLORS[name]))
            fc = np.clip(base[None, :] * shade[:, None] + 0.12 * shade[:, None], 0, 1)
            ax.add_collection3d(Poly3DCollection(t, facecolors=fc, edgecolors="none"))
        ax.set_proj_type("ortho")
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(0, hi[2])
        ax.set_box_aspect(hi - np.array([lo[0], lo[1], 0]), zoom=1.0)
        ax.set_axis_off()
        ax.set_title(lbl, fontsize=10)
    fig.suptitle(title, fontsize=12)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=0.93, wspace=0, hspace=0.05)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="baseline")
    ap.add_argument("--half", action="store_true", help="export only the Y >= 0 half")
    ap.add_argument("--rh-front", type=float)
    ap.add_argument("--rh-rear", type=float)
    ap.add_argument("--fw-flap-delta", type=float, help="extra FW flap rotation [deg]")
    ap.add_argument("--rw-flap-delta", type=float, help="extra RW flap rotation [deg]")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()

    over = {k: v for k, v in (("ride_height_front", args.rh_front),
                              ("ride_height_rear", args.rh_rear),
                              ("fw_flap_delta", args.fw_flap_delta),
                              ("rw_flap_delta", args.rw_flap_delta)) if v is not None}
    p = CarParams().with_(**over)

    t0 = time.time()
    sprung = sprung_parts(p)
    ground = build_car(p, sprung, half=True)
    parts = ground if args.half else build_car(p, sprung)
    print(f"built in {time.time() - t0:.1f} s  (rake {p.pitch_deg:.2f} deg)")

    rows = regulation_checks(p, sprung, ground)
    w = max(len(r[0]) for r in rows)
    for desc, val, lim, ok in rows:
        val = f"{val:.1f}" if isinstance(val, float) else val
        print(f"  {'OK ' if ok else 'NG '} {desc:<{w}}  {val:>16}  ({lim})")

    for name, s in parts.items():
        bb = s.BoundingBox()
        print(f"  {name:<13} valid={s.isValid()} solids={len(s.Solids())}  "
              f"X {bb.xmin:7.0f}..{bb.xmax:5.0f}  Y {bb.ymin:5.0f}..{bb.ymax:4.0f}  "
              f"Z {bb.zmin:4.0f}..{bb.zmax:4.0f} mm")

    outdir = ROOT / "cad" / "out" / (args.name + ("_half" if args.half else ""))
    export(parts, outdir)
    (outdir / "params.json").write_text(json.dumps(p.to_dict(), indent=2), encoding="utf-8")
    print(f"exported {outdir.relative_to(ROOT)}  (STL in m, STEP in mm)")

    if not args.no_render:
        fig = ROOT / "docs" / "figures" / f"car2026_{outdir.name}.png"
        render(parts, fig, f"Simplified 2026 F1 car ({outdir.name}) - FIA 2026 Technical "
                           f"Regulations Issue 8 dimensions")
        print(f"saved {fig.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
