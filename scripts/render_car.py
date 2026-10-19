"""Shaded 3D renders of built cars (pyvista / VTK, off-screen) for visual review.

matplotlib (used by build_car.py) cannot depth-sort overlapping surfaces, so
undercuts and wing curl are hard to judge there. This script renders the
exported STLs properly; half models are mirrored to the full car.

    python scripts/render_car.py fia2026_half
    python scripts/render_car.py baseline_half fia2026_half      # side by side
Output: docs/figures/render_<name>[_vs_<name>].png
"""
import argparse
import sys
from pathlib import Path

import pyvista as pv

ROOT = Path(__file__).resolve().parents[1]

COLORS = {"body": "#22305a", "front_wing": "#1b1b1f", "rear_wing": "#1b1b1f",
          "wheels_front": "#2a2a2a", "wheels_rear": "#2a2a2a", "halo": "#8d939c",
          "wake_boards": "#1b1b1f", "mirrors": "#22305a", "helmet": "#e0b33a",
          "suspension_front": "#3a3d44", "suspension_rear": "#3a3d44"}

# (title, camera position, focal point, up) in metres; X rearward, Y right, Z up
VIEWS = [
    ("front 3/4", (-4.2, -4.0, 2.4), (1.4, 0.0, 0.35), (0, 0, 1)),
    ("rear 3/4", (6.8, -3.6, 2.6), (2.0, 0.0, 0.35), (0, 0, 1)),
    ("side", (1.6, -9.0, 0.45), (1.6, 0.0, 0.45), (0, 0, 1)),
    ("top", (1.6, 0.0, 9.0), (1.6, 0.0, 0.0), (-1, 0, 0)),
    ("underside", (1.6, 0.0, -9.0), (1.6, 0.0, 0.0), (-1, 0, 0)),
    ("front", (-9.0, 0.0, 0.45), (1.6, 0.0, 0.45), (0, 0, 1)),
]


def load(name):
    folder = ROOT / "cad" / "out" / name
    if not folder.is_dir():
        sys.exit(f"{folder.relative_to(ROOT)} not found - build it with build_car.py first")
    meshes = {}
    for stl in sorted(folder.glob("*.stl")):
        m = pv.read(stl)
        if m.bounds[2] > -1e-3:                       # half model: mirror across Y = 0
            m = m.merge(m.reflect((0, 1, 0), point=(0, 0, 0)))
        meshes[stl.stem] = m
    return meshes


def render(names, out):
    cols = len(names)
    pl = pv.Plotter(off_screen=True, shape=(len(VIEWS), cols), window_size=(900 * cols, 520 * len(VIEWS)),
                    border=False)
    pl.set_background("white")
    for c, name in enumerate(names):
        meshes = load(name)
        for r, (title, pos, focal, up) in enumerate(VIEWS):
            pl.subplot(r, c)
            for part, m in meshes.items():
                pl.add_mesh(m, color=COLORS.get(part, "#555555"), smooth_shading=True,
                            split_sharp_edges=True, feature_angle=35,
                            specular=0.25, specular_power=20)
            road = pv.Plane(center=(1.6, 0, -0.001), direction=(0, 0, 1), i_size=9, j_size=5)
            if title not in ("underside",):
                pl.add_mesh(road, color="#e9ebee")
            pl.add_text(f"{name} - {title}", font_size=9, color="black")
            pl.camera_position = [pos, focal, up]
            pl.camera.parallel_projection = title in ("side", "top", "underside", "front")
            pl.reset_camera_clipping_range()
            if pl.camera.parallel_projection:
                pl.camera.parallel_scale = 1.1 if title == "front" else 3.2
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(out))
    pl.close()
    print(f"saved {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+", help="folders under cad/out/")
    args = ap.parse_args()
    out = ROOT / "docs" / "figures" / ("render_" + "_vs_".join(args.names) + ".png")
    render(args.names, out)


if __name__ == "__main__":
    main()
