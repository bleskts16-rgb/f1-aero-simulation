"""Extract the floor / venturi-tunnel station tables from the vendored
text-to-cad F1 concept car and convert them to this project's conventions.

The reference source is parsed, never executed (it needs the `cadgen` runtime).
Their frame is X forward +, Y left +, origin on the front axle at road level;
ours is X rearward +, Y right +, same origin. So x_ours = -x_ttc, and the
tables (all |Y| on one side) carry over unchanged in Y and Z.

Each table also gets s = x_ours / wheelbase so it can be rescaled from their
3600 mm wheelbase to ours (3400 mm, 2026 regulations).

    python scripts/extract_ttc_reference.py
Output: docs/references/ttc_f1_floor.json, docs/figures/ttc_f1_floor_tables.png
"""
import ast
import json
import operator
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
TTC = ROOT / "third_party" / "text-to-cad"
LIB = TTC / "models" / "f1" / "lib"

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}

# Floor tables worth carrying over: (name, meaning, value unit)
FLOOR_TABLES = [
    ("_HW", "floor plan-form half width", "|Y| mm"),
    ("_KEEL_Y", "flat central keel half width", "|Y| mm"),
    ("_TUNNEL_H", "tunnel-roof crown height above the local keel underside", "mm"),
    ("_KEEL_TOP", "keel top (deck) height", "Z mm"),
    ("_WALL_BOT", "floor-edge wing bottom bead (lowest visible line)", "Z mm"),
    ("_WALL_T", "floor-edge wall thickness", "mm"),
    ("_SHELL_T", "floor shell thickness", "mm"),
]
FLOOR_SCALARS = ["_KEEL_EXIT_Z", "_FENCE_N", "_FENCE_ROOT_CHORD", "_FENCE_LE_X",
                 "_FENCE_F", "_FENCE_BOT_Z", "_FENCE_CAMBER", "_STRAKE_LE_X",
                 "_STRAKE_F", "_STRAKE_EXIT_Z"]
SPEC_SCALARS = ["WHEELBASE", "FLOOR_Z_FRONT", "FLOOR_Z_REAR", "FLOOR_LE_X", "FLOOR_TE_X",
                "FLOOR_HALF_W", "DIFFUSER_START_X", "DIFFUSER_EXIT_Z", "PLANK_W",
                "PLANK_T", "TIRE_OD", "TIRE_W_FRONT", "TIRE_W_REAR"]


def _eval(node, env):
    """Evaluate literals, names and + - * / only."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return env[node.attr]          # spec.X inside part modules
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_eval(e, env) for e in node.elts)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand, env))
    raise ValueError("unsupported")


def constants(path, env=None):
    """Module-level NAME = <simple expression> assignments of a source file."""
    env = dict(env or {})
    out = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            tgt, val = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            tgt, val = node.target.id, node.value
        else:
            continue
        try:
            env[tgt] = out[tgt] = _eval(val, env)
        except (ValueError, KeyError, TypeError, ZeroDivisionError):
            pass
    return out


def main():
    sha = (TTC / ".pinned_sha").read_text().strip()
    spec = constants(LIB / "spec.py")
    floor = constants(LIB / "floor.py", spec)
    wb = spec["WHEELBASE"]

    tables = {}
    for name, meaning, unit in FLOOR_TABLES:
        rows = [(-x, v) for x, v in floor[name]]          # x_ours = -x_ttc
        tables[name.strip("_").lower()] = {
            "meaning": meaning, "unit": unit,
            "x_mm": [r[0] for r in rows],
            "s": [round(r[0] / wb, 5) for r in rows],
            "value": [r[1] for r in rows],
        }

    def conv(k, v):
        # station tables / single stations along X flip sign; others are kept
        return tuple(-x for x in v) if k.endswith("_X") and isinstance(v, tuple) else v

    out = {
        "source": {
            "repo": "https://github.com/earthtojake/text-to-cad",
            "commit": sha, "path": "models/f1/src/lib/floor.py, spec.py",
            "license": "MIT (third_party/text-to-cad/LICENSE)",
        },
        "conventions": "x_mm: from front axle, rearward + (ours); s = x_mm / wheelbase_ref; "
                       "Y values are |Y| on one side; Z from the road",
        "wheelbase_ref_mm": wb,
        "spec": {k: (-spec[k] if k.endswith("_X") else spec[k]) for k in SPEC_SCALARS if k in spec},
        "floor_scalars": {k.strip("_").lower(): conv(k, floor[k])
                          for k in FLOOR_SCALARS if k in floor},
        "floor_tables": tables,
    }
    dst = ROOT / "docs" / "references" / "ttc_f1_floor.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"saved {dst.relative_to(ROOT)}  ({len(tables)} tables, commit {sha[:7]})")
    plot(out, ROOT / "docs" / "figures" / "ttc_f1_floor_tables.png")


def plot(data, path):
    plt.rcParams.update({"font.family": "serif", "xtick.direction": "in",
                         "ytick.direction": "in", "xtick.top": True, "ytick.right": True,
                         "axes.linewidth": 0.8, "font.size": 9})
    navy, red, grey = "#1f3a68", "#a23b3b", "#7a7a7a"
    t = data["floor_tables"]
    sp = data["spec"]
    fig, (a0, a1) = plt.subplots(2, 1, figsize=(7.2, 6.0), sharex=True)

    a0.plot(t["hw"]["s"], t["hw"]["value"], "-o", color=navy, ms=3, lw=1.1,
            label="floor half width")
    a0.plot(t["keel_y"]["s"], t["keel_y"]["value"], "-s", color=red, ms=3, lw=1.1,
            label="keel half width (tunnel inner wall)")
    a0.set_ylabel(r"$|Y|$ [mm]")
    a0.legend(frameon=False, loc="lower center")

    a1.plot(t["tunnel_h"]["s"], t["tunnel_h"]["value"], "-o", color=navy, ms=3, lw=1.1,
            label="tunnel roof above keel underside")
    a1.plot(t["wall_bot"]["s"], t["wall_bot"]["value"], "-s", color=red, ms=3, lw=1.1,
            label="floor-edge bottom bead (Z)")
    a1.set_ylabel("height [mm]")
    a1.set_xlabel(r"$s = x / L_\mathrm{wb}$  (0 = front axle, 1 = rear axle)")
    a1.legend(frameon=False, loc="upper left")

    wb = data["wheelbase_ref_mm"]
    for ax in (a0, a1):
        for x, lbl in ((sp["FLOOR_LE_X"], "floor LE"), (sp["DIFFUSER_START_X"], "diffuser")):
            ax.axvline(x / wb, color=grey, lw=0.6, ls="--")
            ax.text(x / wb, ax.get_ylim()[1], f" {lbl}", va="top", fontsize=7, color=grey)
        ax.axvline(1.0, color=grey, lw=0.6, ls=":")
    sha = data["source"]["commit"][:7]
    fig.suptitle(f"text-to-cad F1 floor station tables (commit {sha}), project frame",
                 fontsize=9)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    print(f"saved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
