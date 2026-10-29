from __future__ import annotations

from typing import Any

from app.config import settings


def minmax(values: list[float]) -> list[float]:
    low = min(values, default=0.0)
    high = max(values, default=0.0)
    if high <= low:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def rank_routes(routes: list[dict[str, Any]], is_night: bool, mode: str, multipliers: dict[str, float] | None = None) -> list[dict[str, Any]]:
    if not routes:
        return routes
    duration = minmax([float(route["durationSeconds"]) for route in routes])
    delay = minmax([float(route.get("trafficDelaySeconds", 0)) for route in routes])
    m = multipliers or {}

    def scaled(*factors: str) -> float:
        return sum(m.get(factor, 1.0) for factor in factors) / len(factors)

    base_night = {"car": (0.45, 0.15, 0.2, 0.2), "pedestrian": (0.55, 0.15, 0.15, 0.15), "bicycle": (0.5, 0.18, 0.16, 0.16)}[mode]
    # At night lighting, police and residential feed the ranking only through NAS, so their multipliers scale the NAS term.
    night_weights = (
        base_night[0] * scaled("nas", "light", "police", "residential"),
        base_night[1] * scaled("shop", "hospital"),
        base_night[2] * scaled("closure"),
        base_night[3] * scaled("duration"),
    )
    day_weights = {"nas": 0.09, "light": 0.20, "hospital": 0.17, "shop": 0.13, "police": 0.22, "residential": 0.12, "delay": 0.04, "closure": 0.02, "duration": 0.01}
    day_weights = {name: weight * m.get(name, 1.0) for name, weight in day_weights.items()}
    for index, route in enumerate(routes):
        nas = float(route["nightActivityScore"]) / 100
        lighting = float(route["streetLightingScore"]) / 100
        police = float(route.get("policeAdvantageScore", 0)) / 100
        amenity = min(1.0, (route.get("activitySummary", {}).get("shops", {}).get("open", 0) + route.get("activitySummary", {}).get("hospitals", {}).get("open", 0)) / 6)
        closure = min(1.0, float(route.get("severeIncidentCount", 0)) / 2)
        preference_score = float(route.get("preferenceScore", 0)) / 100
        if is_night:
            score = night_weights[0] * nas + night_weights[1] * amenity - night_weights[2] * closure - night_weights[3] * duration[index] + settings.preference_match_bonus * preference_score
        else:
            score = day_weights["nas"] * nas + day_weights["light"] * lighting + day_weights["police"] * police + day_weights["hospital"] * min(1.0, route.get("activitySummary", {}).get("hospitals", {}).get("open", 0) / 2) + day_weights["shop"] * min(1.0, route.get("activitySummary", {}).get("shops", {}).get("open", 0) / 5) + day_weights["residential"] * float(route.get("residentialCoveragePercent", 0)) / 100 - day_weights["delay"] * delay[index] - day_weights["closure"] * closure - day_weights["duration"] * duration[index] + settings.preference_match_bonus * preference_score
        route["rankScore"] = round(score, 4)
    routes.sort(key=lambda route: route["rankScore"], reverse=True)
    for rank, route in enumerate(routes, start=1):
        route["rank"] = rank
    return routes
