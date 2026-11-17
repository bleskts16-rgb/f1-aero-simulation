"""Write a space-filling design list (Latin hypercube) over chosen design variables.

    python scripts/make_doe.py doe1 --n 40 --vars RH1 RH2 FW2 RW2 EC2 EC1 SP1 FW5 \
        --range FW2=-4:2 --range EC2=0.85:1.05 --range FW5=0.04:0.07

Variables not listed stay at the G1 v5 baseline. Ranges default to cad/design.py; --range
narrows one (e.g. where a screening endpoint failed the regulation checks). The sample is
an optimised Latin hypercube (scipy.stats.qmc, centred-discrepancy optimisation, fixed seed),
rounded to a step per unit so the values are readable and reproducible.
Writes data/designs/<name>.csv (same columns as the screening list) and prints a summary.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.stats import qmc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STEP = {"deg": 0.1, "mm": 0.5, "-": 0.001}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--vars", nargs="+", required=True)
    ap.add_argument("--range", action="append", default=[], help="ID=lo:hi")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    from cad.design import BY_ID, VARIABLES

    rng = {}
    for v in a.vars:
        rng[v] = [BY_ID[v].lo, BY_ID[v].hi]
    for r in a.range:
        k, lohi = r.split("=")
        rng[k] = [float(x) for x in lohi.split(":")]
    sampler = qmc.LatinHypercube(d=len(a.vars), optimization="random-cd", seed=a.seed)
    U = sampler.random(a.n)
    lo = np.array([rng[v][0] for v in a.vars])
    hi = np.array([rng[v][1] for v in a.vars])
    V = lo + U * (hi - lo)
    for j, v in enumerate(a.vars):
        s = STEP[BY_ID[v].unit]
        V[:, j] = np.clip(np.round(V[:, j] / s) * s, lo[j], hi[j])

    out = ROOT / "data" / "designs" / f"{a.name}.csv"
    ids = [v.id for v in VARIABLES]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id"] + ids)
        for i in range(a.n):
            row = {v: f"{V[i, j]:g}" for j, v in enumerate(a.vars)}
            w.writerow([f"{a.name}_{i + 1:03d}"] + [row.get(k, "") for k in ids])
    print(f"wrote {out.relative_to(ROOT)}: {a.n} designs over {', '.join(a.vars)} (seed {a.seed})")
    for j, v in enumerate(a.vars):
        print(f"  {v:4s} [{lo[j]:g}, {hi[j]:g}] {BY_ID[v].unit:3s} sample min {V[:, j].min():g} max {V[:, j].max():g}")
    print(f"  centred discrepancy {qmc.discrepancy(U):.4f}")


if __name__ == "__main__":
    main()
