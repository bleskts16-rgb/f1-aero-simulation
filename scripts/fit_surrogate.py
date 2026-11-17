"""Fit the scalar aero surrogate (GP per output) and validate it by leave-one-out.

    python scripts/fit_surrogate.py                       # screening + noise lists, grid2 L1
    python scripts/fit_surrogate.py --lists screening noise doe1

For each output (total CL*A, CD*A and the part values in surrogate/data.py) a GP is fitted
on all finished cases with the noise fixed at the sd of the base-like cases. Validation is
true leave-one-out: each case is removed, the hyperparameters are refitted, and the case
is predicted. Each left-out case is labelled by what the rest of the data knows about the
variable it changes:
  base-like  : base and the tiny-change noise cases
  two-sided  : the other end of the same variable is still in the data
  one-sided  : no other case moves this variable (a pure extrapolation from the prior)
With one-variable-at-a-time data the one-sided cases cannot be predicted; what matters
there is whether the predicted uncertainty says so (z = error / sd within about +-2).

Writes data/surrogate/scalar_<scheme>_<level>.json (model), docs/results/surrogate_scalar_<scheme>_<level>.md,
docs/figures/surrogate_parity_<level>.png and docs/figures/surrogate_slices_<level>.png.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from surrogate.data import IDS, TARGETS, load, noise_sd  # noqa: E402
from surrogate.gp import GP  # noqa: E402

LABELS = {"cla": "CL·A", "cda": "CD·A", "fw_cla": "앞날개 CL·A", "rw_cla": "뒷날개 CL·A",
          "body_cla": "차체 CL·A", "wheels_cla": "바퀴 CL·A", "body_cda": "차체 CD·A", "wheels_cda": "바퀴 CD·A"}


def kind(data, i):
    if data["list"][i] != "screening" or data["id"][i] == "base":
        return "base-like"
    moved = set(data["values"][i])
    others = [j for j in range(len(data["id"])) if j != i and data["list"][j] == "screening"
              and set(data["values"][j]) & moved]
    return "two-sided" if others else "one-sided"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lists", nargs="+", default=["screening", "noise"])
    ap.add_argument("--scheme", default="grid2")
    ap.add_argument("--level", default="L1")
    ap.add_argument("--targets", nargs="+", default=list(TARGETS))
    a = ap.parse_args()

    data = load(a.lists, a.scheme, a.level)
    X, n = data["X"], len(data["id"])
    kinds = [kind(data, i) for i in range(n)]
    print(f"{n} cases: " + ", ".join(f"{k} {kinds.count(k)}" for k in ("base-like", "two-sided", "one-sided")))
    model, val = {}, {}
    for t in a.targets:
        y = data["Y"][t]
        sn = noise_sd(data, t)
        gp = GP(sn).fit(X, y)
        mu, sd = np.empty(n), np.empty(n)
        for i in range(n):                                    # true LOO with refitted hyperparameters
            keep = np.arange(n) != i
            g = GP(sn, restarts=4).fit(X[keep], y[keep])
            m, s = g.predict(X[i:i + 1], noise=True)
            mu[i], sd[i] = m[0], s[0]
        model[t] = dict(gp.params(), theta=gp.theta.tolist())
        val[t] = dict(y=y.tolist(), loo_mu=mu.tolist(), loo_sd=sd.tolist(), noise_sd=sn)
        e = mu - y
        print(f"{t:11s} noise {sn:.4f}  LOO rmse " + "  ".join(
            f"{k} {np.sqrt(np.mean(e[[j for j in range(n) if kinds[j] == k]] ** 2)):.4f}"
            for k in ("base-like", "two-sided", "one-sided")), flush=True)

    out = dict(lists=a.lists, scheme=a.scheme, level=a.level, ids=data["id"], vars=IDS,
               X=X.tolist(), kinds=kinds, model=model, validation=val)
    (ROOT / "data" / "surrogate").mkdir(parents=True, exist_ok=True)
    tag = f"{a.scheme}_{a.level}"
    (ROOT / "data" / "surrogate" / f"scalar_{tag}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    write_md(out, tag)
    plot_parity(out, a.level)
    plot_slices(out, data, a.level)


def write_md(out, tag):
    kinds = out["kinds"]
    lines = [f"# 값 서로게이트 (GP) 검증: {tag}", "",
             f"- 학습 데이터: {', '.join(out['lists'])} 목록의 완료 케이스 {len(kinds)}개"
             f"(base 계열 {kinds.count('base-like')}, 양쪽 {kinds.count('two-sided')}, 한쪽 {kinds.count('one-sided')}).",
             "- 모델: 출력마다 GP 하나(`surrogate/gp.py`). 커널 = 선형 + Matern 5/2(변수별 길이) + 고정 잡음.",
             "  잡음 σ는 base 계열 7대의 표준편차(재메싱 잡음 시험)로 고정했다.",
             "- 검증: 진짜 leave-one-out(케이스 하나를 빼고 하이퍼파라미터까지 다시 맞춘 뒤 그 케이스를 예측).",
             "  - base 계열: base와 미세 변경 케이스",
             "  - 양쪽: 같은 변수의 반대쪽 끝이 데이터에 남아 있는 케이스(기울기는 알지만 빠진 쪽은 여전히 외삽)",
             "  - 한쪽: 그 변수를 움직인 다른 케이스가 없는 경우(외삽, 사전분포만으로 예측)",
             "- RMSE가 잡음 σ와 비슷하면 잡음 수준까지 맞춘 것이다. |z| = |오차| / 예측 σ 가 2 이하인 비율이 약 95 %면 불확실성이 정직하다.", "",
             "| 출력 | 잡음 σ | RMSE base 계열 | RMSE 양쪽 | RMSE 한쪽 | |z|≤2 비율 (전체) | |z|≤2 비율 (한쪽) |",
             "|---|---|---|---|---|---|---|"]
    for t, v in out["validation"].items():
        y, mu, sd = map(np.array, (v["y"], v["loo_mu"], v["loo_sd"]))
        e, z = mu - y, np.abs(mu - y) / sd
        def rm(k):
            s = [i for i, kk in enumerate(kinds) if kk == k]
            return f"{np.sqrt(np.mean(e[s] ** 2)):.4f}" if s else ""
        one = [i for i, kk in enumerate(kinds) if kk == "one-sided"]
        lines.append(f"| {LABELS[t]} | {v['noise_sd']:.4f} | {rm('base-like')} | {rm('two-sided')} | {rm('one-sided')} "
                     f"| {100 * np.mean(z <= 2):.0f} % | {100 * np.mean(z[one] <= 2):.0f} % |")
    lines += ["", "## 케이스별 LOO (CL·A, CD·A)", "",
              "| id | 종류 | CL·A CFD | CL·A 예측 ± σ | z | CD·A CFD | CD·A 예측 ± σ | z |", "|---|---|---|---|---|---|---|---|"]
    vc, vd = out["validation"]["cla"], out["validation"]["cda"]
    for i, did in enumerate(out["ids"]):
        zc = (vc["loo_mu"][i] - vc["y"][i]) / vc["loo_sd"][i]
        zd = (vd["loo_mu"][i] - vd["y"][i]) / vd["loo_sd"][i]
        lines.append(f"| {did} | {kinds[i]} | {vc['y'][i]:.3f} | {vc['loo_mu'][i]:.3f} ± {vc['loo_sd'][i]:.3f} | {zc:+.1f} "
                     f"| {vd['y'][i]:.3f} | {vd['loo_mu'][i]:.3f} ± {vd['loo_sd'][i]:.3f} | {zd:+.1f} |")
    (ROOT / "docs" / "results" / f"surrogate_scalar_{tag}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "font.size": 8, "xtick.direction": "in", "ytick.direction": "in",
                         "xtick.top": True, "ytick.right": True, "mathtext.fontset": "stix"})
    return plt


def plot_parity(out, level):
    plt = _style()
    col = {"base-like": "0.45", "two-sided": "#1f3a68", "one-sided": "#9b2d2d"}
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 3.4))
    for ax, t, name in ((axs[0], "cla", r"$C_LA$ [m$^2$]"), (axs[1], "cda", r"$C_DA$ [m$^2$]")):
        v = out["validation"][t]
        y, mu, sd = map(np.array, (v["y"], v["loo_mu"], v["loo_sd"]))
        for k, c in col.items():
            s = [i for i, kk in enumerate(out["kinds"]) if kk == k]
            ax.errorbar(y[s], mu[s], yerr=2 * sd[s], fmt="o", ms=3.5, color=c, ecolor=c, elinewidth=0.6,
                        capsize=1.5, label=k)
        lo, hi = min(y.min(), mu.min()), max(y.max(), mu.max())
        pad = 0.05 * (hi - lo)
        ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "k-", lw=0.6)
        for f in (-2, 2):
            ax.plot([lo - pad, hi + pad], [lo - pad + f * v["noise_sd"], hi + pad + f * v["noise_sd"]],
                    "k:", lw=0.5)
        ax.set_xlim(lo - pad, hi + pad); ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlabel(f"CFD {name}"); ax.set_ylabel(f"leave-one-out prediction {name}")
        ax.set_aspect("equal")
    axs[0].legend(frameon=False, fontsize=7, loc="upper left")
    fig.suptitle("Scalar GP surrogate, leave-one-out (bars ±2σ predictive, dotted ±2σ CFD noise)", fontsize=8)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / f"surrogate_parity_{level}.png", dpi=200)


def plot_slices(out, data, level):
    """1-D slices through the baseline along each variable (others at baseline)."""
    from surrogate.data import SPAN, X0
    from cad.design import VARIABLES
    plt = _style()
    X = np.array(out["X"])
    fig, axs = plt.subplots(4, 5, figsize=(9.0, 6.6), sharey=True)
    for t, c in (("cla", "#1f3a68"), ("cda", "#9b2d2d")):
        m = out["model"][t]
        g = GP(m["noise_sd"]).fit(X, np.array(out["validation"][t]["y"]), theta=np.array(m["theta"]))
        base = g.predict(np.zeros((1, X.shape[1])))[0][0]
        for j, (ax, v) in enumerate(zip(axs.flat, VARIABLES)):
            s = np.linspace((v.lo - X0[j]) / SPAN[j], (v.hi - X0[j]) / SPAN[j], 41)
            Xs = np.zeros((len(s), X.shape[1])); Xs[:, j] = s
            mu, sd = g.predict(Xs)
            xv = X0[j] + s * SPAN[j]
            ax.plot(xv, mu - base, color=c, lw=1.0)
            ax.fill_between(xv, mu - base - 2 * sd, mu - base + 2 * sd, color=c, alpha=0.15, lw=0)
            on = [i for i in range(len(X)) if np.allclose(np.delete(X[i], j), 0, atol=1e-9)]
            yv = np.array(out["validation"][t]["y"])
            ax.plot(X0[j] + X[on, j] * SPAN[j], yv[on] - base, "o", ms=2.5, color=c)
            ax.axhline(0, color="k", lw=0.4)
            ax.set_title(f"{v.id} [{v.unit}]", fontsize=8)
    for ax in axs[:, 0]:
        ax.set_ylabel(r"$\Delta$ from base [m$^2$]")
    axs.flat[0].plot([], [], color="#1f3a68", label=r"$C_LA$"); axs.flat[0].plot([], [], color="#9b2d2d", label=r"$C_DA$")
    axs.flat[0].legend(frameon=False, fontsize=7)
    fig.suptitle("GP slices through the baseline (mean ±2σ of the latent function; dots = CFD on that axis)", fontsize=8)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / f"surrogate_slices_{level}.png", dpi=200)


if __name__ == "__main__":
    main()
