"""Open a built car in ParaView: every STL as its own coloured source, half models
mirrored to the full car, camera at a front 3/4 view.

    # GUI (Windows PowerShell); the model folder under cad/out/ comes from F1_CAR
    $env:F1_CAR = "fia2026_half"; paraview --script=scripts/pv_car.py
    # batch screenshot
    pvpython scripts/pv_car.py fia2026_half --save docs/figures/pv_fia2026.png

Parts stay separate in the Pipeline Browser, so they can be hidden or recoloured
one by one.
"""
import os
import sys
from pathlib import Path

from paraview.simple import *  # noqa: F401,F403  (filters are registered at run time)

# the GUI's --script runs without __file__; it is started from the repository root
HERE = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd() / "scripts"
ROOT = HERE.parent

COLORS = {"body": (0.13, 0.19, 0.35), "front_wing": (0.10, 0.10, 0.12),
          "rear_wing": (0.10, 0.10, 0.12), "wheels_front": (0.16, 0.16, 0.16),
          "wheels_rear": (0.16, 0.16, 0.16), "halo": (0.55, 0.58, 0.61),
          "wake_boards": (0.10, 0.10, 0.12), "mirrors": (0.13, 0.19, 0.35),
          "suspension_front": (0.23, 0.24, 0.27), "suspension_rear": (0.23, 0.24, 0.27)}


def mirror_y(src, name):
    """Reflect about the plane Y = 0 and keep the input. ParaView 6 renamed Reflect
    to AxisAlignedReflect; a per-part 'Y Min' plane would mirror the wheels about
    their own inner face, so the plane is set explicitly."""
    if "AxisAlignedReflect" in globals():
        r = AxisAlignedReflect(registrationName=name, Input=src)  # noqa: F405
        r.PlaneMode = "Interactive"
        r.ReflectionPlane.Origin = [0.0, 0.0, 0.0]
        r.ReflectionPlane.Normal = [0.0, 1.0, 0.0]
    else:
        r = Reflect(registrationName=name, Input=src)  # noqa: F405
        r.Plane = "Y"
        r.Center = 0.0
    r.CopyInput = 1
    return r


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else os.environ.get("F1_CAR", "fia2026_half")
    folder = ROOT / "cad" / "out" / name
    stls = sorted(folder.glob("*.stl"))
    if not stls:
        raise SystemExit(f"no STL in {folder} - build it with scripts/build_car.py first")

    view = GetActiveViewOrCreate("RenderView")
    for stl in stls:
        src = STLReader(registrationName=stl.stem, FileNames=[str(stl)])
        src.UpdatePipeline()
        if src.GetDataInformation().GetBounds()[2] > -1e-3:   # half model, Y >= 0
            src = mirror_y(src, stl.stem + "_full")
        disp = Show(src, view)
        disp.AmbientColor = disp.DiffuseColor = COLORS.get(stl.stem, (0.4, 0.4, 0.4))
        disp.Specular = 0.3

    try:                                    # ParaView >= 5.10 uses colour palettes
        view.UseColorPaletteForBackground = 0
    except AttributeError:
        pass
    view.Background = [1.0, 1.0, 1.0]
    view.OrientationAxesVisibility = 1
    Render(view)        # the first render resets the camera, so set it afterwards
    # metres; X rearward, Y right, Z up
    view.CameraPosition = [-3.7, -3.6, 2.2]
    view.CameraFocalPoint = [1.4, 0.0, 0.35]
    view.CameraViewUp = [0.0, 0.0, 1.0]
    view.CameraViewAngle = 30
    Render(view)

    if "--save" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--save") + 1])
        SaveScreenshot(str(out), view, ImageResolution=[1920, 1080])
        print(f"saved {out}")


main()
