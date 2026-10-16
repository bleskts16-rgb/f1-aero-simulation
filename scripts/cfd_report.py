"""Summarise a finished case: mesh size, wall time per step, solver speed, peak memory,
CL*A / CD*A per part, and a run-time estimate for longer runs / other machines.

    python scripts/cfd_report.py cfd/runs/baseline_half_coarse
    python scripts/cfd_report.py cfd/runs/baseline_half_coarse --iters 2000 --cores 8 16 --cells 4e6
    python scripts/cfd_report.py cfd/runs/baseline_half_coarse --cores 6 --speed-factor 2   # faster PC

Forces come from the half model and are doubled for the full car.
CL*A is positive for downforce (same convention as lapsim.Vehicle.cla).
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read_timing(case):
    t = {}
    f = case / "log.timing"
    if not f.exists():
        return t
    for line in f.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            t.setdefault(parts[0], {})[parts[1]] = float(parts[2])
    return {k: v for k, v in t.items() if "start" in v}


def read_mem(case):
    f = case / "log.mem"
    if not f.exists():
        return None
    a = np.loadtxt(f, ndmin=2)
    return a[:, 0], a[:, 1]


def solver_speed(case):
    """Seconds per iteration from simpleFoam's ExecutionTime, skipping start-up."""
    f = case / "log.simpleFoam"
    if not f.exists():
        return None, 0
    txt = f.read_text(errors="ignore")
    exe = np.array([float(x) for x in re.findall(r"^ExecutionTime = ([\d.eE+-]+) s", txt, re.M)])
    if len(exe) < 5:
        return None, len(exe)
    d = np.diff(exe)[min(20, len(exe) // 4):]
    return float(np.median(d)), len(exe)


def cell_count(case):
    f = case / "log.checkMesh"
    if not f.exists():
        return None
    m = re.search(r"^\s*cells:\s+(\d+)", f.read_text(errors="ignore"), re.M)
    return int(m.group(1)) if m else None


def forces(case, q, avg_frac=0.2):
    out = {}
    for d in sorted((case / "postProcessing").glob("forces_*")):
        files = sorted(d.glob("*/force.dat"))
        if not files:
            continue
        rows = []
        for f in files:
            for line in f.read_text().splitlines():
                if line.strip() and not line.startswith("#"):
                    rows.append([float(x) for x in line.replace("(", " ").replace(")", " ").split()])
        a = np.array(rows)
        n = max(1, int(len(a) * avg_frac))
        fx, fz = a[-n:, 1].mean(), a[-n:, 3].mean()
        out[d.name.replace("forces_", "")] = dict(
            cla=-2 * fz / q, cda=2 * fx / q, iters=len(a),
            cla_trace=-2 * a[:, 3] / q)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--iters", type=int, default=2000, help="iterations for the run-time estimate")
    ap.add_argument("--cores", type=int, nargs="*", default=[4, 8, 16])
    ap.add_argument("--cells", type=float, nargs="*", default=[1e6, 4e6, 10e6])
    ap.add_argument("--speed-factor", type=float, default=1.0,
                    help="per-core speed of the target machine relative to this one (assumption)")
    args = ap.parse_args()
    case = (ROOT / args.case).resolve()
    meta = json.loads((case / "case.json").read_text(encoding="utf-8"))

    print(f"case {meta['name']}  level={meta['level']}  h0={meta['h0']} m  np={meta['np']}  "
          f"U={meta['u_inf']} m/s")
    cells = cell_count(case)
    print(f"cells: {cells:,}" if cells else "cells: (no checkMesh log)")

    timing = read_timing(case)
    mem = read_mem(case)
    base = mem[1][:3].min() if mem else 0.0
    print("\nstep                    wall [min]   peak extra RAM [GB]")
    for step, t in timing.items():
        end = t.get("end")
        dur = (end - t["start"]) / 60 if end else float("nan")
        peak = ""
        if mem:
            sel = (mem[0] >= t["start"]) & (mem[0] <= (end or mem[0][-1]))
            if sel.any():
                peak = f"{(mem[1][sel].max() - base) / 1024:6.2f}"
        print(f"  {step:<22}{dur:10.1f}   {peak:>12}")
    mesh_steps = ("surfaceFeatureExtract", "blockMesh", "decomposePar", "snappyHexMesh", "checkMesh")
    mesh_min = sum((timing[s]["end"] - timing[s]["start"]) / 60 for s in mesh_steps
                   if s in timing and "end" in timing[s])
    print(f"  {'meshing total':<22}{mesh_min:10.1f}")

    spi, n_it = solver_speed(case)
    if spi:
        print(f"\nsimpleFoam: {n_it} iterations, {spi:.2f} s/iteration on {meta['np']} cores")
    if spi and cells:
        cost = spi * meta["np"] / (cells / 1e6)   # core-seconds per million cell-iterations
        print(f"cost: {cost:.1f} core-s per (1M cells x 1 iteration)  <- machine-specific constant")
        sf = args.speed_factor
        print(f"\nestimate for {args.iters} iterations (linear in cells, ideal core scaling, "
              f"per-core speed x{sf:g} of this machine):")
        print("  cells      " + "".join(f"{c:>8d} cores" for c in args.cores))
        for nc in args.cells:
            hrs = [cost / sf * nc / 1e6 * args.iters / c / 3600 for c in args.cores]
            print(f"  {nc / 1e6:5.1f}M     " + "".join(f"{h:12.1f} h" for h in hrs))

    q = 0.5 * meta["rho"] * meta["u_inf"] ** 2
    f = forces(case, q)
    if f:
        print(f"\nforces (full car, mean of last 20 % of {next(iter(f.values()))['iters']} iterations; "
              f"not converged unless the run was long enough):")
        print("  part          CL*A [m^2]  CD*A [m^2]")
        for k in ("front_wing", "body", "rear_wing", "wheels", "total"):
            if k in f:
                print(f"  {k:<12}{f[k]['cla']:11.3f}{f[k]['cda']:12.3f}")
        if "total" in f:
            tr = f["total"]["cla_trace"]
            n = len(tr)
            if n >= 40:
                a, b = tr[n // 2: 3 * n // 4].mean(), tr[3 * n // 4:].mean()
                print(f"  total CL*A drift between the 3rd and 4th quarter of the run: {b - a:+.3f} m^2")


if __name__ == "__main__":
    main()
