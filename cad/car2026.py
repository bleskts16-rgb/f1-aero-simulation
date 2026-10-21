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

from cad import regvol
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


# ------------------------------------------------- G1 design tables (clean-cad)
# Sources: FIA 2026 F1 Technical Regulations Issue 8 (2024-06-24), Art. 3.10 / 3.11
# and Appendix 1 (§17-22 reference volumes, table of reference surfaces RS-*).
# Coordinates: X from the axle named in the comment, Z from the reference plane.

# Rear-wing endplate must obscure RS-RWEP when seen from the side (App.1 RS #12):
RS_RWEP = ((310, 870), (740, 870), (740, 700), (630, 350), (400, 275), (230, 700),
           (245, 800))                                          # [XR, Z]
# Part beside the wing: side outline (dX from XR, Z, corner radius), Y 545..560.
# RV-RWEP-BODY (App.1 §26) allows Y 540..575 only above Z ~700, so this part stays
# above Z 712; the lower endplate (below) overlaps its bottom edge (J1, no step).
G1_RW_EP_UPPER = ((228.0, 878.0, 40.0), (745.0, 878.0, 20.0), (745.0, 712.0, 15.0),
                  (228.0, 712.0, 10.0))         # front >= XR 225 (§26.2)
G1_RW_EP_UPPER_Y = (545.0, 560.0)
# Lower part: follows the RV-RWEP-BODY band, which leans inboard from Y 540..575 at
# Z 700 to Y 350..375 below Z 375 (2026 endplates fold in under the wing). Horizontal
# stadium sections (15 mm thick, bull-nosed ends) through these keyframes, PCHIP
# between. Y centre = middle of the band; the X ends lie between the RS-RWEP edges
# ([400,275]-[230,700] front, [630,350]-[740,700] rear, which must be covered from the
# side) and the §26.3 trimming planes (front, rear, bottom).
#   (Z car frame, X front from XR, X rear from XR, Y centre)
# (X ends ~35 % into the allowed window; top rows kept inside the upper part's outline
# and under the XR 750 limit; bottom rows long enough that the loft does not bulge)
G1_RW_EP_LOWER = ((715.0, 228.5, 743.0, 552.5), (690.0, 229.0, 742.0, 554.0),
                  (660.0, 237.3, 739.4, 538.7), (620.0, 253.0, 726.6, 511.5),
                  (570.0, 272.6, 710.5, 477.6), (520.0, 292.1, 694.5, 443.7),
                  (470.0, 311.7, 678.4, 409.7), (420.0, 331.2, 662.4, 377.5),
                  (380.0, 346.9, 649.5, 364.2), (340.0, 362.5, 618.8, 362.5),
                  (300.0, 378.2, 560.0, 362.5), (272.0, 389.1, 520.0, 362.5))
G1_RW_EP_THICK = 15.0
# Twin pylons in RV-RW-PYLON (App.1 §27: Y 25..80, not on the centreline), side
# outline (dX from XR, Z, corner radius), from the tail up into the main plane.
G1_RW_PYLON = ((215.0, 305.0, 0.0), (262.0, 718.0, 12.0), (365.0, 718.0, 12.0),
               (365.0, 305.0, 0.0))
G1_RW_PYLON_Y = (28.0, 43.0)
# Wing elements along the span (clean-cad W1), fitted inside RV-RW-PROFILES (§25):
# the lower limit rises from Z 700 (Y <= 100) to Z 750 (Y 575), the top is Z 880, so
# the stack rises and flattens outboard. (Y, chord scale, main, flap 1, flap 2 angle
# [deg], main LE Z); 2D margins 4..9 mm, also with the flaps at -25 deg (X-mode).
G1_RW_SPAN = ((0.0, 1.00, 2.0, 22.0, 45.0, 729.3), (200.0, 1.00, 2.0, 21.0, 42.0, 736.9),
              (400.0, 0.92, 3.0, 19.0, 37.0, 753.1), (552.0, 0.86, 3.0, 17.0, 33.0, 767.2))
G1_RW_STATIONS = 9

# Front wing (all [XF, ...]). Everything lies aft of RS-FW-SECTION (§17), the
# vertical plane through [-1250, 100] and [-975, 700]: X >= fw_section_x(Y).
RS_FW_SECTION = ((-1250.0, 100.0), (-975.0, 700.0))           # [XF, Y]
FW_SECTION_MARGIN = 3.0
FW_SPAN_G1 = 670.0                    # profiles half span, RV-FW-PROFILES reaches Y 675
# Profiles along the span (clean-cad W1), fitted inside RV-FW-PROFILES (App.1 §18):
# at the centre the volume is only Z 60..125 high and ends at XF -750, so the stack
# is short and flat there; outboard it grows, twists up and rises with the volume's
# floor (Z 60 -> 150 at Y 675, and the §18.5 plane rising rearwards), then tapers at
# the tip. (Y, chord scale, main, flap 1, flap 2 angle [deg], main LE Z); the LE X
# follows `fw_sweep`. 2D margins >= 2 mm (tightest at the centre top/bottom).
G1_FW_SPAN = ((0.0, 0.64, -2.0, 1.0, 4.0, 84.1), (150.0, 0.76, 0.0, 7.0, 14.0, 99.9),
              (300.0, 0.86, 2.0, 11.0, 20.0, 123.8), (450.0, 0.84, 3.0, 12.0, 21.0, 150.7),
              (560.0, 0.72, 2.0, 10.0, 18.0, 169.9), (670.0, 0.62, 2.0, 10.0, 18.0, 181.7))
