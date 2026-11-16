"""Mesh-quality summary of a design-list CFD run, read from the logs each case already has.

    python scripts/mesh_quality.py data/designs/screening.csv            # grid2 L1
    python scripts/mesh_quality.py data/designs/screening.csv --level L2

For every case cfd/runs/<list>/<id>_<scheme>_<level> it reads
  log.snappyHexMesh : share of wall faces that got layers, the per-patch layer table
                      (mean layer count of the target 3, and layer thickness as % of the
                      target), illegal faces left at the end;
  log.checkMesh     : max non-orthogonality, max skewness, number of highly skewed faces,
                      failed checks.
The purpose is to see whether the mesh differs between designs enough to explain force
differences that look like noise (both ends of a variable lower than base). It writes
docs/results/mesh_quality_<list>_<scheme>_<level>.md next to the force table.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_designs import read_designs  # noqa: E402

LAYER_PATCHES = ["body", "front_wing", "rear_wing", "wheels_front", "wheels_rear", "helmet", "wake_boards"]


def snappy(log):
    txt = log.read_text(errors="replace")
    out = {}
    ext = re.findall(r"Extruding (\d+) out of (\d+) faces \(([\d.]+)%\)", txt)
    if ext:
        out["extruded_pct"] = float(ext[-1][2])
        out["wall_faces"] = int(ext[-1][1])
    m = re.search(r"Finished meshing with (\d+) illegal faces", txt)
    out["illegal_faces"] = int(m.group(1)) if m else 0
    m = re.search(r"Layer mesh : cells:(\d+)", txt)
    out["cells"] = int(m.group(1)) if m else None
    i = txt.rfind("overall thickness")
    layers = {}
    if i >= 0:
        for line in txt[i:].splitlines()[3:]:
            w = line.split()
            if len(w) < 6:
                break
            layers[w[0]] = dict(faces=int(w[1]), target=int(w[2]), mean=float(w[3]), thick_pct=float(w[5]))
    out["layers"] = layers
    return out


def checkmesh(log):
    txt = log.read_text(errors="replace")
    out = {}
    m = re.search(r"non-orthogonality Max: ([\d.]+) average: ([\d.]+)", txt)
    if m:
        out["nonorth_max"], out["nonorth_avg"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"Max skewness = ([\d.]+)(?:, (\d+) highly skew faces)?", txt)
    if m:
        out["skew_max"] = float(m.group(1))
        out["skew_faces"] = int(m.group(2) or 0)
    m = re.search(r"Failed (\d+) mesh checks", txt)
    out["failed_checks"] = int(m.group(1)) if m else 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs")
    ap.add_argument("--level", default="L1")
    ap.add_argument("--scheme", default="grid2")
    a = ap.parse_args()
    src = ROOT / a.designs
    tag, suffix = src.stem, f"{a.scheme}_{a.level}"
    resdir = ROOT / "docs" / "results" / f"cfd_{tag}_{suffix}"
    rows = {}
    for did, values in read_designs(src):
        case = ROOT / "cfd" / "runs" / tag / f"{did}_{suffix}"
        if not (case / "log.snappyHexMesh").exists():
            continue
        r = dict(values=values, **snappy(case / "log.snappyHexMesh"))
        if (case / "log.checkMesh").exists():
            r.update(checkmesh(case / "log.checkMesh"))
        f = resdir / f"{did}.json"
        if f.exists():
            r["forces"] = json.loads(f.read_text(encoding="utf-8")).get("forces", {})
        rows[did] = r

    base = rows.get("base")
    lines = [f"# 격자 품질: {tag} ({suffix})", "",
             "- 출처: 각 케이스의 `log.snappyHexMesh`(경계층), `log.checkMesh`(품질). `scripts/mesh_quality.py`로 만든다.",
             "- 경계층 %: 벽 면 중 층이 붙은 면의 비율(snappyHexMesh 마지막 Extruding 줄).",
             "- 부품 열: 평균 층 수 / 목표 3층(괄호는 목표 두께 대비 실제 두께 %).",
             "- ΔCL·A는 base 대비 전체 차량 값(힘 표와 같음).", "",
             "| id | 셀 [M] | 경계층 % | 차체 | 앞날개 | 뒷날개 | 앞바퀴 | 뒷바퀴 | 플로어 보드 | 불량 면 | 비직교 최대 [°] | 비틀림 최대 (개수) | ΔCL·A | ΔCD·A |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    show = ["body", "front_wing", "rear_wing", "wheels_front", "wheels_rear", "wake_boards"]
    for did, r in rows.items():
        def lay(p):
            v = r["layers"].get(p)
            return f"{v['mean']:.2f} ({v['thick_pct']:.0f})" if v else ""
        t, bt = r.get("forces", {}).get("total"), (base or {}).get("forces", {}).get("total")
        d = (lambda k: f"{t[k] - bt[k]:+.3f}") if t and bt else (lambda k: "")
        lines.append(f"| {did} | {r['cells'] / 1e6:.3f} | {r.get('extruded_pct', float('nan')):.2f} | "
                     + " | ".join(lay(p) for p in show)
                     + f" | {r['illegal_faces']} | {r.get('nonorth_max', float('nan')):.1f} | "
                       f"{r.get('skew_max', float('nan')):.2f} ({r.get('skew_faces', 0)}) | {d('cla')} | {d('cda')} |")
    out = ROOT / "docs" / "results" / f"mesh_quality_{tag}_{suffix}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (resdir.parent / f"mesh_quality_{tag}_{suffix}.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
