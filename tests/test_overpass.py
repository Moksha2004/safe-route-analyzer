import asyncio
import json

import httpx

from app.clients.overpass import OverpassClient

SNAPSHOT = {
    "bbox": {"south": 12.8, "west": 77.4, "north": 13.2, "east": 77.85},
    "fetchedAt": "2026-10-29T12:00:00+00:00",
    "points": [[12.93, 77.62], [12.95, 77.70], [13.10, 77.50]],
}


def test_snapshot_serves_lamps_inside_area_without_network(tmp_path):
    path = tmp_path / "lamps.json"
    path.write_text(json.dumps(SNAPSHOT))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("live Overpass should not be called inside the snapshot area")

    async def run():
        client = OverpassClient("https://overpass.test/api", httpx.AsyncClient(transport=httpx.MockTransport(handler)), snapshot_path=path)
        lamps = await client.street_lamps((12.92, 77.60, 12.96, 77.71))
        assert lamps == [{"type": "node", "lat": 12.93, "lon": 77.62}, {"type": "node", "lat": 12.95, "lon": 77.70}]
        assert "2026-10-29" in client.snapshot_note()
        await client.close()

    asyncio.run(run())


def test_live_overpass_used_outside_snapshot_area(tmp_path):
    path = tmp_path / "lamps.json"
    path.write_text(json.dumps(SNAPSHOT))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"elements": [{"type": "node", "lat": 19.07, "lon": 72.87}]})

    async def run():
        transport_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = OverpassClient("https://overpass.test/api", transport_client, snapshot_path=path)
        lamps = await client.street_lamps((19.0, 72.8, 19.1, 72.9))
        assert len(calls) == 1 and lamps[0]["lat"] == 19.07
        await transport_client.aclose()

    asyncio.run(run())