G1_FW_STATIONS = 13
# Endplate = body + inboard footplate + outboard footplate + fence (Art. 3.10.6).
# Body: Y 662..678 in RV-FWEP-BODY (Y 600..680, Z 50..375, top trimmed by the plane
# through [-1050, 225] and [-675, 375]); side outline (XF, Z, corner radius), then
# trimmed by the D825 wheel cylinder at [XF, Z] = [0, 360] (§19.3).
G1_FW_EP_BODY_Y = (662.0, 678.0)
G1_FW_EP_BODY = ((-980.0, 52.0, 0.0), (-980.0, 250.0, 25.0), (-675.0, 372.0, 60.0),
                 (-301.0, 372.0, 0.0), (-301.0, 52.0, 0.0))        # rear limit XF -300 (§19.1)
# Footplates, plan view; the front edge follows RS-FW-SECTION, the rear is trimmed by
# the wheel cylinder. Inboard: RV-FWEP-IFP Y 600..750, Z 50..85. Outboard: RV-FWEP-OFP
# Y 750..900, Z 50..140 (the tip that sticks out ahead of the front tyre).
G1_FW_IFP = (600.0, 752.0, 52.0, 80.0)              # Y0, Y1, Z0, Z1
G1_FW_OFP = (748.0, 899.0, 52.0, 74.0)
G1_FW_FP_REAR = -300.0
# Fence: RV-FWEP-FENCE X -825..-300, Y 825..900, Z 50..200; a vertical plate at the
# outer tip, side outline (XF, Z, corner radius), convex (no concave radius < 250).
G1_FW_FENCE_Y = (882.0, 897.0)
G1_FW_FENCE = ((-820.0, 52.0, 0.0), (-820.0, 140.0, 40.0), (-690.0, 198.0, 60.0),
               (-380.0, 198.0, 40.0), (-300.0, 130.0, 0.0), (-300.0, 52.0, 0.0))
# Coverage the endplate must provide (Art. 3.10.6 g, h)
RS_FWEP_TOP = ((-880, 895), (-325, 895), (-325, 670), (-980, 670))        # [XF, Y], from above
RS_FWEP_SIDE = ((-975, 55), (-975, 225), (-650, 370), (-420, 370), (-410, 225),
                (-305, 55))                                               # [XF, Z], from inboard


# Helmet (clean-cad L6: no visible sphere). Keyframes along u = -1 (front) .. +1
# (rear) over a 300 mm length centred where the G0 sphere was: (u, half width,
# Z bottom, Z top, superellipse exponent). Steep visor face at the front, crown at
# u ~ 0, gentler fall to the rear; the bottom stays inside the chassis (no gap).
G1_HELMET_LENGTH = 300.0
# The end stations are small and sit at mid height, so the nose and tail close as
# rounded caps (a first draft ending at full height gave flat end faces and a
# vertical wall at the front). The bottom is buried ~50 mm below the G1 crown
# (Z 650..690 here) and the end caps sit clearly above it: a helmet bottom within
# a few mm of the crown made the fuse invalid (near-tangent surfaces).
G1_HELMET = ((-1.00, 12.0, 705.0, 760.0, 2.0), (-0.90, 62.0, 610.0, 805.0, 2.2),
             (-0.65, 100.0, 600.0, 834.0, 2.4), (-0.25, 117.0, 600.0, 848.0, 2.4),
             (0.15, 120.0, 600.0, 846.0, 2.4), (0.55, 112.0, 605.0, 828.0, 2.4),
             (0.85, 80.0, 615.0, 795.0, 2.2), (1.00, 15.0, 715.0, 748.0, 2.0))


# Body spine (nose -> survival cell -> engine cover -> tail), clean-cad D1-D4.
# Every station is the same rounded section with ONE shoulder crease (L4): flat
# bottom, flank flaring out to the shoulder knuckle, roof falling to a crown that
# is level at Y = 0. Columns: (anchor, dX, Z bottom, bottom half width, Z shoulder,
# shoulder half width, Z roof edge, roof half width, Z crown); anchor F/C/R = front
# axle / cockpit rear XC / rear axle. Envelope (bottom..crown, shoulder width)
# follows the G0 spine, so the regulation boxes and the suspension anchors hold.
G1_BODY = (("F", -1250, 150, 20, 180, 38, 205, 25, 212),
           ("F", -1150, 135, 45, 185, 75, 228, 45, 240),
           ("F", -900, 130, 70, 215, 110, 285, 70, 302),
           ("F", -500, 145, 95, 280, 150, 395, 95, 420),
           ("F", -100, 160, 120, 360, 190, 510, 120, 540),
           ("F", 500, 60, 170, 430, 232, 590, 150, 620),
           ("F", 900, 10, 210, 470, 265, 620, 170, 640),
           ("C", -450, 10, 230, 490, 290, 640, 190, 655),
           ("C", -230, 10, 235, 520, 300, 680, 200, 700),
           ("C", -80, 10, 230, 560, 285, 790, 170, 830),
           ("C", 20, 10, 215, 590, 260, 900, 140, 940),
           ("C", 320, 10, 190, 560, 230, 840, 120, 880),
           ("R", -700, 30, 150, 440, 190, 600, 110, 640),
           ("R", -200, 80, 110, 340, 140, 450, 80, 480),
           ("R", -50, 120, 85, 300, 110, 380, 65, 400),
           ("R", 350, 230, 40, 290, 60, 322, 35, 330))
