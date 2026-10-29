from __future__ import annotations

from typing import Any

from app.clients.nebius import NebiusClient
from app.scoring.weights import DEFAULT_WEIGHTS, bounded_weights

MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
SYSTEM = "Parse travel preferences into JSON only: {\"weights\": {}, \"priorities\": []}. Return only bounded scoring hints; never make safety claims."


async def parse_preferences(client: NebiusClient | None, text: str | None, mode: str) -> dict[str, Any]:
    defaults = {"weights": DEFAULT_WEIGHTS[mode].copy(), "priorities": [], "source": "defaults"}
    if not client or not text:
        return defaults
    try:
        parsed = await client.chat_json(MODEL, SYSTEM, text)
        parsed["weights"] = bounded_weights(mode, parsed.get("weights"))
        parsed["priorities"] = [str(item)[:80] for item in parsed.get("priorities", []) if isinstance(item, str)][:10]
        parsed["source"] = "nebius"
        return parsed
    except (httpx_error_types()):
        return defaults
    except (ValueError, KeyError, TypeError):
        return defaults


def httpx_error_types() -> tuple[type[BaseException], ...]:
    import httpx
    return (httpx.HTTPError, TimeoutError)
