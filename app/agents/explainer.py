from __future__ import annotations

import json
import re
from typing import Any

from app.clients.nebius import NebiusClient

MODEL = "nvidia/nemotron-3-super-120b-a12b"
TIMEOUT_SECONDS = 25.0
SYSTEM = (
    "You compare alternative routes for a traveller using only the structured metrics supplied. "
    "Write one or two plain-language sentences per route (under 45 words), in the order given, explaining why it ranks where it does "
    "compared with the other routes: cite its night activity score out of 100, concrete counts (police stations, open shops, hospitals, "
    "mapped street lamps per km, nearby homes) and travel time, and connect them to the traveller's priorities when given. "
    "streetLightingScore is relative to the best-lit route in this comparison, not an absolute rating, and OpenStreetMap lamp mapping "
    "is sparse: describe lighting with lampsPerKm and comparisons (for example 'more mapped lamps than the other routes'), never as "
    "excellent or well lit unless lampsPerKm is above 15. "
    "Talk like a helpful local, not a data report:never mention field names, weights, weighted parts, decimals beyond one place or "
    "words like 'component', 'signal' or 'search'. Say a fact is unknown or unmapped rather than bad when data is missing. "
    "Do not invent places, numbers or crime information. Never claim a route is safe, safer, guaranteed safe or crime-free. "
    'Return JSON {"explanations": [string, ...]} with exactly one string per route.'
)
_ROUTE_FIELDS = (
    "rank", "nightActivityScore", "streetLightingScore", "lampsPerKm", "nightActivityBreakdown", "durationSeconds",
    "distanceMeters", "trafficDelaySeconds", "activitySummary", "policeCount", "residentialCoveragePercent", "preferenceMatches",
)
_BANNED = re.compile(r"\b(guaranteed\s+safe|completely\s+safe|crime[- ]free|100%\s+safe)\b", re.IGNORECASE)


async def explain_routes(client: NebiusClient | None, routes: list[dict[str, Any]], priorities: list[str] | None = None) -> list[str | None]:
    if not client or not routes:
        return [None] * len(routes)
    payload = {
        "travellerPriorities": priorities or [],
        "routes": [{key: route.get(key) for key in _ROUTE_FIELDS} for route in routes],
    }
    try:
        result = await client.chat_json(MODEL, SYSTEM, json.dumps(payload, default=str), timeout=TIMEOUT_SECONDS, max_tokens=200 * len(routes) + 200)
    except Exception:
        return [None] * len(routes)
    explanations = result.get("explanations", [])
    if not isinstance(explanations, list):
        return [None] * len(routes)
    return [(_BANNED.sub("", str(explanations[i])).strip()[:500] or None) if i < len(explanations) else None for i in range(len(routes))]
