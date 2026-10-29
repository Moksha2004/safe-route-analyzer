from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "bengaluru_street_lamps.json"
LIVE_TIMEOUT_SECONDS = 30.0


def _load_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    with path.open() as handle:
        return json.load(handle)


class OverpassClient:
    def __init__(self, url: str, client: httpx.AsyncClient | None = None, snapshot_path: Path | None = SNAPSHOT_PATH) -> None:
        self.url = url
        self.client = client or httpx.AsyncClient(timeout=LIVE_TIMEOUT_SECONDS, headers={"User-Agent": "safe-route/1.0", "Accept": "application/json"})
        self._owns_client = client is None
        self._snapshot = _load_snapshot(snapshot_path)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def snapshot_covers(self, bbox: tuple[float, float, float, float]) -> bool:
        if not self._snapshot:
            return False
        south, west, north, east = bbox
        area = self._snapshot["bbox"]
        return area["south"] <= south and area["west"] <= west and north <= area["north"] and east <= area["east"]

    def snapshot_note(self) -> str | None:
        if not self._snapshot:
            return None
        return f"Street lamps inside the bundled area come from an OpenStreetMap snapshot fetched {self._snapshot['fetchedAt'][:10]} (© OpenStreetMap contributors, ODbL)."

    async def street_lamps(self, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
        south, west, north, east = bbox
        if self.snapshot_covers(bbox):
            return [
                {"type": "node", "lat": lat, "lon": lon}
                for lat, lon in self._snapshot["points"]
                if south <= lat <= north and west <= lon <= east
            ]
        query = f"[out:json][timeout:60];node[\"highway\"=\"street_lamp\"]({south},{west},{north},{east});out body;"
        response = await self.client.post(self.url, data={"data": query})
        response.raise_for_status()
        return response.json().get("elements", [])
