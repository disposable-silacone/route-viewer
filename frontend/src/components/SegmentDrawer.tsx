import React, { useEffect, useState } from 'react'
import {
  ActivitySegments,
  SegmentUsageRow,
  fetchActivitySegments,
  formatKm,
} from '../api/client'

type Props = {
  activityId: string | null
  open: boolean
  onClose: () => void
  refreshKey?: number
}

function shortSegmentId(id: string): string {
  if (id.length <= 28) return id
  return `${id.slice(0, 14)}…${id.slice(-10)}`
}

export const SegmentDrawer: React.FC<Props> = ({
  activityId,
  open,
  onClose,
  refreshKey = 0,
}) => {
  const [data, setData] = useState<ActivitySegments | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !activityId) {
      setData(null)
      setSelectedId(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchActivitySegments(activityId)
      .then((rows) => {
        if (!cancelled) setData(rows)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activityId, open, refreshKey])

  if (!open) return null

  const segments = data?.segments ?? []

  return (
    <aside className="qa-segment-drawer panel" aria-label="Segment usage">
      <div className="qa-segment-drawer-head">
        <div>
          <strong>Segments</strong>
          {data && (
            <span className="muted" style={{ marginLeft: 8 }}>
              {data.segment_count} unique
            </span>
          )}
        </div>
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          Close
        </button>
      </div>
      {loading && <div className="qa-banner">Loading segments…</div>}
      {error && <div className="qa-banner error">{error}</div>}
      {!loading && !error && segments.length === 0 && (
        <div className="qa-empty">
          No segment usage yet. Run Match on this activity first.
        </div>
      )}
      {segments.length > 0 && (
        <div className="qa-segment-table-wrap">
          <table className="qa-segment-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Segment</th>
                <th>Len</th>
                <th>×</th>
                <th title="Issue flags — coming soon">Flag</th>
              </tr>
            </thead>
            <tbody>
              {segments.map((row: SegmentUsageRow, idx: number) => {
                const active = row.segment_id === selectedId
                return (
                  <tr
                    key={row.segment_id}
                    className={active ? 'selected' : undefined}
                    onClick={() =>
                      setSelectedId(active ? null : row.segment_id)
                    }
                    title={row.segment_id}
                  >
                    <td>{row.first_seen_order ?? idx + 1}</td>
                    <td className="mono">{shortSegmentId(row.segment_id)}</td>
                    <td>{formatKm(row.matched_length_m)}</td>
                    <td>{row.traversals}</td>
                    <td className="muted">—</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="qa-panel-foot muted">
        Row select reserved for map highlight & issue flags.
      </div>
    </aside>
  )
}
