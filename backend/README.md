# AI Heat Safety Assistant

A FastAPI backend that turns hyperlocal temperature intelligence from the
**FortyGuard Temperature API** into actionable heat-safety guidance: risk
analysis, activity recommendations, an outdoor-activity planner, and a
data-grounded AI chat assistant.

---

## Overview

Extreme heat is dangerous, and risk is highly local. This service fetches
temperature data for a location from FortyGuard, normalises it into a clean
internal model, classifies the heat risk, and exposes simple JSON endpoints a
frontend can consume. AI features (recommendations, planner, chat) are always
**grounded in verified temperature data** — the assistant never invents
temperature values, and clearly separates measured data from general advice.

> **Not medical advice.** All guidance is general and informational. Individual
> heat tolerance varies.

---

## Features

Only features that are actually implemented are listed here.

- **FortyGuard heatmaps (live-verified, U.S. only)** — submit a heatmap job for
  an area + time window and get back GeoJSON temperature tiles, via the official
  async FortyGuard API (`POST /api/v1/heatmap`, `GET /api/v1/heatmap/{id}`). The
  frontend never talks to FortyGuard directly.
- **Hyperlocal temperature intelligence** — reads from the FortyGuard
  Temperature API via a single, isolated adapter and normalises the response.
- **Heat-risk analysis** — uses FortyGuard's official risk level when provided;
  otherwise calculates a level from temperature using the documented US NWS
  Heat Index categories (with humidity-aware heat index when available).
- **AI safety recommendations** — activity-specific, data-grounded advice.
- **Outdoor activity guidance** — suggests safer timing based on current
  conditions (clearly labelled as *not* a forecast).
- **AI heat assistant (chat)** — answers natural-language questions using
  verified data.
- **Robust API integration** — timeouts, connection errors, 4xx/5xx handling,
  missing-field handling, and consistent error responses.
- **Optional LLM** — if an OpenAI-compatible provider is configured the prose
  is written by the model; otherwise deterministic rule-based text is used.

---

## Architecture

```
Frontend
   │  HTTP (JSON)
   ▼
FastAPI Router            app/routers/*      — HTTP request/response only
   ▼
Service Layer             app/services/*     — business logic + external calls
   ▼
FortyGuard Temperature API   (external)      — via app/services/fortyguard_service.py
   ▼
Normalized Temperature Data  app/schemas/temperature.py: NormalizedTemperature
   ▼
Heat Intelligence Service    app/services/heat_service.py  — risk classification
   ▼
AI Service (where required)  app/services/ai_service.py    — grounded guidance
   ▼
FastAPI Response
   ▼
Frontend
```

Responsibilities are strictly separated: routers do HTTP only, services hold
logic and all external I/O, schemas validate data, and `core/` holds config,
logging, and error types. The FortyGuard API is touched in exactly one file.

---

## Tech Stack

- Python 3.11+ (developed and verified on 3.14)
- FastAPI, Uvicorn
- Pydantic v2, pydantic-settings
- httpx (async HTTP)
- python-dotenv
- pytest, pytest-asyncio

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # App factory, CORS, exception handlers, wiring
│   ├── core/
│   │   ├── config.py           # Settings (env vars via pydantic-settings)
│   │   ├── logging.py          # Logging setup + secret redaction helpers
│   │   └── exceptions.py       # Typed errors -> HTTP status codes
│   ├── routers/                # health, temperature, heat_risk,
│   │                           # recommendations, outdoor_plan, chat
│   ├── services/
│   │   ├── fortyguard_service.py  # THE FortyGuard integration seam
│   │   ├── heat_service.py        # Risk classification (NWS-based)
│   │   └── ai_service.py          # Grounded AI/rule-based guidance
│   └── schemas/                # Pydantic request/response + internal models
├── tests/                      # pytest suite (all external HTTP mocked)
├── .env.example
├── requirements.txt
├── pytest.ini
├── run.py
└── README.md
```

---

## Setup (Windows PowerShell)

```powershell
# 1. Open the backend project
cd D:\ai-heat-safety-assistant\backend

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
.venv\Scripts\activate

