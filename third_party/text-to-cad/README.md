# text-to-cad (vendored reference, read-only)

A pinned subset of [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad),
MIT License (see `LICENSE`, Copyright (c) 2026 Thompson Labs LLC).
Commit: see `.pinned_sha` (`24573128ceaab564f497d7c12f995c41784c9539`, 2026-10-11).

Kept here so both work PCs (and their separate Claude accounts) can read the same
reference. Nothing in this folder is imported or executed by the project; the
`.py` files need the `cadgen` runtime and build123d. Files are unmodified.

| Path | What it is |
|---|---|
| `models/f1/README.md` | Part list and build notes of their F1 concept car |
| `models/f1/lib/spec.py` | Master dimensions, design rules, coordinate system (X forward +, Y left +) |
| `models/f1/lib/surfaces.py` | Shared helpers: airfoil/blade/body lofts, validity, repair, loft-escape check |
| `models/f1/lib/floor.py` | Floor, venturi tunnels, fences, plank, diffuser, strakes (station tables) |
| `models/f1/lib/front_wing.py`, `rear_wing.py`, `sidepods.py`, `nose.py`, `engine_cover.py` | Bodywork and wings |
| `skills/cad/SKILL.md`, `skills/cad/references/*.md` | Their agent's CAD workflow rules (modelling, validation, repair, snapshots) |

How the project uses it: [docs/references/text-to-cad-f1.md](../../docs/references/text-to-cad-f1.md).
