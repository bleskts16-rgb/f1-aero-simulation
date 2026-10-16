"""Simplified parametric F1 car following the 2026 FIA Technical Regulations (Issue 8).

Coordinates follow FIA Art. 2.6.1: X increases rearwards, Y to the driver's right,
Z up, units in mm. The car frame has its origin at the front axle (XF = 0) on the
reference plane Z = 0 (bottom of the floor). `build_car` returns every part in the
ground frame: the car is pitched to the requested front/rear ride heights and the
road is the plane Z = 0, so the geometry can go straight into a CFD domain.

Main dimensions come from the regulations; shapes inside the reference volumes are
simple aerodynamic placeholders (superellipse lofts, NACA wing sections), not a real
team design. Left out: halo, mirrors, suspension, brake ducts, floor boards/feet,
plank, cooling inlets/outlets (sidepods are closed).
"""
from dataclasses import dataclass, asdict, replace
import math

import cadquery as cq
import numpy as np
from OCP.Approx import Approx_ChordLength, Approx_Centripetal, Approx_IsoParametric
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections

V = cq.Vector


@dataclass(frozen=True)
class CarParams:
    # Fundamental dimensions (Art. 2.8)
    wheelbase: float = 3400.0       # XF=0 -> XR=0, max 3400 (2.8.2)
    xf_minus_xa: float = 100.0      # front axle behind survival-cell front, 0..150 (2.8.3)
    xc_minus_xa: float = 1930.0     # cockpit rear behind XA, 1830..2030 (2.8.4)
    half_width: float = 950.0       # bodywork |Y| limit; tyre outer face placed here (2.8.1)

    # Tyres: rims are 18" (462.6 mm, Art. 10.7.2); tyre sizes are supplier data -> assumptions
    tyre_f_diameter: float = 705.0
    tyre_f_width: float = 335.0     # ~ front rim overall width 334 (10.7.2)
    tyre_r_diameter: float = 710.0
    tyre_r_width: float = 420.0     # ~ rear rim overall width 420.3 (10.7.2)
    tyre_shoulder: float = 40.0     # sidewall edge radius
    tyre_squash: float = 5.0        # tyre sunk into the road for a finite contact patch

    # Ride height: road -> Z=0 plane, measured at each axle (sets rake)
    ride_height_front: float = 30.0
    ride_height_rear: float = 80.0

    # Front wing: 3 elements inside RV-FW-PROFILES (App.1 §18), slot gap 5..15 (3.10.1e)
    fw_chords: tuple = (260.0, 170.0, 125.0)
    fw_angles: tuple = (4.0, 18.0, 32.0)     # chord incidence [deg], + = trailing edge up
    fw_le: tuple = (-1230.0, 70.0)           # main-plane leading edge [XF, Z]
    fw_span_half: float = 640.0
    fw_gap: float = 10.0
    fw_overlap: float = 15.0
    fw_flap_delta: float = 0.0               # extra rotation of the two flaps (active aero, 3.10.9)

    # Rear wing: 3 elements inside RV-RW-PROFILES (App.1 §25), gap 10..15 (3.11.1d)
    rw_chords: tuple = (190.0, 120.0, 90.0)
    rw_angles: tuple = (2.0, 22.0, 45.0)
    rw_le: tuple = (250.0, 705.0)            # main-plane leading edge [XR, Z]
    rw_span_half: float = 552.0
    rw_gap: float = 12.0
    rw_overlap: float = 15.0
    rw_flap_delta: float = 0.0               # extra rotation of the two flaps (3.11.6)

    # Diffuser (floor body rear, App.1 §4): ramp from XR+diffuser_start to XR+165
    diffuser_start: float = -600.0
    diffuser_exit_height: float = 170.0
    floor_thickness: float = 20.0

    def to_dict(self):
        return asdict(self)

    def with_(self, **kw):
        return replace(self, **kw)

    @property
    def xa(self):
        return -self.xf_minus_xa

    @property
    def xc(self):
        return self.xa + self.xc_minus_xa

    @property
    def xr(self):
        return self.wheelbase

    @property
    def pitch_deg(self):
        return math.degrees(math.atan2(self.ride_height_rear - self.ride_height_front,
                                       self.wheelbase))


