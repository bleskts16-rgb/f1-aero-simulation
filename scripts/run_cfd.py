"""Mesh and solve a case made by make_cfd_case.py.

    python scripts/run_cfd.py cfd/runs/baseline_half_coarse

On Windows the case is copied into the WSL file system (~/f1cfd/<name>; running on
/mnt/c is several times slower), run there, and logs + postProcessing/ are copied
back. On Linux it runs in place. OpenFOAM is loaded from $FOAM_BASHRC if set,
otherwise the first of /usr/lib/openfoam/openfoam*/etc/bashrc, /opt/openfoam*/etc/bashrc,
~/ofenv.sh that exists.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LOAD_FOAM = r"""
for f in "$FOAM_BASHRC" /usr/lib/openfoam/openfoam*/etc/bashrc /opt/openfoam*/etc/bashrc "$HOME/ofenv.sh"; do
    if [ -n "$f" ] && [ -f "$f" ]; then . "$f"; break; fi
done
[ -n "$WM_PROJECT_DIR" ] || { echo "OpenFOAM not found - set FOAM_BASHRC"; exit 1; }
echo "OpenFOAM $WM_PROJECT_VERSION, $(nproc) cores, $(free -g | awk '/^Mem:/{print $2}') GB RAM visible"
"""

WSL_SCRIPT = LOAD_FOAM + r"""
src="$1"; dst="$HOME/f1cfd/$(basename "$src")"
mkdir -p "$dst"
cp -ru "$src/." "$dst/"
cd "$dst"
bash Allrun; rc=$?
cp -r log.* "$src/" 2>/dev/null
[ -d postProcessing ] && cp -r postProcessing "$src/"
echo "results copied back to $src (full case stays in $dst)"
exit $rc
"""


def to_wsl_path(p: Path) -> str:
    p = p.resolve()
    return f"/mnt/{p.drive[0].lower()}{p.as_posix()[2:]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--distro", help="WSL distribution (default: the default one)")
    args = ap.parse_args()
    case = (ROOT / args.case).resolve()
    if not (case / "Allrun").exists():
        sys.exit(f"{case} is not a case made by make_cfd_case.py")

    if os.name == "nt":
        script = case / "run_wsl.sh"
        script.write_bytes(WSL_SCRIPT.encode())
        cmd = ["wsl.exe"] + (["-d", args.distro] if args.distro else []) + \
              ["-e", "bash", to_wsl_path(script), to_wsl_path(case)]
    else:
        cmd = ["bash", "-c", LOAD_FOAM + 'bash "$1"', "run", str(case / "Allrun")]
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
