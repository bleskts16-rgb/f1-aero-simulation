"""Lap-time change of each CFD design, per circuit, with the fitted 2026 lap model.

    python scripts/lap_delta_designs.py data/designs/screening.csv
    python scripts/lap_delta_designs.py data/designs/screening.csv --ref docs/results/cfd_noise_grid2_L1

The CFD car is a simplified model, so its absolute CL*A / CD*A are not those of a real car.
Only the relative change of each design is used: delta = (design - ref) / ref, where ref is
the mean of the base-like cases in --ref (base + tiny-change remeshing-noise cases; the
single base case sits ~0.6 % above that mean). The change is applied to the fitted car of
data/aero_2026.json and a qualifying lap is run on each fitted circuit (lapsim.rules2026).

The CFD is corner mode (Z) only, so two assumptions for straight mode (X) are run:
  zx : the same relative change in X mode, except the flap-angle variables FW2 / RW2
       (in X mode the flaps sit at a fixed open angle, so X is unchanged for them)
  z  : X mode unchanged for every design (lower bound for drag effects on straights)
Lap-time noise: the remeshing noise of the reference cases (sd of CL*A and CD*A) propagated
with the lap model's linear sensitivities; |dT| below 2 sigma is marked as noise level.

Not in the model: aero balance (front/rear split), ride height effects other than aero.
Writes docs/results/lap_<list>_<scheme>_<level>.md / .json and docs/figures/lap_<list>_<level>.png.
"""
import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

FLAP_VARS = {"FW2", "RW2"}


