# Route Viewer

A local web application for ingesting GPS activity files, building a **global OpenStreetMap street catalog** by geographic tiles, map-matching activities to canonical **segment IDs**, and visualizing/exporting route usage — not overlapping per-activity polylines.

Built for the **FinishLine** project: multiple map **customers** share OSM catalog work when geography overlaps; each customer's activities are stored separately.

## What It Does Today

1. **Ingest** — Parse `.gpx`, `.fit`, `.tcx` (and `.gz` / `.zip` archives) for a **customer ID**. Persist activities in SQLite + SpatiaLite, cluster into **regions** (~10 km), register required **catalog tiles** (5 km grid). Does **not** wipe the DB on re-ingest.
2. **Catalog coverage** — Report which OSM catalog tiles a customer's activity geometry requires and whether each tile is `pending` / `ready`. OSM **build worker not implemented yet**.
3. **View** — Leaflet map with per-activity raw/snapped GeoJSON (legacy flow).
4. **Map-match** — GraphHopper snap to roads (legacy per-activity GeoJSON; does **not** yet write `activity_segment_usage`).
5. **Export** — GeoJSON or SVG from selected activities (legacy flow).

## Target Architecture (in progress)

FinishLine is moving from **per-activity polylines** to **segment-centric** storage:

```
Customer ingest  →  activities (per customer)
                 →  catalog_tiles (global coverage gate)
                 →  OSM build per tile  →  network_segments (global)
                 →  map-match  →  activity_segment_usage + segment_stats
                 →  map viz / export by segment usage counts
```

**Three geographic layers** (do not confuse them):

| Layer | Purpose | Shared across customers? |
|-------|---------|--------------------------|
| **Regions** | UI grouping, ~10 km activity clusters | Yes (global `regions` table) |
| **Catalog tiles** | OSM build unit, coverage gate | Yes (global `catalog_tiles`) |
| **Network segments** | Canonical street geometry + stable IDs | Yes (global `network_segments`) |

**Critical rule:** `region_id` does **not** mean OSM catalog is ready. Coverage = all **catalog tiles** touched by the customer's activity geometry have `status = ready`.

---

## Git Branch Strategy (June 2026)

Active development is on:

```
feat/catalog-tiles-multi-customer-ingest
```

- `master` = last merged stable state (pre segment-centric work).
- Feature branch is pushed to `origin`; **no PR yet** — merge to `master` when the full milestone is done (OSM build + segment map-match + viz).
- Solo dev workflow: commit and push on the feature branch; merge locally when ready.

