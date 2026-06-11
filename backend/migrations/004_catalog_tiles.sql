CREATE TABLE IF NOT EXISTS catalog_tiles (
  tile_id TEXT PRIMARY KEY,
  tile_scheme TEXT NOT NULL,
  catalog_version TEXT NOT NULL,
  lat_idx INTEGER NOT NULL,
  lon_idx INTEGER NOT NULL,
  bbox_min_lon REAL NOT NULL,
  bbox_min_lat REAL NOT NULL,
  bbox_max_lon REAL NOT NULL,
  bbox_max_lat REAL NOT NULL,
  fetch_min_lon REAL NOT NULL,
  fetch_min_lat REAL NOT NULL,
  fetch_max_lon REAL NOT NULL,
  fetch_max_lat REAL NOT NULL,
  fetch_margin_m REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  segment_count INTEGER,
  built_at TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_catalog_tiles_status ON catalog_tiles (status);
CREATE INDEX IF NOT EXISTS ix_catalog_tiles_tile_scheme ON catalog_tiles (tile_scheme);
