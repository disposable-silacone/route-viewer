## Route Viewer – Handoff for a new AI agent

### Purpose
Local-first app to ingest GPX/FIT activities, normalize to SQLite, render raw/matched routes on a Leaflet map, select/filter/export, and map-match via a local GraphHopper server. Includes debugging tools to inspect snapping behavior.

## Repository structure (key paths)
- `backend/app/main.py`: FastAPI app, CORS, router wiring, data dir bootstrap.
- `backend/app/api/`
  - `routes_health.py`: GET `/healthz` – health probe.
  - `routes_ingest.py`: POST `/ingest` – resets DB/cache, ingests folder/zip; GET `/ingest/progress` – live ingest counters.
  - `routes_activities.py`: GET `/activities` (filters), GET `/activities/{id}/geojson?variant=matched`.
  - `routes_export.py`: POST `/export` – merged FeatureCollection.
    - SVG export writes an on-disk copy to `<last ingest folder>/exports/snapped.svg` and returns the SVG with `X-Export-Path` header.
  - `routes_mapmatch.py`: POST `/mapmatch` – sends GPX (includes per-point timestamps when available) to GH `/match`; persists `{id}_matched.json` with the matched LineString. Note: at present we do not persist `details` or `snapped_waypoints` into the saved GeoJSON (UI gracefully handles absence).
  - `routes_inspect.py`: GET `/inspect?lat&lon&profile&radius&samples` – probes GH near a point; returns nearest edge polyline, center snapped point, and sampled candidate snaps.
  - State-aware GH routing: `routes_mapmatch.py` detects the activity's state from coordinates and selects a local GH server port per state: PA=8989, NY=8988, NJ=8987, FL=8986.
- `backend/app/core/`
  - `parse_gpx.py`: Robustly extracts `<trk><name>`, type, points, timestamps; computes distance.
  - `parse_fit.py`: FIT parsing (FitFile) → points, timestamps, distance, type mapping (run/ride/walk/etc).
  - `geojson.py`: Writes per-activity FeatureCollection (LineString).
  - `walker.py`: Recurses for `.gpx`/`.fit`.
  - `storage.py` (if present later): persistent helpers.
- `backend/app/db/`
  - `models.py`: `Activity` ORM with `source_path`, `name`, `activity_type`, times, distance, bbox, `geojson_path`, `hash_sig`.
  - `session.py`: SQLite engine/session (`.data/app.db`).
- `frontend/src/pages/`
  - `Home.tsx`: Ingest UI; shows live progress “Scanned X/Y | Parsed P (new N, dup D, errors E)”.
  - `MapPage.tsx`: Map, unified right drawer, toggles, selection/sort, rectangle select, export, map match. Debug: snapped points overlay, click-to-inspect overlay, road_class/OSM IDs popup.
- `frontend/src/styles/ui.css`: Tokens and UI primitives; drawer is resizable (`resize: both`).
- `graphhopper/config_*.yaml`: Working GH 5.x configs per state.
- `graphs/*`: GH graph caches (generated).
- `graphhopper/pbf/*`: OSM PBFs (inputs).

