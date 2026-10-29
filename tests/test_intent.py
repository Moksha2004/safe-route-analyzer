import asyncio
import json

import httpx
import pytest

from app.agents.agent1_route_engine import _near_route
from app.agents.agent2a_intent import parse_preferences
from app.clients.nebius import NebiusClient
from app.scoring.ranking import rank_routes
from app.scoring.weights import bounded_multipliers


def _nebius_returning(content, observed=None) -> NebiusClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if observed is not None:
            observed.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return NebiusClient("test-key", "https://example.test/v1", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_bounded_multipliers_clamps_and_drops_unknown_factors():
    assert bounded_multipliers({"police": 9, "light": 0.1, "shop": "high", "crime": 1.5, "nas": True}) == {"police": 1.5, "light": 0.5}


def test_intent_parser_disables_reasoning_and_extracts_factors_and_landmarks():
    observed: list[dict] = []
    reply = json.dumps({"multipliers": {"police": 1.4, "duration": 0.6}, "priorities": ["police", "made-up"], "landmarks": ["Lake", "lake", "MG Road", "park", "temple"]})
    client = _nebius_returning(reply, observed)
    parsed = asyncio.run(parse_preferences(client, "police matters, happy to walk longer past a lake"))
    assert observed[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert parsed["source"] == "nebius"
    assert parsed["multipliers"] == {"police": 1.4, "duration": 0.6}
    assert parsed["priorities"] == ["police"]
    assert parsed["landmarks"] == ["lake", "mg road", "park"]


def test_intent_parser_falls_back_when_model_returns_no_content():
    parsed = asyncio.run(parse_preferences(_nebius_returning(None), "prefer police"))
    assert parsed["source"] == "defaults"
    assert parsed["multipliers"] == {}


def test_multipliers_change_day_ranking():
    def routes():
        return [
            {"routeId": "lit", "durationSeconds": 900, "nightActivityScore": 40, "streetLightingScore": 100, "policeAdvantageScore": 0},
            {"routeId": "police", "durationSeconds": 900, "nightActivityScore": 40, "streetLightingScore": 0, "policeAdvantageScore": 90},
        ]

    assert rank_routes(routes(), is_night=False, mode="car", multipliers={"light": 1.5, "police": 0.5})[0]["routeId"] == "lit"
    assert rank_routes(routes(), is_night=False, mode="car", multipliers={"light": 0.5, "police": 1.5})[0]["routeId"] == "police"


@pytest.mark.parametrize(("lon", "expected"), [(77.6100, True), (77.6105, False)])
def test_corridor_check_uses_segments_not_only_sample_points(lon, expected):
    # Samples are 1.1 km apart; a POI on the road midway is ~550 m from either sample but 0 m from the segment.
    samples = [[77.60, 12.90], [77.62, 12.90]]
    poi_lat = 12.90 if expected else 12.9010
    assert _near_route({"position": {"lat": poi_lat, "lon": lon}}, samples, 100) is expected
