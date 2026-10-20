"""Create an OpenFOAM case (snappyHexMesh + simpleFoam, k-omega SST) for the half car.

    python scripts/build_car.py --half                       # geometry first
    python scripts/make_cfd_case.py --level coarse --np 4    # -> cfd/runs/baseline_half_coarse
    python scripts/run_cfd.py cfd/runs/baseline_half_coarse  # mesh + solve (WSL on Windows)
    python scripts/cfd_report.py cfd/runs/baseline_half_coarse

Mesh levels L1..L5 share the same refinement layout and prism-layer settings; only the
background cell size h0 changes, by a constant ratio r = 4/3 per level, so every cell
in the domain shrinks by the same factor (what a GCI / Richardson study needs).
Cell counts grow by roughly r^3 = 2.37 per level.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "cfd" / "templates" / "car_half"
PARTS = ("body", "front_wing", "rear_wing", "wheels_front", "wheels_rear")

# background cell size h0 [m]; refinement level n gives h0 / 2^n
RATIO = 4 / 3
LEVELS = {f"L{i + 1}": dict(h0=round(0.40 / RATIO ** i, 4)) for i in range(5)}
LAYERS = 3
REFINE = dict(LV_WAKE=2, LV_NEAR=3, LV_BODY_MIN=4, LV_BODY_MAX=5,
              LV_WING_MIN=5, LV_WING_MAX=6, LV_WINGBOX=5)

# Mesh schemes. grid1 (2026-10-16): layers relative to the local surface cell, so the
# first-cell height and y+ change with the level, and the underfloor gap is resolved only
# by the surface levels. grid2 (2026-10-20): the gap under the floor and the diffuser get
# their own refinement boxes at the finest body level, and the first prism layer has a
# fixed absolute thickness, so every level sees the same near-wall treatment.
SCHEMES = {
    "grid1": dict(floor_boxes=False, layer_mode="relativeSizes       true;",
                  layer_size=["expansionRatio      1.2;", "finalLayerThickness 0.5;",
                              "minThickness        0.1;"],
                  layer_feature_angle=60, mq_relaxed=""),
    "grid2": dict(floor_boxes=True, layer_mode="relativeSizes       false;",
                  layer_size=["firstLayerThickness 0.0008;   // y+ ~ 50 at the first cell centre, U = 50 m/s",
                              "expansionRatio      1.25;",
                              "minThickness        0.0002;"],
                  # layers continue round sharp edges (wheel shoulders, contact patch) and
                  # may relax non-orthogonality where they would otherwise collapse
                  layer_feature_angle=130, mq_relaxed="relaxed { maxNonOrtho 75; }",
                  # wheels at the body's finest level: a ~3 mm absolute layer stack on 25 mm
                  # level-4 cells failed the quality checks (1.0-1.4 of 3 layers at L1)
                  lv_wheel=5),
}

Y_SHIFT = -0.001   # move the closed half model 1 mm across Y=0 so it cuts the symmetry plane cleanly


def shift_stl(src, dst, dy):
    b = src.read_bytes()
    n = int(np.frombuffer(b, "<u4", 1, 80)[0])
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    tri = np.frombuffer(b, rec, n, 84).copy()
    tri["v"][:, :, 1] += dy
    dst.write_bytes(b"f1-aero-simulation half car".ljust(80, b" ")
                    + np.uint32(n).tobytes() + tri.tobytes())
    return tri["v"].reshape(-1, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", default="cad/out/baseline_half",
                    help="folder from build_car.py --half (STL in m + params.json)")
    ap.add_argument("--level", choices=LEVELS, default="L1")
    ap.add_argument("--layers", type=int, default=LAYERS, help="prism layers (0 = none)")
    ap.add_argument("--h0", type=float, help="override background cell size [m]")
    ap.add_argument("--np", type=int, default=4, help="MPI ranks")
    ap.add_argument("--iter", type=int, default=300, help="simpleFoam iterations")
    ap.add_argument("--u", type=float, default=50.0, help="freestream speed [m/s]")
    ap.add_argument("--name")
    ap.add_argument("--outdir", default="cfd/runs", help="parent folder for the case")
    ap.add_argument("--scheme", choices=SCHEMES, default="grid1", help="mesh scheme (see SCHEMES)")
    args = ap.parse_args()

    geom = (ROOT / args.geom).resolve()
    p = json.loads((geom / "params.json").read_text(encoding="utf-8"))
    lev = dict(LEVELS[args.level], layers=args.layers)
    if args.h0:
        lev["h0"] = args.h0
    name = args.name or f"{geom.name}_{args.level}"
    case = ROOT / args.outdir / name
    if case.exists():
        sys.exit(f"{case.relative_to(ROOT)} exists - remove it or pick --name")

    shutil.copytree(TEMPLATE, case)
    tri = case / "constant" / "triSurface"
    tri.mkdir(parents=True)
    ymin = 0.0
    for part in PARTS:
        v = shift_stl(geom / f"{part}.stl", tri / f"{part}.stl", Y_SHIFT)
        ymin = min(ymin, float(v[:, 1].min()))
    if ymin < Y_SHIFT - 0.01:
        sys.exit(f"{geom} is not a Y >= 0 half model (y min {ymin:.3f} m); use build_car.py --half")

    h0, u, nu = lev["h0"], args.u, 1.5e-5
    # fixed domain for every level (blockage ~3 %); cells are near-cubic, never resized
    xmin, xlen, ylen, zlen = -6.0, 22.0, 5.2, 5.2
    nx, ny, nz = (max(1, round(L / h0)) for L in (xlen, ylen, zlen))
    k = 1.5 * (0.005 * u) ** 2
    rf = p["tyre_f_diameter"] / 2000
    rr = p["tyre_r_diameter"] / 2000
    sq = p["tyre_squash"] / 1000
    wb = p["wheelbase"] / 1000
    values = dict(
        NU=nu, U_INF=u, RHO=1.2, K_INF=f"{k:.6g}", OMEGA_INF=f"{k / (10 * nu):.6g}",
        XMIN=xmin, XMAX=xmin + xlen, YMAX=ylen, ZMAX=zlen,
        NX=nx, NY=ny, NZ=nz, NP=args.np, N_ITER=args.iter, COFR_X=wb / 2,
        WF_X=0.0, WF_Z=round(rf - sq, 6), WF_OMEGA=f"{-u / rf:.6g}",
        WR_X=wb, WR_Z=round(rr - sq, 6), WR_OMEGA=f"{-u / rr:.6g}",
        ADD_LAYERS="true" if lev["layers"] else "false", N_LAYERS=max(lev["layers"], 1),
        **REFINE,
    )
    sch = SCHEMES[args.scheme]
    values["LAYER_MODE"] = sch["layer_mode"]
    values["LAYER_SIZE"] = "\n    ".join(sch["layer_size"])
    values["LAYER_FEATURE_ANGLE"] = sch["layer_feature_angle"]
    values["MQ_RELAXED"] = sch["mq_relaxed"]
    values["LV_WHEEL"] = sch.get("lv_wheel", REFINE["LV_BODY_MIN"])
    if sch["floor_boxes"]:
        # ground frame: the floor underside sits at the front/rear ride height and the
        # diffuser rises to its exit height at XR+165 (cad/car2026.py)
        x0, x1 = 0.35, wb + 0.20
        xd0 = wb + p["diffuser_start"] / 1000 - 0.05
        xd1 = wb + 0.165 + 0.30
        z_floor = (p["ride_height_rear"] + p["floor_thickness"]) / 1000 + 0.01
        z_diff = (p["ride_height_rear"] + p["diffuser_exit_height"]) / 1000 + 0.06
        values["EXTRA_GEOMETRY"] = (
            f"floorBox {{ type box; min ({x0} 0 0); max ({x1:.3f} 0.76 {z_floor:.3f}); }} // gap under the floor\n"
            f"    diffBox  {{ type box; min ({xd0:.3f} 0 0); max ({xd1:.3f} 0.42 {z_diff:.3f}); }} // diffuser + exit")
        values["EXTRA_REGIONS"] = (f"floorBox {{ mode inside; levels ((1E15 {REFINE['LV_BODY_MAX']})); }}\n"
                                   f"        diffBox  {{ mode inside; levels ((1E15 {REFINE['LV_BODY_MAX']})); }}")
    else:
        values["EXTRA_GEOMETRY"] = values["EXTRA_REGIONS"] = ""
    for f in case.rglob("*"):
        if f.is_file() and f.parent.name != "triSurface":
            text = f.read_bytes().decode("utf-8").replace("\r\n", "\n")
            for key, val in values.items():
                if val == "":      # drop the whole placeholder line
                    text = re.sub(rf"^[ \t]*@{key}@\n", "", text, flags=re.M)
                text = text.replace(f"@{key}@", str(val))
            left = sorted(set(re.findall(r"@[A-Z_]+@", text)))
            if left:
                sys.exit(f"unfilled placeholders in {f.name}: {left}")
            f.write_bytes(text.encode("utf-8"))

    meta = dict(name=name, geometry=str(geom.relative_to(ROOT)), level=args.level, scheme=args.scheme,
                h0=h0, layers=lev["layers"], np=args.np, iterations=args.iter,
                u_inf=u, rho=1.2, half_model=True, y_shift=Y_SHIFT,
                cell_size_mm={f"L{n}": round(1000 * h0 / 2 ** n, 2) for n in range(7)},
                values=values)
    (case / "case.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    sizes = ", ".join(f"L{n}={1000 * h0 / 2 ** n:.1f}mm" for n in (0, 3, 5, 6))
    print(f"created {case.relative_to(ROOT)}  ({nx}x{ny}x{nz} background, {sizes})")


if __name__ == "__main__":
    main()