# 4. Install requirements
pip install -r requirements.txt

# 5. Configure environment
copy .env.example .env
#    then edit .env and fill in the FortyGuard values (see below)

# 6. Start the API
uvicorn app.main:app --reload --port 8000
#    or:  python run.py
```

On macOS/Linux the only differences are `source .venv/bin/activate` and `cp`
instead of `copy`.

---

## Environment Variables

Configure everything via `.env` (copy from `.env.example`). Secrets stay in
`.env`, which is git-ignored — they are never hard-coded or returned by the API.

### FortyGuard (required for live temperature/heat-risk)

| Variable | Purpose |
|---|---|
| `FORTYGUARD_API_KEY` | Your FortyGuard API key (secret). |
| `FORTYGUARD_BASE_URL` | API host, e.g. `https://api.fortyguard.com`. |
| `FORTYGUARD_TEMPERATURE_PATH` | Exact temperature endpoint path from the docs. |
| `FORTYGUARD_AUTH_HEADER` / `FORTYGUARD_AUTH_SCHEME` | How the key is sent (default `Authorization` / `Bearer`). |
| `FORTYGUARD_HTTP_METHOD` / `FORTYGUARD_REQUEST_STYLE` | `GET`+`query` or `POST`+`json`. |
| `FORTYGUARD_LOCATION_PARAM` / `_LAT_PARAM` / `_LON_PARAM` | Outgoing parameter names. |
| `FORTYGUARD_TIMEOUT_SECONDS` | Request timeout (default 10). |

> **Why these are configurable:** the exact FortyGuard request/response
> contract was not present in this workspace, and the public docs
> (`https://docs-api.fortyguard.com`) are JavaScript-rendered. Rather than
> guess an endpoint or fabricate response fields, the vendor-specific details
> are expressed as configuration and confirmed against the real docs at
> deploy time. Until `FORTYGUARD_API_KEY`, `FORTYGUARD_BASE_URL` and
> `FORTYGUARD_TEMPERATURE_PATH` are set, the temperature and heat-risk
> endpoints return **HTTP 503** instead of returning fake data. See the
> "FORTYGUARD CONTRACT" note at the top of
> `app/services/fortyguard_service.py`; adjust the response field candidates in
> `_normalize()` to match the confirmed response shape.

### AI provider (optional)

| Variable | Purpose |
|---|---|
| `AI_API_KEY` | Secret key for an OpenAI-compatible provider. |
| `AI_BASE_URL` | Base URL such that `<AI_BASE_URL>/chat/completions` is valid. |
| `AI_MODEL` | Model id, e.g. `gpt-4o-mini`. |
| `AI_TIMEOUT_SECONDS` | AI request timeout (default 30). |

If unset, AI endpoints return deterministic, data-grounded guidance
(`generated_by: "rule_based"`). If set, the model writes the prose
(`generated_by: "llm"`), with automatic fallback to rule-based on any failure.

### Other

| Variable | Purpose |
|---|---|
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed origins (defaults to common localhost dev ports). |
| `ENVIRONMENT`, `LOG_LEVEL` | App environment and log verbosity. |

---

## API Endpoints

Base URL: `http://127.0.0.1:8000`

### `GET /health`
Liveness/readiness probe. Never exposes secrets.

```json
{
  "status": "ok",
  "app": "AI Heat Safety Assistant",
  "version": "0.1.0",
  "environment": "development",
  "fortyguard_configured": false,
  "ai_llm_enabled": false
}
```

### `POST /api/v1/temperature`
Hyperlocal temperature + normalised risk level.

**Request**
```json
{ "location": "Karachi, Pakistan" }
```
`latitude` + `longitude` may be sent instead of (or with) `location`.

