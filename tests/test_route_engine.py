import asyncio

from app.agents.agent1_route_engine import RouteEngine, _preference_terms
from app.models.schemas import AnalyzeRequest, Coordinate


class FakeTomTom:
    async def routes(self, start, destination, mode, alternatives, departure=None):
        return [
            {
                "legs": [{"points": [
                    {"longitude": 77.60, "latitude": 12.90},
                    {"longitude": 77.61, "latitude": 12.91},
                    {"longitude": 77.62, "latitude": 12.92},
                ]}],
                "summary": {"lengthInMeters": 3000, "travelTimeInSeconds": 900, "trafficDelayInSeconds": 120},
            },
            {
                "legs": [{"points": [
                    {"longitude": 77.60, "latitude": 12.90},
                    {"longitude": 77.615, "latitude": 12.915},
                    {"longitude": 77.62, "latitude": 12.92},
                ]}],
                "summary": {"lengthInMeters": 3500, "travelTimeInSeconds": 1000, "trafficDelayInSeconds": 60},
            },
        ]

    async def along_route_pois(self, points):
        return []

    async def along_route_search(self, points, query):
        if query == "lake" and any(abs(point[0] - 77.615) < 0.0001 for point in points):
            return [{"id": "lake-1", "poi": {"name": "Bellandur Lake"}, "position": {"lat": 12.915, "lon": 77.615}}]
        return []

    async def incidents(self, bbox):
        return []


class FakeOverpass:
    async def street_lamps(self, bbox):
        return []


def test_preference_terms_extract_landmarks_from_natural_language():
    assert _preference_terms("I prefer a route that goes near a lake and park") == ["lake", "park"]


def test_route_engine_returns_geojson_nas_lighting_and_limitations():
    async def run():
        request = AnalyzeRequest(
            start=Coordinate(lat=12.90, lon=77.60),
            destination=Coordinate(lat=12.92, lon=77.62),
            mode="car",
            maxRoutes=2,
            departureTime="2026-10-25T21:00:00+05:30",
            preferences="I prefer a route with lake",
        )
        result = await RouteEngine(FakeTomTom(), FakeOverpass(), None).analyze(request)
        assert len(result["routes"]) == 2
        for route in result["routes"]:
            assert route["geometry"]["type"] == "LineString"
            assert 0 <= route["nightActivityScore"] <= 100
            assert 0 <= route["streetLightingScore"] <= 100
            assert "streetLighting" in route["nightActivityBreakdown"]["missingSignals"]
            assert "nightTrafficActivity" in route["missingSignals"]
        assert result["safetyClaims"] is False
        assert result["limitations"]
        lake_route = next(route for route in result["routes"] if route["preferenceMatches"])
        assert lake_route["preferenceMatches"] == ["lake"]
        assert lake_route["preferenceScore"] == 100
        assert any(feature["properties"].get("matchedPreference") == "lake" for feature in lake_route["poiFeatures"]["features"])
        assert result["routes"][0]["routeId"] == lake_route["routeId"]

    asyncio.run(run())


def test_route_engine_extracts_shop_hospital_police_and_residential_activity():
    class ActivityTomTom(FakeTomTom):
        async def along_route_pois(self, points):
            opened = {"timeRanges": [{"startTime": {"date": "2026-10-25", "hour": 19, "minute": 0}, "endTime": {"date": "2026-10-25", "hour": 23, "minute": 59}}]}
            return [
                {"id": "shop", "_safeRouteCategory": "shops", "poi": {"name": "Test Pharmacy", "openingHours": opened}, "position": {"lat": 12.91, "lon": 77.61}},
                {"id": "hospital", "_safeRouteCategory": "hospitals", "poi": {"name": "Test Hospital", "openingHours": opened}, "position": {"lat": 12.91, "lon": 77.61}},
                {"id": "police", "_safeRouteCategory": "police", "poi": {"name": "Police Station"}, "position": {"lat": 12.91, "lon": 77.61}},
                {"id": "residential", "_safeRouteCategory": "residential", "poi": {"name": "Residential Area"}, "position": {"lat": 12.91, "lon": 77.61}},
            ]

    async def run():
        request = AnalyzeRequest(
            start=Coordinate(lat=12.90, lon=77.60),
            destination=Coordinate(lat=12.92, lon=77.62),
            mode="car",
            maxRoutes=1,
            departureTime="2026-10-25T20:00:00+05:30",
        )
        result = await RouteEngine(ActivityTomTom(), FakeOverpass(), None).analyze(request)
        route = result["routes"][0]
        assert route["activitySummary"]["shops"]["total"] == 1
        assert route["activitySummary"]["shops"]["open"] == 1
        assert route["activitySummary"]["hospitals"]["open"] == 1
        assert route["policeCount"] == 1
        assert route["residentialCoveragePercent"] > 0
        assert route["nightActivityBreakdown"]["components"]["policePresence"] > 0

    asyncio.run(run())


def test_route_engine_handles_unknown_shop_and_hospital_hours_without_crashing():
    class UnknownHoursTomTom(FakeTomTom):
        async def along_route_pois(self, points):
            return [
                {"id": "shop", "_safeRouteCategory": "shops", "poi": {"name": "Unknown Hours Shop"}, "position": {"lat": 12.91, "lon": 77.61}},
                {"id": "hospital", "_safeRouteCategory": "hospitals", "poi": {"name": "Unknown Hours Hospital"}, "position": {"lat": 12.91, "lon": 77.61}},
            ]

    async def run():
        request = AnalyzeRequest(
            start=Coordinate(lat=12.90, lon=77.60),
            destination=Coordinate(lat=12.92, lon=77.62),
            mode="car",
            maxRoutes=1,
            departureTime="2026-10-25T20:00:00+05:30",
        )
        result = await RouteEngine(UnknownHoursTomTom(), FakeOverpass(), None).analyze(request)
        route = result["routes"][0]
        assert route["activitySummary"]["shops"]["unknown"] == 1
        assert route["activitySummary"]["hospitals"]["unknown"] == 1
        assert "shopOpeningHours" in route["missingSignals"]
        assert "hospitalOpeningHours" in route["missingSignals"]
        assert "openShopsAtNight" not in route["nightActivityBreakdown"]["components"]
        assert "openHospitalsAtNight" not in route["nightActivityBreakdown"]["components"]

    asyncio.run(run())