# ---------------------------------------------------------------- primitives

def _superellipse(x, a, z0, z1, n=3.0, npts=13):
    """Half section (Y >= 0) in an X-plane, spanning z0..z1, closed on Y=0.
    The curve meets Y=0 at right angles so the mirrored car is smooth."""
    zc, b = 0.5 * (z0 + z1), 0.5 * (z1 - z0)
    t = np.linspace(-np.pi / 2, np.pi / 2, npts)
    c, s = np.cos(t), np.sin(t)
    y = a * np.abs(c) ** (2 / n)
    z = zc + b * np.sign(s) * np.abs(s) ** (2 / n)
    pts = [V(x, yi, zi) for yi, zi in zip(y, z)]
    curve = cq.Edge.makeSpline(pts, tangents=[V(0, 1, 0), V(0, -1, 0)], scale=True)
    return cq.Wire.assembleEdges([curve, cq.Edge.makeLine(pts[-1], pts[0])])


_PAR = {"centripetal": Approx_Centripetal, "chord": Approx_ChordLength,
        "uniform": Approx_IsoParametric}


def _loft(sections, n=3.0, par="centripetal"):
    """sections: [(X, half_width, z_bottom, z_top[, exponent]), ...] ordered in X.
    Centripetal parametrisation keeps unevenly spaced sections from overshooting
    (CadQuery's makeLoft uses chord length, which bulged the tail by ~80 mm)."""
    wires = [_superellipse(*sec) if len(sec) == 5 else _superellipse(*sec, n)
             for sec in sections]
    ts = BRepOffsetAPI_ThruSections(True, False, 1e-6)
    ts.SetParType(_PAR[par])
    for w in wires:
        ts.AddWire(w.wrapped)
    ts.Build()
    return cq.Solid(ts.Shape())


def _naca4(m, p, t, npts=50):
    """NACA 4-digit section (open trailing edge), returned TE-upper -> LE -> TE-lower."""
    beta = np.linspace(0, np.pi, npts)
    x = 0.5 * (1 - np.cos(beta))
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                  + 0.2843 * x**3 - 0.1015 * x**4)
    yc = np.where(x < p, m / p**2 * (2 * p * x - x**2),
                  m / (1 - p)**2 * ((1 - 2 * p) + 2 * p * x - x**2))
    dyc = np.where(x < p, 2 * m / p**2 * (p - x), 2 * m / (1 - p)**2 * (p - x))
    th = np.arctan(dyc)
    xu, zu = x - yt * np.sin(th), yc + yt * np.cos(th)
    xl, zl = x + yt * np.sin(th), yc - yt * np.cos(th)
    xs = np.concatenate([xu[::-1], xl[1:]])
    zs = np.concatenate([zu[::-1], zl[1:]])
    return xs, zs


def _wing_element(le_x, le_z, chord, angle_deg, y0, y1, naca=(0.06, 0.4, 0.12)):
    """Inverted (downforce) cambered section extruded along Y from y0 to y1."""
    s, h = _naca4(*naca)
    h = -h                                  # camber down -> suction side below
    a = math.radians(angle_deg)             # + = trailing edge up
    X = le_x + chord * (s * math.cos(a) - h * math.sin(a))
    Z = le_z + chord * (s * math.sin(a) + h * math.cos(a))
    spline = cq.Edge.makeSpline([V(xi, y0, zi) for xi, zi in zip(X, Z)])
    te = cq.Edge.makeLine(V(X[-1], y0, Z[-1]), V(X[0], y0, Z[0]))
    face = cq.Face.makeFromWires(cq.Wire.assembleEdges([spline, te]))
    solid = cq.Solid.extrudeLinear(face, V(0, y1 - y0, 0))
    te_pt = (float(X[0]), float(Z[0]))
    return solid, te_pt


