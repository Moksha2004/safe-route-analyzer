from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.agents.agent1_route_engine import RouteEngine
from app.config import settings
from app.models.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/places/search")
async def search_places(
    request: Request,
    q: str = Query(min_length=2, max_length=150),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
) -> dict[str, list[dict]]:
    engine: RouteEngine = request.app.state.engine
    if not engine.tomtom:
        raise HTTPException(status_code=503, detail="Place search requires TOMTOM_API_KEY")
    near = {"lat": lat, "lon": lon} if lat is not None and lon is not None else None
    try:
        return {"results": await engine.tomtom.search_places(q.strip(), limit=settings.place_search_limit, near=near, radius_meters=settings.place_search_radius_meters)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Map place search is temporarily unavailable") from exc


@router.post("/routes/analyze", response_model=AnalyzeResponse)
async def analyze_routes(payload: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    engine: RouteEngine = request.app.state.engine
    try:
        result = await engine.analyze(payload)
        return AnalyzeResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Route analysis provider request failed") from exc
