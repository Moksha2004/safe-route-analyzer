from __future__ import annotations

from typing import Any

from app.scoring.weights import NAS_WEIGHTS


def score_night_activity(components: dict[str, float | None]) -> tuple[float, dict[str, Any]]:
    available = {name: value for name, value in components.items() if name in NAS_WEIGHTS and value is not None}
    total_weight = sum(NAS_WEIGHTS[name] for name in available)
    if not total_weight:
        return 0.0, {"components": {}, "weightedParts": {}, "missingSignals": list(NAS_WEIGHTS)}
    weighted = {name: (float(available[name]) / 100) * NAS_WEIGHTS[name] for name in available}
    score = round(max(0.0, min(100.0, sum(weighted.values()) / total_weight * 100)), 1)
    return score, {
        "components": {name: round(float(value), 1) for name, value in available.items()},
        "weightedParts": {name: round(value * 100, 2) for name, value in weighted.items()},
        "missingSignals": [name for name in NAS_WEIGHTS if name not in available],
    }