def load_recs(d):
    out = {}
    for f in Path(d).glob("*.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        if r.get("status") == "done":
            out[r["id"]] = r
    return out


def lap(args):
    track, kw = args
    from lapsim import load_track
    from lapsim.rules2026 import Car2026, simulate_2026
    fit = json.loads((ROOT / "data" / "aero_2026.json").read_text(encoding="utf-8"))
    car = Car2026(cla=fit["cla_z"], cda=fit["cda_z"], cla_x=fit["cla_x"], cda_x=fit["cda_x"])
    return simulate_2026(load_track(track), car.with_modes(**kw)).lap_time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs")
    ap.add_argument("--level", default="L1")
    ap.add_argument("--scheme", default="grid2")
    ap.add_argument("--ref", default="docs/results/cfd_noise_grid2_L1",
                    help="folder of base-like result JSONs; their mean is the reference")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    from build_designs import read_designs
    src = ROOT / a.designs
    tag, suffix = src.stem, f"{a.scheme}_{a.level}"
    recs = load_recs(ROOT / "docs" / "results" / f"cfd_{tag}_{suffix}")
    refs = load_recs(ROOT / a.ref)
    rc = np.array([r["forces"]["total"]["cla"] for r in refs.values()])
    rd = np.array([r["forces"]["total"]["cda"] for r in refs.values()])
    ref = dict(cla=rc.mean(), cda=rd.mean(), cla_sd=rc.std(ddof=1), cda_sd=rd.std(ddof=1), n=len(rc))

    fit = json.loads((ROOT / "data" / "aero_2026.json").read_text(encoding="utf-8"))
    sens = json.loads((ROOT / "data" / "aero_sensitivity_2026.json").read_text(encoding="utf-8"))["per_track"]
    tracks = list(fit["tracks"])
    designs = [(d, v) for d, v in read_designs(src) if d in recs and d != "base"]

    jobs, keys = [], []
    for t in tracks:
        jobs.append((t, {})); keys.append((t, "ref", ""))
    for did, values in designs:
        f = recs[did]["forces"]["total"]
        dl, dd = f["cla"] / ref["cla"] - 1, f["cda"] / ref["cda"] - 1
        zx = {"cla": fit["cla_z"] * (1 + dl), "cda": fit["cda_z"] * (1 + dd)}
        z = dict(zx)
        if not (set(values) & FLAP_VARS):
            zx.update(cla_x=fit["cla_x"] * (1 + dl), cda_x=fit["cda_x"] * (1 + dd))
        for t in tracks:
            for mode, kw in (("zx", zx), ("z", z)):
                jobs.append((t, kw)); keys.append((t, did, mode))
    with ProcessPoolExecutor(a.workers) as ex:
        times = list(ex.map(lap, jobs, chunksize=4))
    T = dict(zip(keys, times))

    # 2-sigma lap-time noise per circuit (difference of one case from the reference mean)
    k = np.sqrt(1 + 1 / ref["n"])
    sl, sd = 100 * ref["cla_sd"] / ref["cla"], 100 * ref["cda_sd"] / ref["cda"]
    noise = {}
    for t in tracks:
        s = sens[t]
        noise[t] = 2 * k * np.hypot((s["cla"]["s_per_pct"] + s["cla_x"]["s_per_pct"]) * sl,
                                    (s["cda"]["s_per_pct"] + s["cda_x"]["s_per_pct"]) * sd)

    rows = {}
    for did, values in designs:
        f = recs[did]["forces"]["total"]
        rows[did] = dict(values=values, d_cla_pct=100 * (f["cla"] / ref["cla"] - 1),
                         d_cda_pct=100 * (f["cda"] / ref["cda"] - 1),
                         zx={t: T[(t, did, "zx")] - T[(t, "ref", "")] for t in tracks},
                         z={t: T[(t, did, "z")] - T[(t, "ref", "")] for t in tracks})
    out = dict(reference={k_: float(v) for k_, v in ref.items()}, ref_folder=a.ref,
               ref_lap={t: T[(t, "ref", "")] for t in tracks}, noise_2sigma=noise, designs=rows)
    stem = f"lap_{tag}_{suffix}"
    (ROOT / "docs" / "results" / f"{stem}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    write_md(out, tracks, tag, suffix, stem)
    plot(out, tracks, tag, a.level)
    print(f"docs/results/{stem}.md")


def write_md(out, tracks, tag, suffix, stem):
    ref, noise = out["reference"], out["noise_2sigma"]
    lines = [f"# 설계별 랩타임 변화: {tag} ({suffix})", "",
             f"- 기준: base와 사실상 같은 차 {ref['n']}대(`{out['ref_folder']}`)의 평균 "
             f"CL·A {ref['cla']:.4f}, CD·A {ref['cda']:.4f}. 설계의 상대 변화(%)를 랩 모델의 맞춘 2026 차"
             "(`data/aero_2026.json`)에 곱해 예선 랩을 돌렸다(`lapsim/rules2026.py`).",
             "- 값은 기준 대비 랩타임 변화 [s]. **음수 = 빨라짐.**",
             "- 주 가정(zx): 직선 모드(X)에도 같은 % 변화를 준다. 단 플랩 각 변수(FW2, RW2)는 X 모드 플랩이 고정이라 X는 그대로 둔다.",
             "  하한 가정(z): X 모드는 모든 설계에서 그대로. 표의 마지막 열은 z 가정의 9개 서킷 평균이다.",
             "- `·` 표시: 재메싱 잡음(기준 7대 표준편차를 랩 모델 민감도로 옮긴 2σ)보다 작은 변화. 잡음 크기는 마지막 줄.",
             "- 랩 모델에 없는 것: 앞뒤 다운포스 배분(밸런스), 라이드 하이트의 공력 외 영향. 랩 모델 절대 오차는 RMS 1.3 s지만 여기서는 같은 모델 안의 차이만 본다.", "",
             "| id | 바꾼 값 | ΔCL·A [%] | ΔCD·A [%] | " + " | ".join(tracks) + " | 평균 (zx) | 평균 (z) |",
             "|---|---|---|---|" + "---|" * (len(tracks) + 2)]
    for did, r in out["designs"].items():
        ch = ", ".join(f"{k}={v:g}" for k, v in r["values"].items())
        cells = []
        for t in tracks:
            v = r["zx"][t]
            cells.append(f"{v:+.2f}" + ("·" if abs(v) < noise[t] else ""))
        lines.append(f"| {did} | {ch} | {r['d_cla_pct']:+.1f} | {r['d_cda_pct']:+.1f} | " + " | ".join(cells)
                     + f" | {np.mean(list(r['zx'].values())):+.2f} | {np.mean(list(r['z'].values())):+.2f} |")
    lines.append("| 잡음 2σ | | | | " + " | ".join(f"±{noise[t]:.2f}" for t in tracks) + " | | |")
    lines.append("| 기준 랩 [s] | | | | " + " | ".join(f"{out['ref_lap'][t]:.2f}" for t in tracks) + " | | |")
    (ROOT / "docs" / "results" / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def plot(out, tracks, tag, level):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "font.size": 8, "xtick.direction": "in", "ytick.direction": "in",
                         "mathtext.fontset": "stix"})
    ids = list(out["designs"])
    M = np.array([[out["designs"][d]["zx"][t] for t in tracks] for d in ids])
    lim = np.abs(M).max()
    fig, ax = plt.subplots(figsize=(7.4, 0.24 * len(ids) + 1.4))
    im = ax.imshow(M, cmap="RdBu_r", norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    for i, d in enumerate(ids):
        for j, t in enumerate(tracks):
            v = M[i, j]
            small = abs(v) < out["noise_2sigma"][t]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=6.3,
                    color=("0.55" if small else ("w" if abs(v) > 0.55 * lim else "k")))
    lab = [f"{d}  ({', '.join(f'{k}={v:g}' for k, v in out['designs'][d]['values'].items())})" for d in ids]
    ax.set_yticks(range(len(ids)), lab, fontsize=7)
    ax.set_xticks(range(len(tracks)), tracks, rotation=30, ha="left")
    ax.xaxis.tick_top()
    prev = None
    for i, d in enumerate(ids):
        if prev and d[:2] != prev[:2]:
            ax.axhline(i - 0.5, color="k", lw=0.5)
        prev = d
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label("lap-time change [s]  (+ slower, − faster)")
    ax.set_xlabel("grey numbers: below the 2σ remeshing noise of that circuit", fontsize=7)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / f"lap_{tag}_{level}.png", dpi=200)


if __name__ == "__main__":
    main()
