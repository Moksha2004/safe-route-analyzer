from __future__ import annotations

from typing import Any

from app.scoring.weights import NAS_WEIGHTS

# Unknown signals count as neutral rather than bad or good, so one strong signal cannot produce 100/100 on its own.
UNKNOWN_SIGNAL_VALUE = 0.5


def score_night_activity(components: dict[str, float | None]) -> tuple[float, dict[str, Any]]:
    available = {name: value for name, value in components.items() if name in NAS_WEIGHTS and value is not None}
    if not available:
        return 0.0, {"components": {}, "weightedParts": {}, "missingSignals": list(NAS_WEIGHTS), "evidenceCoverage": 0.0}
    weighted = {name: (float(available[name]) / 100) * NAS_WEIGHTS[name] for name in available}
    missing = [name for name in NAS_WEIGHTS if name not in available]
    neutral = sum(NAS_WEIGHTS[name] for name in missing) * UNKNOWN_SIGNAL_VALUE
    total_weight = sum(NAS_WEIGHTS.values())
    score = round(max(0.0, min(100.0, (sum(weighted.values()) + neutral) / total_weight * 100)), 1)
    return score, {
        "components": {name: round(float(value), 1) for name, value in available.items()},
        "weightedParts": {name: round(value * 100, 2) for name, value in weighted.items()},
        "missingSignals": missing,
        "evidenceCoverage": round(100 * sum(NAS_WEIGHTS[name] for name in available) / total_weight, 1),
    }