## Runtime basics
- Prereqs: Python 3.11+, Node 18+, Java 17+.
- Backend: from `backend/` → `pip install -r requirements.txt` → `python -m uvicorn app.main:app --reload --port 8000`
- Frontend: from `frontend/` → `npm i` → `npm run dev` (http://localhost:5173)
- GH server (example PA): `java -Xms4g -Xmx8g -jar graphhopper/map-matching.jar server graphhopper/config_PA.yaml`
- Multi-state setup: the backend auto-selects GH base by state (PA=8989, NY=8988, NJ=8987, FL=8986). Inspector uses `GRAPHOPPER_BASE_URL` if set; map-match uses state-based ports regardless of that env var.
- Health: backend `GET /healthz` should return “ok”; GH root should 200.

## Storage and cache locations
- SQLite: `backend/.data/app.db` (auto-created).
- Raw GeoJSON: `…/cache/geojson/{uuid}.json`
- Matched GeoJSON: `…/cache/geojson/{uuid}_matched.json`
- Cache root default: `%LOCALAPPDATA%\RouteViewer\cache` on Windows (falls back to `.cache`, can override via `DATA_CACHE_DIR`).

## Process flow

### Ingest (folder or zip)
1. UI `Home.tsx` POSTs to `/ingest` with `{ sourceUri }`.
2. Backend:
   - Recreates DB tables and clears `cache/geojson`.
   - Walks the folder and collects `.gpx`/`.fit`.
   - Parses each file to `ParsedTrack`:
     - GPX: prefers `<trk><name>`, derives `type` from `<type>`, collects points and UTC start/end; computes distance via haversine.
     - FIT: decodes record/session, converts semicircles→deg, infers sport/sub_sport→type, uses distance field or computes if absent.
   - Dedup guards:
     - path duplicate (`source_path`),
     - composite hash signature of rounded start time, rounded distance, type, bbox.
   - Writes per-activity Raw GeoJSON and inserts row in SQLite.
   - Updates in-memory progress counters.
3. Progress reporting:
   - GET `/ingest/progress` returns `{ started, done, total, scanned, parsed, new, duplicates, errors, current }`.
   - `Home.tsx` polls every 500 ms and renders “Scanned X/Y | Parsed P (new N, dup D, errors E)”.

### Activities load and render
1. `MapPage.tsx` GETs `/activities` with filters (type, minDist, maxDist).
2. For each activity: GET `/activities/{id}/geojson` (raw); optionally also `?variant=matched`.
3. Renders:
   - Raw (red), Matched (blue), basemap. Fit-to-bounds on visible subset.
   - Drawer contains toggles, filters, sort, selection, rectangle select, export, map match.
   - Panel is resizable; “selected only” view for each layer.

### Map matching
1. UI calls POST `/mapmatch` with `{ ids, profile, gpsAccuracy? }`.
   - Profile defaults to bike in API; UI picks foot for run/walk else bike.
   - Optional `gpsAccuracy` forwarded to GH.
2. Backend:
   - Reads raw GeoJSON and builds GPX; includes per-point timestamps when available (ingest stores them from GPX/FIT).
   - Calls `GH /match?profile=...&type=json&points_encoded=false&debug=true&details=road_class&details=osm_way_id[&gps_accuracy=...]` against a state-specific GH server.
   - Extracts `paths[0].points.coordinates` → matched polyline.
   - Persists `{id}_matched.json` with properties `{ id, variant: 'matched', profile_used }`. Details/snapped_waypoints are currently not persisted to file.
3. Frontend:
   - Blue matched line. If `details` and `snapped_waypoints` are present they are displayed; otherwise the UI shows a fallback note.

### Inspector (debugging snapping)
- GET `/inspect?lat&lon&profile&radius&samples`:
  - Queries GH “route” from point to a nearby offset to obtain the nearest edge, `details`, and `snapped_waypoints`.
  - Samples around a circle to approximate candidate snapping points.
  - Returns FeatureCollection with:
    - center point, snapped center, candidate snapped points, and a small polyline along the nearest edge.
- `MapPage.tsx`:
  - When “Show snapped points” is enabled, clicking the map overlays these artifacts for ~5 seconds to inspect local graph behavior.

### Export
- POST `/export` with `{ ids: string[], format: 'geojson', variant?: 'matched' }` → merged FeatureCollection download.
  - For `format: 'svg'`, backend composes a simple projected SVG of selected paths and also saves it to `<last ingest>/exports/snapped.svg`.

## Key logic and decisions
- GPX name precedence: `<trk><name>` is captured and saved; fallback to file stem.
- FIT parsing:
  - Records yield lon/lat; timestamps normalize to UTC; distance field used if present.
  - Sport mapping: running→run, cycling→ride, walking/hiking→walk, swimming→swim; else passthrough/unknown.
- Dedup:
  - Composite signature: rounded start minute, rounded distance (10 m), inferred type, bbox.
  - Path-level duplicate guard on `source_path`.
- GraphHopper integration:
  - Use 5.x style custom model configs; omit legacy `map_matching` keys.
  - Request `details=road_class,osm_way_id` and `debug=true` for diagnostics.
  - `gps_accuracy` is forwarded when provided to constrain snap distance. The backend's current default GPS accuracy is relatively permissive (run/walk ~30 m; ride ~35 m; swim ~40 m) vs. the UI defaults (5–10 m).
  - State-aware server selection: PA=8989, NY=8988, NJ=8987, FL=8986.

## Frontend UI highlights
- `MapPage.tsx`:
  - Drawer: layer toggles (raw/snapped/basemap), “selected only” filters, type/min/max distance, rectangle select, Export, Map Match, Clear.
  - Sorting by Name/Start/Date/Type/Distance; start shows first-point lat/lon (placeholder for future reverse geocode).
  - Debug toggles: GPS accuracy field; “Show snapped points” (cyan); click-to-inspect (purple/green/orange).
- `ui.css` drawer is resizable (`resize: both`), with min/max limits and sticky header.

## Troubleshooting notes
- If you see side-street detours in matched lines:
  - Lower `gps_accuracy` (e.g., 5–10 m) for Garmin tracks.
  - Ensure profile matches activity (foot vs bike).
  - Use Inspector to verify nearest edge and candidate snaps at problematic points.
- If GH import fails:
  - Use absolute PBF paths; ensure configs include `encoder + weighting: custom` and minimal `custom_model`.
- If OneDrive prompts to delete many files:
  - Cache now defaults to `%LOCALAPPDATA%\RouteViewer\cache`; override via `DATA_CACHE_DIR` if desired.

## Future-facing work (next steps; snapping focus)

### 1) Improve map-matching fidelity (avoid side-street “jogs”)
- Parameter tuning (fast lift):
  - Default `gps_accuracy` by device source (e.g., Garmin 5–8 m).
  - Consider exposing `max_visited_nodes` (if supported in your GH build) to limit wandering.
- Enrich input to GH: [Done]
  - GPX sent to `/match` now includes per-point timestamps when available; ingest stores timestamps from GPX/FIT and the raw GeoJSON carries them as Point features.
- Post-processing cleanup:
  - A short-excursion cleanup helper exists but is currently disabled in the backend while testing baseline map-matching.
- Custom model nudges:
  - Slightly de-prioritize `residential` when a parallel `primary/secondary/tertiary` is nearby and aligned with heading, but ensure foot legality for sidewalks/paths.
  - Penalize frequent short turns (turn cost surrogate) if your GH build allows influencing via custom_model/priority.
- Corridor-constrained matching (optional advanced):
  - Pre-compute a “mainline” corridor by simplifying the raw track then buffering ~gps_accuracy; reject candidate edges outside the corridor to discourage perpendicular side streets.

Concrete tasks:
- Backend:
  - Enhance `/mapmatch` GPX builder to include per-point timestamps; persist times during ingest.
  - Add server config option for default `gps_accuracy` by type/device, overridable per request.
  - Optional: add `maxVisitedNodes` passthrough if available.
- Frontend:
  - Input for default gps acc by type; per-match override retained.
  - “Re-run last match with new parameters” action for quick iteration.
  - Visual “detour highlighter” that thickens segments with sharp left/right and short length.
- Config:
  - Prototype custom_model priorities that gently favor through-roads for bike/foot while respecting access; keep changes minimal to avoid biasing off-trail.

### 2) UX and data quality
- Reverse geocode start city/state; store in DB as `start_city`, `start_state`; show in table and sort/filter.
- Replace alert() with snackbars for map-match results.
- Batch-fetch GeoJSON with concurrency cap; virtualize the routes table for large sets.

### 3) Testing/observability
- Unit tests for: GPX/FIT parsing, dedup signature, map-match response parsing.
- Add logs for `/mapmatch` (params, response status) and `/inspect` (lat/lon/profile).

## API reference (current)
- POST `/ingest` → `{ summary, batchId: null }` (resets DB/cache; ingests path)
- GET `/ingest/progress` → `{ started, done, total, scanned, parsed, new, duplicates, errors, current }`
- GET `/activities?type=&start=&end=&minDist=&maxDist=` → activity rows
- GET `/activities/{id}/geojson?variant=matched` → FeatureCollection
- POST `/export` `{ ids: string[], format: 'geojson', variant?: 'matched' }` → FC download
  - For `format: 'svg'`, returns SVG and writes a copy under `<last ingest>/exports/snapped.svg` (path in `X-Export-Path`).
- POST `/mapmatch` `{ ids: string[], profile: 'foot'|'bike'|'car', gpsAccuracy?: number }` → `{ matched, failed }`
- GET `/inspect?lat&lon&profile&radius&samples` → FeatureCollection + `{ meta.details }`

If you want, I can proceed by adding per-point timestamps into the map-match GPX and a small post-processor to remove short side-street excursions.


### Cloud deployment plan (addendum)

- **Targets**: Deploy on Cloud Run; store raw GPX/FIT and exports in GCS; orchestrate ingest/map-match/export via Firebase for queue/order management. Configure primarily in Cloud Console [[memory:6987751]]. Use Artifact Registry in `us-east4` [[memory:6987722]]. Single-user operational needs, minimal moving parts [[memory:6987727]][[memory:6987733]].

### High-level architecture
- **Services**
  - **route-viewer-api** (Cloud Run): FastAPI backend from `backend/`. Stateless; reads/writes GeoJSON in GCS; uses managed DB (Cloud SQL Postgres) or Firestore for activities metadata (SQLite is not durable on Cloud Run).
  - **graphhopper-mapmatching** (Cloud Run or GCE): GraphHopper Map Matching server. Precompute graph caches offline and store in GCS; containers mount read-only via GCS FUSE.
  - Optional: **ingest-job** (Cloud Run Job) for large batch ingests triggered by Firebase queue.
- **Storage**
  - `gs://<RAW_BUCKET>`: Raw uploads (GPX/FIT) and optional original zips.
  - `gs://<CACHE_BUCKET>/geojson/`: Raw and matched per-activity GeoJSON.
  - `gs://<GRAPH_BUCKET>/graphs/<STATE>/`: Prebuilt GH graph caches (read-only at runtime).
  - Exports: `gs://<EXPORT_BUCKET>/exports/merged-*.geojson`.
- **Queue/order management**
  - Firebase (Firestore) “orders” collection with docs: { status, sourceUri (gs://...), filters, profile, createdAt, userId }.
  - Cloud Run webhook (or Firebase Function) transitions: Requested → Ingesting → Ready → Matching → Exported.
  - Optional: enqueue per-order tasks via Cloud Tasks (HTTP target = Cloud Run) for reliable at-least-once delivery.

### Containerization and deploy
- Build/push backend image
  - Dockerfile at repo root or `backend/` (multi-stage, installs `requirements.txt`).
  - Push to Artifact Registry in `us-east4` [[memory:6987722]].
- Deploy Cloud Run service (console-first setup [[memory:6987751]])
  - Env vars:
    - `EXPORT_BUCKET`, `RAW_BUCKET`, `CACHE_BUCKET`, `GRAPH_BUCKET`
    - `GRAPHOPPER_BASE_URL=https://graphhopper-…run.app`
    - If using Cloud SQL: `DB_URL=postgresql+psycopg://…`
    - If using Firestore: `DATA_BACKEND=firebase` (feature flag you’ll add)
    - Default tuning: `DEFAULT_GPS_ACCURACY=8`
  - Concurrency 40–80; memory 1–2 GiB (backend). CPU always allocated: off.
- Deploy GraphHopper service
  - Build image with `map-matching.jar` and configs.
  - First run (import) as a Cloud Run Job or GCE VM; copy generated `graphs/<STATE>/` to `gs://<GRAPH_BUCKET>/graphs/<STATE>/`.
  - Runtime mounts:
    - `GRAPH_LOCATION` set to GCS FUSE mount path (Cloud Run “Volumes → Cloud Storage”).
    - `datareader.file` points to PBF in GCS or baked into image.
  - Memory 8–12 GiB; CPU 2–4. Concurrency 1.

### Backend changes to enable cloud mode
- Storage adapters
  - Add GCS client (google-cloud-storage) for:
    - Reading raw `gs://...` in `/ingest` (stream GPX/FIT).
    - Writing GeoJSON to `gs://<CACHE_BUCKET>/geojson/{id}.json` and `{id}_matched.json`.
    - Writing merged exports to `gs://<EXPORT_BUCKET>/exports/…`.
- Metadata store
  - Replace SQLite with:
    - Cloud SQL Postgres (SQLAlchemy URL via `DB_URL`), or
    - Firestore (simple DAO layer mirroring fields in `Activity`).
- Ingest entry points
  - Accept `sourceUri` as `gs://bucket/path` or local path.
  - Progress endpoint remains `/ingest/progress` (in-memory); for distributed runs store progress in Firestore (doc per order).
- Map-match integration
  - Add default `gps_accuracy` from env; still allow per-request override.
  - Persist GH `details` and `snapped_waypoints` as now.

### Firebase orchestration
- Firestore data model
  - Collection `orders/{orderId}`: { status, sourceUri, typeFilters, minDist, maxDist, profile, gpsAccuracy, exportDest, createdAt, updatedAt, error }
- Flow
  - Client writes order doc → Firebase Function (or client) enqueues Cloud Task to POST Cloud Run `/ingest` (idempotent by orderId).
  - After ingest, backend sets status=Ready and writes counts to the doc.
  - Client or function triggers `/mapmatch` (with heuristics: foot for run/walk) → status=Matched.
  - Client hits `/export` → backend writes to `EXPORT_BUCKET` and updates doc with `exportUri`.
- Security
  - Service account on Cloud Run has roles: Storage Object Admin (scoped), Cloud SQL Client or Firestore access, Cloud Tasks Enqueuer (if needed).

### CI/CD
- Build in Cloud Build or GitHub Actions:
  - Lint/test → docker build → push to Artifact Registry (us-east4) [[memory:6987722]] → deploy Cloud Run (staged and prod).

### GraphHopper graph management
- Precompute once per state:
  - Run an import job (Cloud Run Job or GCE), with `-Xms4g -Xmx8g`, using your `config_STATE.yaml`.
  - Upload the resulting `graphs/STATE/` directory to `gs://<GRAPH_BUCKET>/graphs/STATE/`.
- Runtime:
  - Mount `gs://<GRAPH_BUCKET>` via Cloud Run “Volumes → Cloud Storage” (read-only), set `graph.location` to the mounted path.
  - Ensure `details` (road_class, osm_way_id) and `custom_model` fields match GH 5.x expectations.

### Future-looking tasks (cloud)
- Implement GCS adapters in:
  - `routes_ingest.py`: accept `gs://` paths, stream reads, write GeoJSON to GCS.
  - `routes_export.py`: stream merged FC to client or write to `EXPORT_BUCKET` and return `gs://` URL.
- Abstract DB:
  - Add `db/dao.py` with conditional backend (SQLAlchemy vs Firestore).
- Firebase integration:
  - Add `/orders/{id}` endpoints or use Firestore exclusively.
  - Optional WebSocket/SSE for live progress per order.
- Observability:
  - Structured logs (request ids, order ids), Error Reporting.
  - Minimal metrics: ingest rate, parse errors, map-match failures.

### Snapping improvements roadmap (ties to your next priority)
- Use timestamps in `/mapmatch` GPX (currently we submit only coordinates). Persist per-point timestamps at ingest so the GPX builder can include `<time>`.
- Default `gps_accuracy` by activity type/device; surface in UI; store choice per match.
- Inspector already added:
  - “Show snapped points” (cyan), click overlay (nearest edge = purple, snapped center = green, candidates = orange).
- Custom model nudges (small, safe biases):
  - Slightly increase priority for primary/secondary/tertiary vs residential for bike/foot while preserving access rules.
  - Penalize rapid oscillations via minor priority adjustments if supported.
- Post-match cleanup:
  - Detect and remove very short perpendicular excursions that leave and return to the same road within ≤30–50 m.

If you want, I can start by adding GCS read/write adapters to `/ingest` and `/export`, and a Firestore metadata layer; then prepare Dockerfiles and a Cloud Run deploy template for `us-east4` [[memory:6987722]].

## Valhalla migration plan (for next agent)

Goal: Add an alternative map-matching backend using Valhalla, selectable alongside GraphHopper.

High-level tasks:
- Backend:
  - Introduce a `MAPMATCH_ENGINE` setting (`graphhopper` default, `valhalla` optional) via env or request param.
  - Add Valhalla client in `routes_mapmatch.py` that:
    - Reads raw GeoJSON, constructs Valhalla trace attributes/trace route request (`/trace_attributes` or `/trace_route`).
    - Maps profiles (`foot|bike|car`) to Valhalla costing (`pedestrian|bicycle|auto`).
    - Supports `gps_accuracy` equivalent (`search_radius`/`gps_accuracy`) when available.
    - Produces matched LineString GeoJSON identical to GH output shape.
  - Keep GH path as-is; choose engine per request or global default.
- Config:
  - Add `VALHALLA_BASE_URL` (e.g., `http://localhost:8002`). Document Docker run for Valhalla.
- Frontend:
  - Optional toggle to select engine (default to server default). Existing UI can remain unchanged initially.
- Testing:
  - Golden tests for small traces against both engines; verify geometry and basic stats.

Migration notes:
- Timestamped GPX is already generated; reuse for Valhalla inputs (or post raw coords/times directly).
- Details parity: Valhalla’s attributes differ from GH `details`; start by returning only the matched geometry, then add attributes.
- State routing is GH-specific; Valhalla can run as a single service; keep GH state logic side-by-side.