# Route Viewer

A local web application for ingesting GPS activity files (GPX and FIT), visualizing routes on an interactive map, snapping them to the road network via [GraphHopper](https://www.graphhopper.com/) map-matching, and exporting the results as GeoJSON or SVG.

Built for the FinishLine project to review and refine GPS tracks from Garmin and similar devices before producing route line prints.

## What It Does

1. **Ingest** — Scan a local folder (or single file) for `.gpx` and `.fit` activity files, parse track points and metadata, deduplicate by content signature, and store activities in a SQLite database with cached GeoJSON.
2. **View** — Browse ingested activities on a Leaflet map with filters (activity type, distance range), toggle raw vs. map-matched ("snapped") routes, and select routes via checkboxes or a rectangle draw tool.
3. **Map-match** — Send selected activities to a GraphHopper map-matching server to snap GPS traces onto OpenStreetMap roads. The backend auto-detects which US state an activity is in (PA, NY, NJ, FL) and routes to the correct regional GraphHopper instance.
4. **Export** — Download selected routes as merged GeoJSON or as a single SVG file (saved both to the browser and to an `exports/` folder next to the ingest source).

## Architecture

```
route-viewer/
├── frontend/          React + Vite + Leaflet UI (port 5173)
├── backend/           FastAPI Python API (port 8000)
├── graphhopper/       Per-state GraphHopper map-matching server configs
└── start_graphhopper_servers.bat   Launches all GH servers
```

| Service | Port | Purpose |
|---------|------|---------|
| Frontend (Vite) | 5173 | React SPA |
| Backend (FastAPI) | 8000 | REST API |
| GraphHopper PA | 8989 | Pennsylvania road network |
| GraphHopper NY | 8988 | New York road network |
| GraphHopper NJ | 8987 | New Jersey road network |
| GraphHopper FL | 8986 | Florida road network |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Java 17+ (for GraphHopper)
- GraphHopper `map-matching.jar` and per-state `.osm.pbf` extracts (not included in repo; see `graphhopper/` configs for expected paths)

### 1. Start GraphHopper servers

```bat
start_graphhopper_servers.bat
```

Or start individual servers manually (see [MAPMATCH_IMPROVEMENTS.md](MAPMATCH_IMPROVEMENTS.md) for details).

### 2. Start the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, enter a local folder path containing GPX/FIT files, click **Ingest**, then **View on Map**.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE` | `http://localhost:8000` | Backend URL (frontend) |
| `VITE_ORIGIN` | `http://localhost:5173` | Allowed CORS origin (backend) |
| `VITE_TILE_URL` | OpenStreetMap tiles | Basemap tile URL (frontend) |
| `DATA_CACHE_DIR` | `%LOCALAPPDATA%/RouteViewer/cache` | GeoJSON cache directory |
| `DB_PATH` | `.data/app.db` | SQLite database path |
| `GRAPHOPPER_BASE_URL` | `http://localhost:8989` | Default GH URL (inspect endpoint) |

---

## File Reference

### Root

| File | Description |
|------|-------------|
| `package.json` | Root-level npm manifest with shared Leaflet Draw dependencies. |
| `package-lock.json` | Lockfile for root npm dependencies. |
| `.gitignore` | Ignores node_modules, Python caches, `.env`, SQLite DBs, OSM PBF files, GraphHopper graph caches, and generated export/cache directories. |
| `start_graphhopper_servers.bat` | Windows batch script that launches four GraphHopper map-matching servers (PA, NY, NJ, FL) in separate terminal windows. |
| `MAPMATCH_IMPROVEMENTS.md` | Technical notes on map-matching enhancements: timestamp-aware GPX generation, activity-type GPS accuracy defaults, excursion cleanup, multi-state GraphHopper routing, and logging. |

### Backend (`backend/`)

#### Entry Point

| File | Description |
|------|-------------|
| `requirements.txt` | Python dependencies: FastAPI, Uvicorn, SQLAlchemy, gpxpy, fitparse, Shapely, NumPy. |
| `app/main.py` | FastAPI application factory. Configures CORS, creates data directories, registers all API routers, and initializes the SQLite schema on startup. |
| `app/__init__.py` | Package marker. |

#### API Routes (`backend/app/api/`)

| File | Endpoint(s) | Description |
|------|-------------|-------------|
| `routes_health.py` | `GET /healthz` | Health check; reports configured GraphHopper base URL. |
| `routes_ingest.py` | `POST /ingest`, `GET /ingest/progress` | Scans a local folder or file for GPX/FIT files, parses tracks, deduplicates by hash signature, writes GeoJSON cache files, and stores `Activity` records. Resets the database on each ingest. Exposes in-process progress polling. |
| `routes_activities.py` | `GET /activities`, `GET /activities/{id}/geojson` | Lists activities with optional filters (type, date range, distance). Returns raw or `matched` variant GeoJSON for a given activity. |
| `routes_export.py` | `POST /export` | Exports selected activities as merged GeoJSON or SVG. SVG export projects lon/lat to a pixel canvas and also writes `snapped.svg` to `{ingest_source}/exports/`. |
| `routes_mapmatch.py` | `POST /mapmatch` | Sends activity tracks to GraphHopper's `/match` endpoint. Auto-detects state from coordinates, builds timestamp-aware GPX, applies GPS accuracy defaults by activity type, and saves `*_matched.json` GeoJSON alongside the raw cache file. |
| `routes_inspect.py` | `GET /inspect` | Debug endpoint: given a lat/lon, queries GraphHopper for the nearest road edge and samples candidate snap points in a radius. Returns a GeoJSON FeatureCollection for map overlay. |
| `__init__.py` | — | Package marker. |

#### Core Logic (`backend/app/core/`)

| File | Description |
|------|-------------|
| `parse_gpx.py` | Parses GPX files via `gpxpy`. Extracts coordinates, timestamps, activity type, distance (haversine), and duration. Returns a `ParsedTrack` dataclass. |
| `parse_fit.py` | Parses Garmin FIT files via `fitparse`. Converts semicircle coordinates, maps sport/sub-sport to activity types (run, ride, walk, swim), and returns a `ParsedTrack`. |
| `geojson.py` | Writes a LineString GeoJSON FeatureCollection to disk, optionally embedding per-point timestamp/elevation metadata as additional Point features. |
| `walker.py` | Recursively walks a directory tree and yields `.gpx` and `.fit` file paths. |
| `storage.py` | Defines a `StorageProvider` protocol and `LocalStorageProvider` for filesystem access (supports `file://` URIs and zip detection). Prepared for future archive support; not yet wired into ingest. |

#### Database (`backend/app/db/`)

| File | Description |
|------|-------------|
| `models.py` | SQLAlchemy `Activity` model: id, source path/format, activity type, name, timestamps, distance, elevation, GeoJSON cache path, bounding box, content hash, and ingest timestamp. |
| `session.py` | Creates the SQLite engine and `SessionLocal` factory. Database path configurable via `DB_PATH` env var. |

#### Tests

| File | Description |
|------|-------------|
| `test_mapmatch_improvements.py` | Placeholder test file (currently empty). Intended for tests covering GPS accuracy defaults, excursion cleanup, and timestamp-aware GPX generation. |

### Frontend (`frontend/`)

#### Config & Build

| File | Description |
|------|-------------|
| `package.json` | Frontend dependencies: React 18, Vite, Leaflet, react-leaflet, leaflet-draw, axios, react-router-dom. |
| `package-lock.json` | npm lockfile. |
| `vite.config.ts` | Vite config with React plugin; dev server on port 5173. |
| `tsconfig.json` | TypeScript compiler options for the app source. |
| `tsconfig.node.json` | TypeScript config for Vite/Node tooling files. |
| `index.html` | HTML shell; mounts the React app at `#root`. |

#### Source (`frontend/src/`)

| File | Description |
|------|-------------|
| `main.tsx` | React entry point. Renders `<App />` in StrictMode and imports Leaflet/Draw CSS. |
| `pages/App.tsx` | Top-level router with routes for `/` (Home) and `/map` (MapPage). |
| `pages/Home.tsx` | Ingest page. Accepts a local folder path, POSTs to `/ingest`, polls `/ingest/progress` for live status, and links to the map view. |
| `pages/MapPage.tsx` | Main map interface. Loads activities and GeoJSON from the API, renders raw (orange) and snapped (blue) routes on a Leaflet map, provides a control panel for filtering, selection (checkbox or rectangle draw), map-matching, SVG export, and snap-debug inspection on map click. |
| `styles/ui.css` | Shared UI styles: CSS variables, panel/toolbar/button/field classes, and drawer layout for the activity list. |

### GraphHopper (`graphhopper/`)

| File | Description |
|------|-------------|
| `config_PA.yaml` | GraphHopper config for Pennsylvania. Points to a PA OSM PBF extract, stores graph cache in `./graphs/PA`, defines foot/bike/car profiles, listens on port **8989**. |
| `config_NY.yaml` | New York config. Port **8988**, graph cache `./graphs/NY`. |
| `config_NJ.yaml` | New Jersey config. Port **8987**, graph cache `./graphs/NJ`. |
| `config_FL.yaml` | Florida config. Port **8986**, graph cache `./graphs/FL`. |

Each config ignores motorway/trunk highways during import, encodes `road_class` and `osm_way_id` for debug overlays, and uses custom speed models per profile. OSM PBF file paths are machine-specific and must be updated before first use.

> **Note:** `map-matching.jar`, OSM `.pbf` extracts, and prebuilt `graphs/` directories are not tracked in git (see `.gitignore`). You must download/build these separately.

---

## Typical Workflow

```
Local GPX/FIT folder
        │
        ▼
  POST /ingest  ──►  SQLite DB + GeoJSON cache
        │
        ▼
  GET /activities + /geojson  ──►  Map view (raw routes)
        │
        ▼
  POST /mapmatch  ──►  GraphHopper (state auto-detected)
        │
        ▼
  *_matched.json  ──►  Map view (snapped routes)
        │
        ▼
  POST /export  ──►  snapped.svg (+ GeoJSON option)
```

## Related Documentation

See [MAPMATCH_IMPROVEMENTS.md](MAPMATCH_IMPROVEMENTS.md) for detailed notes on map-matching quality improvements, GPS accuracy defaults, excursion cleanup, and the multi-state GraphHopper architecture.
