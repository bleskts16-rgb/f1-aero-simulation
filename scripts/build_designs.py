"""Build a list of designs and check each one (docs/design_parameters.md §8.2).

A design list is a CSV: an `id` column and one column per design variable (docs ID
such as FW1, or a CarParams field); an empty cell keeps the G1 v5 baseline. Each design
is built like `build_car.py --half --fia` with those values into cad/out/<list>/<id>_half
(STL, STEP, params.json with the design vector), then the regulation and geometry
checks run. A design that fails a check, or whose build fails, is marked and not used
for CFD.

Each design leaves check.json in its folder, and a design that has one is skipped
(--force rebuilds). A lock file lets several workers share one list (memory allows two
on an 8 GB PC; one design takes about 5 min): run one forwards and one with --reverse.
Every worker writes the summary of all checked designs of the list at its end:
docs/results/designs_<list>.md and cad/out/<list>/summary.csv (--report: summary only).

    python scripts/build_designs.py --write-screening data/designs/screening.csv
    python scripts/build_designs.py data/designs/screening.csv [--reverse] [--only FW1_lo FW1_hi]
"""
import argparse
import csv
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cad import design  # noqa: E402


def write_screening(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = [v.id for v in design.VARIABLES]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id"] + ids)
        for name, d in design.screening():
            w.writerow([name] + [d.get(i, "") for i in ids])
    print(f"wrote {path.relative_to(ROOT)} ({len(design.screening())} designs)")


def read_designs(path):
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        did = r.pop("id").strip()
        out.append((did, {k: float(v) for k, v in r.items() if v not in ("", None)}))
    return out


def failures(res):
    bad = [f"{d}: {v}" for d, v, _, ok in res["rows"] if ok is False]
    bad += [f"{c.name}: {c.detail}" for c in res["checks"] if not c.ok]
    return bad


def run_one(did, values, outdir):
    """Build and check one design; returns the check.json record."""
    from build_car import build_and_check, git_source       # imports CadQuery
    changed = ", ".join(f"{k}={v:g}" for k, v in values.items()) or "baseline"
    t0 = time.time()
    try:
        res = build_and_check(design.params(values), outdir, half=True, verbose=False)
        bad, status = failures(res), ("OK" if res["ok"] else "NG")
    except Exception as e:                                  # a build failure is a result too
        bad, status = [f"build error: {type(e).__name__}: {e}"], "ERROR"
        traceback.print_exc()
    src = git_source()
    rec = dict(id=did, changed=changed, status=status, seconds=round(time.time() - t0, 1),
               failures=bad, values=values, commit=src["commit"], dirty=src["dirty"])
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "check.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", nargs="?", help="design list CSV")
    ap.add_argument("--write-screening", metavar="CSV", help="write the 41-design screening list and stop")
    ap.add_argument("--only", nargs="+", help="build only these ids")
    ap.add_argument("--reverse", action="store_true", help="work from the end of the list")
    ap.add_argument("--force", action="store_true", help="rebuild designs that already have check.json")
    ap.add_argument("--report", action="store_true", help="only write the summary of checked designs")
    args = ap.parse_args()
    if args.write_screening:
        write_screening(ROOT / args.write_screening)
        return 0
    if not args.designs:
        ap.error("give a design list CSV (or --write-screening)")

    src = ROOT / args.designs
    tag = src.stem
    outroot = ROOT / "cad" / "out" / tag
    designs = read_designs(src)
    todo = [d for d in designs if not args.only or d[0] in set(args.only)]
    if args.reverse:
        todo = todo[::-1]
    t_all = time.time()
    for i, (did, values) in enumerate([] if args.report else todo, 1):
        outdir = outroot / f"{did}_half"
        if (outdir / "check.json").exists() and not args.force:
            continue
        outdir.mkdir(parents=True, exist_ok=True)
        lock = outdir / ".building"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # another worker has it
        except FileExistsError:
            continue
        os.close(fd)
        try:
            rec = run_one(did, values, outdir)
        finally:
            lock.unlink(missing_ok=True)
        print(f"[{i}/{len(todo)}] {did:<10} {rec['status']:<5} {rec['seconds']:5.0f} s  {rec['changed']}"
              + ("\n      " + "\n      ".join(rec["failures"]) if rec["failures"] else ""), flush=True)

    recs = []
    for did, _ in designs:
        f = outroot / f"{did}_half" / "check.json"
        if f.exists():
            recs.append(json.loads(f.read_text(encoding="utf-8")))
    if not recs:
        print("no checked designs yet")
        return 0
    outroot.mkdir(parents=True, exist_ok=True)
    with (outroot / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "changed", "status", "seconds", "failures"])
        for r in recs:
            w.writerow([r["id"], r["changed"], r["status"], r["seconds"], " | ".join(r["failures"])])
    write_md(tag, src, recs, len(designs))
    n_ok = sum(r["status"] == "OK" for r in recs)
    print(f"{n_ok}/{len(recs)} checked designs pass ({len(designs) - len(recs)} not checked yet); "
          f"this run {(time.time() - t_all) / 60:.0f} min", flush=True)
    return 0


def write_md(tag, src, recs, n_total):
    commits = sorted({r["commit"] + (" (작업 트리 변경 있음)" if r["dirty"] else "") for r in recs})
    lines = [f"# 설계 목록 빌드 검사: {tag}", "",
             f"- 목록: `{src.relative_to(ROOT).as_posix()}` ({n_total}개), 형상: `cad/out/{tag}/<id>_half`",
             f"- 커밋: {', '.join(commits)}",
             "- 판정: 규정 검사(기준 볼륨, 슬롯, 덮음, 형상 규칙, 바퀴 간극)와 형상 QA(로프트 이탈, 양의 부피, 부착, STL 닫힘)를 "
             "모두 통과하면 OK. 계산 실패(ERROR)는 통과가 아니다.", "",
             "| id | 바꾼 값 | 판정 | 시간 [s] | 실패 항목 |", "|---|---|---|---|---|"]
    for r in recs:
        fail = "<br>".join(x.replace("|", "/") for x in r["failures"]) or "–"
        lines.append(f"| {r['id']} | {r['changed']} | {r['status']} | {r['seconds']:.0f} | {fail} |")
    n_ok = sum(r["status"] == "OK" for r in recs)
    lines += ["", f"{n_ok}/{len(recs)} 통과" + (f", {n_total - len(recs)}개 미검사." if len(recs) < n_total else ".")]
    out = ROOT / "docs" / "results" / f"designs_{tag}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
