"""Run CFD for a built design list, one case after another on this PC (WSL).

    python scripts/build_designs.py data/designs/screening.csv            # geometry + checks first
    python scripts/run_designs_cfd.py data/designs/screening.csv --skip FB1_lo FB4_hi
    python scripts/run_designs_cfd.py data/designs/screening.csv --report  # summary only

Only designs whose check.json says OK are run (a design that failed a regulation check
is not CFD data). For each design the case cfd/runs/<list>/<id>_<scheme>_<level> is made
(make_cfd_case.py), meshed and solved (run_cfd.py), then the surface fields are
extracted and checked against the forces (surface_fields.py). The result of each case
goes to docs/results/cfd_<list>_<scheme>_<level>/<id>.json (small, committed), so the
company and home PCs can each run a disjoint part of the list (--only / --reverse) and
commit without conflicts; --report rebuilds the summary table from all the JSON files
present. surface_fields.npz stays in the case folder (not in git).

A failed case is recorded and the next one starts, so the list can run unattended.
Finished cases are skipped; run the same command again to continue.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_designs import read_designs  # noqa: E402
from grid_study import case_result      # noqa: E402

AREF = 1.474


def finished(case):
    t = case / "log.timing"
    if not t.exists():
        return False
    tail = t.read_text().split("simpleFoam end")
    return len(tail) > 1 and "rc=0" in tail[-1].splitlines()[0]


def step_minutes(case):
    """Wall time per Allrun step [min] from log.timing."""
    out, start = {}, {}
    for line in (case / "log.timing").read_text().splitlines():
        w = line.split()
        if len(w) >= 3 and w[1] == "start":
            start[w[0]] = float(w[2])
        elif len(w) >= 3 and w[1] == "end" and w[0] in start:
            out[w[0]] = round((float(w[2]) - start[w[0]]) / 60, 1)
    return out


def stl_md5(geom):
    h = hashlib.md5()
    for f in sorted(geom.glob("*.stl")):
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:12]


def record(did, values, geom, case, a, status, note=""):
    q = 0.5 * 1.2 * a.u ** 2
    rec = dict(id=did, values=values, status=status, note=note, case=case.relative_to(ROOT).as_posix(),
               level=a.level, scheme=a.scheme, iterations=a.iter, np=a.np, u_inf=a.u,
               geometry=geom.relative_to(ROOT).as_posix(), stl_md5=stl_md5(geom),
               commit=json.loads((geom / "check.json").read_text(encoding="utf-8")).get("commit"))
    if status == "done":
        r = case_result(case, q, 1000)
        rec.update(cells=r.get("cells"), iters=r.get("iters"), minutes=step_minutes(case),
                   yplus=r.get("yplus"),
                   forces={k: {kk: round(float(vv), 5) for kk, vv in v.items()}
                           for k, v in r.items() if isinstance(v, dict) and "cla" in v})
        mem = case / "log.mem"
        if mem.exists():
            m = np.loadtxt(mem, comments="#", ndmin=2)
            rec["peak_mem_gb"] = round(float(m[:, 1].max()) / 1024, 2) if len(m) else None
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", help="design list CSV (built with build_designs.py)")
    ap.add_argument("--level", default="L1")
    ap.add_argument("--scheme", default="grid2")
    ap.add_argument("--np", type=int, default=4)
    ap.add_argument("--iter", type=int, default=2000)
    ap.add_argument("--u", type=float, default=50.0)
    ap.add_argument("--only", nargs="+", help="run only these ids")
    ap.add_argument("--skip", nargs="+", default=[], help="ids not to run (e.g. same geometry as base)")
    ap.add_argument("--reverse", action="store_true", help="work from the end of the list")
    ap.add_argument("--report", action="store_true", help="only rewrite the summary")
    a = ap.parse_args()

    src = ROOT / a.designs
    tag = src.stem
    suffix = f"{a.scheme}_{a.level}"
    runs = ROOT / "cfd" / "runs" / tag
    resdir = ROOT / "docs" / "results" / f"cfd_{tag}_{suffix}"
    resdir.mkdir(parents=True, exist_ok=True)
    designs = read_designs(src)
    todo = [d for d in designs if (not a.only or d[0] in a.only) and d[0] not in a.skip]
    if a.reverse:
        todo = todo[::-1]

    for did, values in [] if a.report else todo:
        geom = ROOT / "cad" / "out" / tag / f"{did}_half"
        chk = geom / "check.json"
        if not chk.exists() or json.loads(chk.read_text(encoding="utf-8"))["status"] != "OK":
            continue                           # not built yet, or not a legal design
        case = runs / f"{did}_{suffix}"
        out = resdir / f"{did}.json"
        if out.exists() and json.loads(out.read_text(encoding="utf-8"))["status"] == "done":
            continue
        if (case / ".running").exists():
            print(f"skip {did} (.running: another worker, or a stopped run - delete the file to retry)")
            continue
        if not case.exists():
            subprocess.check_call([sys.executable, str(ROOT / "scripts" / "make_cfd_case.py"),
                                   "--geom", str(geom.relative_to(ROOT)), "--level", a.level,
                                   "--np", str(a.np), "--iter", str(a.iter), "--u", str(a.u),
                                   "--scheme", a.scheme, "--name", case.name,
                                   "--outdir", str(runs.relative_to(ROOT))])
        (case / ".running").write_text(time.strftime("%Y-%m-%d %H:%M"))
        t0 = time.time()
        print(f"=== {did} -> {case.relative_to(ROOT)} ({time.strftime('%m-%d %H:%M')})", flush=True)
        try:
            rc = 0 if finished(case) else subprocess.call(
                [sys.executable, str(ROOT / "scripts" / "run_cfd.py"), str(case.relative_to(ROOT))])
            if rc:
                rec = record(did, values, geom, case, a, "failed", f"run_cfd exit {rc}")
            else:
                rs = subprocess.call([sys.executable, str(ROOT / "scripts" / "surface_fields.py"),
                                      str(case.relative_to(ROOT))])
                rec = record(did, values, geom, case, a, "done",
                             "" if rs == 0 else f"surface_fields exit {rs}")
        finally:
            (case / ".running").unlink(missing_ok=True)
        out.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        f = rec.get("forces", {}).get("total")
        print(f"    {rec['status']} in {(time.time() - t0) / 3600:.1f} h"
              + (f": CL.A {f['cla']:.3f} +- {f['cla_se']:.3f}, CD.A {f['cda']:.3f} +- {f['cda_se']:.3f}" if f else "")
              + (f"  ({rec['note']})" if rec["note"] else ""), flush=True)
        write_report(tag, src, designs, resdir, suffix)
    write_report(tag, src, designs, resdir, suffix)


def write_report(tag, src, designs, resdir, suffix):
    recs = {}
    for f in resdir.glob("*.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        recs[r["id"]] = r
    base = recs.get("base", {}).get("forces", {}).get("total")
    lines = [f"# 설계 목록 CFD: {tag} ({suffix})", "",
             f"- 목록 `{src.relative_to(ROOT).as_posix()}`, 결과 JSON `{resdir.relative_to(ROOT).as_posix()}/<id>.json`, "
             "케이스 `cfd/runs/" + tag + "/<id>_" + suffix + "`",
             "- 값은 전체 차량(반쪽 ×2), 마지막 1000회 평균 ± 자기상관 보정 표준오차, q = 1500 Pa. CL·A는 다운포스 +.",
             "- Δ는 base 대비. 표면장(평균 Cp, Cf)은 각 케이스의 `surface_fields.npz`에 있다(저장소에는 없음).", "",
             "| id | 바꾼 값 | 상태 | 셀 [M] | CL·A | CD·A | ΔCL·A | ΔCD·A | 앞날개 CL·A | 뒷날개 CL·A | 시간 [h] |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for did, values in designs:
        r = recs.get(did)
        if not r:
            continue
        ch = ", ".join(f"{k}={v:g}" for k, v in values.items()) or "baseline"
        f = r.get("forces", {}).get("total")
        if not f:
            lines.append(f"| {did} | {ch} | {r['status']} {r.get('note', '')} | | | | | | | | |")
            continue
        fw = r["forces"].get("front_wing", {}).get("cla")
        rw = r["forces"].get("rear_wing", {}).get("cla")
        d = (lambda k: f"{f[k] - base[k]:+.3f}") if base else (lambda k: "")
        hrs = sum(r.get("minutes", {}).values()) / 60
        lines.append(f"| {did} | {ch} | {r['status']}{' (' + r['note'] + ')' if r.get('note') else ''} "
                     f"| {r['cells'] / 1e6:.2f} | {f['cla']:.3f} ± {f['cla_se']:.3f} | {f['cda']:.3f} ± {f['cda_se']:.3f} "
                     f"| {d('cla')} | {d('cda')} | {fw:.3f} | {rw:.3f} | {hrs:.1f} |")
    n_done = sum(r["status"] == "done" for r in recs.values())
    lines += ["", f"{n_done}/{len(designs)} 완료."]
    out = ROOT / "docs" / "results" / f"cfd_{tag}_{suffix}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
