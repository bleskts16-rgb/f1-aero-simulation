"""Create an OpenFOAM case (snappyHexMesh + simpleFoam, k-omega SST) for the half car.

    python scripts/build_car.py --half                       # geometry first
    python scripts/make_cfd_case.py --level coarse --np 4    # -> cfd/runs/baseline_half_coarse
    python scripts/run_cfd.py cfd/runs/baseline_half_coarse  # mesh + solve (WSL on Windows)
    python scripts/cfd_report.py cfd/runs/baseline_half_coarse

Mesh levels share the same refinement layout; only the background cell size (and
prism layers) change, so cell counts scale by roughly (h0_a / h0_b)^3 between levels.
"""
import argparse
import json
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "cfd" / "templates" / "car_half"
PARTS = ("body", "front_wing", "rear_wing", "wheels_front", "wheels_rear")

# background cell size h0 [m]; refinement level n gives h0 / 2^n
LEVELS = {
    "coarse": dict(h0=0.40, layers=0),
    "medium": dict(h0=0.25, layers=3),
    "fine":   dict(h0=0.20, layers=5),
}
REFINE = dict(LV_WAKE=2, LV_NEAR=3, LV_BODY_MIN=4, LV_BODY_MAX=5,
              LV_WING_MIN=5, LV_WING_MAX=6, LV_WINGBOX=5)

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
    ap.add_argument("--level", choices=LEVELS, default="coarse")
    ap.add_argument("--h0", type=float, help="override background cell size [m]")
    ap.add_argument("--np", type=int, default=4, help="MPI ranks")
    ap.add_argument("--iter", type=int, default=300, help="simpleFoam iterations")
    ap.add_argument("--u", type=float, default=50.0, help="freestream speed [m/s]")
    ap.add_argument("--name")
    args = ap.parse_args()

    geom = (ROOT / args.geom).resolve()
    p = json.loads((geom / "params.json").read_text(encoding="utf-8"))
    lev = dict(LEVELS[args.level])
    if args.h0:
        lev["h0"] = args.h0
    name = args.name or f"{geom.name}_{args.level}"
    case = ROOT / "cfd" / "runs" / name
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
    xmin, xlen, ylen, zlen = -6.0, 22.0, 5.0, 5.0
    nx, ny, nz = (math.ceil(L / h0) for L in (xlen, ylen, zlen))
    k = 1.5 * (0.005 * u) ** 2
    rf = p["tyre_f_diameter"] / 2000
    rr = p["tyre_r_diameter"] / 2000
    sq = p["tyre_squash"] / 1000
    wb = p["wheelbase"] / 1000
    values = dict(
        NU=nu, U_INF=u, RHO=1.2, K_INF=f"{k:.6g}", OMEGA_INF=f"{k / (10 * nu):.6g}",
        XMIN=xmin, XMAX=round(xmin + nx * h0, 6), YMAX=round(ny * h0, 6), ZMAX=round(nz * h0, 6),
        NX=nx, NY=ny, NZ=nz, NP=args.np, N_ITER=args.iter, COFR_X=wb / 2,
        WF_X=0.0, WF_Z=round(rf - sq, 6), WF_OMEGA=f"{-u / rf:.6g}",
        WR_X=wb, WR_Z=round(rr - sq, 6), WR_OMEGA=f"{-u / rr:.6g}",
        ADD_LAYERS="true" if lev["layers"] else "false", N_LAYERS=max(lev["layers"], 1),
        **REFINE,
    )
    for f in case.rglob("*"):
        if f.is_file() and f.parent.name != "triSurface":
            text = f.read_bytes().decode("utf-8").replace("\r\n", "\n")
            for key, val in values.items():
                text = text.replace(f"@{key}@", str(val))
            left = sorted(set(re.findall(r"@[A-Z_]+@", text)))
            if left:
                sys.exit(f"unfilled placeholders in {f.name}: {left}")
            f.write_bytes(text.encode("utf-8"))

    meta = dict(name=name, geometry=str(geom.relative_to(ROOT)), level=args.level,
                h0=h0, layers=lev["layers"], np=args.np, iterations=args.iter,
                u_inf=u, rho=1.2, half_model=True, y_shift=Y_SHIFT,
                cell_size_mm={f"L{n}": round(1000 * h0 / 2 ** n, 2) for n in range(7)},
                values=values)
    (case / "case.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    sizes = ", ".join(f"L{n}={1000 * h0 / 2 ** n:.1f}mm" for n in (0, 3, 5, 6))
    print(f"created {case.relative_to(ROOT)}  ({nx}x{ny}x{nz} background, {sizes})")


if __name__ == "__main__":
    main()