Latest milestone commit message: *Add multi-customer ingest, geospatial schema, and catalog tile coverage.*

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Java 17+ (for GraphHopper map-matching)
- **SpatiaLite** — Windows: download [mod_spatialite](https://www.gaia-gis.it/gaia-sins/windows-bin-x64/) and set `SPATIALITE_EXTENSION` to the full path of `mod_spatialite.dll` (all DLLs in the same folder).
- GraphHopper `map-matching.jar` and per-state `.osm.pbf` extracts (see `graphhopper/`; not in repo).

### 1. Start GraphHopper (optional, for map-match)

```bat
start_graphhopper_servers.bat
```

### 2. Start the backend

```powershell
$env:SPATIALITE_EXTENSION = "C:\path\to\mod_spatialite.dll"
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

On startup, `bootstrap_database()` runs: SpatiaLite init, ORM tables, SQL migrations (`backend/migrations/*.sql`).

Initialize manually if needed:

```bash
cd backend
python scripts/init_db.py
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Enter a **customer ID** and local folder path, click **Ingest**.

### Check catalog coverage (browser or Swagger)

```
http://localhost:8000/catalog/coverage?customerId=YOUR_CUSTOMER
http://localhost:8000/docs
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE` | `http://localhost:8000` | Backend URL (frontend) |
| `VITE_ORIGIN` | `http://localhost:5173` | CORS origin (backend) |
| `DB_PATH` | `.data/app.db` | SQLite database file |
| `SPATIAL_BACKEND` | `spatialite` | `spatialite` or `postgis` (stub) |
| `SPATIALITE_EXTENSION` | `mod_spatialite` | **Required on Windows** — full path to DLL |
| `DATA_CACHE_DIR` | `%LOCALAPPDATA%/RouteViewer/cache` | Cache root; GeoJSON at `{cache}/geojson/{customerId}/` |
| `REGION_CLUSTER_KM` | `10` | Region clustering distance at ingest |
| `CATALOG_TILE_KM` | `5` | Catalog tile size (use `2.5` for finer grid) |
| `CATALOG_ACTIVITY_BUFFER_KM` | `0.5` | Buffer around activity geometry before tiling |
| `CATALOG_FETCH_MARGIN_M` | `350` | Extra margin on tile bbox for OSM fetch (edge continuity) |
| `CATALOG_VERSION` | `1` | Catalog build rules version (stored on tiles) |
| `CATALOG_TILE_SCHEME_VERSION` | `v1` | Grid scheme version (encoded in `tile_scheme`) |
| `GRAPHOPPER_BASE_URL` | `http://localhost:8989` | Default GH URL (inspect endpoint) |

---

## Development Notes — What Was Built (June 2026)

This section is the handoff doc if chat context is lost. See also [backend/SCHEMA.md](backend/SCHEMA.md).

### 1. Multi-customer persistent ingest

**Before:** Each ingest wiped the entire DB and GeoJSON cache.

**Now:**

- Ingest requires `customerId` (and optional `customerName`) in `POST /ingest`.
- Activities are **upserted** per customer; only that customer's stale rows (not in current batch) are removed.
- GeoJSON cache: `{DATA_CACHE_DIR}/geojson/{customerId}/{activity_id}.json`
- Uniqueness: `(customer_id, hash_sig)` — same activity content can exist under different customers.
- Legacy rows without `customer_id` were backfilled to customer `_legacy` via migration bootstrap.

**Content hash** (`hash_sig`): SHA1 of rounded start time, rounded distance, activity type, and bbox.

**Activity ID:** `act_{sha1(customerId|hash_sig)[:32]}` — see `backend/app/db/segment_ids.py`.

**Supported ingest paths:** `.gpx`, `.fit`, `.tcx`, `.gpx.gz`, `.fit.gz`, `.tcx.gz`, folders, `.zip` — see `backend/app/core/ingest_paths.py`.

### 2. Geospatial schema (SpatiaLite)

Tables in `backend/app/db/models.py`:

| Table | Role |
|-------|------|
| `customers` | Map clients |
| `regions` | ~10 km activity clusters (UI / grouping) |
| `catalog_tiles` | Global 5 km OSM build cells + status |
| `network_segments` | Global canonical OSM segment geometry |
| `activities` | One row per run, FK to `customer_id` + `region_id` |
| `activity_segment_usage` | `(activity_id, segment_id)` traversals — **empty until map-match refactor** |
| `segment_stats` | Aggregated per-segment counts — **empty until Task 6** |

Spatial SQL is isolated in `backend/app/db/spatial/` (SpatiaLite + PostGIS stub).

**Migrations** (`backend/migrations/`):

| File | Purpose |
|------|---------|
| `001_initial_schema.sql` | Indexes for activities / segment_stats |
| `002_customers.sql` | `customers` table |
| `003_drop_hash_sig_global_unique.sql` | Drop legacy global unique on `hash_sig` |
| `004_catalog_tiles.sql` | `catalog_tiles` table |

Bootstrap also runs `_drop_global_hash_sig_uniqueness` and `_backfill_legacy_customer_id` in `backend/app/db/migrate.py`.

### 3. Region clustering (Task 2 — done)

At ingest:

1. Parse all files → `ActivityDraft` with centroid + bbox.
2. Greedy cluster by centroid (`REGION_CLUSTER_KM`, default 10 km).
3. Merge clusters that share the same `region_id` (2 dp centroid grid).
4. Upsert `regions` row; assign each activity a `region_id`.

**Region ID:** `reg_{sha1(round(lat,2), round(lon,2))[:12]}`  
**Region name:** e.g. `40.59°N, 75.52°W` (display only)

API: `GET /regions`

Regions are **not** used for catalog coverage checks.

### 4. Catalog tiles + coverage (Task 3 — done)

**Tile math:** `backend/app/core/catalog_tiles.py`

- Fixed lat/lon grid, ~5 km cells (`CATALOG_TILE_KM`).
- **Tile scheme:** `latlon-5000m-v1` (includes size so 2.5 km grid stays distinct).
- **Tile ID:** `tile_{scheme}_{lat_idx}_{lon_idx}` e.g. `tile_latlon-5000m-v1_2907_1767`.
- Each tile has **core bbox** (5 km) and **fetch_bbox** (core + `CATALOG_FETCH_MARGIN_M`).
- Required tiles computed from **buffered activity geometry** (v1: buffered route bbox; corridor buffer planned later).

**At ingest:** All tiles touched by activity coordinates are registered in `catalog_tiles` as `pending` (unless already `ready` / `building`).

**Readiness:** A tile is covered when `catalog_tiles.status == 'ready'`. `segment_count` is **diagnostic only** (some tiles legitimately have few segments).

**APIs:**

| Endpoint | Description |
|----------|-------------|
| `GET /catalog/coverage?customerId=` | Per-customer tile status summary + tile list |
| `GET /catalog/tiles?status=pending` | List global catalog tiles |

**Coverage is NOT filtered by `region_id` on segments** — global catalog, global spatial queries.

Ingest response includes a `catalog` block: `{ required_tiles, new, existing, skipped_ready, tile_scheme, catalog_version }`.

### 5. Stable ID conventions

Defined in `backend/app/db/segment_ids.py`:

```python
make_segment_id(way_id, node_a, node_b)  # -> "osm:123:456:789" (nodes sorted)
make_region_id(lat, lon)                 # -> "reg_{hash12}"
make_activity_id(customer_id, hash_sig)
make_tile_id(tile_scheme, lat_idx, lon_idx)
```

Segment IDs must be **global** and based on full OSM way/node topology — not clipped tile geometry (enforced when OSM build is implemented).

### 6. Legacy flows still working

These were **not** fully rewired to the segment-centric model:

- Map page loads all activities (no `customer_id` filter in UI yet).
- Map-match writes `*_matched.json` per activity, not `activity_segment_usage`.
- Export uses per-activity GeoJSON.
- `network_segments` table is **empty** — no OSM build yet.

GraphHopper multi-state routing (PA/NY/NJ/FL) unchanged — see [MAPMATCH_IMPROVEMENTS.md](MAPMATCH_IMPROVEMENTS.md).

### 7. Known data state after test ingest

Example customer `test_20260611_1634`: **68 catalog tiles**, all `pending`, `catalog_complete: false`. Geography spans FL, GA, NC, PA/Lehigh Valley, NYC, upstate NY — typical for a large Garmin export.

---

## Roadmap — Next Steps (in order)

| # | Task | Status |
|---|------|--------|
| 1 | Geospatial schema + SpatiaLite | **Done** |
| 2 | Region clustering at ingest | **Done** |
| 3 | Catalog tiles + coverage API | **Done** |
| 4 | **OSM catalog build worker** — fetch `fetch_bbox` per pending tile, populate `network_segments`, mark tile `ready` | **Next** |
| 5 | Map-match → segment ID sequences + `activity_segment_usage` | Pending |
| 6 | Populate `segment_stats` | Pending |
| 7 | Aggregation APIs (segment heatmap, usage) | Pending |
| 8 | Segment-centric map visualization | Pending |
| 9 | Export from aggregated segments | Pending |
| 10 | Update docs / frontend (customer filter, coverage UI) | Pending |

**Suggested v1 proof for Task 4:** Build catalog for one Lehigh Valley tile (~40.6°N, 75.5°W), then map-match one activity and query segment stats.

**OSM source options for Task 4:**

- Clip from existing state `.osm.pbf` files (PA/NY/NJ/FL — already used by GraphHopper), or
- Overpass API per tile `fetch_bbox`.

Prefer PBF clip where tiles fall inside a known extract (faster for 68 tiles).

---

## API Reference (current)

| Endpoint | Description |
|----------|-------------|
| `GET /healthz` | Health check |
| `POST /ingest` | Ingest with `{ sourceUri, customerId, customerName? }` |
| `GET /ingest/progress` | In-process ingest progress |
| `GET /activities?customer_id=&region_id=` | List activities (filters optional) |
| `GET /activities/{id}/geojson?variant=matched` | Activity GeoJSON |
| `GET /regions` | List region clusters |
| `GET /catalog/coverage?customerId=` | Catalog tile coverage for customer |
| `GET /catalog/tiles?status=` | List catalog tiles |
| `POST /mapmatch` | GraphHopper map-match (legacy) |
| `POST /export` | GeoJSON / SVG export (legacy) |
| `GET /inspect` | GraphHopper snap debug |

Interactive docs: http://localhost:8000/docs

---

## Key Files (segment-centric work)

| Path | Role |
|------|------|
| `backend/app/api/routes_ingest.py` | Multi-customer ingest, clustering, tile registration |
| `backend/app/api/routes_catalog.py` | Coverage + tile listing |
| `backend/app/api/routes_regions.py` | Region listing |
| `backend/app/core/catalog_tiles.py` | Tile grid math + config |
| `backend/app/core/region_cluster.py` | Activity clustering |
| `backend/app/db/catalog_tiles.py` | `CatalogTileRepository` |
| `backend/app/db/models.py` | All ORM models |
| `backend/app/db/migrate.py` | Bootstrap + legacy hash_sig fix |
| `backend/app/db/repositories.py` | Region + Segment repositories |
| `backend/app/db/segment_ids.py` | ID conventions |
| `backend/app/db/sync.py` | Remove stale customer activities |
| `backend/SCHEMA.md` | Schema reference |
| `frontend/src/pages/Home.tsx` | Customer ID + ingest UI |

**Tests:** `backend/test_catalog_tiles.py`, `test_region_cluster.py`, `test_customer_ids.py`, `test_ingest_paths.py`, `test_parse_tcx.py`

---

## Typical Workflow (today)

```
Local GPX/FIT/TCX folder + customerId
        │
        ▼
  POST /ingest  ──►  activities + regions + catalog_tiles (pending)
        │
        ▼
  GET /catalog/coverage  ──►  which tiles need OSM build?
        │
        ▼
  [NOT BUILT YET] OSM build per tile  ──►  network_segments (ready)
        │
        ▼
  GET /activities + /geojson  ──►  Map view (raw routes, legacy)
        │
        ▼
  POST /mapmatch  ──►  GraphHopper  ──►  *_matched.json (legacy)
        │
        ▼
  POST /export  ──►  snapped.svg
```

## Typical Workflow (target)

```
POST /ingest  ──►  catalog_tiles pending
POST /catalog/build (TBD)  ──►  network_segments, tiles ready
POST /mapmatch  ──►  activity_segment_usage
Refresh segment_stats  ──►  GET aggregation APIs  ──►  segment heatmap map + export
```

---

## Architecture Diagram

```
route-viewer/
├── frontend/          React + Vite + Leaflet (port 5173)
├── backend/           FastAPI + SQLite/SpatiaLite (port 8000)
│   ├── app/core/      parse, geo, region_cluster, catalog_tiles
│   ├── app/db/        models, migrations, spatial adapter
│   └── migrations/    numbered SQL migrations
├── graphhopper/       Per-state map-matching configs
└── .data/app.db       SQLite + spatial tables (gitignored)
```

| Service | Port |
|---------|------|
| Frontend | 5173 |
| Backend | 8000 |
| GraphHopper PA / NY / NJ / FL | 8989 / 8988 / 8987 / 8986 |

---

## Related Documentation

- [MAPMATCH_IMPROVEMENTS.md](MAPMATCH_IMPROVEMENTS.md) — GraphHopper map-matching quality, multi-state servers.
- [backend/SCHEMA.md](backend/SCHEMA.md) — Database tables, spatial adapter, segment IDs.
