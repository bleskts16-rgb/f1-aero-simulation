"""ParaView view of a finished half-car case (works on the decomposed case).

    paraview --script=pv_view.py              # interactive, from the case folder
    pvpython pv_view.py --save shots          # writes shots_cp.png / shots_u.png

Left: pressure coefficient Cp on the car, mirrored to the full car.
Right: velocity magnitude on the centreline plane (Y = 0), side view.
"""
import os
import sys

from paraview.simple import *  # noqa: F401,F403

# the GUI's --script runs without __file__; it is started from the case folder
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
CASE = os.path.join(HERE, "case.foam")
U_INF = @U_INF@
PARTS = ("body", "front_wing", "rear_wing", "wheels_front", "wheels_rear")
open(CASE, "a").close()


def reader(name, regions):
    r = OpenFOAMReader(registrationName=name, FileName=CASE)
    r.CaseType = "Decomposed Case" if os.path.isdir(os.path.join(os.path.dirname(CASE), "processor0")) \
        else "Reconstructed Case"
    r.UpdatePipelineInformation()
    avail = r.GetProperty("MeshRegions").Available
    r.MeshRegions = [a for a in avail if regions(a)]
    r.CellArrays = ["p", "U"]
    return r


car = reader("car", lambda a: a.split("/")[-1] in PARTS and not a.startswith("group"))
fluid = reader("fluid", lambda a: a == "internalMesh")
scene = GetAnimationScene()
scene.UpdateAnimationUsingDataTimeSteps()
scene.AnimationTime = car.TimestepValues[-1] if car.TimestepValues else 0

cp = Calculator(registrationName="Cp", Input=car, AttributeType="Cell Data",
                ResultArrayName="Cp", Function=f"p/(0.5*{U_INF}^2)")
cp_pts = CellDatatoPointData(registrationName="Cp_points", Input=cp)
full = Reflect(registrationName="full_car", Input=cp_pts, Plane="Y", Center=0.0, CopyInput=1)

mid = Slice(registrationName="centreline", Input=fluid)
mid.SliceType = "Plane"
mid.SliceType.Origin = [1.5, 0.0005, 0.5]
mid.SliceType.Normal = [0, 1, 0]
mid_pts = CellDatatoPointData(registrationName="centreline_points", Input=mid)

v1 = GetActiveViewOrCreate("RenderView")
layout = GetLayout(v1)
d1 = Show(full, v1)
ColorBy(d1, ("POINTS", "Cp"))
lut = GetColorTransferFunction("Cp")
lut.ApplyPreset("Cool to Warm", True)
lut.RescaleTransferFunction(-2.0, 1.0)
d1.SetScalarBarVisibility(v1, True)
v1.OrientationAxesVisibility = 1
v1.CameraPosition = [-4.5, -5.5, 3.5]
v1.CameraFocalPoint = [1.4, 0.0, 0.35]
v1.CameraViewUp = [0, 0, 1]
v1.ResetCamera(False)
GetActiveCamera().Dolly(1.5)

layout.SplitHorizontal(0, 0.5)
v2 = CreateView("RenderView")
AssignViewToLayout(view=v2, layout=layout, hint=2)
d2 = Show(mid_pts, v2)
ColorBy(d2, ("POINTS", "U", "Magnitude"))
lut_u = GetColorTransferFunction("U")
lut_u.ApplyPreset("Jet", True)
lut_u.RescaleTransferFunction(0.0, 1.4 * U_INF)
d2.SetScalarBarVisibility(v2, True)
bar = GetScalarBar(lut_u, v2)
bar.WindowLocation = "Upper Right Corner"
bar.Title = "|U| [m/s]"
bar.ComponentTitle = ""
outline = Show(car, v2)
outline.SetRepresentationType("Feature Edges")
outline.AmbientColor = outline.DiffuseColor = [0.1, 0.1, 0.1]
ColorBy(outline, None)
v2.InteractionMode = "2D"
v2.CameraPosition = [1.4, -10, 0.6]
v2.CameraFocalPoint = [1.4, 0, 0.6]
v2.CameraViewUp = [0, 0, 1]
v2.CameraParallelScale = 1.6
v2.OrientationAxesVisibility = 0

if "--save" in sys.argv:
    stem = sys.argv[sys.argv.index("--save") + 1]
    SaveScreenshot(f"{stem}_cp.png", v1, ImageResolution=[1400, 900])
    SaveScreenshot(f"{stem}_u.png", v2, ImageResolution=[1400, 700])
else:
    SetActiveView(v1)
    Render(v1)
    Render(v2)
