from __future__ import annotations

from typing import Any


def normalize_lamp_density(counts: list[int], lengths_m: list[int]) -> list[tuple[float, float]]:
    # Scored as a share of the best-lit alternative; min-max turned 1.6 vs 1.3 lamps/km into 100 vs 0.
    densities = [count / max(length, 1) * 1000 for count, length in zip(counts, lengths_m, strict=False)]
    high = max(densities, default=0.0)
    if high == 0:
        return [(density, 0.0) for density in densities]
    return [(round(density, 2), round(100 * density / high, 1)) for density in densities]


def lamp_features(elements: list[dict[str, Any]], max_points: int = 500) -> list[dict[str, Any]]:
    nodes = [item for item in elements if item.get("type") == "node" and isinstance(item.get("lat"), (int, float)) and isinstance(item.get("lon"), (int, float))]
    if len(nodes) > max_points:
        stride = len(nodes) / max_points
        nodes = [nodes[int(index * stride)] for index in range(max_points)]
    return [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [item["lon"], item["lat"]]}, "properties": {"id": item.get("id"), "highway": "street_lamp"}}
        for item in nodes
    ]