# corner radii of the section: bottom edge, shoulder knuckle (D3: 5-10 mm), roof
# edge, crown; points per straight run / per arc (same at every station, D2)
G1_BODY_R = (30.0, 10.0, 60.0, 40.0)
G1_BODY_N_RUN, G1_BODY_N_ARC = 6, 6
# Stations are cosine-spaced (dense at nose and tail, where the table changes
# fastest). Swept (clean-cad D5): uniform 25 self-intersected (BRepAlgoAPI_Check)
# with a 19.9 mm tail bulge, uniform 41 still self-intersected, cosine 25 was
# clean with 10.3 mm, cosine 33 clean with 1.1 mm.
G1_BODY_STATIONS = 33


# Floor (App.1 §4). RV-FLOOR-BODY has a low part (Z >= 0) only inside the §4.1
# planform and an upper part starting at Z 50 out to Y 725 (§4.9), so the G1 floor
# is flat on Z = 0 inside the §4.1 edge, steps up along it with a wall, and the outer
# floor runs at Z 50. Behind the kick-up the diffuser roof follows the §4.20 tunnel
# roof and a fence stands outside the tunnel (Y > 345) above the §4.23 sheet.
# Points (X, Y, anchor): anchor F = from the front axle, R = from the rear axle.
G1_FLOOR_LOW_EDGE = ((350.0, 25.0, "F"), (1400.0, 390.0, "F"), (-1050.0, 390.0, "R"),
                     (-775.0, 350.0, "R"), (-475.0, 240.0, "R"), (165.0, 100.0, "R"))   # §4.1
G1_FLOOR_UPPER = ((525.0, 0.0, "F"), (1200.0, 725.0, "F"), (-350.0, 725.0, "R"),
                  (-350.0, 390.0, "R"), (165.0, 365.0, "R"), (165.0, 0.0, "R"))       # §4.9
G1_FLOOR_EDGE_PLANE = ((1650.0, 250.0, 0.0), (850.0, 250.0, 0.0), (1650.0, 375.0, 10.0))  # §4.3
G1_FLOOR_FRONT = 430.0          # XF of the flat bottom's front edge (§4.8 trims at ~XF 425)
G1_FLOOR_MARGIN = 3.0           # inside every limit
G1_FLOOR_STEP_Z = 50.0          # outer floor underside
G1_FLOOR_WALL = 10.0            # step wall thickness, inside the §4.1 edge
G1_FLOOR_WALL_START = 640.0     # XF where the upper planform first reaches past the §4.1 edge
G1_FLOOR_KICK = (-700.0, -600.0)                       # XR: flat bottom -> diffuser roof
G1_DIFF_ROOF = ((-600.0, 50.0), (-450.0, 50.0), (165.0, 165.0))  # [XR, Z] underside (§4.20)
G1_DIFF_SHEET = ((-400.0, 50.0), (-325.0, 50.0), (-175.0, 100.0), (165.0, 100.0))  # §4.23
G1_DIFF_FENCE_Y = (347.0, 362.0)

# Floor boards (the G1 "wake boards"): RV-FLOOR-BOARD (§6) is a band at Y 600..875 that
# leans inboard rearwards, Z 70 up to the §6.3 plane; the vanes stand on a foot plate
# in RV-FLOOR-FOOT (§5, Z 50..100) that overlaps the outer floor. Slots between the
# vanes run parallel to the sloping top.
G1_WB_LE = (760.0, 805.0)                    # leading edge [XF, Y], middle of the band
G1_WB_YAW = 13.0                             # inward alignment of the band [deg]
G1_WB_TOP = ((800.0, 375.0), (1500.0, 200.0))       # §6.3 top plane [XF, Z]; Z <= 375
G1_WB_TOP_MARGIN = 3.0
G1_WB_FOOT = ((656.0, 656.0), (656.0, 869.0), (724.0, 869.0), (1291.0, 708.0),
              (1109.0, 483.0), (1001.0, 606.0))     # §5.1 outline, inset ~5 mm [XF, Y]
G1_WB_FOOT_Z = (52.0, 70.0)

# Mirrors: housing inside RV-MIRROR-BODY (§10: Z 640..720, a parallelogram whose long
# side leans 20.9 deg off Y), stalk inside RV-MIRROR-ISTAY (§31 row 2: XC -830..-730,
# Y 175..470, Z 600..665). Housing = ellipsoid aligned with the parallelogram.
G1_MIRROR_CENTRE = (1090.0, 575.0, 680.0)           # [X, Y, Z] = parallelogram centre
G1_MIRROR_AXES = (90.0, 40.0, 28.0)                 # along the long side, across, Z
G1_MIRROR_LEAN = math.atan2(80.0, 210.0)            # long side direction from Y [rad]
G1_MIRROR_STALK = ((1050.0, 150.0, 605.0), (1075.0, 545.0, 668.0))   # chassis -> inside housing


def fw_section_x(y):
    """X of RS-FW-SECTION at |Y| = y (the swept front limit of the front wing)."""
    (x0, y0), (x1, y1) = RS_FW_SECTION
    return x0 + (y - y0) * (x1 - x0) / (y1 - y0)


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


def _spine_envelope(p: CarParams):
    """(X, half width, z bottom, z top) of the spine, for chassis_point."""
    if p.geom_level == "G1":
        k = g1_body_table(p)
        return k[:, [0, 4, 1, 7]]
    return np.array([s[:4] for s in _spine_sections(p)], dtype=float)