**Response (200, once FortyGuard is configured)** — fields are populated only
when provided upstream:
```json
{
  "location": "Karachi, Pakistan",
  "temperature": 38.5,
  "unit": "°C",
  "temperature_celsius": 38.5,
  "humidity_percent": 55.0,
  "risk_level": "high",
  "risk_level_source": "calculated",
  "resolution": "2m",
  "measured_at": "2026-08-22T10:00:00Z",
  "source": "fortyguard",
  "timestamp": "2026-08-22T10:00:01.123456+00:00"
}
```

**Response (503, when not configured)**
```json
{ "error": { "code": "fortyguard_not_configured", "message": "...", "status_code": 503 } }
```

### `POST /api/v1/heatmap`
Submit a FortyGuard **heatmap** job and get its result. This is the verified,
production FortyGuard integration (async *submit → poll*, hidden behind one
request). **FortyGuard coverage is U.S. only** — use a U.S. location (preferred
test point: **San Jose, California**).

The frontend calls this endpoint; it must **never** call `api.fortyguard.com`
directly. Provide an area of interest as either an explicit GeoJSON
`polygon_aoi`, or a `latitude`/`longitude` centre (a small square AOI is built
for you — that squaring is *our* convenience, not a FortyGuard feature).

**Request** (single-hour `tcm` snapshot near San Jose)
```json
{
  "latitude": 37.3382,
  "longitude": -121.8863,
  "radius_km": 1.0,
  "start_date": "2024-07-15",
  "start_time": "14:00",
  "filter_type": 1,
  "analytic_type": "tcm",
  "granularity": 100
}
```

- `filter_type`: `1`=single hour (needs `start_time`), `2`=hour range (needs
  `start_time`+`end_time`), `3`=single day, `4`=day range (needs `end_date`).
- `granularity` ∈ `{60, 80, 100}`.
- `analytic_type` ∈ `tcm | time_of_measure | exceedance | persistence`.
  `exceedance`/`persistence` additionally require `threshold` (°C) and
  `direction` (`above`/`below`).
- Tile values live under `properties.average_temperature` for `tcm` (tiles also
  carry `min_temperature`/`max_temperature`/`tile_id`), and under
  `properties.value` for analysis types (`value_key` in the response tells you
  which). The `tcm` tile shape is confirmed against the live API; the analysis
  shapes follow the docs and are not yet live-verified.

**Response (200, completed within the wait budget)**
```json
{
  "activity_id": "…",
  "status": "completed",
  "ready": true,
  "analytic_type": "tcm",
  "value_key": "average_temperature",
  "tile_count": 384,
  "stats": { "analytic_type": "tcm", "units": "C", "min": 30.1, "max": 34.7, "mean": 32.2 },
  "result": { "stats_data": { }, "map_data": { "type": "FeatureCollection", "features": [] } },
  "poll_url": null,
  "coverage_note": "FortyGuard coverage is U.S. only — …",
  "disclaimer": "Heatmap values are model-derived environmental data …",
  "timestamp": "2026-08-23T10:00:01.123456+00:00"
}
```

**Response (202, still processing after the wait budget)** — poll `poll_url`:
```json
{
  "activity_id": "…",
  "status": "processing",
  "ready": false,
  "poll_url": "/api/v1/heatmap/…",
  "timestamp": "2026-08-23T10:00:26.123456+00:00"
}
```

### `GET /api/v1/heatmap/{activity_id}`
Fetch a previously-submitted heatmap job: **200** completed, **202** still
processing, **404** unknown/expired id, **502** if the upstream task failed.

### `POST /api/v1/heat-risk`
Risk level, explanation and recommended actions.

**Request**
```json
{ "location": "Jacobabad" }
```

**Response (200)**
```json
{
  "location": "Jacobabad",
  "temperature": 45.0,
  "unit": "°C",
  "temperature_celsius": 45.0,
  "humidity_percent": null,
  "heat_index_celsius": null,
  "risk_level": "very_high",
  "risk_level_source": "calculated",
  "explanation": "Very high heat risk — limit outdoor exposure. Measured temperature is 45.0°C. Risk level is calculated from temperature using US NWS Heat Index categories.",
  "recommended_actions": ["Avoid strenuous outdoor activity; reschedule to a cooler time if possible.", "..."],
  "disclaimer": "This is general, informational heat-safety guidance and not medical advice. ...",
  "measured_at": null,
  "timestamp": "2026-08-22T10:00:01.123456+00:00"
}
```

