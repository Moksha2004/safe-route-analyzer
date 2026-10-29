from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.agents.agent2a_intent import defaults as intent_defaults
from app.agents.agent2a_intent import parse_preferences
from app.agents.explainer import explain_routes
from app.clients.nebius import NebiusClient
from app.clients.overpass import OverpassClient
from app.clients.tomtom import TomTomClient
from app.config import settings
from app.models.schemas import AnalyzeRequest, Coordinate
from app.scoring.activity import opening_state
from app.scoring.night_activity import score_night_activity
from app.scoring.ranking import rank_routes
from app.scoring.street_lighting import lamp_features, normalize_lamp_density
from app.scoring.weights import DAY_REFERENCE_HOUR, is_night_hour

LIMITATIONS = [
    "This service does not provide crime data or safety guarantees.",
    "Street lighting reflects mapped OpenStreetMap street_lamp nodes, not verified bulb status; missing nodes do not prove darkness.",
    "Along-route points of interest may be incomplete, and unknown opening hours receive no credit.",
    "Residential coverage is an estimate based on TomTom category evidence, not a population or density measurement.",
]

PREFERENCE_FILLER_WORDS = {
    "a", "an", "and", "around", "by", "find", "for", "i", "in", "is", "it", "its", "me", "near", "of", "on", "or", "please", "prefer", "preferably", "route", "routes", "show", "some", "the", "this", "through", "to", "want", "with", "would", "like", "include", "including", "pass", "passing", "via", "go", "goes", "take", "along", "that", "has", "have", "there", "are", "from", "my", "way", "ways", "more", "less", "safe", "safer", "activity", "active", "shops", "shop", "open", "hospital", "hospitals", "police", "residential", "lighting", "light", "lights", "street", "traffic", "night", "day", "prefer", "want", "choose", "options", "option", "somewhere", "area", "areas",
}


def _preference_terms(text: str | None, limit: int = 5) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"[a-zA-Z0-9]+", text.casefold())
    terms: list[str] = []
    for token in tokens:
        if len(token) < 3 or token in PREFERENCE_FILLER_WORDS or token.isdigit() or token in terms:
            continue
        terms.append(token)
        if len(terms) >= limit:
            break
    return terms


def _mode_activity_categories(mode: str) -> set[str]:
    if mode in {"pedestrian", "bicycle"}:
        return {"pedestrian", "bicycle", "all"}
    return {"car", "all"}


def _position(value: Any) -> dict[str, float] | None:
    if isinstance(value, Coordinate):
        return {"lat": value.lat, "lon": value.lon}
    if not isinstance(value, dict):
        return None
    if "lat" in value and "lon" in value:
        return {"lat": float(value["lat"]), "lon": float(value["lon"])}
    return None


def _route_shape(route: dict[str, Any]) -> list[list[float]]:
    geometry: list[list[float]] = []
    for leg in route.get("legs", []):
        points = leg.get("points", [])
        for point in points:
            if "longitude" not in point or "latitude" not in point:
                continue
            coordinate = [float(point["longitude"]), float(point["latitude"])]
            if not geometry or coordinate != geometry[-1]:
                geometry.append(coordinate)
    return geometry


def _route_signature(points: list[list[float]], samples: int = 25) -> tuple[tuple[float, float], ...]:
    if not points:
        return ()
    if len(points) == 1:
        return ((round(points[0][0], 4), round(points[0][1], 4)),)
    indexes = {round(index * (len(points) - 1) / (samples - 1)) for index in range(samples)}
    sampled = sorted(indexes)
    return tuple((round(points[index][0], 4), round(points[index][1], 4)) for index in sampled)


def _bbox(points: list[list[float]], padding: float = 0.001) -> tuple[float, float, float, float]:
    lons, lats = [point[0] for point in points], [point[1] for point in points]
    return min(lats) - padding, min(lons) - padding, max(lats) + padding, max(lons) + padding