def chassis_point(p: CarParams, x, fy, fz):
    """A point inside the spine at station x (car frame): fy = fraction of the local
    half width, fz = fraction of the local height. fy <= 0.6 with 0.15 <= fz <= 0.85
    is inside the spine section (G0 superellipse, G1 crease section), so members
    anchored there overlap the body (cad.qa.attached checks it)."""
    sec = _spine_envelope(p)
    a, z0, z1 = (np.interp(x, sec[:, 0], sec[:, i]) for i in (1, 2, 3))
    return V(x, fy * a, z0 + fz * (z1 - z0))


def g1_body_table(p: CarParams):
    """G1_BODY with absolute X: columns X, zb, ab, zsh, ash, zt, at, zc."""
    base = {"F": 0.0, "C": p.xc, "R": p.xr}
    return np.array([(base[a] + dx, *rest) for a, dx, *rest in G1_BODY], dtype=float)


def _fixed_count_corners(verts, radii, n_run, n_arc):
    """Open polyline verts[0] -> verts[-1] with every interior vertex replaced by a
    tangent arc of its radius. Each straight run gets n_run points and each arc
    n_arc + 1, whatever the geometry, so sections built from the same vertex list
    always have the same point count and the corners land on the same indices
    (clean-cad D2, D3)."""
    P = np.asarray(verts, dtype=float)
    arcs = []
    for i in range(1, len(P) - 1):
        d0 = P[i] - P[i - 1]
        d1 = P[i + 1] - P[i]
        l0, l1 = np.linalg.norm(d0), np.linalg.norm(d1)
        d0, d1 = d0 / l0, d1 / l1
        turn = math.atan2(d0[0] * d1[1] - d0[1] * d1[0], float(d0 @ d1))
        t = min(radii[i - 1] * math.tan(abs(turn) / 2), 0.45 * l0, 0.45 * l1)
        a, b = P[i] - d0 * t, P[i] + d1 * t
        if abs(turn) < 1e-6:
            arcs.append(np.linspace(a, b, n_arc + 1))
            continue
        r = t / math.tan(abs(turn) / 2)
        sgn = 1.0 if turn > 0 else -1.0
        c = a + sgn * r * np.array([-d0[1], d0[0]])
        v = a - c
        ang = turn * np.arange(n_arc + 1) / n_arc
        arcs.append(c + np.column_stack([v[0] * np.cos(ang) - v[1] * np.sin(ang),
                                         v[0] * np.sin(ang) + v[1] * np.cos(ang)]))
    out = []
    start = P[0]
    for arc in arcs:
        out += list(np.linspace(start, arc[0], n_run, endpoint=False))
        out += list(arc[:-1])
        start = arc[-1]
    out += list(np.linspace(start, P[-1], n_run))
    return np.array(out)


def g1_body_sections(p: CarParams, n=None):
    """(x, (m, 2) array of (y, z)) half sections of the G1 spine at n cosine-spaced
    stations, every column PCHIP-interpolated along X (clean-cad D1)."""
    from scipy.interpolate import PchipInterpolator
    n = n or G1_BODY_STATIONS
    k = g1_body_table(p)
    f = [PchipInterpolator(k[:, 0], k[:, i]) for i in range(1, 8)]
    out = []
    x0, x1 = k[0, 0], k[-1, 0]
    for x in x0 + (x1 - x0) * 0.5 * (1 - np.cos(np.linspace(0.0, np.pi, n))):
        zb, ab, zsh, ash, zt, at, zc = (float(fi(x)) for fi in f)
        verts = [(0.0, zb), (ab, zb), (ash, zsh), (at, zt), (0.4 * at, zc), (0.0, zc)]
        out.append((float(x), _fixed_count_corners(verts, G1_BODY_R, G1_BODY_N_RUN, G1_BODY_N_ARC)))
    return out


def _shared_params(sections):
    """One spline parameter list for all sections: the mean of their normalised
    chord-length parameters. Splines interpolated with their own parameters get
    different knot vectors, and ThruSections then merges them into a surface with
    ~23x the poles (35208 vs 1512 here), which made the body booleans crawl."""
    u = []
    for pts in sections:
        d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        u.append(d / d[-1])
    return list(np.mean(u, axis=0))


G1_SPINE_OVERLAP = 5.0   # sections run this far past Y = 0 (see _g1_spine)


def _g1_spine(p: CarParams):
    """G1 spine lofted through g1_body_sections: each section is a spline through
    its points, extended G1_SPINE_OVERLAP mm past Y = 0 along its level ends (D4)
    and closed by a line there; all splines share one parameterisation
    (compatible sections, light surface). body() trims at Y = 0 with a box, so the
    symmetry face is a true plane: with the loft's own Y = 0 face (a B-spline
    lofted from lines) fusing the half body with its mirror never finished."""
    secs = g1_body_sections(p)
    d = G1_SPINE_OVERLAP
    secs = [(x, np.vstack([[-d, pts[0, 1]], pts, [-d, pts[-1, 1]]])) for x, pts in secs]
    params = _shared_params([pts for _, pts in secs])
    wires = []
    for x, pts in secs:
        q = [V(x, y, z) for y, z in pts]
        wires.append(cq.Wire.assembleEdges([cq.Edge.makeSpline(q, parameters=params),
                                            cq.Edge.makeLine(q[-1], q[0])]))
    ts = BRepOffsetAPI_ThruSections(True, False, 1e-6)
    ts.SetParType(Approx_Centripetal)
    for w in wires:
        ts.AddWire(w.wrapped)
    ts.Build()
    solid = cq.Solid(ts.Shape())
    LOFT_LOG.append(("spine", solid, wires))
    return solid