### `POST /api/v1/recommendations`
Activity-specific, data-grounded recommendations.

**Request**
```json
{ "location": "Karachi", "activity": "running", "user_context": "45-minute run" }
```
`activity` ∈ `walking | running | outdoor_work | commuting | general`.
`location` is optional; without it, general guidance is returned with
`data_available: false`.

**Response (200)**
```json
{
  "location": "Karachi",
  "activity": "running",
  "temperature_celsius": 38.5,
  "risk_level": "high",
  "recommendations": ["Reduce pace and distance in the heat; prefer dawn or after sunset.", "..."],
  "summary": "For running in Karachi: high heat risk (measured 39°C). Proceed with care; shorten and ease the effort.",
  "data_available": true,
  "generated_by": "rule_based",
  "disclaimer": "AI-generated guidance grounded in the temperature data shown. General information only, not medical advice.",
  "timestamp": "2026-08-22T10:00:01.123456+00:00"
}
```

### `POST /api/v1/outdoor-plan`
Safer timing for an activity. **Not a forecast** unless upstream provides one
(`is_forecast` is `false` for current-condition guidance).

**Request**
```json
{ "location": "Karachi", "activity": "outdoor_work" }
```

**Response (200)**
```json
{
  "location": "Karachi",
  "activity": "outdoor_work",
  "temperature_celsius": 38.5,
  "risk_level": "high",
  "recommended_window": "Early morning (before ~09:00) or evening (after ~18:00).",
  "avoid_window": "Late morning to late afternoon (roughly 11:00-16:00).",
  "explanation": "Current conditions near Karachi indicate high heat risk ...",
  "is_forecast": false,
  "data_available": true,
  "disclaimer": "...",
  "timestamp": "2026-08-22T10:00:01.123456+00:00"
}
```

### `POST /api/v1/chat`
Natural-language assistant. Grounds answers in live data when a location is
given; never invents temperature values.

**Request**
```json
{ "question": "Can I go running now?", "location": "Karachi" }
```

**Response (200)**
```json
{
  "answer": "Data in Karachi: it is 39°C, a high heat-risk level (calculated classification). Proceed with care; shorten and ease the effort. Suggested precautions: ...",
  "location": "Karachi",
  "temperature_celsius": 38.5,
  "risk_level": "high",
  "data_available": true,
  "generated_by": "rule_based",
  "disclaimer": "General information only, not medical advice.",
  "timestamp": "2026-08-22T10:00:01.123456+00:00"
}
```

---

## Testing

Automated tests mock all external HTTP — **no test calls the real FortyGuard
or AI APIs.**

```powershell
.venv\Scripts\activate
pytest            # or: pytest -v
```

Coverage includes: health, request validation, temperature normalisation,
unit conversion, nested/official-risk parsing, FortyGuard timeout / connection
/ 404 / 4xx / 5xx / bad-response / not-configured handling, heat-risk
classification + heat index, and AI rule-based grounding + LLM fallback.

### Manual FortyGuard integration test (real API key)

Do this only outside the automated suite, with a real key:

1. Copy `.env.example` to `.env` and set the real `FORTYGUARD_*` values from
   `https://docs-api.fortyguard.com` (endpoint path, auth header/scheme,
   method/style, parameter names).
2. Open `app/services/fortyguard_service.py` and confirm the candidate field
   names in the `_TEMP_KEYS`/`_UNIT_KEYS`/... lists (and `_normalize()`) match
   the real response; adjust if needed.
