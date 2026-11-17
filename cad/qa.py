"""Geometry quality checks for the CFD car.

Adapted from the text-to-cad F1 concept car (third_party/text-to-cad, MIT):
`surfaces.is_valid_shape`, `obox`, `loft_escaped` and the cad skill's rule that
"a failed computation is not a pass". They target the failures that slip past
`Shape.isValid()`:

- an inverted solid (valid topology, negative volume) that meshes as a hole;
- a body that is valid but unfit for further booleans (BRepAlgoAPI_Check);
- a smooth loft that wanders outside its own sections while staying valid and
  watertight (our tail bulged before the centripetal fix); checked slab by slab
  between neighbouring sections, which is stricter than their whole-loft box;
- an exported STL that is not closed, which snappyHexMesh cannot inside-test
  (sliver gaps up to STL_GAP_LIMIT = 0.1 mm pass, see `stl_gaps`).

All functions only read geometry; none of them changes a shape.
"""
from dataclasses import dataclass

import numpy as np
from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def tight_bbox(shape):
    """Bounds from the surfaces themselves. `BoundingBox()` is built from the
    B-spline control poles and over-reports on lofts."""
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return np.array([x0, y0, z0]), np.array([x1, y1, z1])


def signed_volume(solid):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid.wrapped, props)
    return props.Mass()


def solid_checks(name, shape, expect_solids=1, bool_shape=None):
    """Topology, orientation and boolean-suitability of one part.
    expect_solids=None skips the count (parts made of separate members).
    bool_shape: the same part before its rigid ride-height move (car frame), used for
    the BRepAlgoAPI_Check only. The helmet and mirrors are identical in every design and
    pass there, but failed after some pitches (DOE 1: helmet at 0.792 deg, mirrors at
    0.674 deg), which a rigid move cannot do to the geometry (2026-11-17, user)."""
    out = []
    try:
        solids = shape.Solids()
        if expect_solids is not None:
            out.append(Check(f"{name}: solid count", len(solids) == expect_solids,
                             f"{len(solids)} (expect {expect_solids})"))
        vols = [signed_volume(s) for s in solids]
        out.append(Check(f"{name}: positive volume per solid", all(v > 0 for v in vols),
                         ", ".join(f"{v / 1e9:.4f} m3" for v in vols)))
        out.append(Check(f"{name}: BRepCheck valid",
                         BRepCheck_Analyzer(shape.wrapped).IsValid()))
        out.append(Check(f"{name}: boolean-ready (BRepAlgoAPI_Check)",
                         BRepAlgoAPI_Check((bool_shape or shape).wrapped).IsValid(),
                         "car frame" if bool_shape is not None else ""))
    except Exception as e:  # a failed computation is not a pass
        out.append(Check(f"{name}: checks raised", False, repr(e)))
    return out


# Calibrated on the body loft (2026-10-16): centripetal lofts overshoot their
# neighbouring sections by <= 22 mm, chord-length 162 mm (the old tail bulge),
# uniform 73 mm.
LOFT_ESCAPE_LIMIT = 30.0