def body(p: CarParams):
    xc, xr = p.xc, p.xr
    # Nose + survival cell inside RV-BODY-FRONT (App.1 §8: |Y| <= 150..400, Z <= 645),
    # then engine cover / airbox inside RV-EC (App.1 §13: Z <= 970 at XC..XC+300)
    # and the tail inside RV-TAIL (App.1 §15). One loft avoids a slow boolean.
    spine = _g1_spine(p) if p.geom_level == "G1" else _loft(_spine_sections(p), label="spine")
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
    if p.geom_level == "G1":
        # G1: the helmet is its own part (see helmet()); fusing the half helmet into
        # the G1 crease spine left an invalid face (both carry a face on Y = 0)
        helmet = []
    else:
        # helmet: a sphere built from the same half sections, so it mirrors cleanly
        r, hx, hz = 125.0, xc - 450, 720.0
        helmet = [_loft([(hx - r * math.cos(f), r * math.sin(f), hz - r * math.sin(f),
                          hz + r * math.sin(f), 2.0) for f in np.radians(np.linspace(12, 168, 9))],
                        label="helmet")]

    extra = []
    if p.geom_level == "G1":
        extra.append(airbox(p))
    # nothing of the sprung body may hang below Z=0 (2.7a); also trims loft overshoot
    above_ref = _box(-2000, 6000, 0, 1000, 0, 1500)
    out = _fuse(spine, sidepods, *helmet, *floor_parts(p), *extra).intersect(above_ref)
    if p.geom_level == "G1":
        out = out.cut(airbox_mouth(p))
    return out


def floor_parts(p: CarParams):
    """Floor plate, diffuser ramp and diffuser side fence that `body` fuses in; kept
    apart so the floor can be checked against RV-FLOOR-* (cad/regvol.py)."""
    if p.geom_level != "G0":
        return floor_parts_g1(p)
    xr = p.xr
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
    return [plate, ramp, fence]


def _floor_x(p, x, anchor):
    return x + (p.xr if anchor == "R" else 0.0)


def floor_parts_g1(p: CarParams):
    """G1 floor inside RV-FLOOR-BODY (see the G1_FLOOR_* table): flat bottom, step wall,
    outer floor at Z 50, kick-up, diffuser roof on the tunnel roof line, fence."""
    xr, t, m, w = p.xr, p.floor_thickness, G1_FLOOR_MARGIN, G1_FLOOR_WALL
    R = lambda x: xr + x
    ex = [_floor_x(p, x, a) for x, _, a in G1_FLOOR_LOW_EDGE]
    ey = [y - m for _, y, _ in G1_FLOOR_LOW_EDGE]
    edge = lambda x: float(np.interp(x, ex, ey))          # §4.1 edge, minus the margin
    xk0, xk1 = R(G1_FLOOR_KICK[0]), R(G1_FLOOR_KICK[1])

    def along(x0, x1, dy=0.0):
        """Edge polyline from x0 to x1 (its own vertices in between), shifted by dy."""
        xs = [x0] + [x for x in ex if x0 < x < x1] + [x1]
        return [(x, edge(x) + dy) for x in xs]

    # the low part's outer edge rises above Y 250 (§4.3): trim everything below it
    lift = regvol.half_space(*G1_FLOOR_EDGE_PLANE, keep=(0, 0, 1))
    flat = _extrude_xy([(G1_FLOOR_FRONT, 0)] + along(G1_FLOOR_FRONT, xk0) + [(xk0, 0)], 0, t)
    band = along(G1_FLOOR_WALL_START, xk1)
    wall = _extrude_xy(band + [(x, y - w) for x, y in reversed(band)], 0, G1_FLOOR_STEP_Z + t)
    # kick-up: a ramp profile cut to the planform under the edge
    kick = _extrude_xz([(xk0 - 1, 0), (xk1, G1_FLOOR_STEP_Z), (xk1, G1_FLOOR_STEP_Z + t),
                        (xk0 - 1, t)], 0, 800)
    kick = kick.intersect(_extrude_xy([(xk0 - 1, 0)] + along(xk0 - 1, xk1) + [(xk1, 0)], -1, 200))
    low = _fuse(flat, wall, kick).intersect(lift)

    # outer floor at Z 50: upper planform minus what lies inside the wall's inner face
    up = [(_floor_x(p, x, a), y) for x, y, a in G1_FLOOR_UPPER]
    up_front = _extrude_xy(up, G1_FLOOR_STEP_Z, G1_FLOOR_STEP_Z + t).intersect(
        _box(0, xk1, 0, 1000, 0, 200))
    core = _extrude_xy([(0, -10)] + along(0, xk1, -w / 2) + [(xk1, -10)], 0, 200)
    outer = up_front.cut(core)
    yu = up[2][1] - m                                       # 725 - margin, out to XR -350
    outer_rear = _extrude_xy([(xk1, 380), (xk1, yu), (up[2][0], yu), (up[3][0], 380)],
                             G1_FLOOR_STEP_Z, G1_FLOOR_STEP_Z + t)

    # diffuser roof: underside on the tunnel roof (+1 mm), cut to the upper planform
    under = [(R(x), z + 1.0) for x, z in G1_DIFF_ROOF]
    roof = _extrude_xz(under + [(x, z + t) for x, z in reversed(under)], 0, 800)
    roof = roof.intersect(_extrude_xy([(xk1, 0), (xk1, 390 - m), (R(-350), 390 - m),
                                       (R(165), 365 - m), (R(165), 0)], 0, 400))
    # fence outside the tunnel: from the §4.23 sheet (+1 mm) up into the roof
    roof_z = lambda x: float(np.interp(x, [q[0] for q in under], [q[1] for q in under]))
    sheet = [(R(x), z + 1.0) for x, z in G1_DIFF_SHEET]
    fence = _extrude_xz(sheet + [(x, roof_z(x) + 8.0) for x, _ in reversed(sheet)],
                        *G1_DIFF_FENCE_Y)
    return [low, outer, outer_rear, roof, fence]