3. Start the server: `uvicorn app.main:app --port 8000`.
4. Call the endpoint and inspect the result:
   ```powershell
   curl -X POST http://127.0.0.1:8000/api/v1/temperature `
     -H "Content-Type: application/json" `
     -d '{\"location\": \"Karachi, Pakistan\"}'
   ```
5. Confirm a `200` with a real `temperature_celsius` and a `risk_level`. If you
   get a `502 fortyguard_bad_response`, the response field mapping in
   `_normalize()` needs adjusting to the real payload.

---

## API Documentation

Interactive docs are generated automatically by FastAPI:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

---

## Error Handling

All handled errors return a consistent envelope and an appropriate status code;
raw stack traces and secrets are never returned.

```json
{ "error": { "code": "fortyguard_timeout", "message": "…", "status_code": 504 } }
```

| Status | When |
|---|---|
| 400 / 422 | Invalid request / validation failure |
| 404 | Location not found upstream |
| 502 | Upstream API returned an error or unexpected/invalid response |
| 503 | Upstream API unavailable, rate-limited, or not configured |
| 504 | Upstream API timed out |
| 500 | Unexpected internal error (generic, safe message) |

---

## Security

- Secrets live only in `.env`, which is in `.gitignore`; `.env.example` ships
  placeholders.
- API keys are never hard-coded, never logged (logging redacts them), and never
  included in API responses or the OpenAPI schema.
- All incoming data is validated with Pydantic.
- External calls use explicit timeouts and defensive error handling.
- CORS origins are configured via environment; defaults target localhost dev.

---

## Development Status

Verified = implemented **and** exercised (tests and/or a running server).

- [x] Project scaffold, config, logging, CORS, error handling
- [x] **FortyGuard heatmap integration** (`POST /api/v1/heatmap`,
      `GET /api/v1/heatmap/{activity_id}`) — async submit→poll via the verified
      `api-key` header; verified via mocked HTTP (submit, poll, completed,
      failed→502, timeout→504, 404-not-ready, not-configured→503, malformed→502,
      no key leak)
- [x] **FortyGuard heatmap — LIVE integration verified with a real API key**
      *(San Jose, CA, tcm; `POST /api/v1/heatmap` → 200 completed, 384 tiles,
      `value_key=average_temperature`; verified 2026-08-23. No key leaked in
      response or logs.)*
- [x] Legacy FortyGuard temperature adapter — implemented; verified via mocked
      HTTP (success, timeout, connection, 404, 4xx, 5xx, bad-response,
      not-configured)
- [ ] Legacy `/api/v1/temperature` + `/api/v1/heat-risk` **live** — the real
      FortyGuard API has no single-point temperature lookup, so these stay
      **HTTP 503** unless pointed at a compatible endpoint (see "Known gaps"
      below). Not part of the heatmap integration.
- [x] `/health` endpoint (verified on a running server)
- [x] `/api/v1/temperature` endpoint (verified: 200 happy-path via mock, 503, 422)
- [x] `/api/v1/heat-risk` endpoint (verified)
- [x] AI recommendations endpoint (verified, rule-based)
- [x] Outdoor planner endpoint (verified, rule-based)
- [x] AI chat endpoint (verified, rule-based)
- [x] Optional LLM path (verified via mocked provider, incl. fallback)
- [x] Automated tests (52 passing; all external HTTP mocked)
- [ ] Frontend integration

### Known gaps

- The FortyGuard API is heatmap-oriented (area + time → GeoJSON tiles) and has
  **no single point-in-time temperature endpoint**. The pre-existing
  `/api/v1/temperature` and `/api/v1/heat-risk` endpoints were built around such
  a lookup and therefore remain **503** until re-pointed at the heatmap flow
  (that re-pointing is deliberately out of scope for the heatmap integration).
- FortyGuard coverage is **U.S. only** — non-U.S. locations will not return data.
- Live integration verified for **`tcm`** only. `time_of_measure`, `exceedance`,
  and `persistence` are implemented and validated but their live tile shapes are
  **not yet verified** against the real API (the code passes tiles through
  untransformed, so no data is lost regardless).
