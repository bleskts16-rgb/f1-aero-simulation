"""FIA 2026 Technical Regulations (Issue 8) Appendix 1 reference volumes, built in
CadQuery step by step as the text describes them, for legality checks of the car.

Car frame, Y >= 0 half (App.1 §1.4: every volume is symmetric about Y = 0), mm.
XF = X (front axle), XR = X - p.xr, XC = X - p.xc. XDIF (final drive axis, which
must lie within XR +-60, Art. 9.7.1) is taken as XR: the model has no gearbox.

Only the volumes written out in the text are built here; together they bound the
whole body (Art. 3.7-3.9), floor, mirrors and wings. Volumes defined by FIA CAD
files alone (the minimum survival-cell volumes RV-CH-*-MIN, RV-DIFF, wheel drums)
are not available: parts that only they could judge are left out of the model.

Interpretations, noted where they are used:
- a trimming "sheet" acts only over its own extrusion range; its first and last
  edges are continued outwards so the trim has no gap at the ends;
- §4.4 R25 edge radius is left out: the corner turns by 4.6 deg, so the radius
  moves the surface by about 0.02 mm;
- §4.22 "combined with all overlapping material discarded" is the symmetric
  difference; the §4.21 tunnel lies inside §4.19, so it is a cut.
"""
import cadquery as cq

V = cq.Vector
BIG = 20000.0          # half-space size [mm]


# ---------------------------------------------------------------- primitives

def _poly(points3):
    return cq.Face.makeFromWires(cq.Wire.makePolygon([V(*q) for q in points3], close=True))


def prism(points2, plane, at, to):
    """Polygon in an axis plane extruded along the third axis from `at` to `to`.
    plane: "xy" (points [X, Y], extruded in Z), "xz" ([X, Z], in Y) or "yz" ([Y, Z], in X)."""
    if plane == "xy":
        pts, d = [(a, b, at) for a, b in points2], V(0, 0, to - at)
    elif plane == "xz":
        pts, d = [(a, at, b) for a, b in points2], V(0, to - at, 0)
    else:
        pts, d = [(at, a, b) for a, b in points2], V(to - at, 0, 0)
    return cq.Solid.extrudeLinear(_poly(pts), d)


def cuboid(p0, p1):
    """Axis-aligned cuboid with interior diagonal p0-p1."""
    lo = [min(a, b) for a, b in zip(p0, p1)]
    hi = [max(a, b) for a, b in zip(p0, p1)]
    return cq.Solid.makeBox(*(h - l for l, h in zip(lo, hi)), V(*lo))


def half_space(a, b, c, keep):
    """Solid on the `keep` side of the plane through points a, b, c.
    keep: a direction pointing into the kept side (only its sign matters)."""
    a, b, c, k = V(*a), V(*b), V(*c), V(*keep)
    n = (b - a).cross(c - a).normalized()
    if n.dot(k) < 0:
        n = -n
    x = (b - a).normalized()
    plane = cq.Plane(origin=a, xDir=x, normal=n)
    return cq.Workplane(plane).rect(2 * BIG, 2 * BIG).extrude(BIG).val()


def trim(vol, a, b, c, keep):
    return vol.intersect(half_space(a, b, c, keep))


def sheet_keep(points2, plane, e0, e1, keep):
    """Region kept by a trimming sheet: the open polyline `points2` in `plane` ("xz":
    [X, Z] extruded in Y, "yz": [Y, Z] extruded in X), extruded from e0 to e1.
    keep="below" keeps material under the sheet, "above" over it. Outside e0..e1 the
    sheet does not exist and nothing is trimmed. The end edges are continued
    horizontally outwards."""
    q = [(-BIG, points2[0][1])] + list(points2) + [(BIG, points2[-1][1])]
    zc = -BIG if keep == "below" else BIG
    region = prism(q + [(BIG, zc), (-BIG, zc)], plane, e0, e1)
    # everything beyond the extrusion range is kept
    lo, hi = min(e0, e1), max(e0, e1)
    if plane == "xz":
        outside = [cuboid((-BIG, -BIG, -BIG), (BIG, lo, BIG)), cuboid((-BIG, hi, -BIG), (BIG, BIG, BIG))]
    else:
        outside = [cuboid((-BIG, -BIG, -BIG), (lo, BIG, BIG)), cuboid((hi, -BIG, -BIG), (BIG, BIG, BIG))]
    return region.fuse(*outside).clean()


