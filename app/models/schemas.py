from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.config import settings

TravelMode = Literal["car", "pedestrian", "bicycle"]


class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AnalyzeRequest(BaseModel):
    start: str | Coordinate
    destination: str | Coordinate
    mode: TravelMode = "car"
    maxRoutes: int = Field(default=min(settings.default_max_routes, settings.max_routes), ge=1, le=min(settings.max_routes, 5))
    departureTime: str | None = None
    timezone: str = "Asia/Kolkata"
    preferences: str | None = None
    explain: bool = True


class GeoJSONGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict[str, Any]] = Field(default_factory=list)


class RouteResult(BaseModel):
    routeId: str
    rank: int
    rankScore: float
    geometry: GeoJSONGeometry
    durationSeconds: int
    distanceMeters: int
    trafficDelaySeconds: int = 0
    departureTime: datetime | None = None
    estimatedArrivalTime: datetime | None = None
    trafficSemantics: Literal["day_congestion", "night_active_corridor"]
    nightActivityTrafficScore: float | None = None
    nightActivityScore: float
    streetLightingScore: float
    streetLampCount: int = 0
    lampsPerKm: float = 0
    streetLamps: FeatureCollection
    poiFeatures: FeatureCollection
    incidentsAlongRoute: list[dict[str, Any]] = Field(default_factory=list)
    navigationSteps: list[dict[str, Any]] = Field(default_factory=list)
    preferenceScore: float = 0
    preferenceMatches: list[str] = Field(default_factory=list)
    nightActivityBreakdown: dict[str, Any]
    activitySummary: dict[str, Any]
    policeCount: int = 0
    policeAdvantageScore: float = 0
    residentialCoveragePercent: float = 0
    missingSignals: list[str] = Field(default_factory=list)
    explanation: str | None = None


class AnalyzeResponse(BaseModel):
    routes: list[RouteResult]
    parsedPreferences: dict[str, Any]
    safetyClaims: Literal[False] = False
    limitations: list[str]
    dataLimitations: list[str]


class ErrorResponse(BaseModel):
    detail: str


@model_validator(mode="after")
def ensure_coordinates_or_text(request: AnalyzeRequest) -> AnalyzeRequest:
    for field_name in ("start", "destination"):
        value = getattr(request, field_name)
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{field_name} must not be blank")
    return request
