"""Training data for the aero surrogates: design vectors and CFD results of finished cases.

A design list (data/designs/<list>.csv) and its results (docs/results/cfd_<list>_<scheme>_<level>/)
give one sample per finished case. Inputs are all 20 design variables, scaled as
(x - baseline) / (hi - lo), so the baseline is the origin and each range has length 1.
The same case can appear in several lists (the noise list holds a copy of the screening
base), so samples are de-duplicated by case folder.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from cad.design import BASE, VARIABLES, vector  # noqa: E402

IDS = [v.id for v in VARIABLES]
X0 = np.array([vector(BASE)[i] for i in IDS])
SPAN = np.array([v.hi - v.lo for v in VARIABLES])

# surrogate outputs: name -> (force group, coefficient)
TARGETS = {
    "cla": ("total", "cla"), "cda": ("total", "cda"),
    "fw_cla": ("front_wing", "cla"), "rw_cla": ("rear_wing", "cla"),
    "body_cla": ("body", "cla"), "wheels_cla": ("wheels", "cla"),
    "body_cda": ("body", "cda"), "wheels_cda": ("wheels", "cda"),
}


def scale(design):
    """Scaled input vector of a design {ID: value}; missing variables stay at baseline."""
    x = X0.copy()
    for k, v in design.items():
        x[IDS.index(k)] = float(v)
    return (x - X0) / SPAN


def unscale(xs):
    return X0 + np.asarray(xs) * SPAN


def load(lists=("screening", "noise"), scheme="grid2", level="L1"):
    """Samples of the given design lists: dict with id, list, values, X (n, 20), Y {target: (n,)}."""
    from build_designs import read_designs
    out = dict(id=[], list=[], values=[], case=[], X=[], Y={t: [] for t in TARGETS})
    for name in lists:
        res = ROOT / "docs" / "results" / f"cfd_{name}_{scheme}_{level}"
        for did, values in read_designs(ROOT / "data" / "designs" / f"{name}.csv"):
            f = res / f"{did}.json"
            if not f.exists():
                continue
            r = json.loads(f.read_text(encoding="utf-8"))
            if r.get("status") != "done" or r["case"] in out["case"]:
                continue
            out["id"].append(did if name == lists[0] else f"{name}:{did}")
            out["list"].append(name)
            out["values"].append(values)
            out["case"].append(r["case"])
            out["X"].append(scale(values))
            for t, (g, c) in TARGETS.items():
                out["Y"][t].append(r["forces"][g][c])
    out["X"] = np.array(out["X"])
    out["Y"] = {t: np.array(v) for t, v in out["Y"].items()}
    return out


def noise_sd(data, target, base_like_list="noise"):
    """Remeshing + averaging noise of a target: sd over the base-like cases (the noise list,
    which includes the base case)."""
    sel = [i for i, (l, d) in enumerate(zip(data["list"], data["id"]))
           if l == base_like_list or d == "base"]
    return float(np.std(data["Y"][target][sel], ddof=1))
