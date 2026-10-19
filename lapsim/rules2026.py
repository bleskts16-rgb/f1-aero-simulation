"""2026 rules on top of the point-mass QSS model.

What changes from the 2024 model (FIA 2026 Technical Regulations, Issue 8):
- Mass: 724 kg + nominal tyre mass (Art. 4.2); light qualifying fuel added.
- Power: ICE limited by 3000 MJ/h fuel energy flow (Art. 5.4.3), ~400 kW at the crank.
  ERS-K up to 350 kW DC (5.4.7), tapered with speed to 0 at 345 km/h (5.4.8).
- Energy: ERS-K harvest <= 8.5 MJ per lap (5.4.10), state-of-charge window 4 MJ (5.4.9).
  A qualifying lap may start full and end empty, so deployment <= 4 MJ + harvest.
  Deployment follows a speed threshold: full allowed power below v_deploy, none above,
  with v_deploy chosen so the lap uses exactly the available energy ("clipping").
  Only braking harvest is modelled (no partial-load harvesting).
- Active aero: straight-line mode (X: flaps open, low drag, low downforce) where the
  racing line is nearly straight and the car is accelerating; corner mode (Z) everywhere
  else, including all braking and the cornering limit.

Assumed, not regulated: ICE crank power, drivetrain/ERS efficiencies, tyre grip
(same as the 2024 model), where X-mode is allowed (curvature + length threshold).
"""
from dataclasses import dataclass, replace

import numpy as np

from .qss import LapResult, corner_speed, _long_capacity, _resistance
from .track import Track
from .vehicle import Vehicle


@dataclass(frozen=True)
class Car2026(Vehicle):
    mass: float = 774.0          # 724 + ~44 kg tyres + ~6 kg qualifying fuel [kg]
    power: float = 0.0           # unused; see p_ice / p_k
    p_ice: float = 400e3         # ICE crank power [W] (fuel flow limited)
    eta_ice: float = 0.95        # crank -> wheel
    p_k: float = 350e3           # ERS-K DC power limit [W] (5.4.7)
    eta_k: float = 0.92          # DC -> wheel (MGU-K + transmission)
    eta_harv: float = 0.92       # wheel -> DC when harvesting
    e_soc: float = 4.0e6         # usable state-of-charge window [J] (5.4.9)
    e_harv_max: float = 8.5e6    # harvest limit per lap [J] (5.4.10)
    # aero: Z = corner mode (also used by the 2024 field names cla/cda), X = straight mode
    cla: float = 4.8
    cda: float = 1.45
    cla_x: float = 2.4
    cda_x: float = 0.80
    x_radius: float = 800.0      # straight-mode only where turn radius exceeds this [m]
    x_min_len: float = 150.0     # ... over at least this length [m]

    def z(self) -> Vehicle:
        return replace(self)

    def x(self) -> Vehicle:
        return replace(self, cla=self.cla_x, cda=self.cda_x)

    def with_modes(self, **kw):
        return replace(self, **kw)

    def k_limit(self, v):
        """ERS-K propulsion power limit vs speed (Art. 5.4.7-5.4.8) [W]."""
        kph = np.asarray(v) * 3.6
        p = np.where(kph < 340.0, 1800.0 - 5.0 * kph, 6900.0 - 20.0 * kph) * 1e3
        return np.clip(p, 0.0, self.p_k)


@dataclass
class Lap2026(LapResult):
    x_mode: np.ndarray = None    # True where straight mode was active
    v_deploy: float = 0.0        # ERS deployment threshold speed [m/s]
    e_deploy: float = 0.0        # energy deployed (DC) [J]
    e_harvest: float = 0.0       # energy harvested (DC) [J]


def straight_mask(track: Track, car: Car2026) -> np.ndarray:
    """Stations on straight runs long enough to open the flaps."""
    flat = np.abs(track.kappa) < 1.0 / car.x_radius
    n = len(flat)
    out = np.zeros(n, bool)
    if flat.all():
        return ~out
    start = int(np.argmin(flat))          # begin scanning at a non-straight station
    run = []
    for j in range(n + 1):
        i = (start + j) % n
        if j < n and flat[i]:
            run.append(i)
        else:
            if len(run) * track.ds >= car.x_min_len:
                out[run] = True
            run = []
    return out