def test_route_engine_generates_longer_route_through_requested_lake():
    class LakeDetourTomTom(FakeTomTom):
        async def routes(self, start, destination, mode, alternatives, departure=None):
            return [{
                "legs": [{"points": [
                    {"longitude": 77.60, "latitude": 12.90},
                    {"longitude": 77.62, "latitude": 12.92},
                ]}],
                "summary": {"lengthInMeters": 3000, "travelTimeInSeconds": 900, "trafficDelayInSeconds": 0},
            }]

        async def along_route_search(self, points, query):
            return [{"id": "far-lake", "poi": {"name": "Bellandur Lake"}, "position": {"lat": 12.925, "lon": 77.61}}]

        async def route_via(self, start, waypoint, destination, mode, departure=None):
            assert waypoint == {"lat": 12.925, "lon": 77.61}
            return {
                "legs": [{"points": [
                    {"longitude": 77.60, "latitude": 12.90},
                    {"longitude": 77.61, "latitude": 12.925},
                    {"longitude": 77.62, "latitude": 12.92},
                ]}],
                "summary": {"lengthInMeters": 6000, "travelTimeInSeconds": 1800, "trafficDelayInSeconds": 0},
            }

    async def run():
        request = AnalyzeRequest(
            start=Coordinate(lat=12.90, lon=77.60),
            destination=Coordinate(lat=12.92, lon=77.62),
            mode="car",
            maxRoutes=2,
            departureTime="2026-10-25T21:00:00+05:30",
            preferences="Please include a lake on this route",
        )
        result = await RouteEngine(LakeDetourTomTom(), FakeOverpass(), None).analyze(request)
        assert len(result["routes"]) == 2
        preferred = result["routes"][0]
        assert preferred["preferenceMatches"] == ["lake"]
        assert preferred["distanceMeters"] == 6000
        assert preferred["durationSeconds"] == 1800
        assert any(feature["properties"].get("name") == "Bellandur Lake" for feature in preferred["poiFeatures"]["features"])

    asyncio.run(run())


def test_route_engine_falls_back_to_nearby_lake_search_when_along_route_has_no_match():
    class NearbyLakeTomTom(FakeTomTom):
        async def along_route_search(self, points, query):
            return []

        async def search_near_point(self, query, point, limit=5, radius_meters=5000):
            assert query == "lake"
            assert limit == 5
            assert radius_meters == 5000
            return [{"id": "lake-near", "poi": {"name": "Nearby Lake"}, "position": {"lat": 12.93, "lon": 77.615}}]

        async def route_via(self, start, waypoint, destination, mode, departure=None):
            return {
                "legs": [{"points": [
                    {"longitude": 77.60, "latitude": 12.90},
                    {"longitude": 77.615, "latitude": 12.93},
                    {"longitude": 77.62, "latitude": 12.92},
                ]}],
                "summary": {"lengthInMeters": 7000, "travelTimeInSeconds": 2100, "trafficDelayInSeconds": 0},
            }

    async def run():
        request = AnalyzeRequest(
            start=Coordinate(lat=12.90, lon=77.60),
            destination=Coordinate(lat=12.92, lon=77.62),
            mode="car",
            maxRoutes=2,
            preferences="prefer lake",
        )
        result = await RouteEngine(NearbyLakeTomTom(), FakeOverpass(), None).analyze(request)
        preferred = result["routes"][0]
        assert preferred["preferenceMatches"] == ["lake"]
        assert preferred["distanceMeters"] == 7000
        assert preferred["preferenceScore"] == 100

    asyncio.run(run())


def test_route_engine_can_create_a_scenic_waypoint_route_for_a_lake_near_base_route():
    class ScenicLakeTomTom(FakeTomTom):
        async def along_route_search(self, points, query):
            return [{"id": "lake-on-route", "poi": {"name": "Ibbalur Lake"}, "position": {"lat": 12.91, "lon": 77.61}}]

        async def route_via(self, start, waypoint, destination, mode, departure=None):
            assert waypoint == {"lat": 12.91, "lon": 77.61}
            return {
                "legs": [{"points": [
                    {"longitude": 77.60, "latitude": 12.90},
                    {"longitude": 77.608, "latitude": 12.914},
                    {"longitude": 77.61, "latitude": 12.91},
                    {"longitude": 77.62, "latitude": 12.92},
                ]}],
                "summary": {"lengthInMeters": 5200, "travelTimeInSeconds": 1500, "trafficDelayInSeconds": 0},
            }

    async def run():
        request = AnalyzeRequest(
            start=Coordinate(lat=12.90, lon=77.60),
            destination=Coordinate(lat=12.92, lon=77.62),
            mode="car",
            maxRoutes=3,
            preferences="prefer a lake",
        )
        result = await RouteEngine(ScenicLakeTomTom(), FakeOverpass(), None).analyze(request)
        assert any(route["preferenceMatches"] == ["lake"] and route["distanceMeters"] == 5200 for route in result["routes"])

    asyncio.run(run())
