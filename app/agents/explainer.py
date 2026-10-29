from __future__ import annotations

import re
from typing import Any

from app.clients.nebius import NebiusClient

MODEL = "nvidia/nemotron-3-super-120b-a12b"
SYSTEM = "Compare routes using only supplied structured metrics. Mention night activity score and relevant breakdowns. Never claim a route is safe, guaranteed safe, crime-free, or safer. Return JSON {\"explanations\": [string, ...]}."
_BANNED = re.compile(r"\b(guaranteed\s+safe|completely\s+safe|crime[- ]free|100%\s+safe)\b", re.IGNORECASE)


async def explain_routes(client: NebiusClient | None, routes: list[dict[str, Any]]) -> list[str | None]:
    if not client or not routes:
        return [None] * len(routes)
    try:
        result = await client.chat_json(MODEL, SYSTEM, str([{key: route.get(key) for key in ("rank", "nightActivityScore", "streetLightingScore", "nightActivityBreakdown", "durationSeconds", "distanceMeters", "activitySummary", "preferenceScore", "preferenceMatches")} for route in routes]))
        explanations = result.get("explanations", [])
        return [(_BANNED.sub("", str(explanations[i])).strip()[:500] or None) if i < len(explanations) else None for i in range(len(routes))]
    except Exception:
        return [None] * len(routes)
