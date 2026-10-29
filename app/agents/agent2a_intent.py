from __future__ import annotations

from typing import Any

import httpx

from app.clients.nebius import NebiusClient
from app.scoring.weights import MULTIPLIER_MAX, MULTIPLIER_MIN, RANKING_FACTORS, bounded_multipliers

MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
TIMEOUT_SECONDS = 10.0
MAX_LANDMARKS = 3
SYSTEM = (
    "You convert a traveller's free-text route preferences into ranking multipliers and landmark searches. "
    'Return JSON only: {"multipliers": {"<factor>": <number>}, "priorities": ["<factor>", ...], "landmarks": ["<search term>", ...]}. '
    "Allowed factors: " + "; ".join(f"{key} = {meaning}" for key, meaning in RANKING_FACTORS.items()) + ". "
    f"1.0 is neutral; use up to {MULTIPLIER_MAX} for factors the traveller emphasises and down to {MULTIPLIER_MIN} for factors they de-emphasise. "
    "Only include factors the text supports. priorities lists emphasised factors, most important first. "
    f"landmarks lists at most {MAX_LANDMARKS} short map search terms for specific places or features the traveller wants the route to pass "
    "(for example lake, park, temple, MG Road); exclude anything already covered by the factors and leave it empty when none are named. "
    "Never make safety claims."
)


def defaults() -> dict[str, Any]:
    return {"model": MODEL, "multipliers": {}, "priorities": [], "landmarks": [], "source": "defaults"}


async def parse_preferences(client: NebiusClient | None, text: str | None) -> dict[str, Any]:
    if not client or not text:
        return defaults()
    try:
        parsed = await client.chat_json(MODEL, SYSTEM, text, timeout=TIMEOUT_SECONDS, max_tokens=300)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return defaults()
    multipliers = bounded_multipliers(parsed.get("multipliers"))
    priorities = [item for item in parsed.get("priorities", []) if isinstance(item, str) and item in RANKING_FACTORS][:len(RANKING_FACTORS)]
    landmarks: list[str] = []
    for item in parsed.get("landmarks", []) if isinstance(parsed.get("landmarks"), list) else []:
        term = str(item).strip().casefold()[:40]
        if term and term not in landmarks:
            landmarks.append(term)
    return {"model": MODEL, "multipliers": multipliers, "priorities": priorities, "landmarks": landmarks[:MAX_LANDMARKS], "source": "nebius"}
