"""Point-mass vehicle parameters.

Defaults are rough public estimates for a current-era F1 car in qualifying trim.
They are starting values to be calibrated against real telemetry, not team data.
"""
from dataclasses import dataclass, asdict, replace

G = 9.81


@dataclass(frozen=True)
class Vehicle:
    mass: float = 810.0          # car + driver + light fuel load [kg]
    power: float = 700e3         # power at the wheels, ICE + ERS [W]
    rho: float = 1.20            # air density [kg/m^3]
    cla: float = 5.0             # downforce coefficient x area, CL*A [m^2]
    cda: float = 1.30            # drag coefficient x area, CD*A [m^2]
    mu_x: float = 1.75           # longitudinal tyre friction at reference load
    mu_y: float = 1.85           # lateral tyre friction at reference load
    load_sens: float = 0.10      # mu ~ (Fz / m g)^(-load_sens)
    rear_load_frac: float = 0.55 # share of normal load on the driven axle
    crr: float = 0.012           # rolling resistance coefficient
    v_max: float = 105.0         # numerical speed cap [m/s]

    def q(self, v):
        return 0.5 * self.rho * v * v

    def normal_load(self, v):
        return self.mass * G + self.q(v) * self.cla

    def mu_scale(self, fz):
        return (fz / (self.mass * G)) ** (-self.load_sens)

    def with_aero(self, cla=None, cda=None):
        return replace(self, cla=self.cla if cla is None else cla,
                       cda=self.cda if cda is None else cda)

    def to_dict(self):
        return asdict(self)