def _sample(points: list[list[float]], stride: int = 1, limit: int = 80) -> list[list[float]]:
    samples = points[::stride]
    if points and (not samples or samples[-1] != points[-1]):
        samples.append(points[-1])
    if len(samples) > limit:
        step = len(samples) / limit
        samples = [samples[int(index * step)] for index in range(limit)]
    return samples


def _route_length(points: list[list[float]]) -> int:
    total = 0.0
    for first, second in zip(points, points[1:]):
        lat1, lat2 = math.radians(first[1]), math.radians(second[1])
        dlat, dlon = lat2 - lat1, math.radians(second[0] - first[0])
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        total += 6_371_000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(total)


def _passing_time(poi: dict[str, Any], points: list[list[float]], departure: datetime, duration_seconds: int) -> datetime:
    position = poi.get("position", {})
    if not isinstance(position, dict) or position.get("lon") is None or position.get("lat") is None:
        return departure
    target_lon, target_lat = float(position["lon"]), float(position["lat"])
    route_length = max(_route_length(points), 1)
    traveled = 0.0
    best_distance_squared = float("inf")
    traveled_to_closest = 0.0
    for first, second in zip(points, points[1:]):
        latitude_scale = math.cos(math.radians((first[1] + second[1]) / 2))
        dx = (second[0] - first[0]) * latitude_scale
        dy = second[1] - first[1]
        px = (target_lon - first[0]) * latitude_scale
        py = target_lat - first[1]
        segment_squared = dx * dx + dy * dy
        fraction = 0.0 if segment_squared == 0 else min(1.0, max(0.0, (px * dx + py * dy) / segment_squared))
        projected_x, projected_y = fraction * dx, fraction * dy
        distance_squared = (px - projected_x) ** 2 + (py - projected_y) ** 2
        segment_length = math.hypot(dx, dy) * 111_195
        if distance_squared < best_distance_squared:
            best_distance_squared = distance_squared
            traveled_to_closest = traveled + fraction * segment_length
        traveled += segment_length
    return departure + timedelta(seconds=duration_seconds * min(traveled_to_closest / route_length, 1.0))


def _near_route(point: dict[str, Any], samples: list[list[float]], corridor_m: float) -> bool:
    position = point.get("position")
    if isinstance(position, dict):
        coordinates: list[Any] = [[position.get("lon", position.get("longitude")), position.get("lat", position.get("latitude"))]]
    else:
        geometry = point.get("geometry", {})
        coordinates = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
        if isinstance(coordinates, list) and len(coordinates) >= 2 and all(isinstance(value, (int, float)) for value in coordinates[:2]):
            coordinates = [coordinates]
        elif isinstance(coordinates, list):
            coordinates = [coordinate for part in coordinates for coordinate in (part if isinstance(part, list) else [])]
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2 or coordinate[0] is None or coordinate[1] is None:
            continue
        if _distance_to_polyline_m(float(coordinate[0]), float(coordinate[1]), samples) <= corridor_m:
            return True
    return False


def _distance_to_polyline_m(lon: float, lat: float, samples: list[list[float]]) -> float:
    # Distance to segments, not just vertices: samples are ~350 m apart while corridors are 40-100 m wide.
    x_scale = 111_320 * math.cos(math.radians(lat))
    relative = [((route_lon - lon) * x_scale, (route_lat - lat) * 111_320) for route_lon, route_lat in samples]
    if len(relative) == 1:
        return math.hypot(*relative[0])
    best = float("inf")
    for (ax, ay), (bx, by) in zip(relative, relative[1:]):
        dx, dy = bx - ax, by - ay
        length_squared = dx * dx + dy * dy
        t = 0.0 if length_squared == 0 else min(1.0, max(0.0, -(ax * dx + ay * dy) / length_squared))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def _category(poi: dict[str, Any]) -> str:
    poi_details = poi.get("poi", {})
    classification_names = [
        name.get("name", "")
        for classification in poi_details.get("classifications", [])
        for name in classification.get("names", [])
    ] if isinstance(poi_details, dict) else []
    category_ids = [str(item.get("id", "")) for item in poi_details.get("categorySet", [])] if isinstance(poi_details, dict) else []
    text = " ".join([*(str(poi.get(key, "")) for key in ("poi", "address", "categorySet", "categories", "name")), *classification_names, *category_ids]).lower()
    if any(word in text for word in ("police", "police station")):
        return "police"
    if any(word in text for word in ("hospital", "medical center", "clinic")):
        return "hospitals"
    if any(word in text for word in ("supermarket", "grocery", "restaurant", "cafe", "pharmacy", "shop", "store")):
        return "shops"
    if any(word in text for word in ("residential", "housing", "apartment", "neighborhood")):
        return "residential"
    return "other"


