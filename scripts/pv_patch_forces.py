"""Pressure force of one wall patch, face by face, from a finished (decomposed) case.
Run with ParaView's pvpython inside WSL, in the case folder under ~/f1cfd:

    pvpython /mnt/c/.../scripts/pv_patch_forces.py ~/f1cfd/g1r_grid2_L1 body faces.csv

Writes one row per (triangulated) face: centre [m], area vector Sf [m^2] (OpenFOAM
orientation, out of the fluid) and force rho * p * Sf [N] at the last written time.
The sum matches the `forces` function object's pressure part. Binning the rows by
X, Z or face direction shows where a part's drag or lift comes from (2026-10-22:
the body drag rise of the regulation-compliant G1). Viscous force is not included.
"""
import sys

import numpy as np
from paraview import servermanager as sm
from paraview.simple import ExtractSurface, MergeBlocks, OpenFOAMReader, Triangulate
from vtk.util.numpy_support import vtk_to_numpy as v2n

RHO = 1.2


def main():
    case, patch, out = sys.argv[1], sys.argv[2], sys.argv[3]
    open(case + "/case.foam", "a").close()
    r = OpenFOAMReader(FileName=case + "/case.foam")
    r.CaseType = "Decomposed Case"
    r.UpdatePipelineInformation()
    r.MeshRegions = ["patch/" + patch]
    r.CellArrays = ["p"]
    t = max(r.TimestepValues)
    tri = Triangulate(Input=ExtractSurface(Input=MergeBlocks(Input=r)))
    tri.UpdatePipeline(t)
    d = sm.Fetch(tri)
    pts = v2n(d.GetPoints().GetData())
    c = v2n(d.GetPolys().GetData()).reshape(-1, 4)[:, 1:]
    p = v2n(d.GetCellData().GetArray("p"))
    a, b, e = pts[c[:, 0]], pts[c[:, 1]], pts[c[:, 2]]
    sf = 0.5 * np.cross(b - a, e - a)
    f = RHO * p[:, None] * sf
    np.savetxt(out, np.c_[(a + b + e) / 3, sf, f], delimiter=",",
               header="cx,cy,cz,Sx,Sy,Sz,Fx,Fy,Fz", comments="")
    print(f"time {t:g}: {len(p)} faces, pressure force {f.sum(0)} N -> {out}")


if __name__ == "__main__":
    main()
