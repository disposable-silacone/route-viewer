# Segment-Centric Database Schema (Task 1)

SpatiaLite-backed schema designed for a future PostGIS migration. Spatial SQL lives
behind `app/db/spatial/` — do not scatter dialect-specific functions through routes.

## Tables

### `regions`
Geographic processing clusters (centroid + bbox). One region per activity cluster.

### `network_segments`
Canonical road/path geometry. **`segment_id` is the business identity** — stable,
derived from OSM identifiers via `make_segment_id()`. Never use autoincrement IDs
for segments.

### `activities`
One row per imported run. Links to a `region_id` after clustering (Task 2).

### `activity_segment_usage`
Composite primary key `(activity_id, segment_id)`. One summarized row per
activity/segment pair with traversal counts and match metadata.

### `segment_stats`
Aggregated counts per segment — rebuilt after ingest/match (Task 6).

## Stable segment IDs

```python
from app.db.segment_ids import make_segment_id

segment_id = make_segment_id(osm_way_id=123, osm_start_node_id=456, osm_end_node_id=789)
# -> "osm:123:456:789"  (nodes sorted for undirected identity)
```

## Spatial adapter

```python
from app.db.spatial import get_spatial_backend

backend = get_spatial_backend()  # SPATIAL_BACKEND=spatialite|postgis
```

- **SpatiaLite (default):** loads `mod_spatialite`, `InitSpatialMetaData`, R\*Tree via `CreateSpatialIndex`
- **PostGIS (stub):** `ST_Intersects`, GiST index — set `SPATIAL_BACKEND=postgis` and `DATABASE_URL`

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_PATH` | `.data/app.db` | SQLite database file |
| `SPATIAL_BACKEND` | `spatialite` | `spatialite` or `postgis` |
| `SPATIALITE_EXTENSION` | `mod_spatialite` | Path/name of SpatiaLite DLL/SO |
| `DATABASE_URL` | — | PostgreSQL URL when using PostGIS |

## Initialize

```bash
cd backend
pip install -r requirements.txt
python scripts/init_db.py
```

## Ingest & region clustering (Task 2)

Ingest is two-phase:

1. **Parse** all GPX/FIT files and build activity drafts with centroids and bboxes.
2. **Cluster** drafts by centroid (`REGION_CLUSTER_KM`, default **10 km**) and create one
   `regions` row per cluster with a union bbox (+ ~2 km buffer).

Each activity is assigned a `region_id`. Ingest response includes a `regions` summary.

```bash
# Optional: adjust clustering distance
set REGION_CLUSTER_KM=10
```

**API:** `GET /regions` lists clusters and activity counts.

## Repositories

- `RegionRepository` — CRUD for regions
- `SegmentRepository` — segment lookup + `catalog_covers_bbox()` for Task 3

## Migration note

The legacy ingest/map-match API still targets the old activity shape. Tasks 2–6 will
rewire ingest, clustering, catalog build, and map-match to this schema.
