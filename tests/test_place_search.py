import asyncio

import httpx

from app.clients.tomtom import TomTomClient
from datetime import datetime


def test_tomtom_place_search_returns_coordinates_and_display_address():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search/2/search/koramangala.json"
        assert request.url.params["countrySet"] == "IN"
        assert request.url.params["geobias"] == "point:12.9,77.6"
        assert request.url.params["typeahead"] == "true"
        assert request.url.params["maxFuzzyLevel"] == "4"
        assert request.url.params["idxSet"] == "POI,PAD,Str,XStr,Geo,Addr"
        assert request.url.params["limit"] == "10"
        return httpx.Response(200, json={"results": [{"id": "poi-1", "poi": {"name": "Koramangala", "classifications": []}, "address": {"freeformAddress": "Bengaluru, Karnataka"}, "position": {"lat": 12.9352, "lon": 77.6245}}]})

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        tomtom = TomTomClient("test-key", client)
        result = await tomtom.search_places("koramangala", near={"lat": 12.9, "lon": 77.6})
        assert result == [{"id": "poi-1", "label": "Koramangala, Bengaluru, Karnataka", "address": "Bengaluru, Karnataka", "lat": 12.9352, "lon": 77.6245}]
        await client.aclose()

    asyncio.run(run())


def test_place_search_prefers_typo_tolerant_text_match_before_far_provider_match():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [
            {"id": "far", "score": 0.99, "poi": {"name": "Mathru International Airport", "classifications": []}, "address": {"freeformAddress": "Far City"}, "position": {"lat": 13.5, "lon": 77.5}},
            {"id": "near", "score": 0.75, "poi": {"name": "Mathru Hospital", "classifications": []}, "address": {"freeformAddress": "Bellandur, Bengaluru"}, "position": {"lat": 12.93, "lon": 77.62}},
        ]})

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        tomtom = TomTomClient("test-key", client)
        result = await tomtom.search_places("mathru bellandur", near={"lat": 12.9, "lon": 77.6})
        assert result[0]["id"] == "near"
        assert all("_combinedRelevance" not in place for place in result)
        await client.aclose()

    asyncio.run(run())


def test_search_near_point_uses_configured_radius_and_india_filter():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search/2/search/lake.json"
        assert request.url.params["lat"] == "12.9352"
        assert request.url.params["lon"] == "77.6245"
        assert request.url.params["radius"] == "5000"
        assert request.url.params["countrySet"] == "IN"
        assert request.url.params["limit"] == "7"
        return httpx.Response(200, json={"results": [{"id": "lake-1", "poi": {"name": "Ibbalur Lake"}, "position": {"lat": 12.935, "lon": 77.624}}]})

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        tomtom = TomTomClient("test-key", client)
        result = await tomtom.search_near_point("lake", {"lat": 12.9352, "lon": 77.6245}, limit=7, radius_meters=5000)
        assert result[0]["poi"]["name"] == "Ibbalur Lake"
        await client.aclose()

    asyncio.run(run())


def test_routing_requests_include_departure_datetime():
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"routes": [{"legs": []}]})

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        tomtom = TomTomClient("test-key", client)
        departure = datetime.fromisoformat("2026-10-27T08:30:00+05:30")
        await tomtom.routes({"lat": 12.9, "lon": 77.6}, {"lat": 12.95, "lon": 77.65}, "car", 2, departure=departure)
        await tomtom.route_via({"lat": 12.9, "lon": 77.6}, {"lat": 12.92, "lon": 77.62}, {"lat": 12.95, "lon": 77.65}, "car", departure=departure)
        assert len(observed) == 2
        for request in observed:
            assert request.url.params["departAt"] == departure.isoformat()
            assert request.url.params["traffic"] == "true"
        await client.aclose()

    asyncio.run(run())


def test_along_route_activity_fetches_each_category_with_weekly_hours_and_timezone():
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        assert request.method == "POST"
        assert request.url.params["openingHours"] == "nextSevenDays"
        assert request.url.params["timeZone"] == "iana"
        query = request.url.path.rsplit("/", 1)[-1].replace(".json", "").replace("%20", " ")
        category = "hospitals" if query == "hospital" else "police" if query == "police station" else "shops" if query in {"pharmacy", "supermarket", "restaurant", "cafe"} else "residential"
        return httpx.Response(200, json={"results": [{"id": query, "poi": {"name": query.title()}, "position": {"lat": 12.91, "lon": 77.61}}]})

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        tomtom = TomTomClient("test-key", client)
        results = await tomtom.along_route_pois([[77.60, 12.90], [77.61, 12.91]])
        assert len(observed) == 7
        assert {item["_safeRouteCategory"] for item in results} == {"shops", "hospitals", "police", "residential"}
        await client.aclose()

    asyncio.run(run())