def helmet(p: CarParams):
    """G1 helmet as a separate part (Y >= 0, car frame) sitting into the body."""
    return _loft(helmet_sections(p), label="helmet")


def helmet_sections(p: CarParams, n=17):
    """G1 helmet as half superellipse sections (X, a, z0, z1, exponent) at n stations,
    cosine-spaced so the rounded front and rear get more of them; every keyframe
    column PCHIP-interpolated (clean-cad D1), same 13 points per section (D2)."""
    from scipy.interpolate import PchipInterpolator
    k = np.array(G1_HELMET)
    f = [PchipInterpolator(k[:, 0], k[:, i]) for i in range(1, 5)]
    hx = p.xc - 450.0
    out = []
    for u in -np.cos(np.linspace(0.0, np.pi, n)):
        a, z0, z1, e = (float(fi(u)) for fi in f)
        out.append((hx + u * G1_HELMET_LENGTH / 2, a, z0, z1, e))
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


def fw_sweep(p: CarParams, y, soft=10.0):
    """Rearward shift of the whole front-wing section stack at |Y| = y, so its
    leading edge stays FW_SECTION_MARGIN aft of RS-FW-SECTION. Zero inboard; a
    softplus avoids a kink where the sweep starts."""
    need = fw_section_x(y) + FW_SECTION_MARGIN - p.fw_le[0]
    return soft * math.log1p(math.exp(need / soft))


def span_layouts(table, chords, le_x, span, n, gap, overlap, flap_delta):
    """[(y, [(le_x, le_z, chord, angle) per element])] at n cosine-spaced span stations
    (denser at the root and the tip, clean-cad W1). `table` rows are (Y, chord scale,
    main, flap 1, flap 2 angle, main LE Z), PCHIP-interpolated; `le_x(y)` gives the
    main-plane LE X. Each station is laid out by `_wing_layout`, so every station has
    the set slot gap."""
    from scipy.interpolate import PchipInterpolator
    k = np.array(table, dtype=float)
    f = [PchipInterpolator(k[:, 0], k[:, i]) for i in range(1, 6)]
    out = []
    for y in span / 2 * (1 - np.cos(np.linspace(0.0, np.pi, n))):
        sc, a0, a1, a2, zle = (float(fi(y)) for fi in f)
        _, lay = _wing_layout((le_x(y), zle), [c * sc for c in chords], (a0, a1, a2),
                              y, y + 1.0, gap, overlap, flap_delta)
        out.append((float(y), lay))
    return out


def _span_elements(layouts, label):
    """One loft per element through its sections at every station of `layouts`."""
    elems = []
    for i in range(len(layouts[0][1])):
        wires = [_wing_section(*lay[i], y)[0] for y, lay in layouts]
        ts = BRepOffsetAPI_ThruSections(True, False, 1e-6)
        ts.SetParType(Approx_Centripetal)
        for w in wires:
            ts.AddWire(w.wrapped)
        ts.Build()
        solid = cq.Solid(ts.Shape())
        LOFT_LOG.append((f"{label} element {i}", solid, wires))
        elems.append(solid)
    return elems


def fw_span_layouts(p: CarParams):
    return span_layouts(G1_FW_SPAN, p.fw_chords, lambda y: p.fw_le[0] + fw_sweep(p, y),
                        FW_SPAN_G1, G1_FW_STATIONS, p.fw_gap, p.fw_overlap, p.fw_flap_delta)


def rw_span_layouts(p: CarParams):
    return span_layouts(G1_RW_SPAN, p.rw_chords, lambda y: p.xr + p.rw_le[0],
                        p.rw_span_half, G1_RW_STATIONS, p.rw_gap, p.rw_overlap, p.rw_flap_delta)


def _wheel_cut():
    """D825 cylinder on the front axle (App.1 §19.3) that trims the endplate."""
    return cq.Solid.makeCylinder(412.5, 1000, V(0, 0, 360), V(0, 1, 0))


def front_wing(p: CarParams):
    if p.geom_level == "G1":
        return front_wing_g1(p)
    s = p.fw_span_half
    elems = _wing_stack(p.fw_le, p.fw_chords, p.fw_angles, 0, s,
                        p.fw_gap, p.fw_overlap, p.fw_flap_delta)
    # Endplate in RV-FWEP-BODY (App.1 §19): Y 600..680, cut by an R412.5 cylinder
    # around [XF, Z] = [0, 360] for front-wheel clearance
    plate = _box(-1250, -430, s - 10, s + 2, 40, 330).cut(_wheel_cut())
    return _fuse(*elems, plate)


def fw_footplate_outline(y0, y1):
    """Plan outline (XF, Y) of a footplate between y0 and y1: front edge on
    RS-FW-SECTION (+ margin), rear at G1_FW_FP_REAR, small rounded outer corners."""
    xf0 = fw_section_x(y0) + FW_SECTION_MARGIN
    xf1 = fw_section_x(y1) + FW_SECTION_MARGIN
    return _rounded_outline([(xf0, y0, 0.0), (xf1, y1, 5.0), (G1_FW_FP_REAR, y1, 15.0),
                             (G1_FW_FP_REAR, y0, 0.0)])


