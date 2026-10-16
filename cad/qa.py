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
- an exported STL that is not closed, which snappyHexMesh cannot inside-test.

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


def solid_checks(name, shape, expect_solids=1):
    """Topology, orientation and boolean-suitability of one part.
    expect_solids=None skips the count (parts made of separate members)."""
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
                         BRepAlgoAPI_Check(shape.wrapped).IsValid()))
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


def report(checks, title="geometry QA"):
    print(f"  -- {title}")
    w = max(len(c.name) for c in checks)
    for c in checks:
        print(f"  {'OK ' if c.ok else 'NG '} {c.name:<{w}}  {c.detail}")
    return all(c.ok for c in checks)
