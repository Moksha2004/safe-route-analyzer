from __future__ import annotations

from typing import Any

import httpx


class OverpassClient:
    def __init__(self, url: str, client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self.client = client or httpx.AsyncClient(timeout=60.0, headers={"User-Agent": "safe-route/1.0", "Accept": "application/json"})
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def street_lamps(self, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
        south, west, north, east = bbox
        query = f"[out:json][timeout:60];node[\"highway\"=\"street_lamp\"]({south},{west},{north},{east});out body;"
        response = await self.client.post(self.url, data={"data": query})
        response.raise_for_status()
        return response.json().get("elements", [])
