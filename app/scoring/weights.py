from __future__ import annotations

from datetime import time
from typing import Any

NIGHT_START = time(20, 0)
NIGHT_END = time(6, 0)
DAY_REFERENCE_HOUR = 21

RANKING_FACTORS: dict[str, str] = {
    "nas": "overall night activity score",
    "light": "mapped street lighting",
    "police": "police stations along the route",
    "hospital": "hospitals open when passing",
    "shop": "shops, pharmacies and restaurants open when passing",
    "residential": "residential stretches",
    "delay": "avoiding traffic delay",
    "closure": "avoiding closures and severe incidents",
    "duration": "shorter travel time",
}
MULTIPLIER_MIN = 0.5
MULTIPLIER_MAX = 1.5

NAS_WEIGHTS = {
    "streetLighting": 0.22,
    "policePresence": 0.22,
    "openShopsAtNight": 0.16,
    "residentialCoverage": 0.15,
    "nightTrafficActivity": 0.15,
    "openHospitalsAtNight": 0.10,
}


def is_night_hour(hour: int) -> bool:
    return hour >= NIGHT_START.hour or hour < NIGHT_END.hour


def bounded_multipliers(proposed: Any = None) -> dict[str, float]:
    if not isinstance(proposed, dict):
        return {}
    bounded: dict[str, float] = {}
    for key in RANKING_FACTORS:
        value = proposed.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            bounded[key] = round(min(max(float(value), MULTIPLIER_MIN), MULTIPLIER_MAX), 2)
    return bounded
