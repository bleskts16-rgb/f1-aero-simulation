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

from cad import car2026, qa, regvol  # noqa: E402
from cad.car2026 import CarParams, sprung_parts, build_car, _wing_stack  # noqa: E402

COLORS = {"body": "#3b4a6b", "front_wing": "#b0413e", "rear_wing": "#b0413e",
          "wheels_front": "#2b2b2b", "wheels_rear": "#2b2b2b",
          "halo": "#9aa0a8", "wake_boards": "#b0413e", "mirrors": "#3b4a6b", "helmet": "#e0b33a",
          "suspension_front": "#6b7280", "suspension_rear": "#6b7280"}
# parts that must clear the tyres
CLEAR_OF_TYRES = ("body", "front_wing", "rear_wing", "halo", "wake_boards", "mirrors")


class _BB:
    """Tight bounds with the attribute names of cq.BoundBox."""
    def __init__(self, shape):
        (self.xmin, self.ymin, self.zmin), (self.xmax, self.ymax, self.zmax) = qa.tight_bbox(shape)


def regulation_checks(p, sprung, ground):
    """(description, value, limit, ok) for the limits this model is meant to respect."""
    bb = {k: _BB(v) for k, v in sprung.items()}
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
    add("App.1 s19-22 FW endplate |Y| max [mm]", fw.ymax, "<= 900", fw.ymax <= 900)
    add("App.1 s25 RW profiles |Y| max [mm]", p.rw_span_half, "<= 575", p.rw_span_half <= 575)
    add("App.1 s25/26 RW Z max [mm]", rw.zmax, "<= 880", rw.zmax <= 880)
    add("App.1 s26 RW rear X (XR) [mm]", rw.xmax - p.xr, "<= 750", rw.xmax - p.xr <= 750)

    if p.geom_level == "G0":
        for tag, le, ch, an, gap, ov, dlt, lo, hi in (
                ("3.10.1e FW", p.fw_le, p.fw_chords, p.fw_angles, p.fw_gap, p.fw_overlap,
                 p.fw_flap_delta, 5, 15),
                ("3.11.1d RW", (p.xr + p.rw_le[0], p.rw_le[1]), p.rw_chords, p.rw_angles,
                 p.rw_gap, p.rw_overlap, p.rw_flap_delta, 10, 15)):
            el = _wing_stack(le, ch, an, -10, 10, gap, ov, dlt)
            gaps = [el[i].distance(el[i + 1]) for i in range(len(el) - 1)]
            add(f"{tag} slot gaps [mm]", ", ".join(f"{g:.1f}" for g in gaps), f"{lo}..{hi}",
                all(lo - 0.1 <= g <= hi + 0.1 for g in gaps))
    else:
        # span-lofted elements: gaps at every station of the span table
        for tag, layouts, lo, hi in (("3.10.1e FW", car2026.fw_span_layouts(p), 5, 15),
                                     ("3.11.1d RW", car2026.rw_span_layouts(p), 10, 15)):
            gaps = []
            for y, lay in layouts:
                el = [car2026._wing_element(*q, y, y + 1.0)[0] for q in lay]
                gaps += [el[i].distance(el[i + 1]) for i in range(len(el) - 1)]
            add(f"{tag} slot gaps, {len(layouts)} stations [mm]",
                f"{min(gaps):.1f}..{max(gaps):.1f}", f"{lo}..{hi}",
                all(lo - 0.1 <= g <= hi + 0.1 for g in gaps))

    if p.geom_level != "G0":
        rows += g1_wing_checks(p, sprung)
    rows += volume_checks(p, sprung)

    wheels = ground["wheels_front"].fuse(ground["wheels_rear"])
    clear_parts = [k for k in CLEAR_OF_TYRES if k in ground]
    clear = min(ground[k].distance(wheels) for k in clear_parts)
    add("bodywork to tyre clearance [mm]", round(clear, 1), "> 10", clear > 10)
    zmin = min(_BB(ground[k]).zmin for k in sprung)
    add("lowest sprung part above road [mm]", round(zmin, 1), "> 0", zmin > 0)
    return rows


