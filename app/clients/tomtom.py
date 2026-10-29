from __future__ import annotations

import asyncio
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any
from urllib.parse import quote

import httpx


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _query_match(query_tokens: list[str], candidate: str) -> float:
    candidate_tokens = _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    token_scores = [
        max(SequenceMatcher(None, query_token, candidate_token).ratio() for candidate_token in candidate_tokens)
        for query_token in query_tokens
    ]
    return sum(token_scores) / len(token_scores)


def _distance_meters(origin: dict[str, float] | None, position: dict[str, Any]) -> float | None:
    if origin is None or "lat" not in position or "lon" not in position:
        return None
    lat1, lat2 = radians(origin["lat"]), radians(float(position["lat"]))
    delta_lat = lat2 - lat1
    delta_lon = radians(float(position["lon"]) - origin["lon"])
    haversine = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(haversine))


class TomTomClient:
    BASE_URL = "https://api.tomtom.com"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=12.0)
        self._owns_client = client is None
        self._search_semaphore = asyncio.Semaphore(4)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def geocode(self, place: str) -> dict[str, float]:
        response = await self.client.get(f"{self.BASE_URL}/search/2/geocode/{quote(place, safe='')}.json", params={"key": self.api_key, "limit": 1})
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            raise ValueError(f"No geocoding result for {place!r}")
        position = results[0]["position"]
        return {"lat": float(position["lat"]), "lon": float(position["lon"])}

    async def search_places(
        self,
        query: str,
        limit: int = 10,
        near: dict[str, float] | None = None,
        radius_meters: int = 50_000,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "key": self.api_key,
            "limit": min(max(limit, 1), 20),
            "countrySet": "IN",
            "language": "en-GB",
            "idxSet": "POI,PAD,Str,XStr,Geo,Addr",
            "typeahead": "true",
            "minFuzzyLevel": 1,
            "maxFuzzyLevel": 4,
        }
        if near:
            # Bias toward nearby results without a hard radius filter; a strict
            # radius can hide useful matches when the typed place is misspelled.
            params["geobias"] = f"point:{near['lat']},{near['lon']}"
        response = await self.client.get(
            f"{self.BASE_URL}/search/2/search/{quote(query, safe='')}.json",
            params=params,
        )
        response.raise_for_status()
        suggestions = []
        query_tokens = _tokens(query)
        for result in response.json().get("results", []):
            position = result.get("position", {})
            poi = result.get("poi", {})
            address = result.get("address", {})
            if not isinstance(position, dict) or "lat" not in position or "lon" not in position:
                continue
            name = poi.get("name") or address.get("freeformAddress") or query
            full_address = address.get("freeformAddress", "")
            label = f"{name}, {full_address}" if full_address and full_address.lower() not in name.lower() else name
            searchable_text = " ".join((str(name), str(full_address), str(address.get("neighbourhood", "")), str(address.get("municipality", ""))))
            lexical_match = _query_match(query_tokens, searchable_text)
            distance = _distance_meters(near, position) if near else None
            suggestions.append({
                "id": result.get("id", f"{position['lat']},{position['lon']}"),
                "label": label,
                "address": full_address,
                "lat": float(position["lat"]),
                "lon": float(position["lon"]),
                "_relevance": lexical_match,
                "_providerScore": float(result.get("score", 0) or 0),
                "_distance": distance,
            })
        provider_max = max((item["_providerScore"] for item in suggestions), default=0.0)
        for suggestion in suggestions:
            provider_relevance = suggestion["_providerScore"] / provider_max if provider_max else 0.0
            distance = suggestion["_distance"]
            proximity_relevance = max(0.0, 1.0 - distance / max(radius_meters, 1)) if distance is not None else 0.0
            suggestion["_combinedRelevance"] = 0.75 * suggestion["_relevance"] + 0.15 * provider_relevance + 0.10 * proximity_relevance
        suggestions.sort(key=lambda item: (
            -item["_combinedRelevance"],
            item["_distance"] if item["_distance"] is not None else float("inf"),
        ))
        for suggestion in suggestions:
            suggestion.pop("_relevance")
            suggestion.pop("_providerScore")
            suggestion.pop("_distance")
            suggestion.pop("_combinedRelevance")
        return suggestions

    async def routes(
        self,
        start: dict[str, float],
        destination: dict[str, float],
        mode: str,
        alternatives: int,
        departure: datetime | None = None,
    ) -> list[dict[str, Any]]:
        origin = f"{start['lat']},{start['lon']}"
        target = f"{destination['lat']},{destination['lon']}"
        url = f"{self.BASE_URL}/routing/1/calculateRoute/{origin}:{target}/json"
        params: dict[str, Any] = {"key": self.api_key, "travelMode": mode, "maxAlternatives": alternatives, "alternativeType": "anyRoute", "traffic": "true", "sectionType": "traffic", "routeType": "fastest", "instructionsType": "tagged", "language": "en-GB", "computeTravelTimeFor": "all"}
        if departure is not None:
            params["departAt"] = departure.isoformat()
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json().get("routes", [])

    async def route_via(
        self,
        start: dict[str, float],
        waypoint: dict[str, float],
        destination: dict[str, float],
        mode: str,
        departure: datetime | None = None,
    ) -> dict[str, Any] | None:
        locations = (start, waypoint, destination)
        path = ":".join(f"{point['lat']},{point['lon']}" for point in locations)
        params: dict[str, Any] = {
            "key": self.api_key,
            "travelMode": mode,
            "maxAlternatives": 0,
            "traffic": "true",
            "sectionType": "traffic",
            "routeType": "fastest",
            "instructionsType": "tagged",
            "language": "en-GB",
            "computeTravelTimeFor": "all",
        }
        if departure is not None:
            params["departAt"] = departure.isoformat()
        response = await self.client.get(f"{self.BASE_URL}/routing/1/calculateRoute/{path}/json", params=params)
        response.raise_for_status()
        routes = response.json().get("routes", [])
        return routes[0] if routes else None

    async def along_route_pois(self, points: list[list[float]]) -> list[dict[str, Any]]:
        if not points:
            return []
        route = {"route": {"points": [{"lat": lat, "lon": lon} for lon, lat in points]}}
        queries = [
            ("police", "police station"),
            ("hospitals", "hospital"),
            ("shops", "pharmacy"),
            ("shops", "supermarket"),
            ("shops", "restaurant"),
            ("shops", "cafe"),
            ("residential", "residential area"),
        ]

        async def search(query: str, category: str) -> list[dict[str, Any]]:
            try:
                async with self._search_semaphore:
                    response = await self.client.post(
                        f"{self.BASE_URL}/search/2/searchAlongRoute/{quote(query, safe='')}.json",
                        params={"key": self.api_key, "limit": 20, "maxDetourTime": 600, "openingHours": "nextSevenDays", "timeZone": "iana", "spreadingMode": "plan"},
                        json=route,
                    )
                response.raise_for_status()
                fetched_at = datetime.now(timezone.utc).isoformat()
                return [{**item, "_safeRouteCategory": category, "_safeRouteOpeningHoursFetchedAt": fetched_at} for item in response.json().get("results", [])]
            except httpx.HTTPError:
                return [{"_safeRouteSearchError": category}]

        responses = await asyncio.gather(*(search(query, category) for category, query in queries))
        results: list[dict[str, Any]] = []
        for response in responses:
            results.extend(response)
        return results

    async def search_near_point(
        self,
        query: str,
        point: dict[str, float],
        limit: int = 5,
        radius_meters: int = 5_000,
    ) -> list[dict[str, Any]]:
        """Search fuzzy POI/landmark matches around a waypoint location."""
        params = {
            "key": self.api_key,
            "limit": min(max(limit, 1), 20),
            "countrySet": "IN",
            "language": "en-GB",
            "idxSet": "POI,Geo",
            "lat": point["lat"],
            "lon": point["lon"],
            "radius": radius_meters,
            "typeahead": "false",
            "minFuzzyLevel": 1,
            "maxFuzzyLevel": 4,
        }
        response = await self.client.get(
            f"{self.BASE_URL}/search/2/search/{quote(query, safe='')}.json",
            params=params,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    async def along_route_search(self, points: list[list[float]], query: str) -> list[dict[str, Any]]:
        if not points or not query.strip():
            return []
        route = {"route": {"points": [{"lat": lat, "lon": lon} for lon, lat in points]}}
        response = await self.client.post(
            f"{self.BASE_URL}/search/2/searchAlongRoute/{quote(query.strip(), safe='')}.json",
            params={"key": self.api_key, "limit": 20, "maxDetourTime": 1800, "openingHours": "nextSevenDays", "spreadingMode": "plan"},
            json=route,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    async def incidents(self, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
        south, west, north, east = bbox
        response = await self.client.get(f"{self.BASE_URL}/traffic/services/5/incidentDetails", params={"key": self.api_key, "bbox": f"{west},{south},{east},{north}", "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events,from,to,roadNumbers}}}", "language": "en-GB", "categoryFilter": "0,1,2,3,4,5,6,7,8,9,10,11,14"})
        response.raise_for_status()
        return response.json().get("incidents", [])