def fuse(*shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return out.clean()


# ------------------------------------------------------------ front wing §17-22

def _rs_fw_section_keep():
    """§17.1 RS-FW-SECTION; the volumes keep what lies rearward of it."""
    return half_space((-1250, 100, 0), (-975, 700, 0), (-975, 700, 275), keep=(1, 0, 0))


def _fw_cylinder():
    """§19.3 D825 cylinder on [XF, Z] = [0, 360], Y 600..900."""
    return cq.Solid.makeCylinder(412.5, 300, V(0, 600, 360), V(0, 1, 0))


def rv_fw_profiles():
    v = prism([(0, 60), (100, 60), (675, 150), (675, 275), (400, 275), (0, 125)], "yz", -1250, -500)
    v = v.intersect(_rs_fw_section_keep())                                              # §18.3
    v = trim(v, (-750, 0, 0), (-500, 400, 0), (-500, 400, 275), keep=(-1, 0, 0))       # §18.4
    return trim(v, (-750, 0, 110), (-825, 675, 150), (-500, 675, 225), keep=(0, 0, 1))  # §18.5


def rv_fwep_body():
    v = cuboid((-1250, 600, 50), (-300, 680, 375)).intersect(_rs_fw_section_keep())
    v = v.cut(_fw_cylinder())                                                           # §19.4
    return trim(v, (-675, 675, 375), (-1050, 675, 225), (-1050, 600, 225), keep=(0, 0, -1))


def rv_fwep_ofp():
    v = cuboid((-1250, 750, 50), (-300, 900, 140)).intersect(_rs_fw_section_keep())
    return v.cut(_fw_cylinder())


def rv_fwep_ifp():
    return cuboid((-1250, 600, 50), (-300, 750, 85)).intersect(_rs_fw_section_keep())


def rv_fwep_fence():
    return cuboid((-825, 825, 50), (-300, 900, 200)).cut(_fw_cylinder())


def rv_fw_pylon():
    """§31 row 5 stay volume."""
    return cuboid((-1200, 50, 60), (-1025, 150, 200))


def front_wing_volumes():
    return {"RV-FW-PROFILES": rv_fw_profiles(), "RV-FWEP-BODY": rv_fwep_body(),
            "RV-FWEP-OFP": rv_fwep_ofp(), "RV-FWEP-IFP": rv_fwep_ifp(),
            "RV-FWEP-FENCE": rv_fwep_fence(), "RV-FW-PYLON": rv_fw_pylon()}


# ------------------------------------------------------------- rear wing §25-27

def rv_rw_profiles(xr):
    v = cuboid((xr + 240, 0, 700), (xr + 630, 575, 880))
    return trim(v, (xr + 240, 100, 700), (xr + 240, 575, 750), (xr + 630, 575, 750), keep=(0, 0, 1))


def rv_rwep_body(xr):
    v = prism([(350, 250), (350, 425), (540, 700), (540, 880), (575, 880), (575, 675),
               (375, 375), (375, 250)], "yz", xr + 225, xr + 750)
    v = trim(v, (xr + 225, 575, 650), (xr + 375, 575, 250), (xr + 375, 375, 250), keep=(1, 0, 0))
    v = trim(v, (xr + 750, 575, 625), (xr + 625, 575, 250), (xr + 625, 375, 250), keep=(-1, 0, 0))
    return trim(v, (xr + 450, 425, 250), (xr + 750, 425, 325), (xr + 750, 400, 325), keep=(0, 0, 1))


def rv_rw_pylon(xr):
    """§27, with XDIF taken as XR (see module docstring)."""
    return prism([(xr, 300), (xr, 450), (xr + 250, 775), (xr + 375, 775), (xr + 375, 300)],
                 "xz", 25, 80)


def rear_wing_volumes(xr):
    return {"RV-RW-PROFILES": rv_rw_profiles(xr), "RV-RWEP-BODY": rv_rwep_body(xr),
            "RV-RW-PYLON": rv_rw_pylon(xr),
            "RV-RW-BRACE": cuboid((xr + 400, 0, 310), (xr + 500, 375, 350)),     # §31 row 9
            "RV-RW-FAIRING": cuboid((xr + 250, 0, 725), (xr + 600, 25, 900))}    # §31 row 12


# ------------------------------------------------------------------ floor §4-7

def rv_floor_body(xr):
    R = lambda x: xr + x
    # §4.1-4.3: low part, planform to Y 390, trimmed by the rising outer edge plane
    a = prism([(350, 0), (350, 25), (1400, 390), (R(-1050), 390), (R(-775), 350),
               (R(-475), 240), (R(165), 100), (R(165), 0)], "xy", 0, 275)
    a = trim(a, (1650, 250, 0), (850, 250, 0), (1650, 375, 10), keep=(0, 0, 1))
    # §4.4 R25 edge radius left out (module docstring)
    a = a.intersect(sheet_keep([(1450, 275), (1450, 75), (R(-600), 75), (R(-300), 175),
                                (R(165), 200)], "xz", 0, 400, "below"))          # §4.5-4.7
    a = trim(a, (350, 0, 275), (425, 0, 0), (425, 75, 0), keep=(1, 0, 0))         # §4.8
    # §4.9-4.19: upper part, Z 50..200, out to Y 725
    b = prism([(525, 0), (1200, 725), (R(-350), 725), (R(-350), 390), (R(165), 365),
               (R(165), 0)], "xy", 50, 200)
    b = b.intersect(sheet_keep([(525, 150), (1225, 150), (1625, 75), (R(-600), 75),
                                (R(-300), 175), (R(165), 200)], "xz", 0, 725, "below"))
    b = b.intersect(sheet_keep([(0, 150), (300, 150), (725, 115)], "yz", 525, 1500, "below"))
    b = b.intersect(sheet_keep([(400, 175), (450, 75), (800, 75)], "yz", R(-600), R(-350),
                               "below"))
    # §4.20-4.22: diffuser tunnel, symmetric difference with the upper part
    t = prism([(R(-450), 50), (R(165), 165), (R(165), 50)], "xz", 0, 345)
    rest = t.cut(b)
    b = b.cut(t)
    if rest.Volume() > 1.0:
        b = b.fuse(rest)
    # §4.23-4.25: diffuser side, Y 325..390, material below the sheet discarded
    b = b.intersect(sheet_keep([(R(-350), 50), (R(-325), 50), (R(-175), 100), (R(165), 100)],
                               "xz", 325, 390, "above"))
    return a.fuse(b).clean()                                                      # §4.26


def rv_floor_foot():
    return prism([(650, 650), (650, 875), (725, 875), (1300, 710), (1110, 475), (1000, 600)],
                 "xy", 50, 100)


def rv_floor_board():
    v = prism([(650, 875), (725, 875), (1300, 715), (1500, 650), (1500, 600), (650, 775)],
              "xy", 70, 375)
    return trim(v, (1500, 675, 200), (1500, 600, 200), (800, 875, 375), keep=(0, 0, -1))


def rv_floor_bib(xc):
    return prism([(425, 0), (425, 85), (800, 150), (xc - 700, 150), (xc - 700, 0)], "xy", 0, 50)


def floor_volumes(xr, xc):
    return {"RV-FLOOR-BODY": rv_floor_body(xr), "RV-FLOOR-FOOT": rv_floor_foot(),
            "RV-FLOOR-BOARD": rv_floor_board(), "RV-FLOOR-BIB": rv_floor_bib(xc)}


# ----------------------------------------------------------- body §8, §11-13, §15-16

def _y_cylinder(xc0, zc0, diameter, y0, y1):
    return cq.Solid.makeCylinder(diameter / 2, y1 - y0, V(xc0, y0, zc0), V(0, 1, 0))


def rv_body_front(xc):
    """§8: nose + forward chassis + mid chassis (RV-NOSE / CH-FRONT / CH-MID)."""
    C = lambda x: xc + x
    a = _y_cylinder(C(-1000), -4853, 11000, 0, 400).intersect(
        prism([(C(-875), 195), (C(-875), 645), (-1300, 645), (-1300, 125), (-1000, 125),
               (C(-1830), 225)], "xz", 0, 400))                                  # §8.1-8.4
    b = prism([(C(-875), 0), (C(300), 0), (C(300), 970), (C(0), 970), (C(0), 770),
               (C(-350), 770), (C(-350), 645), (C(-875), 645)], "xz", 0, 400)    # §8.5-8.6
    v = a.fuse(b).intersect(prism([(-1300, 0), (-1300, 150), (C(-1830), 200), (C(-1015), 265),
                                   (C(-400), 400), (C(300), 400), (C(300), 0)], "xy", 0, 970))
    return v.cut(cuboid((C(0), 150, 0), (C(300), 400, 970))).clean()             # §8.11-8.12


def rv_dri_cool(xa, xc):
    """§11: cuboid on XA, intersected with the D11040 cylinder."""
    return cuboid((xa + 100, 0, 550), (xa + 525, 100, 675)).intersect(
        _y_cylinder(xc - 1000, -4855, 11040, 0, 100))


def rv_sidepod():
    return prism([(900, 0), (900, 275), (1200, 715), (1300, 715), (1300, 0)], "xy", 50, 600)


def rv_ec(xr, xc):
    R, C = (lambda x: xr + x), (lambda x: xc + x)
    v1 = prism([(1300, 0), (1300, 715), (R(-1300), 715), (R(-50), 225), (R(-50), 0)], "xy", 50, 600)
    v1 = trim(v1, (C(0), 0, 600), (C(0), 725, 600), (R(-50), 0, 350), keep=(0, 0, -1))   # §13.3
    v2 = prism([(C(300), 50), (R(-50), 50), (R(-50), 600), (C(500), 970), (C(300), 970)],
               "xz", 0, 400)                                                              # §13.4-5
    v3 = prism([(R(-160), 760), (R(-395), 760), (C(500), 970), (C(500), 500), (R(-160), 500)],
               "xz", 0, 25)                                                               # §13.6-7
    v4 = cuboid((C(0), 150, 50), (C(300), 400, 970))                                      # §13.8
    v = fuse(v1, v2, v3, v4)
    return trim(v, (R(-1300), 715, 50), (R(-1300), 715, 600), (R(-50), 225, 50), keep=(0, -1, 0))


def rv_tail(xr):
    """§15, with XDIF taken as XR (module docstring)."""
    R = lambda x: xr + x
    side = prism([(R(-110), 0), (R(-110), 480), (R(10), 480), (R(350), 380), (R(760), 380),
                  (R(760), 175), (R(350), 175), (R(10), 0)], "xz", 0, 125)
    plan = prism([(R(-110), 0), (R(760), 0), (R(760), 60), (R(350), 60), (R(10), 125),
                  (R(-110), 125)], "xy", 0, 480)
    return side.intersect(plan)


def body_volumes(xa, xc, xr):
    """Art. 3.7-3.9: front bodywork, sidepod, engine cover, tail, tailpipe."""
    return {"RV-BODY-FRONT": rv_body_front(xc), "RV-DRI-COOL": rv_dri_cool(xa, xc),
            "RV-SIDEPOD": rv_sidepod(), "RV-EC": rv_ec(xr, xc), "RV-TAIL": rv_tail(xr),
            "RV-TAILPIPE": cuboid((xr - 55, 0, 350), (xr + 250, 75, 550))}            # §16


# -------------------------------------------------------------------- mirrors §10

def mirror_volumes(xc):
    C = lambda x: xc + x
    return {"RV-MIRROR-BODY": prism([(C(-830), 470), (C(-730), 470), (C(-650), 680),
                                     (C(-750), 680)], "xy", 640, 720),
            "RV-MIRROR-ISTAY": cuboid((C(-830), 175, 600), (C(-730), 470, 665)),   # §31 row 2
            "RV-MIRROR-RSTAY": cuboid((C(-765), 530, 500), (C(-450), 630, 640))}   # §31 row 3
