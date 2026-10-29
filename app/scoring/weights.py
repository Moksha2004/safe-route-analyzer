from __future__ import annotations

from datetime import time
from typing import Any

NIGHT_START = time(20, 0)
NIGHT_END = time(6, 0)
DAY_REFERENCE_HOUR = 21

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "car": {"nas": 0.24, "light": 0.12, "hospital": 0.12, "shop": 0.10, "police": 0.14, "residential": 0.10, "delay": 0.08, "closure": 0.07, "duration": 0.03},
    "pedestrian": {"nas": 0.30, "light": 0.15, "hospital": 0.10, "shop": 0.09, "police": 0.14, "residential": 0.10, "delay": 0.04, "closure": 0.05, "duration": 0.03},
    "bicycle": {"nas": 0.28, "light": 0.14, "hospital": 0.10, "shop": 0.09, "police": 0.14, "residential": 0.10, "delay": 0.06, "closure": 0.06, "duration": 0.03},
}

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


def bounded_weights(mode: str, proposed: Any = None) -> dict[str, float]:
    defaults = DEFAULT_WEIGHTS.get(mode, DEFAULT_WEIGHTS["car"]).copy()
    if not isinstance(proposed, dict):
        return defaults
    for key in defaults:
        value = proposed.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            defaults[key] = min(max(float(value), defaults[key] * 0.5), defaults[key] * 1.5)
    return defaults