def _lap(track: Track, car: Car2026, v_deploy: float, xmask: np.ndarray):
    n, ds = len(track.s), track.ds
    vz, vx = car.z(), car.x()
    vc = corner_speed(vz, track.kappa)
    i0 = int(np.argmin(vc))
    order = np.roll(np.arange(n), -i0)
    k, vcr, xm = track.kappa[order], vc[order], xmask[order]

    fwd = np.empty(n)
    deploy = np.zeros(n)                  # DC power deployed at each station [W]
    fwd[0] = vcr[0]
    for i in range(n - 1):
        v = fwd[i]
        veh = vx if xm[i] else vz
        p_k = float(car.k_limit(v)) if v < v_deploy else 0.0
        p_wheel = car.eta_ice * car.p_ice + car.eta_k * p_k
        fx_grip, fz = _long_capacity(veh, v, k[i], veh.mu_x)
        f_power = p_wheel / max(v, 1.0)
        f_trac = fx_grip * veh.rear_load_frac
        f_drive = min(f_power, f_trac)
        if f_power <= f_trac:
            deploy[i] = p_k
        a = (f_drive - _resistance(veh, v, fz)) / veh.mass
        fwd[i + 1] = min(np.sqrt(max(v * v + 2.0 * a * ds, 0.0)), vcr[i + 1])

    bwd = np.empty(n)
    nxt_v, nxt_k = vcr[0], k[0]
    for i in range(n - 1, -1, -1):
        fx_grip, fz = _long_capacity(vz, nxt_v, nxt_k, vz.mu_x)
        a = (fx_grip + _resistance(vz, nxt_v, fz)) / vz.mass
        bwd[i] = min(np.sqrt(nxt_v * nxt_v + 2.0 * a * ds), vcr[i])
        nxt_v, nxt_k = bwd[i], k[i]

    v_r = np.minimum(fwd, bwd)
    v_next = np.roll(v_r, -1)
    dt = 2.0 * ds / (v_r + v_next)
    on_power = (v_r >= fwd - 1e-9) & (v_next > v_r)          # accelerating on the forward curve
    braking = (v_r >= bwd - 1e-9) & (v_next < v_r)
    e_dep = float(np.sum(deploy * on_power * dt))
    # braking power available beyond aero drag, capped by the ERS-K limit
    decel = (v_r ** 2 - v_next ** 2) / (2.0 * ds)
    p_brake = vz.mass * decel * v_r - np.array([_resistance(vz, vv, vz.normal_load(vv)) for vv in v_r]) * v_r
    e_harv = float(np.sum(np.minimum(np.maximum(p_brake, 0.0) * car.eta_harv, car.p_k) * braking * dt))
    e_harv = min(e_harv, car.e_harv_max)

    v = np.empty(n)
    v[order] = v_r
    xmode = np.empty(n, bool)
    xmode[order] = xm & ~braking
    vn = np.roll(v, -1)
    return dict(
        track=track, vehicle=car, v=v, ax=(vn ** 2 - v ** 2) / (2.0 * ds), ay=v * v * track.kappa,
        v_corner=vc, lap_time=float(np.sum(2.0 * ds / (v + vn))), x_mode=xmode,
        v_deploy=v_deploy, e_deploy=e_dep, e_harvest=e_harv)


def simulate_2026(track: Track, car: Car2026, active_aero: bool = True) -> Lap2026:
    """Qualifying lap: deploy as much as the energy budget allows (4 MJ + harvest)."""
    xmask = straight_mask(track, car) if active_aero else np.zeros(len(track.s), bool)

    def run(vd):
        return Lap2026(**_lap(track, car, vd, xmask))

    full = run(car.v_max + 1.0)
    if full.e_deploy <= car.e_soc + full.e_harvest:
        return full
    lo, hi = 0.0, car.v_max + 1.0
    best = run(lo)
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        r = run(mid)
        if r.e_deploy <= car.e_soc + r.e_harvest:
            lo, best = mid, r
        else:
            hi = mid
        if hi - lo < 0.05:
            break
    return best
