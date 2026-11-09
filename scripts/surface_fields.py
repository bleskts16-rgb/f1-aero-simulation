"""Surface pressure and wall shear stress of a finished case -> one compact file.

    python scripts/surface_fields.py cfd/runs/screening/base_grid2_L1

The case's `surfaces` function object (make_cfd_case.py, from 2026-11-09) writes one
VTK surface per part at the last iteration, with pMean and wallShearStressMean averaged
over the same last-1000-iteration window as the forces. This script turns them into
<case>/surface_fields.npz (float32, a few MB) for surface-field surrogates:

    part          int   index into `parts`
    centre        (n,3) face centre [m] (CFD frame: X rearward from the front axle, Y >= 0, Z up)
    Sf            (n,3) face area vector [m^2], pointing out of the fluid (into the car)
    cp            (n,)  mean pressure coefficient  p / (0.5 U^2)          (kinematic p)
    cf            (n,3) mean skin-friction vector  tau_w / (0.5 U^2)
    cp_last, cf_last    the same at the last iteration (no average)

As a check it integrates the mean fields back into forces and compares them with the
forces function objects averaged over the same window; they must agree to round-off.
Forces are full-car values (x2), as everywhere else in the project.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]
WINDOW = 1000
FORCE_GROUPS = {"wheels": ("wheels_front", "wheels_rear"),
                "suspension": ("suspension_front", "suspension_rear")}


def polys_of(mesh):
    """Vertex index lists of each polygon (legacy 'faces' array: n, i0, i1, ...)."""
    f = np.asarray(mesh.faces)
    out, i = [], 0
    while i < len(f):
        n = f[i]
        out.append(f[i + 1:i + 1 + n])
        i += n + 1
    return out


def face_area_vectors(mesh):
    """Face area vectors in the vertex order OpenFOAM wrote (boundary faces point out of
    the fluid domain), by fan triangulation about each polygon's first vertex."""
    pts = np.asarray(mesh.points, float)
    polys = polys_of(mesh)
    sizes = np.array([len(p) for p in polys])
    sf = np.zeros((len(polys), 3))
    for n in np.unique(sizes):          # vectorised per polygon size
        sel = np.flatnonzero(sizes == n)
        v = pts[np.stack([polys[i] for i in sel])]           # (m, n, 3)
        sf[sel] = 0.5 * np.cross(v[:, 1:-1] - v[:, :1], v[:, 2:] - v[:, :1]).sum(axis=1)
    return sf


def mean_forces(case, group, window):
    f = sorted((case / "postProcessing" / f"forces_{group}").glob("*/force.dat"))
    if not f:
        return None
    a = np.vstack([np.loadtxt(x, comments="#", ndmin=2) for x in f])
    a = a[np.unique(a[:, 0], return_index=True)[1]]           # restarts repeat no rows, but be safe
    w = a[-min(window, len(a)):]
    return w[:, 4:7].mean(axis=0), w[:, 7:10].mean(axis=0)     # pressure, viscous


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--window", type=int, default=WINDOW, help="force rows the means were averaged over")
    args = ap.parse_args()
    case = (ROOT / args.case).resolve() if not Path(args.case).is_absolute() else Path(args.case)
    meta = json.loads((case / "case.json").read_text(encoding="utf-8"))
    u, rho = meta["u_inf"], meta["rho"]
    q_kin = 0.5 * u ** 2
    times = sorted((case / "postProcessing" / "surfaces").glob("*"), key=lambda d: float(d.name))
    if not times:
        sys.exit(f"no postProcessing/surfaces in {case} (case made before 2026-11-09?)")
    sdir = times[-1]
    parts = sorted(f.stem for f in sdir.glob("*.vtp"))
    data = {k: [] for k in ("part", "centre", "Sf", "cp", "cf", "cp_last", "cf_last")}
    integ = {}
    for k, name in enumerate(parts):
        m = pv.read(sdir / f"{name}.vtp")
        sf = face_area_vectors(m)
        pm = np.asarray(m.cell_data["pMean"], float)
        tm = np.asarray(m.cell_data["wallShearStressMean"], float)
        data["part"].append(np.full(m.n_cells, k, np.int16))
        data["centre"].append(np.asarray(m.cell_centers().points, float))
        data["Sf"].append(sf)
        data["cp"].append(pm / q_kin)
        data["cf"].append(tm / q_kin)
        data["cp_last"].append(np.asarray(m.cell_data["p"], float) / q_kin)
        data["cf_last"].append(np.asarray(m.cell_data["wallShearStress"], float) / q_kin)
        # forces on the car: pressure along Sf; wallShearStress is the stress the wall
        # exerts on the fluid (OpenFOAM convention), so the fluid drags the car with -tau
        integ[name] = (rho * (pm[:, None] * sf).sum(0),
                       -rho * (tm * np.linalg.norm(sf, axis=1)[:, None]).sum(0))
    out = {k: np.concatenate(v).astype(np.int16 if k == "part" else np.float32) for k, v in data.items()}
    np.savez_compressed(case / "surface_fields.npz", parts=np.array(parts), u_inf=u, rho=rho,
                        time=float(sdir.name), **out)

    # check against the forces function objects (full car = x2; q = 0.5 rho U^2)
    q = 0.5 * rho * u ** 2
    groups = {n: (n,) for n in parts if not any(n in g for g in FORCE_GROUPS.values())}
    groups.update({g: ps for g, ps in FORCE_GROUPS.items() if all(p in parts for p in ps)})
    groups["total"] = tuple(parts)
    print(f"{case.name}: {len(out['cp'])} faces, {len(parts)} parts, t = {sdir.name} "
          f"-> {(case / 'surface_fields.npz').stat().st_size / 1e6:.1f} MB")
    print(f"{'group':12s} {'CL.A surf':>10s} {'CL.A force':>10s} {'CD.A surf':>10s} {'CD.A force':>10s}"
          f" {'CD.A visc':>9s} {'max dev':>8s}")
    worst = 0.0
    for g, ps in groups.items():
        fp = sum(integ[p][0] for p in ps)
        fv = sum(integ[p][1] for p in ps)
        ref = mean_forces(case, g, args.window)
        s_cla, s_cda = -2 * (fp + fv)[2] / q, 2 * (fp + fv)[0] / q
        if ref is None:
            print(f"{g:12s} {s_cla:10.4f} {'-':>10s} {s_cda:10.4f} {'-':>10s} {2 * fv[0] / q:9.4f}")
            continue
        rp, rv = ref
        dev = np.abs(np.concatenate([fp - rp, fv - rv])).max() / max(np.linalg.norm(rp + rv), 1e-9)
        worst = max(worst, dev)
        print(f"{g:12s} {s_cla:10.4f} {-2 * (rp + rv)[2] / q:10.4f} {s_cda:10.4f} {2 * (rp + rv)[0] / q:10.4f}"
              f" {2 * fv[0] / q:9.4f} {dev:8.1e}")
    print("check OK" if worst < 1e-3 else f"CHECK FAILED: surface integral differs from forces by {worst:.1e}")
    sys.exit(0 if worst < 1e-3 else 1)


if __name__ == "__main__":
    main()
