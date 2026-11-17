"""Re-run the STL closure check of built designs with the current rule (cad/qa.py stl_gaps).

    python scripts/recheck_stl.py data/designs/doe1.csv            # once
    python scripts/recheck_stl.py data/designs/doe1.csv --watch    # until every design is built

Only the "<part>.stl closed" items are re-evaluated, from the STL files already written,
so no geometry is rebuilt. A design whose only failures were STL closure and which now
passes becomes OK; any other failure (regulation, QA) keeps it NG. The original failure
list is kept in check.json as `failures_before_recheck`. --watch repeats every 2 minutes
while builds are still running (a build started before the rule change still writes the
old verdict), and stops once every design has a check.json and no .building lock remains.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_designs import read_designs  # noqa: E402
from cad import qa  # noqa: E402

TAG = "stl_recheck"


def recheck(geom):
    f = geom / "check.json"
    rec = json.loads(f.read_text(encoding="utf-8"))
    if rec.get(TAG) or rec["status"] == "ERROR":
        return None
    keep, changed = [], []
    for msg in rec["failures"]:
        name = msg.split(".stl closed")[0] if ".stl closed" in msg else None
        if name and (geom / f"{name}.stl").exists():
            n_open, n_tri, gap = qa.stl_gaps(geom / f"{name}.stl")
            if gap <= qa.STL_GAP_LIMIT:
                changed.append(f"{name}.stl: {n_open} open edges, largest gap {gap * 1000:.3f} mm -> pass")
                continue
        keep.append(msg)
    rec[TAG] = dict(rule=f"gap <= {qa.STL_GAP_LIMIT * 1000:g} mm", date=time.strftime("%Y-%m-%d %H:%M"),
                    passed=changed)
    if changed:
        rec["failures_before_recheck"] = rec["failures"]
        rec["failures"] = keep
        if rec["status"] == "NG" and not keep:
            rec["status"] = "OK"
    f.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return rec, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs")
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    src = ROOT / a.designs
    root = ROOT / "cad" / "out" / src.stem
    designs = read_designs(src)
    while True:
        for did, _ in designs:
            g = root / f"{did}_half"
            if (g / "check.json").exists() and not (g / ".building").exists():
                r = recheck(g)
                if r and r[1]:
                    print(f"{time.strftime('%H:%M')} {did}: {r[0]['status']}  " + "; ".join(r[1]), flush=True)
        done = all((root / f"{d}_half" / "check.json").exists() for d, _ in designs)
        busy = any((root / f"{d}_half" / ".building").exists() for d, _ in designs)
        if not a.watch or (done and not busy):
            break
        time.sleep(120)


if __name__ == "__main__":
    main()
