export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export type LayerMode = 'raw' | 'matched' | 'both'

export type CustomerRow = {
  customer_id: string
  name: string | null
  activity_count: number
  first_activity_at: string | null
  last_activity_at: string | null
}

export type ActivityRow = {
  id: string
  customer_id: string
  name: string | null
  source_file?: string | null
  type: string
  region_id?: string | null
  start?: string | null
  distance_m?: number | null
  duration_sec?: number | null
  match_status?: string
  match_confidence?: number | null
  matched_at?: string | null
  bbox?: [number, number, number, number]
}

export type SegmentUsageRow = {
  segment_id: string
  traversals: number
  matched_length_m: number | null
  first_seen_order: number | null
  last_seen_order: number | null
  confidence: number | null
}

export type ActivitySegments = {
  activity_id: string
  match_status: string
  match_confidence: number | null
  segment_count: number
  segments: SegmentUsageRow[]
}

export type ActivityQA = {
  activity_id: string
  match_status: string
  match_confidence: number | null
  raw_distance_m: number | null
  matched_distance_m: number | null
  unique_segments: number | null
  segment_sequence_length: number | null
  low_support_segment_count: number | null
  suppressed_spur_count: number | null
  weak_turn_reassignments: number | null
  matched_at: string | null
}

export async function fetchCustomers(): Promise<CustomerRow[]> {
  const res = await fetch(`${API_BASE}/customers`)
  if (!res.ok) throw new Error('Failed to load customers')
  const data = await res.json()
  return data.customers ?? []
}

export async function fetchActivities(params: {
  customer_id: string
  type?: string
  minDist?: number
  maxDist?: number
  match_status?: string
  start?: string
  end?: string
}): Promise<ActivityRow[]> {
  const q = new URLSearchParams()
  q.set('customer_id', params.customer_id)
  if (params.type) q.set('type', params.type)
  if (params.minDist != null) q.set('minDist', String(params.minDist))
  if (params.maxDist != null) q.set('maxDist', String(params.maxDist))
  if (params.match_status) q.set('match_status', params.match_status)
  if (params.start) q.set('start', params.start)
  if (params.end) q.set('end', params.end)
  const res = await fetch(`${API_BASE}/activities?${q}`)
  if (!res.ok) throw new Error('Failed to load activities')
  return res.json()
}

export async function fetchActivitySegments(activityId: string): Promise<ActivitySegments> {
  const res = await fetch(`${API_BASE}/activities/${activityId}/segments`)
  if (!res.ok) throw new Error('Failed to load segments')
  return res.json()
}

/** ISO datetime for API `start` / `end` query params from a date input (YYYY-MM-DD). */
export function dateFilterToStart(isoDate: string): string {
  return `${isoDate}T00:00:00`
}

export function dateFilterToEnd(isoDate: string): string {
  return `${isoDate}T23:59:59`
}

export async function fetchActivityGeojson(
  activityId: string,
  variant?: 'matched'
): Promise<{ type: string; features: any[] }> {
  const url =
    variant === 'matched'
      ? `${API_BASE}/activities/${activityId}/geojson?variant=matched`
      : `${API_BASE}/activities/${activityId}/geojson`
  const res = await fetch(url)
  if (!res.ok) throw new Error(variant === 'matched' ? 'No matched geometry' : 'No raw geometry')
  return res.json()
}

export async function fetchActivityQA(activityId: string): Promise<ActivityQA> {
  const res = await fetch(`${API_BASE}/activities/${activityId}/qa`)
  if (!res.ok) throw new Error('Failed to load QA metrics')
  return res.json()
}

export type CatalogTileCoverage = {
  tile_id: string
  lat_idx: number
  lon_idx: number
  status: string
  segment_count: number | null
  error_message?: string | null
  bbox: number[]
  fetch_bbox: number[]
}

export type CatalogCoverage = {
  customer_id: string
  tile_scheme: string
  catalog_version: string
  required_tiles: number
  ready_tiles: number
  catalog_complete: boolean
  counts_by_status: Record<string, number>
  tiles: CatalogTileCoverage[]
}

export type CatalogBuildTileResult = {
  tile_id: string
  status: string
  segments_fetched?: number
  segments_upserted?: number
  segment_count?: number
  error?: string | null
}

export type CatalogBuildResult = {
  built: number
  results: CatalogBuildTileResult[]
  message?: string
}

export type MapMatchActivityResult = {
  activity_id: string
  status: string
  segment_count?: number
  required_tiles?: number
  ready_tiles?: number
  missing_tiles?: string[]
  not_ready_tiles?: string[]
  match_confidence?: number | null
  error?: string | null
}

export async function fetchCatalogCoverage(customerId: string): Promise<CatalogCoverage> {
  const q = new URLSearchParams({ customerId })
  const res = await fetch(`${API_BASE}/catalog/coverage?${q}`)
  if (!res.ok) throw new Error('Failed to load catalog coverage')
  return res.json()
}

export async function buildCatalogTiles(
  customerId: string,
  limit: number,
  opts?: { statuses?: string[] }
): Promise<CatalogBuildResult> {
  const body: Record<string, unknown> = { customerId, limit }
  if (opts?.statuses) body.statuses = opts.statuses
  const res = await fetch(`${API_BASE}/catalog/build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const json = await res.json()
  if (!res.ok) throw new Error(JSON.stringify(json))
  return json
}

export async function matchActivities(
  ids: string[],
  opts?: { allowPartial?: boolean }
): Promise<{
  matched: number
  partial: number
  failed: number
  results: MapMatchActivityResult[]
}> {
  const res = await fetch(`${API_BASE}/mapmatch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ids,
      writeGeojson: true,
      allowPartial: opts?.allowPartial ?? false,
    }),
  })
  const json = await res.json()
  if (!res.ok) throw new Error(JSON.stringify(json))
  return json
}

export function formatMatchError(row: MapMatchActivityResult): string {
  if (!row.error) return `Match ${row.status}`
  const parts = [row.error]
  const notReady = row.not_ready_tiles?.length ?? 0
  const missing = row.missing_tiles?.length ?? 0
  if (notReady || missing) {
    parts.push(`(${missing} missing, ${notReady} not ready of ${row.required_tiles ?? '?'} tiles)`)
  }
  return parts.join(' ')
}

export function lineFeatures(
  fc: { features?: any[] } | null | undefined,
  variant?: 'matched' | 'raw'
): any[] {
  if (!fc?.features?.length) return []
  return fc.features.filter((f: any) => {
    if (f.geometry?.type !== 'LineString') return false
    if (variant === 'matched') {
      const p = f.properties as Record<string, unknown> | null
      return p?.variant === 'matched' || p?.matcher === 'catalog'
    }
    return true
  })
}

export function formatKm(m: number | null | undefined): string {
  if (m == null || Number.isNaN(m)) return '—'
  return `${(m / 1000).toFixed(2)} km`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString()
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}
