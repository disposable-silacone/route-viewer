import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import {
  ActivityQA,
  ActivityRow,
  CatalogCoverage,
  CustomerRow,
  LayerMode,
  MapMatchActivityResult,
  buildCatalogTiles,
  dateFilterToEnd,
  dateFilterToStart,
  fetchActivities,
  fetchActivityGeojson,
  fetchActivityQA,
  fetchCatalogCoverage,
  fetchCustomers,
  formatDate,
  formatDateTime,
  formatKm,
  formatMatchError,
  lineFeatures,
  matchActivities,
} from '../api/client'
import { CatalogStrip, formatBuildSummary } from '../components/CatalogStrip'
import { SegmentDrawer } from '../components/SegmentDrawer'
import { useDebounced } from '../hooks/useDebounced'

const CUSTOMER_STORAGE_KEY = 'routeViewer.lastCustomer'

const FitToFeatures: React.FC<{ features: any[] }> = ({ features }) => {
  const map = useMap()
  const lastKeyRef = useRef<string | null>(null)
  useEffect(() => {
    if (!features.length) return
    const layer = L.geoJSON({ type: 'FeatureCollection', features } as any)
    const bounds = layer.getBounds()
    if (!bounds.isValid()) return
    const key = bounds.toBBoxString()
    if (lastKeyRef.current === key) return
    lastKeyRef.current = key
    map.fitBounds(bounds, { padding: [32, 32] })
  }, [features, map])
  return null
}

function parseLayer(value: string | null): LayerMode {
  if (value === 'raw' || value === 'matched' || value === 'both') return value
  return 'both'
}

function matchBadge(status: string | undefined): string {
  if (!status || status === 'pending') return 'pending'
  return status
}

