"""Download F1 circuit centerlines from TUMFTM/racetrack-database (LGPL-3.0).

Each CSV holds the track centerline and the track widths:
    x_m, y_m, w_tr_right_m, w_tr_left_m
"""
from pathlib import Path
import urllib.request

BASE = "https://raw.githubusercontent.com/TUMFTM/racetrack-database/master/tracks/{}.csv"
TRACKS = [
    "Monza", "Spa", "Silverstone", "Budapest", "Catalunya", "Suzuka",
    "Spielberg", "Zandvoort", "MexicoCity", "Montreal", "Sakhir",
    "YasMarina", "Austin", "Melbourne", "SaoPaulo", "Shanghai",
]

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "tracks"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in TRACKS:
        dst = OUT_DIR / f"{name}.csv"
        if dst.exists():
            continue
        with urllib.request.urlopen(BASE.format(name), timeout=30) as r:
            dst.write_bytes(r.read())
        print(f"fetched {name}")


if __name__ == "__main__":
    main()