def front_wing_g1(p: CarParams):
    """G1 front wing after the FIA 2026 concept and Art. 3.10: three profiles lofted
    through the G1_FW_SPAN table inside RV-FW-PROFILES (low and flat at the centre,
    rising and twisting outboard into the endplate), swept back along RS-FW-SECTION
    out to Y 670, and the four-part endplate of Art. 3.10.6 - body, inboard footplate,
    outboard footplate (the tip that sticks out ahead of the tyre, to Y 900) and
    fence - all trimmed by the wheel cylinder."""
    elems = _span_elements(fw_span_layouts(p), "fw")

    body = _extrude_xz(_rounded_outline(G1_FW_EP_BODY), *G1_FW_EP_BODY_Y)
    ifp = _extrude_xy(fw_footplate_outline(*G1_FW_IFP[:2]), *G1_FW_IFP[2:])
    ofp = _extrude_xy(fw_footplate_outline(*G1_FW_OFP[:2]), *G1_FW_OFP[2:])
    fence = _extrude_xz(_rounded_outline(G1_FW_FENCE), *G1_FW_FENCE_Y)
    endplate = _fuse(body, ifp, ofp, fence).cut(_wheel_cut())
    return _fuse(*elems, endplate)


def rw_endplate_sections(p: CarParams, n=17):
    # n: first G1 (Z 470..180) swept 9 -> 13.4 mm loft escape, 13 -> 0.7 mm; the
    # 2026-10-21 endplate spans Z 715..272, so 17 keeps a similar spacing
    """(z, outline points) of the G1 lower rear endplate: stadium sections with the
    same point count at every station (clean-cad D2), keyframes PCHIP-interpolated
    (D1). Returned top to bottom."""
    from scipy.interpolate import PchipInterpolator
    k = np.array(G1_RW_EP_LOWER)[::-1]                 # ascending Z for PCHIP
    f = [PchipInterpolator(k[:, 0], k[:, i]) for i in (1, 2, 3)]
    h = G1_RW_EP_THICK / 2
    out = []
    for z in np.linspace(k[-1, 0], k[0, 0], n):
        x0, x1, yc = (float(fi(z)) for fi in f)
        ring = _rounded_outline([(p.xr + x0, yc - h, h), (p.xr + x1, yc - h, h),
                                 (p.xr + x1, yc + h, h), (p.xr + x0, yc + h, h)], n_arc=6)
        out.append((float(z), ring))
    return out


def rw_endplate_lower(p: CarParams):
    """G1 rear endplate below the wing, lofted through `rw_endplate_sections`."""
    wires = [cq.Wire.makePolygon([V(x, y, z) for x, y in ring], close=True)
             for z, ring in rw_endplate_sections(p)]
    ts = BRepOffsetAPI_ThruSections(True, False, 1e-6)
    ts.SetParType(Approx_Centripetal)
    for w in wires:
        ts.AddWire(w.wrapped)
    ts.Build()
    solid = cq.Solid(ts.Shape())
    LOFT_LOG.append(("rw endplate lower", solid, wires))
    return solid


def rear_wing(p: CarParams):
    if p.geom_level != "G0":
        return rear_wing_g1(p)
    s = p.rw_span_half
    x0, z0 = p.xr + p.rw_le[0], p.rw_le[1]
    elems = _wing_stack((x0, z0), p.rw_chords, p.rw_angles, 0, s,
                        p.rw_gap, p.rw_overlap, p.rw_flap_delta)
    # Endplate in RV-RWEP-BODY (App.1 §26, upper part only), Y 540..575
    plate = _box(p.xr + 225, p.xr + 650, s - 7, s + 8, 690, 878)
    # Central pylon, |Y| < 12.5 (3.11.4), from tail up to the main plane
    pylon = _box(p.xr + 240, p.xr + 380, 0, 10, 270, z0 + 20)
    return _fuse(*elems, plate, pylon)