export const ActivityQAWorkspace: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const urlCustomer = searchParams.get('customer') || searchParams.get('customerId') || ''
  const urlActivity = searchParams.get('activity') || searchParams.get('activityId') || ''

  const [customers, setCustomers] = useState<CustomerRow[]>([])
  const [customerId, setCustomerId] = useState(
    () => urlCustomer || sessionStorage.getItem(CUSTOMER_STORAGE_KEY) || ''
  )
  const [activities, setActivities] = useState<ActivityRow[]>([])
  const [focusedId, setFocusedId] = useState(urlActivity)
  const [layer, setLayer] = useState<LayerMode>(() =>
    parseLayer(searchParams.get('layer'))
  )
  const [typeFilter, setTypeFilter] = useState(() => searchParams.get('type') || '')
  const [matchFilter, setMatchFilter] = useState(() => searchParams.get('match') || '')
  const [dateFrom, setDateFrom] = useState(() => searchParams.get('from') || '')
  const [dateTo, setDateTo] = useState(() => searchParams.get('to') || '')
  const [minDist, setMinDist] = useState<number | ''>('')
  const [maxDist, setMaxDist] = useState<number | ''>('')

  const debouncedMinDist = useDebounced(minDist, 300)
  const debouncedMaxDist = useDebounced(maxDist, 300)

  const [listLoading, setListLoading] = useState(false)
  const [geoLoading, setGeoLoading] = useState(false)
  const [matching, setMatching] = useState(false)
  const [batchMatching, setBatchMatching] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [geoError, setGeoError] = useState<string | null>(null)
  const [matchMessage, setMatchMessage] = useState<string | null>(null)
  const [matchError, setMatchError] = useState(false)

  const [catalog, setCatalog] = useState<CatalogCoverage | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [catalogBuilding, setCatalogBuilding] = useState(false)
  const [buildMessage, setBuildMessage] = useState<string | null>(null)

  const [rawFeatures, setRawFeatures] = useState<any[]>([])
  const [matchedFeatures, setMatchedFeatures] = useState<any[]>([])
  const [qa, setQa] = useState<ActivityQA | null>(null)
  const [segmentsOpen, setSegmentsOpen] = useState(false)
  const [segmentRefreshKey, setSegmentRefreshKey] = useState(0)
  const [copyMsg, setCopyMsg] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchCustomers()
      .then((rows) => {
        if (!cancelled) setCustomers(rows)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!customerId.trim()) {
      setActivities([])
      return
    }
    sessionStorage.setItem(CUSTOMER_STORAGE_KEY, customerId.trim())
    let cancelled = false
    setListLoading(true)
    setListError(null)
    fetchActivities({
      customer_id: customerId.trim(),
      type: typeFilter || undefined,
      match_status: matchFilter || undefined,
      start: dateFrom ? dateFilterToStart(dateFrom) : undefined,
      end: dateTo ? dateFilterToEnd(dateTo) : undefined,
      minDist: debouncedMinDist === '' ? undefined : debouncedMinDist,
      maxDist: debouncedMaxDist === '' ? undefined : debouncedMaxDist,
    })
      .then((rows) => {
        if (cancelled) return
        const sorted = [...rows].sort((a, b) => {
          const ad = a.start ? Date.parse(a.start) : 0
          const bd = b.start ? Date.parse(b.start) : 0
          return bd - ad
        })
        setActivities(sorted)
        if (focusedId && !sorted.some((r) => r.id === focusedId)) {
          setFocusedId(sorted[0]?.id ?? '')
        } else if (!focusedId && sorted.length) {
          setFocusedId(urlActivity && sorted.some((r) => r.id === urlActivity) ? urlActivity : sorted[0].id)
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setListError(err.message)
      })
      .finally(() => {
        if (!cancelled) setListLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [customerId, typeFilter, matchFilter, dateFrom, dateTo, debouncedMinDist, debouncedMaxDist])

  const loadCatalog = useCallback(async () => {
    if (!customerId.trim()) {
      setCatalog(null)
      return
    }
    setCatalogLoading(true)
    setCatalogError(null)
    try {
      const data = await fetchCatalogCoverage(customerId.trim())
      setCatalog(data)
    } catch (err) {
      setCatalogError(err instanceof Error ? err.message : 'Coverage load failed')
    } finally {
      setCatalogLoading(false)
    }
  }, [customerId])

  useEffect(() => {
    loadCatalog()
  }, [loadCatalog])

  const handleBuildTiles = async (
    limit: number,
    opts?: { statuses?: string[] }
  ) => {
    if (!customerId.trim()) return
    setCatalogBuilding(true)
    setBuildMessage(null)
    try {
      const result = await buildCatalogTiles(customerId.trim(), limit, opts)
      setBuildMessage(formatBuildSummary(result))
      await loadCatalog()
    } catch (err) {
      setBuildMessage(err instanceof Error ? err.message : 'Build failed')
    } finally {
      setCatalogBuilding(false)
    }
  }

  const applyMatchResult = async (
    activityId: string,
    row: MapMatchActivityResult | undefined
  ) => {
    if (!row) return
    const failed = row.status === 'failed'
    setMatchError(failed)
    setMatchMessage(
      failed ? formatMatchError(row) : `Match ${row.status} — ${row.segment_count ?? '?'} unique segments`
    )
    if (failed) return

    const [qaData, matchedFc] = await Promise.all([
      fetchActivityQA(activityId),
      fetchActivityGeojson(activityId, 'matched').catch(() => null),
    ])
    setQa(qaData)
    if (matchedFc) setMatchedFeatures(lineFeatures(matchedFc, 'matched'))
    setLayer('both')
    setActivities((prev) =>
      prev.map((a) =>
        a.id === activityId
          ? {
              ...a,
              match_status: qaData.match_status,
              matched_at: qaData.matched_at,
              match_confidence: qaData.match_confidence,
            }
          : a
      )
    )
    setSegmentRefreshKey((k) => k + 1)
  }

  useEffect(() => {
    if (!focusedId) {
      setRawFeatures([])
      setMatchedFeatures([])
      setQa(null)
      return
    }
    let cancelled = false
    setGeoLoading(true)
    setGeoError(null)

    const load = async () => {
      try {
        const needRaw = layer === 'raw' || layer === 'both'
        const needMatched = layer === 'matched' || layer === 'both'
        const [qaData, rawFc, matchedFc] = await Promise.all([
          fetchActivityQA(focusedId),
          needRaw ? fetchActivityGeojson(focusedId).catch(() => null) : Promise.resolve(null),
          needMatched
            ? fetchActivityGeojson(focusedId, 'matched').catch(() => null)
            : Promise.resolve(null),
        ])
        if (cancelled) return
        setQa(qaData)
        setRawFeatures(rawFc ? lineFeatures(rawFc, 'raw') : [])
        setMatchedFeatures(matchedFc ? lineFeatures(matchedFc, 'matched') : [])
      } catch (err) {
        if (!cancelled) setGeoError(err instanceof Error ? err.message : 'Load failed')
      } finally {
        if (!cancelled) setGeoLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [focusedId, layer])

  useEffect(() => {
    const params = new URLSearchParams()
    if (customerId) params.set('customer', customerId)
    if (focusedId) params.set('activity', focusedId)
    params.set('layer', layer)
    if (typeFilter) params.set('type', typeFilter)
    else params.delete('type')
    if (matchFilter) params.set('match', matchFilter)
    else params.delete('match')
    if (dateFrom) params.set('from', dateFrom)
    else params.delete('from')
    if (dateTo) params.set('to', dateTo)
    else params.delete('to')
    setSearchParams(params, { replace: true })
  }, [customerId, focusedId, layer, typeFilter, matchFilter, dateFrom, dateTo, setSearchParams])

  const activityTypes = useMemo(() => {
    const s = new Set<string>()
    for (const a of activities) if (a.type) s.add(a.type)
    return Array.from(s).sort()
  }, [activities])

  const focusedIndex = activities.findIndex((a) => a.id === focusedId)
  const focused = focusedIndex >= 0 ? activities[focusedIndex] : null

  const goPrev = useCallback(() => {
    setFocusedId((current) => {
      const idx = activities.findIndex((a) => a.id === current)
      if (idx > 0) return activities[idx - 1].id
      return current
    })
  }, [activities])

  const goNext = useCallback(() => {
    setFocusedId((current) => {
      const idx = activities.findIndex((a) => a.id === current)
      if (idx >= 0 && idx < activities.length - 1) return activities[idx + 1].id
      return current
    })
  }, [activities])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
      if (e.key === 'ArrowLeft' || e.key === 'k') goPrev()
      if (e.key === 'ArrowRight' || e.key === 'j') goNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [goPrev, goNext])

  const mapFeatures = useMemo(() => {
    const out: any[] = []
    if (layer === 'raw' || layer === 'both') out.push(...rawFeatures)
    if (layer === 'matched' || layer === 'both') out.push(...matchedFeatures)
    return out
  }, [layer, rawFeatures, matchedFeatures])

  const handleCustomerChange = (value: string) => {
    setCustomerId(value)
    setFocusedId('')
  }

  const handleMatch = async () => {
    if (!focusedId) return
    if (catalog && !catalog.catalog_complete) {
      setMatchError(true)
      setMatchMessage(
        `Catalog incomplete (${catalog.ready_tiles}/${catalog.required_tiles} tiles ready). Build pending tiles first.`
      )
      return
    }
    setMatching(true)
    setMatchMessage(null)
    setMatchError(false)
    try {
      const result = await matchActivities([focusedId])
      await applyMatchResult(focusedId, result.results?.[0])
    } catch (err) {
      setMatchError(true)
      setMatchMessage(err instanceof Error ? err.message : 'Match failed')
    } finally {
      setMatching(false)
    }
  }

  const handleMatchPending = async () => {
    if (!catalog?.catalog_complete) {
      setMatchError(true)
      setMatchMessage('Catalog must be complete before batch matching.')
      return
    }
    const pending = activities.filter((a) => a.match_status === 'pending').map((a) => a.id)
    if (pending.length === 0) {
      setMatchMessage('No pending activities in the current list.')
      setMatchError(false)
      return
    }
    const batch = pending.slice(0, 20)
    setBatchMatching(true)
    setMatchMessage(null)
    setMatchError(false)
    try {
      const result = await matchActivities(batch)
      setMatchMessage(
        `Batch: ${result.matched} matched, ${result.partial} partial, ${result.failed} failed`
      )
      setMatchError(result.failed > 0)
      if (focusedId) await applyMatchResult(focusedId, result.results.find((r) => r.activity_id === focusedId))
      setActivities((prev) =>
        prev.map((a) => {
          const row = result.results.find((r) => r.activity_id === a.id)
          if (!row || row.status === 'failed') return a
          return { ...a, match_status: row.status }
        })
      )
    } catch (err) {
      setMatchError(true)
      setMatchMessage(err instanceof Error ? err.message : 'Batch match failed')
    } finally {
      setBatchMatching(false)
    }
  }

  const copyActivityUrl = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopyMsg('Copied!')
      setTimeout(() => setCopyMsg(null), 2000)
    } catch {
      setCopyMsg('Copy failed')
    }
  }

  return (
    <div className="qa-workspace">
      <header className="qa-header">
        <div className="qa-header-left">
          <Link to="/" className="qa-home-link">
            Route Viewer
          </Link>
          <span className="qa-title">Activity QA</span>
        </div>
        <div className="qa-header-controls">
          <label className="field">
            Customer
            <select
              className="qa-select"
              value={customerId}
              onChange={(e) => handleCustomerChange(e.target.value)}
            >
              <option value="">— select —</option>
              {customers.map((c) => (
                <option key={c.customer_id} value={c.customer_id}>
                  {c.name && c.name !== c.customer_id
                    ? `${c.name} (${c.customer_id})`
                    : c.customer_id}{' '}
                  — {c.activity_count}
                </option>
              ))}
            </select>
          </label>
          <input
            className="qa-input"
            placeholder="or type customer id"
            value={customerId}
            onChange={(e) => handleCustomerChange(e.target.value)}
            style={{ width: 160 }}
          />
        </div>
      </header>

      <CatalogStrip
        customerId={customerId}
        coverage={catalog}
        loading={catalogLoading}
        error={catalogError}
        building={catalogBuilding}
        buildMessage={buildMessage}
        onRefresh={loadCatalog}
        onBuild={handleBuildTiles}
      />

      <div className="qa-body">
        <aside className="qa-sidebar panel">
          <div className="qa-sidebar-head">
            <strong>Activities</strong>
            <span className="muted">{activities.length}</span>
          </div>
          <div className="qa-filters">
            <select
              className="qa-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              <option value="">All types</option>
              {activityTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              className="qa-input"
              type="number"
              placeholder="Min m"
              value={minDist}
              onChange={(e) => setMinDist(e.target.value === '' ? '' : Number(e.target.value))}
            />
            <input
              className="qa-input"
              type="number"
              placeholder="Max m"
              value={maxDist}
              onChange={(e) => setMaxDist(e.target.value === '' ? '' : Number(e.target.value))}
            />
          </div>
          <div className="qa-filters qa-filters-row2">
            <select
              className="qa-select"
              value={matchFilter}
              onChange={(e) => setMatchFilter(e.target.value)}
            >
              <option value="">All match</option>
              <option value="pending">pending</option>
              <option value="matched">matched</option>
              <option value="partial">partial</option>
              <option value="failed">failed</option>
            </select>
            <label className="qa-filter-label">
              From
              <input
                className="qa-input"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </label>
            <label className="qa-filter-label">
              To
              <input
                className="qa-input"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </label>
          </div>
          {listError && <div className="qa-banner error">{listError}</div>}
          {listLoading && <div className="qa-banner">Loading list…</div>}
          <div className="qa-list">
            {activities.map((a) => {
              const active = a.id === focusedId
              return (
                <button
                  key={a.id}
                  type="button"
                  className={`qa-list-item${active ? ' active' : ''}`}
                  onClick={() => setFocusedId(a.id)}
                >
                  <div className="qa-list-row1">
                    <span className="qa-list-date">{formatDate(a.start)}</span>
                    <span className={`qa-badge qa-badge-${matchBadge(a.match_status)}`}>
                      {matchBadge(a.match_status)}
                    </span>
                  </div>
                  <div className="qa-list-name">{a.name || a.source_file || a.id}</div>
                  <div className="qa-list-meta">
                    <span>{a.type}</span>
                    <span>{formatKm(a.distance_m)}</span>
                  </div>
                </button>
              )
            })}
            {!listLoading && activities.length === 0 && customerId && (
              <div className="qa-empty">No activities for this customer.</div>
            )}
          </div>
        </aside>

        <main className="qa-main">
          <div className="qa-main-column">
          <div className="qa-toolbar">
            <div className="qa-nav">
              <button className="btn" type="button" onClick={goPrev} disabled={focusedIndex <= 0}>
                ← Prev
              </button>
              <span className="muted">
                {focusedIndex >= 0 ? `${focusedIndex + 1} / ${activities.length}` : '—'}
              </span>
              <button
                className="btn"
                type="button"
                onClick={goNext}
                disabled={focusedIndex < 0 || focusedIndex >= activities.length - 1}
              >
                Next →
              </button>
            </div>
            <div className="qa-layer-toggle" role="group" aria-label="Layer mode">
              {(['raw', 'both', 'matched'] as LayerMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={`btn${layer === mode ? ' btn-primary' : ''}`}
                  onClick={() => setLayer(mode)}
                >
                  {mode === 'both' ? 'Both' : mode === 'raw' ? 'Raw' : 'Matched'}
                </button>
              ))}
            </div>
            <button
              className="btn"
              type="button"
              disabled={!focusedId}
              onClick={() => setSegmentsOpen((v) => !v)}
            >
              {segmentsOpen ? 'Hide segments' : 'Segments'}
            </button>
            <button
              className="btn btn-primary"
              type="button"
              disabled={!focusedId || matching || batchMatching}
              onClick={handleMatch}
            >
              {matching ? 'Matching…' : qa?.match_status === 'matched' ? 'Re-match' : 'Match'}
            </button>
            <button
              className="btn"
              type="button"
              disabled={batchMatching || matching || !catalog?.catalog_complete}
              title={
                catalog?.catalog_complete
                  ? 'Match up to 20 pending activities in list'
                  : 'Complete catalog first'
              }
              onClick={handleMatchPending}
            >
              {batchMatching ? 'Batch…' : 'Match pending'}
            </button>
          </div>

          {focused && (
            <div className="qa-detail-bar">
              <div>
                <strong>{focused.name || focused.source_file}</strong>
                <span className="muted">
                  {' '}
                  · {formatDate(focused.start)} · {focused.type} · {formatKm(focused.distance_m)}
                  {qa?.match_confidence != null && (
                    <> · conf {(qa.match_confidence * 100).toFixed(0)}%</>
                  )}
                </span>
              </div>
              <div className="qa-detail-actions">
                <span className="muted mono">{focused.id}</span>
                <button type="button" className="btn btn-ghost" onClick={copyActivityUrl}>
                  Copy URL
                </button>
                {copyMsg && <span className="qa-copy-msg">{copyMsg}</span>}
              </div>
            </div>
          )}

          <div className="qa-map-wrap">
            {geoLoading && <div className="qa-map-overlay">Loading track…</div>}
            {geoError && <div className="qa-map-overlay warn">{geoError}</div>}
            <MapContainer center={[40.6, -75.5]} zoom={12} className="qa-map">
              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              {layer === 'raw' || layer === 'both' ? (
                rawFeatures.length > 0 && (
                  <GeoJSON
                    data={{ type: 'FeatureCollection', features: rawFeatures } as any}
                    pathOptions={{ color: '#ff5a1f', weight: 3, opacity: 0.85 }}
                  />
                )
              ) : null}
              {layer === 'matched' || layer === 'both' ? (
                matchedFeatures.length > 0 && (
                  <GeoJSON
                    data={{ type: 'FeatureCollection', features: matchedFeatures } as any}
                    pathOptions={{
                      color: '#1479ff',
                      weight: 4,
                      opacity: layer === 'both' ? 0.9 : 1,
                    }}
                  />
                )
              ) : null}
              <FitToFeatures features={mapFeatures} />
            </MapContainer>
          </div>

          <section className="qa-panel panel" aria-label="Match QA metrics">
            <div className="qa-panel-head">
              <strong>Match QA</strong>
              {matchMessage && (
                <span className={`qa-match-msg${matchError ? ' error' : ''}`}>{matchMessage}</span>
              )}
            </div>
            {!focusedId ? (
              <div className="qa-empty">Select an activity to inspect match quality.</div>
            ) : (
              <dl className="qa-metrics">
                <div>
                  <dt>Status</dt>
                  <dd>{qa?.match_status ?? focused?.match_status ?? '—'}</dd>
                </div>
                <div>
                  <dt>Raw distance</dt>
                  <dd>{formatKm(qa?.raw_distance_m ?? focused?.distance_m)}</dd>
                </div>
                <div>
                  <dt>Matched distance</dt>
                  <dd>{formatKm(qa?.matched_distance_m)}</dd>
                </div>
                <div>
                  <dt>Unique segments</dt>
                  <dd>{qa?.unique_segments ?? '—'}</dd>
                </div>
                <div>
                  <dt>Sequence length</dt>
                  <dd>{qa?.segment_sequence_length ?? '—'}</dd>
                </div>
                <div>
                  <dt>Low-support segs</dt>
                  <dd>{qa?.low_support_segment_count ?? '—'}</dd>
                </div>
                <div>
                  <dt>Suppressed spurs</dt>
                  <dd>{qa?.suppressed_spur_count ?? '—'}</dd>
                </div>
                <div>
                  <dt>Last matched</dt>
                  <dd>{formatDateTime(qa?.matched_at ?? focused?.matched_at)}</dd>
                </div>
              </dl>
            )}
            <div className="qa-panel-foot muted">
              Open Segments for ordered usage list · issue flags coming next
            </div>
          </section>
          </div>
          <SegmentDrawer
            activityId={focusedId || null}
            open={segmentsOpen}
            onClose={() => setSegmentsOpen(false)}
            refreshKey={segmentRefreshKey}
          />
        </main>
      </div>
    </div>
  )
}