def g1_wing_checks(p, sprung):
    """Front/rear wing rules checked on G1 only (G0 predates them and fails the
    swept front limit and the endplate coverage; it is kept for the grid studies).
    FIA 2026 Technical Regulations Issue 8, Art. 3.10 and Appendix 1."""
    rows = []
    fw, rw = sprung["front_wing"], sprung["rear_wing"]
    rows.append(("App.1 s18 FW profiles half span [mm]", car2026.FW_SPAN_G1, "<= 675",
                 car2026.FW_SPAN_G1 <= 675))
    verts, _ = fw.tessellate(0.5, 0.2)
    v = np.array([[q.x, q.y, q.z] for q in verts])
    ahead = float(np.min(v[:, 0] - car2026.fw_section_x(np.abs(v[:, 1]))))
    rows.append(("App.1 s17 FW aft of RS-FW-SECTION [mm]", round(ahead, 1), ">= 0", ahead >= -0.5))
    for desc, poly, axes, ray, rng, shape in (
            ("3.10.6g FWEP obscures RS-FWEP-TOP from above", car2026.RS_FWEP_TOP, "xy", "z",
             (-200.0, 1200.0), fw),
            ("3.10.6h FWEP obscures RS-FWEP-SIDE from inboard", car2026.RS_FWEP_SIDE, "xz", "y",
             (600.0, 950.0), fw),
            ("3.11 RW endplate obscures RS-RWEP from the side",
             # rays from Y 300: the lower endplate folds in to Y 355 (§26), the
             # twin pylons (Y 28..43) stay out of the ray range
             [(p.xr + x, z) for x, z in car2026.RS_RWEP], "xz", "y", (300.0, 700.0), rw)):
        frac, missed = qa.obscured(shape, poly, axes, ray, rng)
        val = f"{100 * frac:.1f} %" + (f", e.g. {missed[0][0]:.0f},{missed[0][1]:.0f}" if missed else "")
        rows.append((desc, val, "100 %", not missed))
    return rows


VOLUME_TOL = 1.0   # [mm] depth outside a reference volume still taken as inside (tessellation)


def volume_checks(p, sprung):
    """Parts against the Appendix 1 reference volumes written out in the text
    (cad/regvol.py): material outside their union, as volume and depth. Enforced on
    every level except G0 (fixed for the grid studies, built before these rules were
    read), where the rows are information only (ok = None). Parts mounted on the body
    are judged on what lies outside the body (their buried roots are not bodywork in
    the flow)."""
    xr, xc = p.xr, p.xc
    floor = regvol.floor_volumes(xr, xc)
    body = sprung["body"]
    exposed = lambda k: sprung[k].cut(body) if k in sprung else None
    groups = (
        # nose, chassis, sidepods, engine cover, tail and the floor fused into them;
        # the driver's helmet and the halo (a prescribed part) are separate parts
        ("3.7-3.9 body in RV-BODY-FRONT/DRI-COOL/SIDEPOD/EC/TAIL/TAILPIPE/FLOOR-*", body,
         {**regvol.body_volumes(p.xa, xc, xr), **floor}),
        ("3.10 front wing in RV-FW-PROFILES/FWEP-*/FW-PYLON", sprung["front_wing"],
         regvol.front_wing_volumes()),
        ("3.11 rear wing in RV-RW-PROFILES/RWEP-BODY/RW-PYLON/stays", sprung["rear_wing"],
         regvol.rear_wing_volumes(xr)),
        ("3.5 floor + diffuser in RV-FLOOR-*", car2026._fuse(*car2026.floor_parts(p)), floor),
        ("3.5 wake/floor boards in RV-FLOOR-*", exposed("wake_boards"), floor),
        ("3.4 mirrors in RV-MIRROR-BODY/stays", exposed("mirrors"), regvol.mirror_volumes(xc)),
    )
    half = car2026._box(-3000, 8000, 0, 2000, -500, 2000)      # volumes are built for Y >= 0
    rows = []
    for desc, shape, vols in groups:
        if shape is None:
            continue
        vol, depth, where = qa.outside(shape.intersect(half), regvol.fuse(*vols.values()))
        val = f"{vol / 1000:.1f} cm3 out, max {depth:.0f} mm"
        if where:
            x, y, z = where
            val += f" at X {x:.0f} (XR {x - xr:.0f}), Y {y:.0f}, Z {z:.0f}"
        ok = depth <= VOLUME_TOL if p.geom_level != "G0" else None
        rows.append((f"App.1 {desc}", val, f"<= {VOLUME_TOL:g} mm", ok))
    return rows


