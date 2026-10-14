"""Track geometry: centerline loading, minimum-curvature racing line, curvature."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import osqp
from scipy import sparse
from scipy.interpolate import CubicSpline, splev, splprep
from scipy.ndimage import gaussian_filter1d

TRACK_DIR = Path(__file__).resolve().parents[1] / "data" / "tracks"


@dataclass
class Track:
    name: str
    s: np.ndarray      # arc length along racing line [m]
    x: np.ndarray      # racing line coordinates [m]
    y: np.ndarray
    kappa: np.ndarray  # signed curvature [1/m]
    ds: float          # station spacing [m]
    cx: np.ndarray     # centerline (for plotting)
    cy: np.ndarray

    @property
    def length(self) -> float:
        return self.ds * len(self.s)


def _periodic_spline(x, y):
    """Arc-length parametrised periodic spline through a closed polyline."""
    pts = np.column_stack([x, y])
    pts = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(seg)])
    return CubicSpline(t, pts, bc_type="periodic"), t[-1]


def _resample(x, y, ds):
    spl, L = _periodic_spline(x, y)
    n = int(round(L / ds))
    t = np.linspace(0.0, L, n, endpoint=False)
    p = spl(t)
    return p[:, 0], p[:, 1], spl, t, L / n


def _second_diff(n):
    """Periodic second-difference operator."""
    D = sparse.diags([1.0, -2.0, 1.0], [-1, 0, 1], shape=(n, n), format="lil")
    D[0, n - 1] = 1.0
    D[n - 1, 0] = 1.0
    return D.tocsr()


def min_curvature_offsets(x, y, nx, ny, w_right, w_left, margin):
    """Lateral offsets (positive = left) minimising the summed squared
    second difference of the path, a discrete proxy for curvature."""
    n = len(x)
    D = _second_diff(n)
    A = sparse.vstack([D @ sparse.diags(nx), D @ sparse.diags(ny)]).tocsc()
    b = -np.concatenate([D @ x, D @ y])

    # ||A a - b||^2  ->  1/2 a'Pa + q'a, solved as a sparse box-constrained QP.
    P = (A.T @ A).tocsc()
    q = -(A.T @ b)
    scale = 1.0 / abs(P).max()
    lo = np.minimum(-(w_right - margin), 0.0)
    hi = np.maximum(w_left - margin, 0.0)

    prob = osqp.OSQP()
    prob.setup(sparse.triu(P * scale, format="csc"), q * scale,
               sparse.identity(n, format="csc"), lo, hi,
               eps_abs=1e-9, eps_rel=1e-9, max_iter=200000,
               polish=True, verbose=False)
    return np.clip(prob.solve().x, lo, hi)


def _smooth_centerline(cx, cy, sigma):
    """Periodic smoothing spline; sigma is the expected point noise [m]."""
    tck, _ = splprep([cx, cy], s=len(cx) * sigma ** 2, per=1)
    x, y = splev(np.linspace(0.0, 1.0, len(cx), endpoint=False), tck)
    return np.asarray(x), np.asarray(y)


def load_track(name: str, ds: float = 2.0, margin: float = 0.3,
               racing_line: bool = True, ds_opt: float = 4.0,
               smooth: float = 0.5, kappa_sigma: float = 8.0) -> Track:
    """margin: distance kept between the car's centre and the track edge [m].
    Track widths in the database exclude kerbs, so a value below the car's
    half-width (~1 m) lets the line use them."""
    raw = np.loadtxt(TRACK_DIR / f"{name}.csv", delimiter=",", comments="#")
    cx, cy, wr, wl = raw.T
    if smooth > 0:
        cx, cy = _smooth_centerline(cx, cy, smooth)

    # Racing line is optimised on a coarse grid, then splined to `ds`.
    x, y, spl, t, _ = _resample(cx, cy, ds_opt)
    d = spl(t, 1)
    tx, ty = (d / np.linalg.norm(d, axis=1, keepdims=True)).T
    nx, ny = -ty, tx
    s_raw = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(cx), np.diff(cy)))])
    w_right = np.interp(t, s_raw, wr)
    w_left = np.interp(t, s_raw, wl)

    if racing_line:
        a = min_curvature_offsets(x, y, nx, ny, w_right, w_left, margin)
        x, y = x + a * nx, y + a * ny

    x, y, spl, t, ds_eff = _resample(x, y, ds)
    d1, d2 = spl(t, 1), spl(t, 2)
    kappa = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.hypot(d1[:, 0], d1[:, 1]) ** 3
    if kappa_sigma > 0:
        # A car cannot follow curvature changes much shorter than its own
        # length; this also removes kinks left over from the survey data.
        kappa = gaussian_filter1d(kappa, kappa_sigma / ds_eff, mode="wrap")

    return Track(name=name, s=t, x=x, y=y, kappa=kappa, ds=ds_eff, cx=cx, cy=cy)


def available_tracks():
    return sorted(p.stem for p in TRACK_DIR.glob("*.csv"))
