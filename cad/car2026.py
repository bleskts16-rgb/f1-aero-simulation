"""Simplified parametric F1 car following the 2026 FIA Technical Regulations (Issue 8).

Coordinates follow FIA Art. 2.6.1: X increases rearwards, Y to the driver's right,
Z up, units in mm. The car frame has its origin at the front axle (XF = 0) on the
reference plane Z = 0 (bottom of the floor). `build_car` returns every part in the
ground frame: the car is pitched to the requested front/rear ride heights and the
road is the plane Z = 0, so the geometry can go straight into a CFD domain.

Main dimensions come from the regulations; shapes inside the reference volumes are
simple aerodynamic placeholders (superellipse lofts, NACA wing sections), not a real
team design. Optional detail parts (off by default, see CarParams): halo, suspension,
front wheel wake boards. Left out: mirrors, brake ducts, wheel covers, plank, cooling
inlets/outlets (sidepods are closed).
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

    # Shape level. "G0": regulation envelopes, used by the grid studies (grid1/grid2),
    # must not change. "G1": styled after the FIA 2026 concept car renders
    # (formula1.com, "Explained: 2026 aerodynamic regulations"): spoon-shaped front
    # wing with tall endplates, sidepods with a deep undercut and a downwash top.
    geom_level: str = "G0"
    fw_tip_rise: float = 80.0                # G1: front wing tips raised by this [mm]
    # G1 wheels (clean-cad T1): tyre cross-section revolved about the axle, on an
    # 18" rim (462.6 mm, Art. 10.7.2) with dished wheel covers. One closed solid per
    # wheel, so it stays a single rotating wall in CFD.
    rim_diameter: float = 462.6
    tyre_bead_inset: float = 18.0            # sidewall bulge: max width minus bead width, per side
    tyre_shoulder_w: float = 42.0            # shoulder roll, axial half-axis
    tyre_shoulder_h: float = 58.0            # shoulder roll, radial half-axis
    cover_recess: float = 20.0               # outer wheel cover below the tyre face, at the rim
    cover_dish: float = 10.0                 # extra depth of the cover at the hub
    inner_recess: float = 15.0               # inner (brake side) closing face below the tyre face

    # Optional detail parts. All off = the G0 car used by the grid studies.
    halo: bool = False
    suspension: bool = False
    wake_boards: bool = False
    mirrors: bool = False
    # Front wheel wake boards: front corners of the floor, behind the front tyre, ahead
    # of the sidepod; outline aligned inwards by 15 deg, up to three elements (2026 rules
    # as reported by the press; exact reference volumes not yet checked in the PDF).
    wb_yaw: float = 15.0                     # inward alignment, + = trailing edge inboard
    wb_le: tuple = (580.0, 690.0)            # leading edge of the outline [XF, |Y|]
    wb_chord: float = 400.0
    wb_height: float = 320.0                 # above the floor top
    wb_elements: int = 3
    wb_slot: float = 10.0                    # vertical gap between elements

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

# (label, solid, section wires) of every loft built, for cad.qa.loft_escape
LOFT_LOG = []


def _loft(sections, n=3.0, par="centripetal", label="loft"):
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
    solid = cq.Solid(ts.Shape())
    LOFT_LOG.append((label, solid, wires))
    return solid


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


def _wing_section(le_x, le_z, chord, angle_deg, y, naca=(0.06, 0.4, 0.12)):
    """Closed wire of an inverted (downforce) cambered section in the plane Y = y,
    and its trailing-edge point (X, Z)."""
    s, h = _naca4(*naca)
    h = -h                                  # camber down -> suction side below
    a = math.radians(angle_deg)             # + = trailing edge up
    X = le_x + chord * (s * math.cos(a) - h * math.sin(a))
    Z = le_z + chord * (s * math.sin(a) + h * math.cos(a))
    spline = cq.Edge.makeSpline([V(xi, y, zi) for xi, zi in zip(X, Z)])
    te = cq.Edge.makeLine(V(X[-1], y, Z[-1]), V(X[0], y, Z[0]))
    return cq.Wire.assembleEdges([spline, te]), (float(X[0]), float(Z[0]))


def _wing_element(le_x, le_z, chord, angle_deg, y0, y1, naca=(0.06, 0.4, 0.12)):
    """Inverted (downforce) cambered section extruded along Y from y0 to y1."""
    wire, te_pt = _wing_section(le_x, le_z, chord, angle_deg, y0, naca)
    solid = cq.Solid.extrudeLinear(cq.Face.makeFromWires(wire), V(0, y1 - y0, 0))
    return solid, te_pt


def _wing_layout(le, chords, angles, y0, y1, gap, overlap, flap_delta):
    """(elements, [(le_x, le_z, chord, angle)]): main plane + flaps, each flap tucked
    over the previous trailing edge with a closest distance of `gap` (iterated with
    an exact distance query)."""
    elems, layout = [], []
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
        layout.append((x, z, c, ang))
    return elems, layout


def _wing_stack(le, chords, angles, y0, y1, gap, overlap, flap_delta):
    return _wing_layout(le, chords, angles, y0, y1, gap, overlap, flap_delta)[0]


def _rounded_outline(verts, n_arc=8):
    """Closed polygon through (a, b, r) vertices with each corner replaced by a
    tangent arc of radius r (after text-to-cad floor._corner_pts). Stays inside the
    convex hull of the vertices, unlike a spline through them."""
    P = np.array([v[:2] for v in verts], dtype=float)
    out = []
    for i, (a, b, r) in enumerate(verts):
        p0, p1, p2 = P[i - 1], P[i], P[(i + 1) % len(P)]
        d0 = (p1 - p0) / np.linalg.norm(p1 - p0)
        d1 = (p2 - p1) / np.linalg.norm(p2 - p1)
        turn = math.atan2(d0[0] * d1[1] - d0[1] * d1[0], float(d0 @ d1))
        t = min(r * math.tan(abs(turn) / 2), 0.45 * np.linalg.norm(p1 - p0),
                0.45 * np.linalg.norm(p2 - p1))
        if r <= 0 or abs(turn) < 1e-3 or t < 0.5:
            out.append(tuple(p1))
            continue
        r_eff = t / math.tan(abs(turn) / 2)
        start = p1 - d0 * t
        sgn = 1.0 if turn > 0 else -1.0
        c = start + sgn * r_eff * np.array([-d0[1], d0[0]])
        v = start - c
        for k in range(n_arc + 1):
            ang = turn * k / n_arc
            ca, sa = math.cos(ang), math.sin(ang)
            out.append((c[0] + v[0] * ca - v[1] * sa, c[1] + v[0] * sa + v[1] * ca))
    return out


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

def _spine_sections(p: CarParams):
    """(X, half_width, z_bottom, z_top, exponent) of the nose / chassis / engine cover."""
    xc, xr = p.xc, p.xr
    return [
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
    ]


def chassis_point(p: CarParams, x, fy, fz):
    """A point inside the spine at station x (car frame): fy = fraction of the local
    half width, fz = fraction of the local height. fy <= 0.6 with 0.15 <= fz <= 0.85
    is always inside the superellipse, so members anchored there overlap the body."""
    sec = np.array([s[:4] for s in _spine_sections(p)], dtype=float)
    a, z0, z1 = (np.interp(x, sec[:, 0], sec[:, i]) for i in (1, 2, 3))
    return V(x, fy * a, z0 + fz * (z1 - z0))


def body(p: CarParams):
    xc, xr = p.xc, p.xr
    # Nose + survival cell inside RV-BODY-FRONT (App.1 §8: |Y| <= 150..400, Z <= 645),
    # then engine cover / airbox inside RV-EC (App.1 §13: Z <= 970 at XC..XC+300)
    # and the tail inside RV-TAIL (App.1 §15). One loft avoids a slow boolean.
    spine = _loft(_spine_sections(p), label="spine")
    # Closed sidepods, inside RV-SIDEPOD + RV-EC (|Y| <= 715, Z <= 600)
    if p.geom_level == "G1":
        # deep undercut at the front (the floor stays below an open channel), top
        # falling towards the rear (downwash), narrow coke-bottle waist
        pods = [(1040, 300, 330, 430), (1150, 560, 280, 510), (1350, 690, 220, 545),
                (1800, 670, 150, 520), (2300, 560, 70, 455), (2800, 380, 10, 370),
                (xr - 100, 170, 60, 300)]
    else:
        pods = [(1040, 300, 280, 370), (1120, 560, 150, 470), (1300, 680, 10, 560),
                (1900, 650, 10, 520), (2500, 520, 10, 430), (3000, 320, 10, 340),
                (xr - 100, 170, 60, 300)]
    sidepods = _loft(pods, n=3.5, label="sidepods")
    # helmet: a sphere built from the same half sections, so it mirrors cleanly
    r, hx, hz = 125.0, xc - 450, 720.0
    helmet = _loft([(hx - r * math.cos(f), r * math.sin(f), hz - r * math.sin(f),
                     hz + r * math.sin(f), 2.0) for f in np.radians(np.linspace(12, 168, 9))],
                   label="helmet")

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
    extra = []
    if p.geom_level == "G1":
        extra.append(airbox(p))
    # nothing of the sprung body may hang below Z=0 (2.7a); also trims loft overshoot
    above_ref = _box(-2000, 6000, 0, 1000, 0, 1500)
    out = _fuse(spine, sidepods, helmet, plate, ramp, fence, *extra).intersect(above_ref)
    if p.geom_level == "G1":
        out = out.cut(airbox_mouth(p))
    return out


def airbox(p: CarParams):
    """G1 roll-hoop airbox right behind the driver's head (FIA 2026 renders):
    rounded-triangle sections that rise from the engine cover to a forward-facing
    mouth. Top kept below the 970 mm RV-EC limit with margin for loft bowing."""
    xc = p.xc
    return _loft([(xc - 150, 120, 760, 950, 2.2), (xc - 70, 135, 700, 955, 2.4),
                  (xc + 70, 140, 640, 945, 2.6), (xc + 320, 120, 600, 880, 2.6)],
                 label="airbox")


def airbox_mouth(p: CarParams):
    """Blind elliptical intake, 100 mm deep: the air path is not modelled (closed
    body for CFD), but the mouth and its stagnation region are."""
    xc = p.xc
    plane = cq.Plane(origin=V(xc - 160, 0, 860), xDir=V(0, 1, 0), normal=V(1, 0, 0))
    return cq.Workplane(plane).ellipse(80, 62).extrude(110).val()


def _spoon_element(x, z, c, ang, span, rise, n=9):
    """Wing element lofted through Y stations whose sections are lifted by
    rise * (y / span)^2.5: flat in the middle, curling up into the endplate.
    Every element at a station moves by the same amount, so slot gaps stay as set."""
    wires = [_wing_section(x, z + rise * (y / span) ** 2.5, c, ang, y)[0]
             for y in np.linspace(0.0, span, n)]
    ts = BRepOffsetAPI_ThruSections(True, False, 1e-6)
    ts.SetParType(Approx_Centripetal)
    for w in wires:
        ts.AddWire(w.wrapped)
    ts.Build()
    solid = cq.Solid(ts.Shape())
    LOFT_LOG.append((f"fw element c={c:.0f}", solid, wires))
    return solid


def front_wing(p: CarParams):
    s = p.fw_span_half
    elems, layout = _wing_layout(p.fw_le, p.fw_chords, p.fw_angles, 0, s,
                                 p.fw_gap, p.fw_overlap, p.fw_flap_delta)
    rise = 0.0
    if p.geom_level == "G1":
        rise = p.fw_tip_rise
        elems = [_spoon_element(x, z, c, a, s, rise) for x, z, c, a in layout]
    # Endplate in RV-FWEP-BODY (App.1 §19): Y 600..680, cut by an R412.5 cylinder
    # around [XF, Z] = [0, 360] for front-wheel clearance
    plate = _box(-1250, -430, s - 10, s + 2, 40, 330 + rise)
    plate = plate.cut(cq.Solid.makeCylinder(412.5, 1000, V(0, 0, 360), V(0, 1, 0)))
    return _fuse(*elems, plate)


def rear_wing(p: CarParams):
    s = p.rw_span_half
    x0, z0 = p.xr + p.rw_le[0], p.rw_le[1]
    elems = _wing_stack((x0, z0), p.rw_chords, p.rw_angles, 0, s,
                        p.rw_gap, p.rw_overlap, p.rw_flap_delta)
    # Endplate in RV-RWEP-BODY (App.1 §26, upper part only), Y 540..575
    if p.geom_level == "G1":
        # G1: tall endplate with rounded corners and a curved leading edge that
        # sweeps down towards the rear tyre, as on the FIA 2026 renders
        # (dx from XR, Z, corner radius); straight runs + arcs never leave the hull of
        # these vertices (a periodic spline overshot the 880 mm limit by 38 mm)
        outline = _rounded_outline([(230, 878, 45), (650, 878, 35), (650, 540, 70),
                                    (470, 440, 90), (320, 520, 70), (225, 650, 45)])
        plate = _extrude_xz([(p.xr + dx, z) for dx, z in outline], s - 7, s + 8)
    else:
        plate = _box(p.xr + 225, p.xr + 650, s - 7, s + 8, 690, 878)
    # Central pylon, |Y| < 12.5 (3.11.4), from tail up to the main plane
    pylon = _box(p.xr + 240, p.xr + 380, 0, 10, 270, z0 + 20)
    return _fuse(*elems, plate, pylon)


def _strut(p0, p1, chord=60.0, thick=18.0, ext=10.0):
    """Streamlined member from p0 to p1: an elliptical section whose long axis is the
    flow direction (X) projected onto the section plane. Extended by `ext` at both
    ends so it overlaps what it is attached to."""
    p0, p1 = V(*p0), V(*p1)
    d = (p1 - p0).normalized()
    x = V(1, 0, 0)
    xdir = (x - d * x.dot(d)).normalized()
    plane = cq.Plane(origin=p0 - d * ext, xDir=xdir, normal=d)
    return cq.Workplane(plane).ellipse(chord / 2, thick / 2).extrude((p1 - p0).Length + 2 * ext).val()


def ground_to_car(p: CarParams, v):
    """Inverse of `to_ground` for a single point."""
    a = math.radians(p.pitch_deg)
    x, y, z = v.x, v.y, v.z - p.ride_height_front
    return V(x * math.cos(a) - z * math.sin(a), y, x * math.sin(a) + z * math.cos(a))


def suspension(p: CarParams):
    """Double wishbones, pushrod and track rod / toe link per axle, Y >= 0, car frame.
    Inboard ends sit inside the chassis (`chassis_point`); outboard ends 25 mm inside
    the tyre's inner face. Layout loosely follows the text-to-cad hardpoints
    (third_party/text-to-cad/models/f1/lib/spec.py) refitted to this car; pushrod at
    both ends, the common 2026 choice."""
    out = {}
    for name, x0, d, w, inboard, outboard in (
        ("suspension_front", 0.0, p.tyre_f_diameter, p.tyre_f_width,
         # (x, fy, fz) on the chassis
         dict(lf=(-330, .55, .15), la=(300, .55, .15), uf=(-300, .55, .75),
              ua=(330, .55, .75), push=(-200, .5, .9), steer=(-150, .55, .55)),
         # (dx, dy from the tyre inner face, dz) from the wheel centre
         dict(lower=(0, 25, -170), upper=(-15, 25, 185), push=(5, -30, -165),
              steer=(-150, 25, 60))),
        ("suspension_rear", p.xr, p.tyre_r_diameter, p.tyre_r_width,
         dict(lf=(3100, .55, .35), la=(3450, .55, .45), uf=(3100, .55, .8),
              ua=(3450, .55, .8), push=(3150, .45, .9), steer=(3550, .5, .35)),
         dict(lower=(0, 25, -150), upper=(0, 25, 185), push=(5, -30, -145),
              steer=(150, 25, -110))),
    ):
        y_in = p.half_width - w                       # tyre inner face
        z_c = d / 2 - p.tyre_squash                   # wheel centre height (ground)
        ob = {k: ground_to_car(p, V(x0 + dx, y_in + dy, z_c + dz))
              for k, (dx, dy, dz) in outboard.items()}
        ib = {k: chassis_point(p, *v) for k, v in inboard.items()}
        members = [_strut(ib["lf"], ob["lower"]), _strut(ib["la"], ob["lower"]),
                   _strut(ib["uf"], ob["upper"]), _strut(ib["ua"], ob["upper"]),
                   _strut(ob["push"], ib["push"], chord=50, thick=16),
                   _strut(ib["steer"], ob["steer"], chord=45, thick=15)]
        out[name] = _fuse(*members)
    return out


def halo(p: CarParams):
    """Halo: a 55 mm tube hoop around the cockpit opening plus a faired front strut on
    the centreline. The FIA halo is a prescribed part; this follows its layout only
    (front pillar ahead of the driver, hoop at about helmet height, rear mounts on the
    chassis behind the cockpit)."""
    xc = p.xc
    hoop = [(xc - 70, 230, 650), (xc - 110, 280, 760), (xc - 270, 320, 790),
            (xc - 510, 270, 800), (xc - 680, 140, 800), (xc - 750, 0, 800)]
    pts = [V(*q) for q in hoop] + [V(x, -y, z) for x, y, z in reversed(hoop[:-1])]
    path = cq.Wire.assembleEdges([cq.Edge.makeSpline(pts)])
    ring = cq.Wire.makeCircle(27.5, pts[0], path.tangentAt(0))
    tube = cq.Solid.sweep(ring, [], path, makeSolid=True, isFrenet=False)
    strut = _strut((xc - 750, 0, 800), (xc - 950, 0, 590), chord=90, thick=40)
    return _fuse(tube, strut).intersect(_box(xc - 1200, xc + 200, 0, 600, 300, 1000))


def wake_boards(p: CarParams):
    """Front wheel wake board, Y >= 0, car frame: `wb_elements` cambered vertical vanes
    stacked in Z with `wb_slot` gaps, joined by a leading-edge tower and standing on a
    foot plate that overlaps the floor's front corner. The whole outline is yawed
    inwards by `wb_yaw` and cambered to turn the tyre wake further inboard."""
    t = p.floor_thickness
    yaw = math.radians(p.wb_yaw)
    dx, dy = math.cos(yaw), -math.sin(yaw)          # chord direction, towards inboard
    nx, ny = -dy, dx                                # outboard normal
    lx, ly = p.wb_le
    c = p.wb_chord
    s, h = _naca4(0.04, 0.4, 0.06, npts=40)         # camber bulges outboard
    X = lx + c * (s * dx + h * nx)
    Y = ly + c * (s * dy + h * ny)
    n = p.wb_elements
    he = (p.wb_height - (n - 1) * p.wb_slot) / n
    elems = []
    for i in range(n):
        z0 = t + i * (he + p.wb_slot) - (2.0 if i == 0 else 0.0)   # first one sinks into the foot
        z1 = t + i * (he + p.wb_slot) + he
        edge = cq.Edge.makeSpline([V(xi, yi, z0) for xi, yi in zip(X, Y)])
        te = cq.Edge.makeLine(V(X[-1], Y[-1], z0), V(X[0], Y[0], z0))
        face = cq.Face.makeFromWires(cq.Wire.assembleEdges([edge, te]))
        elems.append(cq.Solid.extrudeLinear(face, V(0, 0, z1 - z0)))
    tower = _strut((lx + 20 * dx, ly + 20 * dy, t - 5), (lx + 20 * dx, ly + 20 * dy, t + p.wb_height),
                   chord=45, thick=16, ext=0)
    # foot: from the board's footprint inwards past the floor's diagonal front edge
    tx, ty = lx + c * dx, ly + c * dy
    ydiag = lambda x: 150 + (x - 420) * 575 / 780          # floor plate edge in body()
    ymax = max(ly, ty) + 30
    foot = _extrude_xy([(lx - 60, ydiag(lx - 60) - 40), (lx - 60, ymax), (tx + 40, ymax),
                        (tx + 40, ydiag(tx + 40) - 40)], 0, t)
    return _fuse(foot, tower, *elems)


def mirrors(p: CarParams):
    """Mirror housing (ellipsoid 150 x 110 x 60 mm) on a streamlined stalk, beside the
    cockpit ahead of the sidepod inlet, as on the FIA 2026 renders. Y >= 0, car frame."""
    x, y, z = 1000.0, 520.0, 660.0
    unit = cq.Solid.makeSphere(1.0, angleDegrees1=-90, angleDegrees2=90)
    housing = unit.transformGeometry(cq.Matrix([[75, 0, 0, x], [0, 55, 0, y], [0, 0, 30, z]]))
    stalk = _strut(chassis_point(p, x, 0.45, 0.85), (x, y - 30, z), chord=50, thick=14)
    return _fuse(housing, stalk)


def tyre_profile(p: CarParams, d, w, n_side=28, n_shoulder=14, n_tread=10):
    """G1 wheel half cross-section as (y, r) points: y axial from the inner tyre face
    (0) to the outer face (w), r radial from the axle. Returns (curve, closing):
    `curve` is the smooth tyre outline from the outer bead over the tread to the
    inner bead; `closing` runs inner bead -> inner face -> axle -> wheel cover ->
    outer bead as straight segments. Sidewall bulge follows t**0.55 from the bead
    to the widest point (clean-cad T1, after text-to-cad wheels.py), then a quarter
    ellipse rolls the shoulder into a flat tread."""
    R = d / 2
    r_rim = p.rim_diameter / 2
    r_bead = r_rim + 12.0
    r_max = R - p.tyre_shoulder_h                 # widest point = start of shoulder roll
    bi, sw, sh = p.tyre_bead_inset, p.tyre_shoulder_w, p.tyre_shoulder_h

    t = np.linspace(0.0, 1.0, n_side)
    side = [(w - bi * (1 - ti ** 0.55), r_bead + (r_max - r_bead) * ti) for ti in t]
    th = np.linspace(0.0, np.pi / 2, n_shoulder)[1:]
    shoulder = [(w - sw + sw * math.cos(a), r_max + sh * math.sin(a)) for a in th]
    tread = [(yy, R) for yy in np.linspace(w - sw, sw, n_tread)[1:-1]]
    outer = side + shoulder                                  # outer face, bead -> tread
    curve = outer + tread + [(w - yy, rr) for yy, rr in reversed(outer)]

    closing = [(p.inner_recess, r_rim), (p.inner_recess, 0.0),
               (w - p.cover_recess - p.cover_dish, 0.0), (w - p.cover_recess, r_rim)]
    return curve, closing


def _revolved_wheel(p: CarParams, x, d, w):
    """Closed solid of revolution about the axle (Y direction) in the ground frame."""
    y0 = p.half_width - w
    zc = d / 2 - p.tyre_squash
    curve, closing = tyre_profile(p, d, w)
    P = lambda yy, rr: V(x, y0 + yy, zc + rr)
    edges = [cq.Edge.makeSpline([P(*q) for q in curve])]
    pts = [curve[-1]] + closing + [curve[0]]
    edges += [cq.Edge.makeLine(P(*a), P(*b)) for a, b in zip(pts, pts[1:])]
    wire = cq.Wire.assembleEdges(edges)
    return cq.Solid.revolve(cq.Face.makeFromWires(wire), 360.0, V(x, 0, zc), V(x, 1, zc))


def wheels(p: CarParams):
    """Right-hand front and rear tyres, already in the ground frame."""
    out = {}
    for name, x, d, w in (("wheels_front", 0.0, p.tyre_f_diameter, p.tyre_f_width),
                          ("wheels_rear", p.xr, p.tyre_r_diameter, p.tyre_r_width)):
        if p.geom_level == "G1":
            out[name] = _revolved_wheel(p, x, d, w)
            continue
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
    """Body, wings and enabled detail parts, Y >= 0 half, in the car frame."""
    parts = {"body": body(p), "front_wing": front_wing(p), "rear_wing": rear_wing(p)}
    if p.halo:
        parts["halo"] = halo(p)
    if p.wake_boards:
        parts["wake_boards"] = wake_boards(p)
    if p.mirrors:
        parts["mirrors"] = mirrors(p)
    if p.suspension:
        parts.update(suspension(p))
    return parts


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
