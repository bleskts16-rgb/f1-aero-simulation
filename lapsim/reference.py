"""Real-world reference laps from FastF1 for validating the simulator."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "fastf1_cache"

# racetrack-database name -> FastF1 event name
EVENTS = {
    "Monza": "Italian Grand Prix",
    "Spa": "Belgian Grand Prix",
    "Silverstone": "British Grand Prix",
    "Budapest": "Hungarian Grand Prix",
    "Catalunya": "Spanish Grand Prix",
    "Suzuka": "Japanese Grand Prix",
    "Spielberg": "Austrian Grand Prix",
    "Zandvoort": "Dutch Grand Prix",
    "MexicoCity": "Mexico City Grand Prix",
    "Montreal": "Canadian Grand Prix",
    "Sakhir": "Bahrain Grand Prix",
    "YasMarina": "Abu Dhabi Grand Prix",
    "Austin": "United States Grand Prix",
    "Melbourne": "Australian Grand Prix",
    "SaoPaulo": "São Paulo Grand Prix",
    "Shanghai": "Chinese Grand Prix",
}


@dataclass
class ReferenceLap:
    track: str
    year: int
    driver: str
    lap_time: float
    distance: np.ndarray  # [m]
    speed: np.ndarray     # [m/s]


def load_reference(track: str, year: int = 2024, session: str = "Q") -> ReferenceLap:
    import fastf1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    ses = fastf1.get_session(year, EVENTS[track], session)
    ses.load(laps=True, telemetry=True, weather=False, messages=False)
    lap = ses.laps.pick_fastest()
    tel = lap.get_car_data().add_distance()
    return ReferenceLap(
        track=track, year=year, driver=str(lap["Driver"]),
        lap_time=lap["LapTime"].total_seconds(),
        distance=tel["Distance"].to_numpy(dtype=float),
        speed=tel["Speed"].to_numpy(dtype=float) / 3.6,
    )


def align(sim_s, sim_v, ref_s, ref_v, n=2000):
    """Resample both speed traces on a lap-fraction grid and find the circular
    shift of the simulation that best matches the reference."""
    f = np.linspace(0.0, 1.0, n, endpoint=False)
    L_sim = sim_s[-1] + (sim_s[1] - sim_s[0])
    vs = np.interp(f * L_sim, sim_s, sim_v, period=L_sim)
    vr = np.interp(f, ref_s / ref_s[-1], ref_v)
    a = vs - vs.mean()
    b = vr - vr.mean()
    corr = np.fft.ifft(np.fft.fft(b) * np.conj(np.fft.fft(a))).real
    shift = int(np.argmax(corr))
    return f, np.roll(vs, shift), vr