def _wing_stack(le, chords, angles, y0, y1, gap, overlap, flap_delta):
    """Main plane + flaps; each flap tucked over the previous trailing edge with a
    closest distance of `gap` (iterated with an exact distance query)."""
    elems = []
    x, z = le
    for i, (c, ang) in enumerate(zip(chords, angles)):
        ang = ang + (flap_delta if i > 0 else 0.0)
        if i == 0:
            el, te = _wing_element(x, z, c, ang, y0, y1)
        else:
            x = te[0] - overlap
            z = te[1] + gap
            for _ in range(6):
                el, new_te = _wing_element(x, z, c, ang, y0, y1)
                d = elems[-1].distance(el)
                if abs(d - gap) < 0.05:
                    break
                z += gap - d
            te = new_te
        elems.append(el)
    return elems


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _fuse(*shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return out.clean()


def _extrude_xz(points_xz, y0, y1):
    """Polygon in an Y-plane ([(X, Z), ...]) extruded from y0 to y1."""
    w = cq.Wire.makePolygon([V(x, y0, z) for x, z in points_xz], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), V(0, y1 - y0, 0))


def _extrude_xy(points_xy, z0, z1):
    """Polygon in a Z-plane ([(X, Y), ...]) extruded from z0 to z1."""
    w = cq.Wire.makePolygon([V(x, y, z0) for x, y in points_xy], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(w), V(0, 0, z1 - z0))


# ------------------------------------------- components (car frame, Y >= 0 half)

def body(p: CarParams):
    xc, xr = p.xc, p.xr
    # Nose + survival cell inside RV-BODY-FRONT (App.1 §8: |Y| <= 150..400, Z <= 645),
    # then engine cover / airbox inside RV-EC (App.1 §13: Z <= 970 at XC..XC+300)
    # and the tail inside RV-TAIL (App.1 §15). One loft avoids a slow boolean.
    spine = _loft([
        (-1250, 40, 150, 210, 3.0),
        (-1200, 70, 130, 230, 3.0),
        (-900, 110, 135, 300, 3.0),
        (-500, 150, 150, 420, 3.0),
        (p.xa, 190, 165, 540, 3.0),
        (500, 230, 60, 620, 3.0),
        (900, 265, 10, 640, 3.0),
        (xc - 450, 290, 10, 655, 3.0),
        (xc - 230, 300, 10, 700, 3.0),
        (xc - 80, 285, 10, 830, 2.8),
        (xc + 20, 260, 10, 940, 2.6),
        (xc + 320, 230, 10, 880, 2.6),
        (xr - 700, 190, 30, 640, 2.6),
        (xr - 200, 140, 80, 480, 2.6),
        (xr - 50, 110, 120, 400, 2.6),
        (xr + 350, 60, 230, 330, 2.6),
    ])
    # Closed sidepods, inside RV-SIDEPOD + RV-EC (|Y| <= 715, Z <= 600)
    sidepods = _loft([
        (1040, 300, 280, 370),
        (1120, 560, 150, 470),
        (1300, 680, 10, 560),
        (1900, 650, 10, 520),
        (2500, 520, 10, 430),
        (3000, 320, 10, 340),
        (xr - 100, 170, 60, 300),
    ], n=3.5)
    # helmet: a sphere built from the same half sections, so it mirrors cleanly
    r, hx, hz = 125.0, xc - 450, 720.0
    helmet = _loft([(hx - r * math.cos(f), r * math.sin(f), hz - r * math.sin(f),
                     hz + r * math.sin(f), 2.0) for f in np.radians(np.linspace(12, 168, 9))])

    # Floor body planform (App.1 §4.1/§4.9), flat bottom on Z=0 ahead of the diffuser
    xd = xr + p.diffuser_start
    t = p.floor_thickness
    plate = _extrude_xy([
        (420, 0), (420, 150), (1200, 725), (xr - 400, 725),
        (xr - 400, 390), (xd, 390), (xd, 0),
    ], 0, t)
    h = p.diffuser_exit_height
    ramp = _extrude_xz([(xd, 0), (xr + 165, h), (xr + 165, h + t), (xd, t)], 0, 390)
    fence = _extrude_xz([(xd, 0), (xr + 165, 0), (xr + 165, h + t), (xd, t)], 375, 390)
    # nothing of the sprung body may hang below Z=0 (2.7a); also trims loft overshoot
    above_ref = _box(-2000, 6000, 0, 1000, 0, 1500)
    return _fuse(spine, sidepods, helmet, plate, ramp, fence).intersect(above_ref)


