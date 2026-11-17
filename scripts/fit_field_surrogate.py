"""Fit and validate the surface-pressure surrogate (surrogate/field.py).

    python scripts/fit_field_surrogate.py                    # screening + noise, grid2 L1
    python scripts/fit_field_surrogate.py --energy 0.995

Steps
 1. Cp of every finished case is projected onto the base surface (sprung parts in the car frame).
 2. Projection check: the projected field is carried back to the case's own faces and
    integrated; the gap to the case's true pressure force is the floor of this method.
 3. POD of the projected fields (area-weighted) and a GP per mode coefficient.
 4. Leave-one-out: each case is removed, POD + GPs are refitted on the rest, its field is
    predicted, carried to its own faces and integrated (pressure CL*A, CD*A).
Writes docs/results/surrogate_field_<scheme>_<level>.md and docs/figures/surrogate_field_*.png;
the fitted basis goes to cfd/runs/surrogate/field_cp_<scheme>_<level>.npz (large, not in git).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from surrogate.data import load  # noqa: E402
from surrogate.field import FieldSurrogate, Surface, load_case, pressure_forces  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lists", nargs="+", default=["screening", "noise"])
    ap.add_argument("--scheme", default="grid2")
    ap.add_argument("--level", default="L1")
    ap.add_argument("--energy", type=float, default=0.99)
    a = ap.parse_args()
    from cad.design import params

    data = load(a.lists, a.scheme, a.level)
    ids, X, n = data["id"], data["X"], len(data["id"])
    base_like = [i for i, (l, d) in enumerate(zip(data["list"], ids)) if l != "screening" or d == "base"]
    surf, truth = [], []
    for i in range(n):
        p = params(data["values"][i])
        cd = load_case(data["case"][i])
        surf.append(Surface(cd, p.ride_height_front, p.pitch_deg))
        truth.append(pressure_forces(cd["cp"], cd["Sf"]))
    truth = np.array(truth)
    ib = ids.index("base")
    bs = surf[ib]
    w = np.linalg.norm(bs.d["Sf"], axis=1)
    F = np.array([bs.pull(surf[i], surf[i].d["cp"]) for i in range(n)])
    print(f"{n} cases projected onto {F.shape[1]} base faces", flush=True)

    def to_case(i, field):
        return pressure_forces(surf[i].pull(bs, field), surf[i].d["Sf"])

    roundtrip = np.array([to_case(i, F[i]) for i in range(n)])

    full = FieldSurrogate(a.energy).fit(X, F, w, base_like)
    print(f"POD: {len(full.gps)} modes keep {100 * full.energy_kept:.2f} % of the field variance", flush=True)
    s = np.linalg.svd((F - F.mean(0)) * np.sqrt(w / w.sum()), compute_uv=False)
    spectrum = (np.cumsum(s ** 2) / np.sum(s ** 2)).tolist()

    loo, loo_rms, nmodes = np.empty((n, 2)), np.empty(n), []
    for i in range(n):
        keep = np.arange(n) != i
        bl = [j - (j > i) for j in base_like if j != i]
        m = FieldSurrogate(a.energy).fit(X[keep], F[keep], w, bl)
        nmodes.append(len(m.gps))
        Fi = m.predict(X[i:i + 1])[0]
        loo[i] = to_case(i, Fi)
        loo_rms[i] = np.sqrt(np.sum(w * (Fi - F[i]) ** 2) / w.sum())
        print(f"  LOO {ids[i]:14s} CL.A_p {truth[i, 0]:.3f} -> {loo[i, 0]:.3f}   CD.A_p {truth[i, 1]:.3f} -> "
              f"{loo[i, 1]:.3f}   field rms {loo_rms[i]:.4f}", flush=True)

    out_dir = ROOT / "cfd" / "runs" / "surrogate"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{a.scheme}_{a.level}"
    np.savez_compressed(out_dir / f"field_cp_{tag}.npz", mean=full.mean.astype(np.float32),
                        modes=full.modes.astype(np.float32), X=X,
                        theta=np.array([g.theta for g in full.gps]), noise=np.array([g.noise_sd for g in full.gps]),
                        base_case=data["case"][ib])
    res = dict(ids=ids, list=data["list"], truth=truth.tolist(), roundtrip=roundtrip.tolist(), loo=loo.tolist(),
               loo_field_rms=loo_rms.tolist(), loo_modes=nmodes, energy=a.energy, spectrum=spectrum,
               n_modes=len(full.gps))
    (ROOT / "docs" / "results" / f"surrogate_field_{tag}.json").write_text(
        json.dumps(res, indent=1), encoding="utf-8", newline="\n")
    write_md(res, tag, base_like)
    plot(res, data, F, bs, X, a, base_like, w)


def write_md(r, tag, base_like):
    ids = r["ids"]
    T, R, L = map(np.array, (r["truth"], r["roundtrip"], r["loo"]))
    bl = np.array(base_like)
    sd = T[bl].std(0, ddof=1)
    oth = [i for i in range(len(ids)) if i not in base_like]
    def rms(e, s):
        return np.sqrt(np.mean(e[s] ** 2, axis=0))
    lines = [f"# 표면장(Cp) 서로게이트 검증: {tag}", "",
             "- 방법: 각 케이스의 평균 Cp를 base 표면으로 옮기고(차체·날개는 차체 좌표에서), 면적 가중 POD 후 모드 계수마다 GP를 맞췄다(`surrogate/field.py`).",
             "  예측한 Cp는 그 설계 자신의 표면으로 다시 옮겨 적분한다(그 설계의 CAD는 필요, CFD는 불필요).",
             "- 힘은 **압력 성분만**이다(마찰 Cf는 다음 단계). 전체 차량 값.",
             f"- POD: 데이터 전체로 {r['n_modes']}개 모드가 분산의 {100 * r['energy']:.0f} % 이상을 담는다. "
             f"모드 5/10/20개의 누적: {100 * r['spectrum'][4]:.1f} / {100 * r['spectrum'][9]:.1f} / {100 * r['spectrum'][min(19, len(r['spectrum']) - 1)]:.1f} %.",
             "", "## 오차 요약 (RMS, m²)", "",
             "| 항목 | 압력 CL·A | 압력 CD·A |", "|---|---|---|",
             f"| base 계열 7대의 표준편차(잡음) | {sd[0]:.4f} | {sd[1]:.4f} |",
             f"| 투영 왕복 오차(모든 케이스, 방법 자체의 한계) | {rms(R - T, slice(None))[0]:.4f} | {rms(R - T, slice(None))[1]:.4f} |",
             f"| LOO 오차, base 계열 | {rms(L - T, bl)[0]:.4f} | {rms(L - T, bl)[1]:.4f} |",
             f"| LOO 오차, 스크리닝 설계 | {rms(L - T, oth)[0]:.4f} | {rms(L - T, oth)[1]:.4f} |",
             "", "## 케이스별", "",
             "| id | 압력 CL·A CFD | 왕복 | LOO 예측 | 압력 CD·A CFD | 왕복 | LOO 예측 | Cp 장 RMS 오차 |",
             "|---|---|---|---|---|---|---|---|"]
    for i, d in enumerate(ids):
        lines.append(f"| {d} | {T[i, 0]:.3f} | {R[i, 0]:.3f} | {L[i, 0]:.3f} | {T[i, 1]:.3f} | {R[i, 1]:.3f} | {L[i, 1]:.3f} "
                     f"| {r['loo_field_rms'][i]:.4f} |")
    (ROOT / "docs" / "results" / f"surrogate_field_{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                                                          newline="\n")


def plot(r, data, F, bs, X, a, base_like, w):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "font.size": 8, "xtick.direction": "in", "ytick.direction": "in",
                         "xtick.top": True, "ytick.right": True, "mathtext.fontset": "stix"})
    ids = r["ids"]
    T, L = np.array(r["truth"]), np.array(r["loo"])
    # parity of pressure forces
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 3.4))
    for ax, k, name in ((axs[0], 0, r"pressure $C_LA$"), (axs[1], 1, r"pressure $C_DA$")):
        for sel, c, lab in ((base_like, "0.45", "base-like"),
                            ([i for i in range(len(ids)) if i not in base_like], "#1f3a68", "screening")):
            ax.plot(T[sel, k], L[sel, k], "o", ms=3.5, color=c, label=lab)
        lo, hi = min(T[:, k].min(), L[:, k].min()), max(T[:, k].max(), L[:, k].max())
        pad = 0.05 * (hi - lo)
        ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "k-", lw=0.6)
        ax.set_xlim(lo - pad, hi + pad); ax.set_ylim(lo - pad, hi + pad); ax.set_aspect("equal")
        ax.set_xlabel(f"CFD {name} [m$^2$]"); ax.set_ylabel(f"field-surrogate LOO {name} [m$^2$]")
    axs[0].legend(frameon=False, fontsize=7)
    fig.suptitle("Cp-field surrogate (POD + GP), leave-one-out, integrated on each design's own surface", fontsize=8)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / f"surrogate_field_parity_{a.level}.png", dpi=200)

    # underbody view of the largest-effect design: CFD dCp vs LOO-predicted dCp
    i = ids.index("EC2_lo") if "EC2_lo" in ids else int(np.argmax(np.abs(T[:, 0] - T[ids.index('base'), 0])))
    keep = np.arange(len(ids)) != i
    bl = [j - (j > i) for j in base_like if j != i]
    m = FieldSurrogate(a.energy).fit(X[keep], F[keep], w, bl)
    pred = m.predict(X[i:i + 1])[0]
    ib = ids.index("base")
    xyz, part = bs.xyz, np.array(bs.d["parts"])[bs.d["part"]]
    sel = (part == "body") & (xyz[:, 2] < 0.12)                    # floor and diffuser underside
    sel &= bs.d["Sf"][:, 2] > 0                                    # faces looking down (Sf into the car = +Z)
    d_true, d_pred = F[i] - F[ib], pred - F[ib]
    lim = np.percentile(np.abs(d_true[sel]), 98)
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 3.0), sharey=True)
    for ax, d, title in ((axs[0], d_true, f"CFD  {ids[i]} − base"), (axs[1], d_pred, f"surrogate (LOO)  {ids[i]} − base")):
        sc = ax.scatter(xyz[sel, 0], xyz[sel, 1], c=d[sel], s=0.4, cmap="RdBu_r", norm=TwoSlopeNorm(0, -lim, lim),
                        rasterized=True)
        ax.set_title(title, fontsize=8); ax.set_xlabel("X car frame [m] (rearward +)"); ax.set_aspect("equal")
    axs[0].set_ylabel("Y [m]")
    cb = fig.colorbar(sc, ax=axs, fraction=0.025, pad=0.02)
    cb.set_label(r"$\Delta C_p$ (negative = more suction)")
    fig.suptitle("Underbody (floor and diffuser), view from below, half car", fontsize=8)
    fig.savefig(ROOT / "docs" / "figures" / f"surrogate_field_underbody_{a.level}.png", dpi=200, bbox_inches="tight")


if __name__ == "__main__":
    main()
