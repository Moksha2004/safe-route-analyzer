# Safe Route Analyzer

Built for the **Nebius x NVIDIA Global AI Hackathon** (Best Apps and Agents track).

A low-scale, evidence-aware multi-route comparison demo for Bengaluru-style trips. TomTom supplies geocoding, route geometry, travel-time summaries, along-route places and incidents. OpenStreetMap street-lamp nodes provide a mapped-lighting signal. NVIDIA Nemotron models, served through **Nebius Token Factory**, parse free-text preferences into scoring weights and narrate the comparison between routes; all provider failures degrade gracefully (the app still returns routes and metrics if an LLM call fails or times out).

**This is not crime data, a safety service, or a safety guarantee.** A mapped OpenStreetMap lamp does not confirm that it works, and missing lamp data does not establish darkness.

## Nebius / NVIDIA usage

- **Provider**: [Nebius Token Factory](https://tokenfactory.nebius.com) (OpenAI-compatible `chat/completions`), see [`app/clients/nebius.py`](app/clients/nebius.py).
- **Intent parsing** — `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` turns free-text preferences (e.g. "prefer open shops, hospitals, police and residential stretches") into bounded scoring weights. See [`app/agents/agent2a_intent.py`](app/agents/agent2a_intent.py). Called with a 200ms budget; falls back to mode defaults on timeout.
- **Route explainer** — `nvidia/nemotron-3-super-120b-a12b` compares routes using only the structured metrics the backend already computed (never raw text), and is filtered for banned "guaranteed safe" phrasing. See [`app/agents/explainer.py`](app/agents/explainer.py).
- The LLMs never choose geometry or touch TomTom/OSM data directly — they only parse intent and narrate numbers the deterministic scoring pipeline already produced.

## Requirements

- Python 3.11+
- Node.js 20+
- TomTom API key for live routes; Nebius Token Factory API key for the AI-parsed preferences and route explanations (optional — the app still works without it, just without the LLM features)

## Configure and run

Copy `.env.example` to `.env` and set `TOMTOM_API_KEY` and `NEBIUS_API_KEY`. Keep `VITE_TOMTOM_API_KEY` equal to `TOMTOM_API_KEY` for the TomTom vector basemap. Without a basemap key, the frontend falls back to the public OpenFreeMap Liberty style. Typed place suggestions are also powered by TomTom and return exact coordinates for either field.

Backend, from the repository root (macOS/Linux):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Windows (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
uvicorn app.main:app --reload
```

Frontend, in `web/`:

```bash
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`. To serve a production build through FastAPI, run `npm run build` in `web/`, then start the backend — it automatically mounts `web/dist` at `/` when present.

## Deploying

A multi-stage `Dockerfile` builds the frontend and serves it from FastAPI in one container; `render.yaml` describes it as a [Render](https://render.com) Blueprint. To deploy on Render: connect this repo as a new Blueprint, and set `TOMTOM_API_KEY`, `NEBIUS_API_KEY`, and `VITE_TOMTOM_API_KEY` (same value as `TOMTOM_API_KEY`) as secret environment variables in the dashboard — everything else has a sane default in `render.yaml`. Any other Docker-capable host works the same way: `docker build --build-arg VITE_TOMTOM_API_KEY=... -t safe-route-analyzer . && docker run -p 8000:8000 --env-file .env safe-route-analyzer`.

## Route and search settings

`MAX_ROUTES` and `DEFAULT_MAX_ROUTES` control the route-count selector (maximum 5). `PLACE_SEARCH_LIMIT` (1–20) controls TomTom autocomplete results, and `PLACE_SEARCH_RADIUS_METERS` controls the strength of its soft nearby bias; it does not exclude matching places outside that radius. Frontend defaults are configurable through `VITE_MAX_ROUTES`, `VITE_DEFAULT_MAX_ROUTES`, `VITE_SEARCH_DEBOUNCE_MS`, and `VITE_MIN_SEARCH_LENGTH` in the root `.env`; restart Vite after changing these. Place suggestions use TomTom fuzzy typeahead and rank lexical/provider relevance first, with proximity from the selected start or current map center as a supporting signal.

Route preferences are also considered in candidate generation and ranking. For example, “prefer a route with a lake” searches TomTom along each route; if that returns no match, it searches around several points along each route, biased to a configurable 5 km radius and constrained to India. A discovered lake outside the route corridor can be used as an explicit routing waypoint to create a genuine longer alternative. `PREFERENCE_ROUTE_CANDIDATES` (default 3) caps waypoint-route requests; `PREFERENCE_SEARCH_RADIUS_METERS` and `PREFERENCE_SEARCH_POINTS_PER_ROUTE` control fallback discovery; `PREFERENCE_CORRIDOR_METERS` (default 500 m) determines when a found POI counts as already on a route; `PREFERENCE_MATCH_BONUS` (default 0.35) controls ranking. Matched landmarks are shown on the map. This depends on TomTom POI coverage and cannot guarantee every landmark is indexed; limitations are returned with the routes.

Choose a route card, then press **Start navigation** to grant foreground GPS access. The map follows your position, shows the remaining route distance and displays TomTom instructions when available. This is a basic live route-following feature, not turn-by-turn voice guidance. Location tracking stops when you press **Stop navigation**, select a different route, or submit a new search.

## API

`GET /api/health`

`POST /api/routes/analyze`

Example request:

```json
{
  "start": "Bellandur, Bengaluru",
  "destination": { "lat": 12.9352, "lon": 77.6245 },
  "mode": "car",
  "maxRoutes": 3,
  "departureTime": null,
  "timezone": "Asia/Kolkata",
  "preferences": "Prefer open shops, hospitals, police and residential stretches"
}
```

Start and destination can each be a place string or `{ "lat": ..., "lon": ... }`. Supported modes: `car`, `pedestrian`, `bicycle`. Response routes include GeoJSON LineStrings, `nightActivityScore`, `streetLightingScore`, lamp points, POI features, signal breakdowns, missing signals and limitations.

## Data and limitations

- The service does not request or infer crime data.
- Unknown business hours receive no positive credit; unknown is not considered closed.
- Route requests send the selected departure date/time to TomTom (`departAt`) for time-dependent routing. TomTom's documented traffic support includes live/current traffic and typical weekday/time speeds; exact future incidents should not be treated as known.
- Overpass is a shared community service. Requests are bounded to a combined route bounding box, identify this client, and degrade without failing route analysis. Configure `OVERPASS_URL` if using an approved alternative endpoint.
- Street-lamp scores are relative across returned alternatives. OSM tagging is incomplete; the score is not a measurement of functioning lights.
- TomTom POIs and category coverage can be incomplete. Residential coverage is a category-evidence estimate, not a density claim.
- Flow sampling and route-specific residential reverse-geocoding are not enabled in this initial scaffold; unavailable signals are surfaced rather than synthesized.
- This demo uses in-process provider clients and no persistent cache, queue, database, or rate limiter.

## Checks

```powershell
pytest
cd web
npm run build
```