def front_wing(p: CarParams):
    s = p.fw_span_half
    elems = _wing_stack(p.fw_le, p.fw_chords, p.fw_angles, 0, s,
                        p.fw_gap, p.fw_overlap, p.fw_flap_delta)
    # Endplate in RV-FWEP-BODY (App.1 §19): Y 600..680, cut by an R412.5 cylinder
    # around [XF, Z] = [0, 360] for front-wheel clearance
    plate = _box(-1250, -430, s - 10, s + 2, 40, 330)
    plate = plate.cut(cq.Solid.makeCylinder(412.5, 1000, V(0, 0, 360), V(0, 1, 0)))
    return _fuse(*elems, plate)


def rear_wing(p: CarParams):
    s = p.rw_span_half
    x0, z0 = p.xr + p.rw_le[0], p.rw_le[1]
    elems = _wing_stack((x0, z0), p.rw_chords, p.rw_angles, 0, s,
                        p.rw_gap, p.rw_overlap, p.rw_flap_delta)
    # Endplate in RV-RWEP-BODY (App.1 §26, upper part only), Y 540..575
    plate = _box(p.xr + 225, p.xr + 650, s - 7, s + 8, 690, 878)
    # Central pylon, |Y| < 12.5 (3.11.4), from tail up to the main plane
    pylon = _box(p.xr + 240, p.xr + 380, 0, 10, 270, z0 + 20)
    return _fuse(*elems, plate, pylon)


def wheels(p: CarParams):
    """Right-hand front and rear tyres, already in the ground frame."""
    out = {}
    for name, x, d, w in (("wheels_front", 0.0, p.tyre_f_diameter, p.tyre_f_width),
                          ("wheels_rear", p.xr, p.tyre_r_diameter, p.tyre_r_width)):
        cyl = cq.Solid.makeCylinder(d / 2, w, V(x, p.half_width - w, d / 2 - p.tyre_squash),
                                    V(0, 1, 0))
        out[name] = cq.Workplane().add(cyl).edges("%CIRCLE").fillet(p.tyre_shoulder).val()
    return out


# ---------------------------------------------------------------- assembly

def to_ground(shape, p: CarParams):
    """Pitch the sprung body to the ride heights and put the road on Z=0."""
    return (shape.rotate(V(0, 0, 0), V(0, 1, 0), -p.pitch_deg)
                 .translate(V(0, 0, p.ride_height_front)))


def sprung_parts(p: CarParams = CarParams()):
    """Body and wings, Y >= 0 half, in the car frame (for regulation checks)."""
    return {"body": body(p), "front_wing": front_wing(p), "rear_wing": rear_wing(p)}


def build_car(p: CarParams = CarParams(), sprung=None, half=False):
    """Dict of named solids in the ground frame (mm). With half=True only the Y >= 0
    side is returned, cut exactly on the symmetry plane."""
    sprung = sprung or sprung_parts(p)
    parts = {k: to_ground(v, p) for k, v in sprung.items()}
    parts.update(wheels(p))
    if half:
        return parts
    # glue: the halves share the Y=0 face exactly
    return {k: v.fuse(v.mirror("XZ"), glue=True).clean() for k, v in parts.items()}
