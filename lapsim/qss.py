"""Quasi-steady-state (QSS) lap time solver for a point-mass car.

1. Cornering limit: highest speed at each station where the lateral demand
   m v^2 |kappa| fits inside the tyre's lateral capacity (aero-loaded).
2. Forward pass: accelerate under power / traction limits, friction ellipse.
3. Backward pass: brake under the friction ellipse, drag helps.
4. Speed = min of the three; lap time = sum(ds / v).
"""
from dataclasses import dataclass

import numpy as np

from .track import Track
from .vehicle import Vehicle


@dataclass
class LapResult:
    track: Track
    vehicle: Vehicle
    v: np.ndarray        # speed [m/s]
    ax: np.ndarray       # longitudinal acceleration [m/s^2]
    ay: np.ndarray       # lateral acceleration [m/s^2]
    v_corner: np.ndarray
    lap_time: float

    @property
    def top_speed_kph(self):
        return self.v.max() * 3.6

    @property
    def min_speed_kph(self):
        return self.v.min() * 3.6

    @property
    def full_throttle_frac(self):
        """Fraction of distance spent accelerating at the power limit."""
        return float(np.mean(self.ax > 0.05))


def corner_speed(veh: Vehicle, kappa: np.ndarray, iters: int = 60) -> np.ndarray:
    """Vectorised bisection for the lateral grip-limited speed."""
    k = np.abs(kappa)
    lo = np.zeros_like(k)
    hi = np.full_like(k, veh.v_max)

    def margin(v):
        fz = veh.normal_load(v)
        return veh.mu_y * veh.mu_scale(fz) * fz - veh.mass * v * v * k

    ok_at_max = margin(hi) >= 0.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        good = margin(mid) >= 0.0
        lo = np.where(good, mid, lo)
        hi = np.where(good, hi, mid)
    return np.where(ok_at_max, veh.v_max, lo)


def _long_capacity(veh: Vehicle, v, kappa, mu):
    """Remaining longitudinal force after lateral demand (friction ellipse)."""
    fz = veh.normal_load(v)
    scale = veh.mu_scale(fz)
    fy_max = veh.mu_y * scale * fz
    use = np.minimum(veh.mass * v * v * abs(kappa) / fy_max, 1.0)
    return mu * scale * fz * np.sqrt(1.0 - use * use), fz


def _resistance(veh: Vehicle, v, fz):
    return veh.q(v) * veh.cda + veh.crr * fz


def simulate(track: Track, veh: Vehicle) -> LapResult:
    n = len(track.s)
    ds = track.ds
    vc = corner_speed(veh, track.kappa)

    # Start from the slowest corner so the closed-lap boundary is consistent.
    i0 = int(np.argmin(vc))
    order = np.roll(np.arange(n), -i0)
    k = track.kappa[order]
    vcr = vc[order]

    # Forward pass: only the driven (rear) axle share of grip is usable.
    fwd = np.empty(n)
    fwd[0] = vcr[0]
    for i in range(n - 1):
        v = fwd[i]
        fx_grip, fz = _long_capacity(veh, v, k[i], veh.mu_x)
        f_drive = min(veh.power / max(v, 1.0), fx_grip * veh.rear_load_frac)
        a = (f_drive - _resistance(veh, v, fz)) / veh.mass
        fwd[i + 1] = min(np.sqrt(max(v * v + 2.0 * a * ds, 0.0)), vcr[i + 1])

    # Backward pass: all four wheels brake; station n-1 wraps onto station 0.
    bwd = np.empty(n)
    nxt_v, nxt_k = vcr[0], k[0]
    for i in range(n - 1, -1, -1):
        fx_grip, fz = _long_capacity(veh, nxt_v, nxt_k, veh.mu_x)
        a = (fx_grip + _resistance(veh, nxt_v, fz)) / veh.mass
        bwd[i] = min(np.sqrt(nxt_v * nxt_v + 2.0 * a * ds), vcr[i])
        nxt_v, nxt_k = bwd[i], k[i]

    v_r = np.minimum(fwd, bwd)
    v = np.empty(n)
    v[order] = v_r

    v_next = np.roll(v, -1)
    ax = (v_next ** 2 - v ** 2) / (2.0 * ds)
    ay = v * v * track.kappa
    lap_time = float(np.sum(2.0 * ds / (v + v_next)))
    return LapResult(track=track, vehicle=veh, v=v, ax=ax, ay=ay,
                     v_corner=vc, lap_time=lap_time)
