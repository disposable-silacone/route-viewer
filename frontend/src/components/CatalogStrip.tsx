import React, { useState } from 'react'
import { CatalogCoverage, CatalogBuildResult } from '../api/client'

type Props = {
  customerId: string
  coverage: CatalogCoverage | null
  loading: boolean
  error: string | null
  building: boolean
  buildMessage: string | null
  onRefresh: () => void
  onBuild: (limit: number, opts?: { statuses?: string[] }) => void
}

function statusLabel(status: string): string {
  return status
}

export const CatalogStrip: React.FC<Props> = ({
  customerId,
  coverage,
  loading,
  error,
  building,
  buildMessage,
  onRefresh,
  onBuild,
}) => {
  const [expanded, setExpanded] = useState(false)

  if (!customerId.trim()) {
    return (
      <div className="qa-catalog-strip muted">
        Select a customer to view OSM catalog coverage.
      </div>
    )
  }

  const required = coverage?.required_tiles ?? 0
  const ready = coverage?.ready_tiles ?? 0
  const pct = required > 0 ? Math.round((ready / required) * 100) : 0
  const counts = coverage?.counts_by_status ?? {}
  const pending = (counts.pending ?? 0) + (counts.missing ?? 0)
  const buildingN = counts.building ?? 0
  const failed = counts.failed ?? 0
  const buildable = failed + pending
  const complete = coverage?.catalog_complete ?? false

  return (
    <div className={`qa-catalog-strip panel${complete ? ' complete' : ''}`}>
      <div className="qa-catalog-strip-main">
        <div className="qa-catalog-strip-stats">
          <strong>Catalog</strong>
          {loading && <span className="muted"> loading…</span>}
          {!loading && coverage && (
            <>
              <span className="qa-catalog-ratio">
                {ready}/{required} ready
              </span>
              <div className="qa-catalog-bar" aria-hidden>
                <div className="qa-catalog-bar-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="muted qa-catalog-pills">
                {pending > 0 && <span className="qa-pill pending">{pending} pending</span>}
                {buildingN > 0 && <span className="qa-pill building">{buildingN} building</span>}
                {failed > 0 && <span className="qa-pill failed">{failed} failed</span>}
                {complete && <span className="qa-pill ready">complete</span>}
              </span>
            </>
          )}
          {error && <span className="qa-catalog-error">{error}</span>}
          {buildMessage && <span className="qa-build-msg">{buildMessage}</span>}
        </div>
        <div className="qa-catalog-strip-actions">
          <button type="button" className="btn btn-ghost" onClick={onRefresh} disabled={loading}>
            Refresh
          </button>
          {failed > 0 && (
            <button
              type="button"
              className="btn"
              disabled={building}
              title="Retry tiles that failed (often Overpass rate limits)"
              onClick={() => onBuild(Math.min(failed, 10), { statuses: ['failed'] })}
            >
              Retry failed ({failed})
            </button>
          )}
          <button
            type="button"
            className="btn"
            disabled={building || buildable === 0}
            onClick={() => onBuild(5)}
          >
            {building ? 'Building…' : 'Build 5 tiles'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={building || buildable === 0}
            onClick={() => onBuild(10)}
          >
            Build 10
          </button>
          {coverage && coverage.tiles.length > 0 && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? 'Hide tiles' : `Tiles (${coverage.tiles.length})`}
            </button>
          )}
        </div>
      </div>
      {expanded && coverage && (
        <div className="qa-catalog-tile-table-wrap">
          <table className="qa-catalog-tile-table">
            <thead>
              <tr>
                <th>Tile</th>
                <th>Status</th>
                <th>Segments</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {coverage.tiles.map((t) => (
                <tr key={t.tile_id}>
                  <td className="mono" title={t.tile_id}>
                    {t.lat_idx}_{t.lon_idx}
                  </td>
                  <td>
                    <span className={`qa-badge qa-badge-${statusLabel(t.status)}`}>
                      {t.status}
                    </span>
                  </td>
                  <td>{t.segment_count ?? '—'}</td>
                  <td className="qa-catalog-tile-error" title={t.error_message ?? undefined}>
                    {t.error_message ? t.error_message.slice(0, 80) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function formatBuildSummary(result: CatalogBuildResult): string {
  const ok = result.results.filter((r) => r.status === 'ready').length
  const failed = result.results.filter((r) => r.error)
  if (result.built === 0) return result.message ?? 'No tiles built'
  let msg = `Built ${result.built}: ${ok} ready`
  if (failed.length > 0) {
    msg += `, ${failed.length} failed`
    const rateLimited = failed.some((r) => r.error?.includes('429'))
    if (rateLimited) msg += ' (Overpass rate limit — wait and retry)'
    else if (failed[0]?.error) msg += ` — ${failed[0].error.slice(0, 100)}`
  }
  return msg
}
