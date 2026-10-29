from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.api.routes import router
from app.clients.nebius import NebiusClient
from app.clients.overpass import OverpassClient
from app.clients.tomtom import TomTomClient
from app.agents.agent1_route_engine import RouteEngine


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    tomtom_key = os.getenv("TOMTOM_API_KEY", "")
    nebius_key = os.getenv("NEBIUS_API_KEY", "")
    tomtom = TomTomClient(tomtom_key) if tomtom_key else None
    overpass = OverpassClient(os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter"))
    nebius = NebiusClient(nebius_key, os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")) if nebius_key else None
    app.state.engine = RouteEngine(tomtom, overpass, nebius, os.getenv("EXPLAINER_ENABLED", "true").lower() == "true")
    try:
        yield
    finally:
        for client in (tomtom, overpass, nebius):
            if client:
                await client.close()


app = FastAPI(title="Safe Route Analyzer", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_csv(os.getenv("CORS_ORIGINS", "http://localhost:5173")), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")

web_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
if os.path.isdir(web_dist):
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