def _time_for_request(value: str | None, timezone: str) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Kolkata")
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(zone) if parsed.tzinfo else parsed.replace(tzinfo=zone)
        except ValueError:
            pass
    return datetime.now(zone)


class RouteEngine:
    def __init__(self, tomtom: TomTomClient | None, overpass: OverpassClient | None, nebius: NebiusClient | None, explain_enabled: bool = True) -> None:
        self.tomtom = tomtom
        self.overpass = overpass
        self.nebius = nebius
        self.explain_enabled = explain_enabled
        self._semaphore = asyncio.Semaphore(4)

    async def analyze(self, request: AnalyzeRequest) -> dict[str, Any]:
        if not self.tomtom:
            raise RuntimeError("TOMTOM_API_KEY is required to analyze routes")
        # Overlaps geocoding/routing. The LLM only rescales ranking weights and names landmarks; it never touches geometry.
        intent_task = asyncio.create_task(parse_preferences(self.nebius, request.preferences)) if self.nebius and request.preferences else None
        try:
            start, destination = _position(request.start), _position(request.destination)
            if start is None:
                start = await self.tomtom.geocode(str(request.start))
            if destination is None:
                destination = await self.tomtom.geocode(str(request.destination))
            departure = _time_for_request(request.departureTime, request.timezone)
            raw_routes = await self.tomtom.routes(
                start,
                destination,
                {"car": "car", "pedestrian": "pedestrian", "bicycle": "bicycle"}[request.mode],
                request.maxRoutes - 1,
                departure=departure,
            )
            if not raw_routes:
                raise ValueError("TomTom returned no routes")
            unique_routes: list[dict[str, Any]] = []
            route_signatures: set[tuple[tuple[float, float], ...]] = set()
            for raw in raw_routes:
                shape = _route_shape(raw)
                signature = _route_signature(shape)
                if len(shape) >= 2 and signature not in route_signatures:
                    unique_routes.append(raw)
                    route_signatures.add(signature)
            raw_routes = unique_routes
            if not raw_routes:
                raise ValueError("TomTom returned no unique routes with valid geometry")
            route_parts = [_route_shape(item) for item in raw_routes]
            if any(len(points) < 2 for points in route_parts):
                raise ValueError("TomTom route is missing valid geometry")
        except BaseException:
            if intent_task:
                intent_task.cancel()
            raise
        parsed = await intent_task if intent_task else intent_defaults()
        night = is_night_hour(departure.hour)
        preference_terms = parsed["landmarks"] if parsed["source"] == "nebius" else _preference_terms(request.preferences)

        async def load_route_pois(points: list[list[float]]) -> list[dict[str, Any]]:
            async with self._semaphore:
                return await self.tomtom.along_route_pois(_sample(points))

        async def load_preference_search(points: list[list[float]], term: str) -> list[dict[str, Any]]:
            async with self._semaphore:
                return await self.tomtom.along_route_search(_sample(points), term)

        async def load_preference_near_point(term: str, point: dict[str, float]) -> list[dict[str, Any]]:
            async with self._semaphore:
                return await self.tomtom.search_near_point(
                    term,
                    point,
                    limit=5,
                    radius_meters=settings.preference_search_radius_meters,
                )

        preference_responses = await asyncio.gather(
            *(load_preference_search(points, term) for points in route_parts for term in preference_terms),
            return_exceptions=True,
        ) if preference_terms else []
        fallback_searches: list[tuple[int, str, asyncio.Task[list[dict[str, Any]]]]] = []
        for route_index, points in enumerate(route_parts):
            for term_index, term in enumerate(preference_terms):
                response_index = route_index * len(preference_terms) + term_index
                response = preference_responses[response_index] if response_index < len(preference_responses) else []
                if not isinstance(response, list) or not response:
                    sample_count = settings.preference_search_points_per_route
                    indexes = sorted({round(index * (len(points) - 1) / (sample_count + 1)) for index in range(1, sample_count + 1)})
                    for sample_index in indexes:
                        sample_point = points[sample_index]
                        fallback_searches.append((route_index, term, asyncio.create_task(
                            load_preference_near_point(term, {"lat": sample_point[1], "lon": sample_point[0]})
                        )))
        nearby_responses = await asyncio.gather(*(task for _, _, task in fallback_searches), return_exceptions=True) if fallback_searches else []

        # First retain landmarks that are already close to a returned route.
        route_preference_evidence: list[list[dict[str, Any]]] = [[] for _ in route_parts]
        candidate_sites: dict[str, tuple[str, dict[str, Any]]] = {}
        for route_index, points in enumerate(route_parts):
            route_samples = _sample(points, stride=max(1, round(len(points) / max(_route_length(points) / 350, 1))))
            for term_index, term in enumerate(preference_terms):
                response_index = route_index * len(preference_terms) + term_index
                results = preference_responses[response_index] if response_index < len(preference_responses) else []
                if not isinstance(results, list):
                    continue
                for result in results:
                    position = result.get("position", {})
                    if not isinstance(position, dict) or position.get("lat") is None or position.get("lon") is None:
                        continue
                    evidence = {**result, "_matchedPreferenceTerm": term}
                    if _near_route(result, route_samples, settings.preference_corridor_meters):
                        route_preference_evidence[route_index].append(evidence)
                    # Every matched place can seed a waypoint route, including
                    # a lake already near a base route: routing through its
                    # entrance may create a useful scenic alternative.
                    site_id = str(result.get("id") or f"{position['lat']:.5f},{position['lon']:.5f}")
                    candidate_sites.setdefault(site_id, (term, result))
        for (route_index, term, _), response in zip(fallback_searches, nearby_responses, strict=True):
            if not isinstance(response, list):
                continue
            route_samples = _sample(route_parts[route_index], stride=max(1, round(len(route_parts[route_index]) / max(_route_length(route_parts[route_index]) / 350, 1))))
            for result in response:
                position = result.get("position", {})
                if not isinstance(position, dict) or position.get("lat") is None or position.get("lon") is None:
                    continue
                evidence = {**result, "_matchedPreferenceTerm": term}
                if _near_route(result, route_samples, settings.preference_corridor_meters):
                    route_preference_evidence[route_index].append(evidence)
                site_id = str(result.get("id") or f"{position['lat']:.5f},{position['lon']:.5f}")
                candidate_sites.setdefault(site_id, (term, result))

        # SearchAlongRoute can find a feature within its allowed detour even if
        # it is not on the original road. Build an actual route via that POI.
        candidate_limit = min(settings.preference_route_candidates, request.maxRoutes)
        candidate_items = list(candidate_sites.values())[:candidate_limit]

        async def route_via_site(term: str, result: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
            position = result["position"]
            waypoint = {"lat": float(position["lat"]), "lon": float(position["lon"])}
            async with self._semaphore:
                route = await self.tomtom.route_via(
                    start,
                    waypoint,
                    destination,
                    {"car": "car", "pedestrian": "pedestrian", "bicycle": "bicycle"}[request.mode],
                    departure=departure,
                )
            return term, result, route

        if candidate_items:
            via_results = await asyncio.gather(
                *(route_via_site(term, result) for term, result in candidate_items),
                return_exceptions=True,
            )
            for via_result in via_results:
                if isinstance(via_result, BaseException):
                    continue
                term, place, via_route = via_result
                if not via_route:
                    continue
                via_shape = _route_shape(via_route)
                signature = _route_signature(via_shape)
                if len(via_shape) < 2 or signature in route_signatures:
                    continue
                raw_routes.append(via_route)
                route_parts.append(via_shape)
                route_signatures.add(signature)
                route_preference_evidence.append([{**place, "_matchedPreferenceTerm": term}])

        async def load_route_pois_with_fallback(points: list[list[float]]) -> list[dict[str, Any]]:
            try:
                return await load_route_pois(points)
            except (httpx.HTTPError, TimeoutError):
                return [{"_safeRouteSearchError": "poiSearch"}]

        bbox = _bbox([point for shape in route_parts for point in shape])

        async def load_incidents() -> list[dict[str, Any]]:
            try:
                return await self.tomtom.incidents(bbox)
            except (httpx.HTTPError, TimeoutError):
                return []

        async def load_lamps() -> list[dict[str, Any]] | None:
            if not self.overpass:
                return None
            try:
                return await self.overpass.street_lamps(bbox)
            except (httpx.HTTPError, TimeoutError, ValueError):
                return None

        *poi_responses, incidents, loaded_lamps = await asyncio.gather(
            *(load_route_pois_with_fallback(points) for points in route_parts),
            load_incidents(),
            load_lamps(),
        )
        poi_search_missing = any(
            any(item.get("_safeRouteSearchError") == "poiSearch" for item in response)
            for response in poi_responses
            if isinstance(response, list)
        )
        poi_responses = [response if isinstance(response, list) else [{"_safeRouteSearchError": "poiSearch"}] for response in poi_responses]
        lighting_missing = loaded_lamps is None
        lamps: list[dict[str, Any]] = loaded_lamps or []
        preliminary: list[dict[str, Any]] = []
        counts: list[int] = []
        lengths: list[int] = []
        for index, raw in enumerate(raw_routes):
            points = route_parts[index]
            samples = _sample(points, stride=max(1, round(len(points) / max(_route_length(points) / 350, 1))))
            length = _route_length(points)
            lengths.append(length)
            route_pois = poi_responses[index] if isinstance(poi_responses[index], list) else []
            poi_search_errors = {
                str(item.get("_safeRouteSearchError"))
                for item in route_pois
                if item.get("_safeRouteSearchError")
            }
            deduped: dict[str, dict[str, Any]] = {}
            for poi in route_pois:
                if poi.get("_safeRouteSearchError"):
                    continue
                poi_id = str(poi.get("id", poi.get("name", id(poi))))
                if _near_route(poi, samples, 100):
                    deduped[poi_id] = poi
            categorized: dict[str, list[dict[str, Any]]] = {"shops": [], "hospitals": [], "police": [], "residential": []}
            features: list[dict[str, Any]] = []
            for poi in deduped.values():
                category = str(poi.get("_safeRouteCategory") or _category(poi))
                if category in categorized:
                    categorized[category].append(poi)
                position = poi.get("position", {})
                if isinstance(position, dict) and position.get("lon") is not None:
                    features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [position["lon"], position["lat"]]}, "properties": {"name": poi.get("poi", {}).get("name", "POI"), "category": category, "id": poi.get("id")}})
            preference_matches: set[str] = set()
            preference_features: list[dict[str, Any]] = []
            for result in route_preference_evidence[index]:
                term = str(result.get("_matchedPreferenceTerm", ""))
                if not term:
                    continue
                poi_info = result.get("poi", {})
                position = result.get("position", {})
                name = poi_info.get("name") if isinstance(poi_info, dict) else None
                address = result.get("address", {})
                name = name or (address.get("freeformAddress") if isinstance(address, dict) else None) or term.title()
                preference_matches.add(term)
                if isinstance(position, dict) and position.get("lon") is not None and position.get("lat") is not None:
                    preference_features.append({
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [position["lon"], position["lat"]]},
                        "properties": {"name": name, "category": "preference", "matchedPreference": term, "id": result.get("id")},
                    })
            features.extend(preference_features)
            counts.append(sum(1 for lamp in lamps if _near_route({"position": {"lat": lamp.get("lat"), "lon": lamp.get("lon")}}, samples, 50 if request.mode == "car" else 40)))
            summary_raw = raw.get("summary", {})
            duration = int(summary_raw.get("travelTimeInSeconds", 0))
            delay = max(0, int(summary_raw.get("trafficDelayInSeconds", 0) or 0))
            mode_categories = _mode_activity_categories(request.mode)
            eligible_shops = [poi for poi in categorized["shops"] if _mode_activity_categories(request.mode).intersection(set(poi.get("_safeRouteModes", ["all"])))]
            eligible_hospitals = [poi for poi in categorized["hospitals"] if _mode_activity_categories(request.mode).intersection(set(poi.get("_safeRouteModes", ["all"])))]
            eligible_police = [poi for poi in categorized["police"] if mode_categories.intersection(set(poi.get("_safeRouteModes", ["all"])))]
            eligible_residential = [poi for poi in categorized["residential"] if mode_categories.intersection(set(poi.get("_safeRouteModes", ["all"])))]
            actual_shop_states = [opening_state(poi, _passing_time(poi, points, departure, duration)) for poi in eligible_shops]
            actual_hospital_states = [opening_state(poi, _passing_time(poi, points, departure, duration)) for poi in eligible_hospitals]
            reference_time = departure if night else departure.replace(hour=DAY_REFERENCE_HOUR, minute=0, second=0, microsecond=0)
            night_shop_states = [opening_state(poi, _passing_time(poi, points, reference_time, duration)) for poi in eligible_shops]
            night_hospital_states = [opening_state(poi, _passing_time(poi, points, reference_time, duration)) for poi in eligible_hospitals]
            police_count = len(eligible_police)
            residential_percent = round(min(100.0, 100 * len(eligible_residential) / max(len(samples), 1)), 1)
            route_incidents = [incident for incident in incidents if _near_route(incident, samples, 75)]
            severe = sum(1 for incident in route_incidents if int(incident.get("properties", {}).get("magnitudeOfDelay", 0) or 0) >= 3)
            summary = {
                "shops": {**{state.lower(): actual_shop_states.count(state) for state in ("OPEN", "CLOSED", "UNKNOWN")}, "total": len(eligible_shops)},
                "hospitals": {**{state.lower(): actual_hospital_states.count(state) for state in ("OPEN", "CLOSED", "UNKNOWN")}, "total": len(eligible_hospitals)},
                "police": {"total": police_count},
                "residential": {"total": len(categorized["residential"])},
            }
            open_shop_score = min(100.0, 100 * night_shop_states.count("OPEN") / 5)
            open_hospital_score = min(100.0, 100 * night_hospital_states.count("OPEN") / 2)
            police_score = min(100.0, police_count * 50 + sum(10 for poi in eligible_police if opening_state(poi, _passing_time(poi, points, departure, duration)) == "OPEN"))
            missing_activity = [name for name, found in (("shops", eligible_shops), ("hospitals", eligible_hospitals), ("police", eligible_police), ("residential", eligible_residential)) if not found]
            if poi_search_missing:
                missing_activity.append("poiSearch")
            missing_activity.extend(f"{name}Search" for name in sorted(poi_search_errors))
            summary_components: dict[str, float] = {}
            if eligible_shops and all(state != "UNKNOWN" for state in night_shop_states):
                summary_components["openShopsAtNight"] = open_shop_score
            elif eligible_shops:
                missing_activity.append("shopOpeningHours")
            if eligible_hospitals and all(state != "UNKNOWN" for state in night_hospital_states):
                summary_components["openHospitalsAtNight"] = open_hospital_score
            elif eligible_hospitals:
                missing_activity.append("hospitalOpeningHours")
            if eligible_police:
                summary_components["policePresence"] = police_score
            if eligible_residential:
                summary_components["residentialCoverage"] = residential_percent
            
            guidance = raw.get("guidance", {})
            navigation_steps = guidance.get("instructions", []) if isinstance(guidance, dict) else []
            preference_score = round(100 * len(preference_matches) / max(len(preference_terms), 1), 1) if preference_terms else 0.0
            preliminary.append({"routeId": f"route-{index + 1}", "rank": 0, "rankScore": 0, "geometry": {"type": "LineString", "coordinates": points}, "durationSeconds": duration, "distanceMeters": int(raw.get("summary", {}).get("lengthInMeters", length)), "trafficDelaySeconds": delay, "departureTime": departure, "estimatedArrivalTime": departure + timedelta(seconds=duration), "trafficSemantics": "night_active_corridor" if night else "day_congestion", "nightActivityTrafficScore": None, "nightActivityScore": 0.0, "streetLightingScore": 0.0, "streetLampCount": counts[-1], "lampsPerKm": round(counts[-1] / max(length / 1000, 0.001), 2), "streetLamps": {"type": "FeatureCollection", "features": []}, "poiFeatures": {"type": "FeatureCollection", "features": features}, "incidentsAlongRoute": route_incidents, "navigationSteps": navigation_steps, "preferenceScore": preference_score, "preferenceMatches": sorted(preference_matches), "activitySummary": summary, "policeCount": police_count, "policeAdvantageScore": police_score, "residentialCoveragePercent": residential_percent, "missingSignals": missing_activity, "_components": summary_components, "severeIncidentCount": severe})
        has_route_lighting = not lighting_missing and any(counts)
        lighting = normalize_lamp_density(counts, lengths) if not lighting_missing else [(count / max(length / 1000, .001), 0.0) for count, length in zip(counts, lengths, strict=True)]
        all_lamp_features = lamp_features(lamps)
        for index, route in enumerate(preliminary):
            route["lampsPerKm"], route["streetLightingScore"] = lighting[index]
            route["streetLamps"] = {"type": "FeatureCollection", "features": [feature for feature in all_lamp_features if _near_route({"position": {"lon": feature["geometry"]["coordinates"][0], "lat": feature["geometry"]["coordinates"][1]}}, _sample(route["geometry"]["coordinates"]), 50 if request.mode == "car" else 40)]}
            if has_route_lighting:
                route["_components"]["streetLighting"] = route["streetLightingScore"]
            if not has_route_lighting:
                route["missingSignals"].append("streetLighting")
            # Flow is intentionally optional; no synthetic night traffic proxy is created.
            route["missingSignals"].append("nightTrafficActivity")
            score, breakdown = score_night_activity(route["_components"])
            route["nightActivityScore"] = score
            breakdown["missingSignals"] = sorted(set(breakdown["missingSignals"] + route["missingSignals"]))
            route["nightActivityBreakdown"] = breakdown
            del route["_components"]
        rank_routes(preliminary, night, request.mode, parsed["multipliers"] or None)
        preliminary = preliminary[:request.maxRoutes]
        explanations: list[str | None] = [None] * len(preliminary)
        if self.explain_enabled and request.explain and self.nebius:
            explanations = await explain_routes(self.nebius, preliminary, parsed["priorities"])
        for route, explanation in zip(preliminary, explanations, strict=True):
            route["explanation"] = explanation
            route.pop("severeIncidentCount", None)
        limitations = LIMITATIONS.copy()
        if len(preliminary) < request.maxRoutes:
            limitations.append(f"TomTom returned {len(preliminary)} distinct route option(s) for this trip; fewer than the requested {request.maxRoutes} were available.")
        if preference_terms:
            limitations.append("Requested landmark matches come from TomTom search results near each route; search coverage may be incomplete, and the route engine may not provide every possible detour alternative.")
        if not has_route_lighting:
            limitations.append("OpenStreetMap returned no mapped street lamps for this request or was unavailable; this is not evidence that routes are unlit.")
        elif self.overpass and self.overpass.snapshot_covers(bbox) and (note := self.overpass.snapshot_note()):
            limitations.append(note)
        return {"routes": preliminary, "parsedPreferences": parsed, "safetyClaims": False, "limitations": limitations, "dataLimitations": limitations}
