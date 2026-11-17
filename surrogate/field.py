"""Surface-field surrogate: mean Cp on a common surface -> POD -> one GP per mode.

Every case has its own mesh, so its faces differ from the next case's. Each case's Cp is
moved onto the faces of the base case ("projection"), part by part, by nearest face centre.
Sprung parts (body, wings, helmet, halo, wake boards, mirrors) are first taken back to the
car frame (cad.car2026.ground_to_car: undo the ride-height shift and the pitch), so a
ride-height design is compared with the base at the same point of the car, not of the road.
Wheels and suspension are matched in the road frame.

On the common surface the fields of all cases form a matrix; its proper orthogonal
decomposition (SVD with face-area weights) gives a few modes, and a GP (surrogate.gp)
predicts each mode coefficient from the design variables. A predicted field is turned into
forces on a design's own surface: Cp is carried back from the base faces to the design's
faces (nearest centre, same frames) and integrated with the design's face area vectors.
That needs the design's geometry (its CAD, minutes) but no CFD.

Only the pressure (Cp) part of the forces is modelled here; skin friction (Cf) is a later
step. Pressure forces: CL*A = -2 sum(Cp Sf_z), CD*A = 2 sum(Cp Sf_x) (full car, Sf into the car).
"""
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from surrogate.gp import GP

ROOT = Path(__file__).resolve().parents[1]
SPRUNG = {"body", "front_wing", "rear_wing", "helmet", "halo", "wake_boards", "mirrors"}


def load_case(case):
    d = np.load(ROOT / case / "surface_fields.npz")
    return dict(parts=[str(p) for p in d["parts"]], part=d["part"].astype(int),
                centre=d["centre"].astype(float), Sf=d["Sf"].astype(float), cp=d["cp"].astype(float))


def car_frame(c, part_names, part, rh_front_mm, pitch_deg, vector=False):
    """Face centres (or, vector=True, directions) of sprung parts in the car frame; others unchanged."""
    out = c.copy()
    a = math.radians(pitch_deg)
    sel = np.isin(np.array(part_names)[part], list(SPRUNG))
    x, z = c[sel, 0], c[sel, 2] - (0.0 if vector else rh_front_mm / 1000.0)
    out[sel, 0] = x * math.cos(a) + z * math.sin(a)
    out[sel, 2] = -x * math.sin(a) + z * math.cos(a)
    return out


def pressure_forces(cp, Sf):
    F = (cp[:, None] * Sf).sum(0)
    return -2 * F[2], 2 * F[0]


class Surface:
    """A case surface in the frame used for matching (sprung parts in the car frame)."""

    K = 12          # candidates per query for the same-side check
    MIN_DOT = 0.3   # normals closer than ~73 deg count as the same side

    def __init__(self, case_data, rh_front_mm, pitch_deg):
        self.d = case_data
        args = (case_data["parts"], case_data["part"], rh_front_mm, pitch_deg)
        self.xyz = car_frame(case_data["centre"], *args)
        nrm = case_data["Sf"] / np.linalg.norm(case_data["Sf"], axis=1, keepdims=True)
        self.nrm = car_frame(nrm, *args, vector=True)
        self.trees = {}

    def tree(self, name):
        if name not in self.trees:
            k = self.d["parts"].index(name)
            idx = np.flatnonzero(self.d["part"] == k)
            self.trees[name] = (cKDTree(self.xyz[idx]), idx)
        return self.trees[name]

    def pull(self, other, values):
        """Values given on `other`'s faces, carried onto this surface's faces: the nearest
        face centre whose normal looks the same way (so a thin wing's upper surface does not
        pick up the lower surface after the element has rotated); plain nearest if none does."""
        out = np.empty(len(self.xyz))
        for k, name in enumerate(self.d["parts"]):
            mine = np.flatnonzero(self.d["part"] == k)
            t, idx = other.tree(name)
            kk = min(self.K, len(idx))
            dist, j = t.query(self.xyz[mine], k=kk)
            if kk == 1:
                dist, j = dist[:, None], j[:, None]
            dot = np.einsum("ij,ikj->ik", self.nrm[mine], other.nrm[idx[j]])
            dist = np.where(dot >= self.MIN_DOT, dist, np.inf)
            pick = np.argmin(dist, axis=1)
            none = ~np.isfinite(dist[np.arange(len(mine)), pick])
            pick[none] = 0
            out[mine] = values[idx[j[np.arange(len(mine)), pick]]]
        return out


class FieldSurrogate:
    def __init__(self, energy=0.999, max_modes=None):
        self.energy, self.max_modes = energy, max_modes

    def fit(self, X, F, w, base_like, theta=None):
        """X (n, d) scaled inputs, F (n, m) fields on the base surface, w (m,) face areas,
        base_like: indices of the repeat cases used for the per-mode noise."""
        self.mean = F.mean(0)
        sw = np.sqrt(w / w.sum())
        U, s, Vt = np.linalg.svd((F - self.mean) * sw, full_matrices=False)
        e = np.cumsum(s ** 2) / np.sum(s ** 2)
        r = int(np.searchsorted(e, self.energy) + 1)
        if self.max_modes:
            r = min(r, self.max_modes)
        self.modes = Vt[:r] / sw                      # field-space modes
        self.sw = sw
        A = U[:, :r] * s[:r]                           # mode coefficients of each case
        self.energy_kept = float(e[r - 1])
        self.gps = []
        for k in range(r):
            sn = max(float(np.std(A[base_like, k], ddof=1)), 1e-6 * s[0])
            self.gps.append(GP(sn, restarts=3).fit(X, A[:, k], theta=None if theta is None else theta[k]))
        return self

    def predict(self, Xs):
        a = np.column_stack([g.predict(Xs)[0] for g in self.gps])
        return self.mean + a @ self.modes

    def project(self, F):
        """Best reconstruction of given fields with the kept modes (POD truncation error only)."""
        a = ((F - self.mean) * self.sw ** 2) @ (self.modes.T)
        G = (self.modes * self.sw ** 2) @ self.modes.T
        return self.mean + np.linalg.solve(G, a.T).T @ self.modes