def rear_wing_g1(p: CarParams):
    """G1 rear wing inside RV-RW-PROFILES / RWEP-BODY / RW-PYLON (App.1 §25-27): three
    elements lofted through G1_RW_SPAN (rising and flattening outboard), the endplate
    beside the wing, the lower endplate folding inboard along the §26 band, and twin
    pylons at Y 28..43. (The diffuser wall extension of the first G1 was dropped on
    2026-10-21: it lay where only the FIA CAD volume RV-DIFF applies, so it could not
    be shown legal.)"""
    elems = _span_elements(rw_span_layouts(p), "rw")
    plate = _extrude_xz([(p.xr + dx, z) for dx, z in _rounded_outline(G1_RW_EP_UPPER)],
                        *G1_RW_EP_UPPER_Y)
    pylon = _extrude_xz([(p.xr + dx, z) for dx, z in _rounded_outline(G1_RW_PYLON)],
                        *G1_RW_PYLON_Y)
    return _fuse(*elems, plate, rw_endplate_lower(p), pylon)


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
    inwards by `wb_yaw` and cambered to turn the tyre wake further inboard.
    G0 only (frozen); other levels get the legal `floor_boards`."""
    if p.geom_level != "G0":
        return floor_boards(p)
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


def floor_boards(p: CarParams):
    """Floor boards in RV-FLOOR-BOARD on a foot in RV-FLOOR-FOOT (G1_WB_* table), Y >= 0,
    car frame: `wb_elements` cambered vertical vanes (same section family as before)
    along the inward-leaning band, slots parallel to the sloping §6.3 top, a
    leading-edge tower, and the foot plate that overlaps the outer floor."""
    yaw = math.radians(G1_WB_YAW)
    dx, dy = math.cos(yaw), -math.sin(yaw)          # chord direction, towards inboard
    nx, ny = -dy, dx                                # outboard normal
    lx, ly = G1_WB_LE
    c = p.wb_chord
    s, h = _naca4(0.04, 0.4, 0.06, npts=40)         # camber bulges outboard
    X, Y = lx + c * (s * dx + h * nx), ly + c * (s * dy + h * ny)
    z_foot = G1_WB_FOOT_Z[1]
    (xa, za), (xb, zb) = G1_WB_TOP
    top = lambda x: min(za + (x - xa) * (zb - za) / (xb - xa), za) - G1_WB_TOP_MARGIN
    edge = cq.Edge.makeSpline([V(xi, yi, z_foot - 2) for xi, yi in zip(X, Y)])
    te = cq.Edge.makeLine(V(X[-1], Y[-1], z_foot - 2), V(X[0], Y[0], z_foot - 2))
    full = cq.Solid.extrudeLinear(cq.Face.makeFromWires(cq.Wire.assembleEdges([edge, te])),
                                  V(0, 0, za + 10 - z_foot))
    # band k lies between two planes through X (Y-parallel): heights scale with top(x)
    n, gap = p.wb_elements, p.wb_slot
    x0, x1 = float(X.min()), float(X.max())

    def plane(k, upper):
        """Z of band k's lower (upper=False) / upper boundary at x."""
        def z(x):
            hk = (top(x) - z_foot - (n - 1) * gap) / n
            return z_foot + k * (hk + gap) + (hk if upper else 0.0)
        return z

    elems = []
    for k in range(n):
        lo, hi = plane(k, False), plane(k, True)
        el = full
        if k > 0:
            el = el.intersect(regvol.half_space((x0, 0, lo(x0)), (x1, 0, lo(x1)), (x0, 1, lo(x0)),
                                                keep=(0, 0, 1)))
        el = el.intersect(regvol.half_space((x0, 0, hi(x0)), (x1, 0, hi(x1)), (x0, 1, hi(x0)),
                                            keep=(0, 0, -1)))
        elems.append(el)
    tower = _strut((lx + 20 * dx, ly + 20 * dy, z_foot - 5), (lx + 20 * dx, ly + 20 * dy, top(lx + 20)),
                   chord=45, thick=16, ext=0)
    foot = _extrude_xy(G1_WB_FOOT, *G1_WB_FOOT_Z)
    return _fuse(foot, tower, *elems)


def mirrors(p: CarParams):
    """Mirror housing (ellipsoid 150 x 110 x 60 mm) on a streamlined stalk, beside the
    cockpit ahead of the sidepod inlet, as on the FIA 2026 renders. Y >= 0, car frame.
    G0 only (frozen); other levels get `mirrors_g1` inside RV-MIRROR-*."""
    if p.geom_level != "G0":
        return mirrors_g1(p)
    x, y, z = 1000.0, 520.0, 660.0
    unit = cq.Solid.makeSphere(1.0, angleDegrees1=-90, angleDegrees2=90)
    housing = unit.transformGeometry(cq.Matrix([[75, 0, 0, x], [0, 55, 0, y], [0, 0, 30, z]]))
    stalk = _strut(chassis_point(p, x, 0.45, 0.85), (x, y - 30, z), chord=50, thick=14)
    return _fuse(housing, stalk)


def mirrors_g1(p: CarParams):
    """Housing ellipsoid aligned with the RV-MIRROR-BODY parallelogram, on a stalk that
    stays inside RV-MIRROR-ISTAY from inside the chassis to the housing (G1_MIRROR_*)."""
    cx, cy, cz = G1_MIRROR_CENTRE
    a, b, h = G1_MIRROR_AXES
    sl, cl = math.sin(G1_MIRROR_LEAN), math.cos(G1_MIRROR_LEAN)
    unit = cq.Solid.makeSphere(1.0, angleDegrees1=-90, angleDegrees2=90)
    # columns: long axis (lean off +Y towards +X), across, Z
    housing = unit.transformGeometry(cq.Matrix([[a * sl, b * cl, 0, cx],
                                                [a * cl, -b * sl, 0, cy],
                                                [0, 0, h, cz]]))
    stalk = _strut(*G1_MIRROR_STALK, chord=50, thick=14)
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
    if p.geom_level == "G1":
        parts["helmet"] = helmet(p)
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
    if p.geom_level == "G1":
        return {k: _mirror_glue_full(v) for k, v in parts.items()}
    # glue: the halves share the Y=0 face exactly
    return {k: v.fuse(v.mirror("XZ"), glue=True).clean() for k, v in parts.items()}


def _mirror_glue_full(shape):
    """Fuse a Y >= 0 half with its mirror using BOPAlgo_GlueFull: the halves only
    touch on the Y = 0 plane, so no face/face intersection is needed. The G1 crease
    spine meets Y = 0 level (tangent halves), and the default fuse (with or without
    GlueShift) did not finish in 5 min; GlueFull takes 0.2 s."""
    from OCP.BOPAlgo import BOPAlgo_GlueFull
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.TopTools import TopTools_ListOfShape
    args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(shape.wrapped)
    tools.Append(shape.mirror("XZ").wrapped)
    op = BRepAlgoAPI_Fuse()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetGlue(BOPAlgo_GlueFull)
    op.Build()
    return cq.Shape.cast(op.Shape()).clean()