def loft_local_escape(solid, wires):
    """Worst local overshoot of a loft built from planar sections normal to one axis
    (X for body lofts, Y for wing lofts): the loft is cut between each pair of
    neighbouring sections and that slab is compared with the box of the two
    sections. A global box misses a bulge that stays inside the overall envelope
    (the old 80 mm tail bulge was only 27 mm outside the whole-body box).
    Returns (excess mm, slab position such as "X 1600", axis of the excess)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    lo_all, hi_all = tight_bbox(solid)
    pad = float(np.max(hi_all - lo_all))
    boxes = [tight_bbox(w) for w in wires]
    k = int(np.argmin(boxes[0][1] - boxes[0][0]))       # section-normal axis
    worst = (0.0, None, None)
    for (a0, b0), (a1, b1) in zip(boxes, boxes[1:]):
        s0, s1 = sorted((float(a0[k]), float(a1[k])))
        if s1 - s0 < 1e-6:
            continue
        lo_c, hi_c = lo_all - pad, hi_all + pad
        lo_c[k], hi_c[k] = s0, s1
        cutter = BRepPrimAPI_MakeBox(gp_Pnt(*lo_c), gp_Pnt(*hi_c)).Shape()
        common = BRepAlgoAPI_Common(solid.wrapped, cutter)
        common.Build()
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(common.Shape(), box, False, False)
        if box.IsVoid():
            continue
        v = box.Get()
        a, b = np.array(v[:3]), np.array(v[3:])
        lo, hi = np.minimum(a0, a1), np.maximum(b0, b1)
        ex = np.maximum(lo - a, b - hi)
        ex[k] = 0.0                     # slabs are cut exactly along the section axis
        i = int(np.argmax(ex))
        if ex[i] > worst[0]:
            worst = (float(ex[i]), f"{'XYZ'[k]} {0.5 * (s0 + s1):.0f}", "xyz"[i])
    return worst


def obscured(shape, polygon, axes, ray_axis, ray_range, step=12.0, margin=1.0):
    """Check a regulation 'must fully obscure RS-...' rule by ray casting.

    polygon: 2D vertices in the two coordinates named by `axes` (e.g. "xz");
    rays run along `ray_axis` (e.g. "y") from ray_range[0] to ray_range[1].
    Grid points `step` apart inside the polygon (shrunk by `margin` mm) are tested;
    returns (fraction covered, list of uncovered 2D points)."""
    from matplotlib.path import Path as MPath
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    poly = np.asarray(polygon, dtype=float)
    path = MPath(poly)
    lo, hi = poly.min(0), poly.max(0)
    g = np.stack(np.meshgrid(np.arange(lo[0] + step / 2, hi[0], step),
                             np.arange(lo[1] + step / 2, hi[1], step)), -1).reshape(-1, 2)
    pts = g[path.contains_points(g, radius=-margin)] if len(g) else g
    ia, ib, ir = ("xyz".index(axes[0]), "xyz".index(axes[1]), "xyz".index(ray_axis))
    d = [0.0, 0.0, 0.0]
    d[ir] = 1.0
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape.wrapped, 1e-6)
    missed = []
    for a, b in pts:
        o = [0.0, 0.0, 0.0]
        o[ia], o[ib], o[ir] = a, b, ray_range[0]
        inter.Perform(gp_Lin(gp_Pnt(*o), gp_Dir(*d)), 0.0, ray_range[1] - ray_range[0])
        if not (inter.IsDone() and inter.NbPnt() > 0):
            missed.append((float(a), float(b)))
    n = len(pts)
    return (1.0 - len(missed) / n if n else 0.0), missed


def read_stl(path):
    """Triangles (n, 3, 3) from an ASCII or binary STL."""
    raw = path.read_bytes()
    if raw[:5] == b"solid" and b"facet" in raw[:1000]:
        nums = [line.split()[1:4] for line in raw.decode("ascii", "replace").splitlines()
                if line.lstrip().startswith("vertex")]
        return np.asarray(nums, dtype=float).reshape(-1, 3, 3)
    n = int.from_bytes(raw[80:84], "little")
    rec = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                             ("a", "<u2")]), count=n, offset=84)
    return rec["v"].astype(float)


STL_GAP_LIMIT = 1e-4   # m; open-edge clusters no larger than this pass (2026-11-17, user)


def stl_gaps(path, merge=1e-7):
    """(open edges, triangles, largest gap [m]) of an exported STL. Open edges are grouped
    into connected clusters (shared vertices) and the largest cluster's bounding-box
    diagonal is reported. OCC tessellation of fused struts can leave a sliver hole of a
    few hundredths of a mm (DOE 1, 2026-11-17: 0.07 mm on suspension_rear at high rake);
    that is far below the smallest mesh cell (~6 mm) and snappyHexMesh never inside-tests
    the part STLs (inside refinement uses boxes; the fluid side is set by locationInMesh),
    so gaps up to STL_GAP_LIMIT pass. Widening `merge` instead is wrong: welding collapses
    small triangles and opens new holes (base body.stl: 1188 open edges at 0.01 mm)."""
    tri = read_stl(path)
    pts, ids = np.unique(np.round(tri.reshape(-1, 3) / merge), axis=0, return_inverse=True)
    pts = pts * merge
    t = ids.ravel().reshape(-1, 3)
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    ue, counts = np.unique(e, axis=0, return_counts=True)
    op = ue[counts != 2]
    if len(op) == 0:
        return 0, len(t), 0.0
    parent = {v: v for v in np.unique(op)}
    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    for a, b in op:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups = {}
    for v in parent:
        groups.setdefault(find(v), []).append(v)
    gap = max(float(np.linalg.norm(pts[g].max(0) - pts[g].min(0))) for g in groups.values())
    return len(op), len(t), gap


def stl_open_edges(path, merge=1e-7):
    """(open edges, triangles) of an exported STL: an edge that is not shared by
    exactly two triangles means the surface is not closed. `merge` is the
    vertex-welding distance in the file's units (m for our STLs)."""
    tri = read_stl(path)
    _, ids = np.unique(np.round(tri.reshape(-1, 3) / merge), axis=0, return_inverse=True)
    t = ids.ravel().reshape(-1, 3)
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int(np.sum(counts != 2)), len(t)


def attached(name, shape, targets, tol=0.01):
    """Every solid of `shape` touches or overlaps each shape in `targets`
    ({label: shape}). Catches members that float in the flow."""
    out = []
    for i, s in enumerate(shape.Solids()):
        for label, tgt in targets.items():
            d = s.distance(tgt)
            out.append(Check(f"{name}[{i}] attached to {label}", d <= tol, f"gap {d:.2f} mm"))
    return out


def outside(shape, allowed, min_volume=1.0, n_max=600):
    """Material of `shape` that lies outside `allowed` (a reference volume or a union
    of them): (volume [mm^3], max depth [mm], deepest point). Depth is the distance
    from the surface points of the excess to `allowed`, sampled at up to n_max
    tessellation vertices, so it can miss the true maximum by about the sampling."""
    import cadquery as cq
    ex = shape.cut(allowed)
    vol = sum(signed_volume(s) for s in ex.Solids())
    if vol < min_volume:
        return max(vol, 0.0), 0.0, None
    verts, _ = ex.tessellate(0.5, 0.2)
    step = max(1, len(verts) // n_max)
    best, where = 0.0, None
    for v in verts[::step]:
        d = cq.Vertex.makeVertex(v.x, v.y, v.z).distance(allowed)
        if d > best:
            best, where = d, (v.x, v.y, v.z)
    return vol, best, where


def report(checks, title="geometry QA"):
    print(f"  -- {title}")
    w = max(len(c.name) for c in checks)
    for c in checks:
        print(f"  {'OK ' if c.ok else 'NG '} {c.name:<{w}}  {c.detail}")
    return all(c.ok for c in checks)