def geometry_checks(parts, outdir, half):
    """cad.qa checks on the exported parts and on every loft that built them."""
    checks = []
    # the full car keeps left/right tyres and wake boards as separate bodies;
    # suspension parts are sets of members (track rod apart from the wishbones)
    expect = {k: 1 if half or not k.startswith(("wheels", "wake_boards", "mirrors")) else 2
              for k in parts}
    expect.update({k: None for k in parts if k.startswith("suspension")})
    for label, solid, wires in car2026.LOFT_LOG:
        excess, slab, axis = qa.loft_local_escape(solid, wires)
        where = f" at {slab} along {axis}" if slab is not None else ""
        checks.append(qa.Check(f"loft '{label}' stays near its sections",
                               excess <= qa.LOFT_ESCAPE_LIMIT,
                               f"{excess:.1f} mm{where} (limit {qa.LOFT_ESCAPE_LIMIT:.0f})"))
    for name, shape in parts.items():
        checks += qa.solid_checks(name, shape, expect[name])
    for name in ("halo", "wake_boards", "mirrors", "helmet"):
        if name in parts:
            checks += qa.attached(name, parts[name], {"body": parts["body"]})
    for name, wheel in (("suspension_front", "wheels_front"), ("suspension_rear", "wheels_rear")):
        if name in parts:
            checks += qa.attached(name, parts[name], {"body": parts["body"], wheel: parts[wheel]})
    for name in parts:
        n_open, n_tri = qa.stl_open_edges(outdir / f"{name}.stl")
        checks.append(qa.Check(f"{name}.stl closed", n_open == 0,
                               f"{n_open} open edges / {n_tri} triangles"))
    return checks


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

    # underside: the floor and diffuser make most of the downforce, so review them too
    views = [("isometric", 22, -125), ("side", 0, -90), ("top", 90, -90),
             ("front", 0, 180), ("underside", -90, -90), ("rear 3/4", 18, -35)]
    fig = plt.figure(figsize=(18, 10))
    for i, (lbl, elev, azim) in enumerate(views):
        ax = fig.add_subplot(2, 3, i + 1, projection="3d")
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
    ap.add_argument("--halo", action="store_true")
    ap.add_argument("--suspension", action="store_true")
    ap.add_argument("--wake-boards", action="store_true", help="front wheel wake boards")
    ap.add_argument("--mirrors", action="store_true")
    ap.add_argument("--details", action="store_true",
                    help="all of halo, suspension, wake boards, mirrors")
    ap.add_argument("--g1", action="store_true",
                    help="G1 shapes after the FIA 2026 renders (spoon front wing, undercut sidepods)")
    ap.add_argument("--fia", action="store_true", help="--g1 --details, output name 'fia2026'")
    ap.add_argument("--wb-yaw", type=float,
                    help="G0 wake board inward alignment [deg] (G1 floor boards follow RV-FLOOR-BOARD)")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()
    args.g1 |= args.fia
    args.details |= args.fia

    over = {k: v for k, v in (("ride_height_front", args.rh_front),
                              ("ride_height_rear", args.rh_rear),
                              ("fw_flap_delta", args.fw_flap_delta),
                              ("rw_flap_delta", args.rw_flap_delta),
                              ("wb_yaw", args.wb_yaw)) if v is not None}
    tags = [t for t, on in (("halo", args.halo), ("susp", args.suspension),
                            ("wb", args.wake_boards), ("mirr", args.mirrors))
            if on or args.details]
    over.update(halo="halo" in tags, suspension="susp" in tags, wake_boards="wb" in tags,
                mirrors="mirr" in tags, geom_level="G1" if args.g1 else "G0")
    p = CarParams().with_(**over)
    if args.name == "baseline":
        if args.fia:
            args.name = "fia2026"
        elif tags or args.g1:
            base = "g1" if args.g1 else "baseline"
            args.name = base + ("_detail" if len(tags) == 4 else
                                "".join("_" + t for t in tags))

    t0 = time.time()
    car2026.LOFT_LOG.clear()
    sprung = sprung_parts(p)
    ground = build_car(p, sprung, half=True)
    parts = ground if args.half else build_car(p, sprung)
    print(f"built in {time.time() - t0:.1f} s  (rake {p.pitch_deg:.2f} deg)")

    rows = regulation_checks(p, sprung, ground)
    reg_ok = all(r[3] is not False for r in rows)
    w = max(len(r[0]) for r in rows)
    print("  -- regulations (tight bounds; '-- ' = information only, not enforced on G0)")
    for desc, val, lim, ok in rows:
        val = f"{val:.1f}" if isinstance(val, float) else val
        mark = "-- " if ok is None else ("OK " if ok else "NG ")
        print(f"  {mark} {desc:<{w}}  {val:>16}  ({lim})")

    for name, s in parts.items():
        bb = _BB(s)
        print(f"  {name:<13} X {bb.xmin:7.0f}..{bb.xmax:5.0f}  Y {bb.ymin:5.0f}..{bb.ymax:4.0f}  "
              f"Z {bb.zmin:4.0f}..{bb.zmax:4.0f} mm")

    outdir = ROOT / "cad" / "out" / (args.name + ("_half" if args.half else ""))
    export(parts, outdir)
    (outdir / "params.json").write_text(json.dumps(p.to_dict(), indent=2), encoding="utf-8")
    print(f"exported {outdir.relative_to(ROOT)}  (STL in m, STEP in mm)")

    geo_ok = qa.report(geometry_checks(parts, outdir, args.half), "geometry QA (cad/qa.py)")

    if not args.no_render:
        fig = ROOT / "docs" / "figures" / f"car2026_{outdir.name}.png"
        render(parts, fig, f"Simplified 2026 F1 car ({outdir.name}) - FIA 2026 Technical "
                           f"Regulations Issue 8 dimensions")
        print(f"saved {fig.relative_to(ROOT)}")

    if not (reg_ok and geo_ok):
        print("FAILED: see NG rows above (a failed check is not a pass)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
