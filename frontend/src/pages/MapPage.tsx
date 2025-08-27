import React, { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap, FeatureGroup } from 'react-leaflet'
// @ts-ignore - types may be incomplete
import { EditControl } from 'react-leaflet-draw'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

type Activity = {
  id: string
  name: string | null
  source_file?: string | null
  type: string
  bbox?: [number, number, number, number]
  distance_m?: number
  start?: string
  start_loc?: string
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

const FitToFeatures: React.FC<{ features: any[] }> = ({ features }) => {
  const map = useMap()
  const lastKeyRef = useRef<string | null>(null)
  useEffect(() => {
    if (!features.length) return
    const allCoords: [number, number][] = []
    for (const f of features) {
      if (f?.geometry?.type === 'LineString') {
        const coords = (f.geometry.coordinates || []) as [number, number][]
        for (let i = 0; i < coords.length; i++) allCoords.push(coords[i])
      }
    }
    if (!allCoords.length) return
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (let i = 0; i < allCoords.length; i++) {
      const [x, y] = allCoords[i]
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
    const bounds: [[number, number], [number, number]] = [
      [minY, minX],
      [maxY, maxX]
    ]
    const key = bounds.flat().join(',')
    if (lastKeyRef.current === key) return
    lastKeyRef.current = key
    // Fit once per unique bounds to avoid recursive re-renders
    map.fitBounds(bounds, { padding: [20, 20] })
  }, [features, map])
  return null
}

const MapClickInspector: React.FC<{ enabled: boolean }> = ({ enabled }) => {
  const map = useMap()
  useEffect(() => {
    if (!enabled) return
    const handler = async (e: any) => {
      const { lat, lng } = e.latlng
      try {
        const url = `${API_BASE}/inspect?lat=${lat}&lon=${lng}&profile=bike`
        const res = await fetch(url)
        if (!res.ok) return
        const fc = await res.json()
        const layer = L.geoJSON(fc as any, {
          pointToLayer: (f: any, latlng: any) => {
            const kind = f?.properties?.kind
            if (kind === 'center') return L.circleMarker(latlng, { radius: 5, color: '#000', fillColor: '#fff', fillOpacity: 1, weight: 2 })
            if (kind === 'snapped_center') return L.circleMarker(latlng, { radius: 5, color: '#0a0', fillColor: '#0f0', fillOpacity: 0.9, weight: 2 })
            return L.circleMarker(latlng, { radius: 3, color: '#333', fillColor: '#ffa500', fillOpacity: 0.9, weight: 1 })
          },
          style: (f: any) => ({ color: f?.properties?.kind === 'edge' ? '#8a2be2' : '#ffa500', weight: 2 })
        }).addTo(map)
        setTimeout(() => { map.removeLayer(layer) }, 5000)
      } catch {}
    }
    map.on('click', handler)
    return () => { map.off('click', handler) }
  }, [enabled, map])
  return null
}

export const MapPage: React.FC = () => {
  const [activities, setActivities] = useState<Activity[]>([])
  const [rawFeatures, setRawFeatures] = useState<any[]>([])
  const [matchedFeatures, setMatchedFeatures] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [type, setType] = useState<string>('')
  const [minDist, setMinDist] = useState<number | ''>('')
  const [maxDist, setMaxDist] = useState<number | ''>('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const drawGroupRef = useRef<L.FeatureGroup | null>(null)
  const [drawReady, setDrawReady] = useState(false)
  useEffect(() => {
    if (drawGroupRef.current && !drawReady) setDrawReady(true)
  }, [drawGroupRef.current, drawReady])
  const [showRaw, setShowRaw] = useState(true)
  const [showMatched, setShowMatched] = useState(false)
  const [showBase, setShowBase] = useState(true)
  const [rawSelectedOnly, setRawSelectedOnly] = useState(false)
  const [matchedSelectedOnly, setMatchedSelectedOnly] = useState(false)
  const [gpsAcc, setGpsAcc] = useState<number | ''>('')
  const [showSnapDebug, setShowSnapDebug] = useState(false)
  const [allTypes, setAllTypes] = useState<string[]>([])
  useEffect(() => {
    let cancelled = false
    async function loadAllTypes() {
      try {
        const res = await fetch(`${API_BASE}/activities`)
        const acts: Activity[] = await res.json()
        if (cancelled) return
        const set = new Set<string>()
        for (const a of acts) if (a.type) set.add(a.type)
        setAllTypes(Array.from(set).sort())
      } catch {}
    }
    loadAllTypes()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const params = new URLSearchParams()
        if (type) params.set('type', type)
        if (minDist !== '') params.set('minDist', String(minDist))
        if (maxDist !== '') params.set('maxDist', String(maxDist))
        const q = params.toString()
        const res = await fetch(`${API_BASE}/activities${q ? `?${q}` : ''}`)
        const acts: Activity[] = await res.json()
        if (cancelled) return
        const startLoc: Record<string,string> = {}
        const raws: any[] = []
        for (const a of acts) {
          const gjRes = await fetch(`${API_BASE}/activities/${a.id}/geojson`)
          if (!gjRes.ok) continue
          const fc = await gjRes.json()
          if (fc?.features?.length) raws.push(...fc.features)
          try {
            const coords = fc?.features?.[0]?.geometry?.coordinates as [number,number][] | undefined
            if (coords && coords.length) {
              const [lon, lat] = coords[0]
              startLoc[a.id] = `${lat.toFixed(5)}, ${lon.toFixed(5)}`
            }
          } catch {}
        }
        if (!cancelled) {
          setRawFeatures(raws)
          setActivities(acts.map(a => ({...a, start_loc: startLoc[a.id] || ''})))
        }
        if (showMatched) {
          const mats: any[] = []
          for (const a of acts) {
            const mRes = await fetch(`${API_BASE}/activities/${a.id}/geojson?variant=matched`)
            if (!mRes.ok) continue
            const mfc = await mRes.json()
            if (mfc?.features?.length) mats.push(...mfc.features)
          }
          if (!cancelled) setMatchedFeatures(mats)
        } else if (!cancelled) {
          setMatchedFeatures([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [type, minDist, maxDist, showMatched])
  useEffect(() => {
    if (type && !allTypes.includes(type)) setType('')
  }, [allTypes])
  const rawToRender = useMemo(() => {
    if (!showRaw) return [] as any[]
    if (!rawSelectedOnly) return rawFeatures
    return rawFeatures.filter(f => selectedIds.has(f?.properties?.id))
  }, [showRaw, rawSelectedOnly, rawFeatures, selectedIds])

  const matchedToRender = useMemo(() => {
    if (!showMatched) return [] as any[]
    if (!matchedSelectedOnly) return matchedFeatures
    return matchedFeatures.filter(f => selectedIds.has(f?.properties?.id))
  }, [showMatched, matchedSelectedOnly, matchedFeatures, selectedIds])

  const shownForFit = useMemo(() => {
    return [...rawToRender, ...matchedToRender]
  }, [rawToRender, matchedToRender])

  return (
    <div style={{ height: '100vh', width: '100vw' }}>
      {/* unified control panel + inspector */}
      <MapContainer center={[0, 0]} zoom={2} style={{ height: '100%', width: '100%' }}>
        {showBase && (
          <TileLayer url={import.meta.env.VITE_TILE_URL ?? 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'} />
        )}
        {showRaw && rawToRender.length > 0 && (
          <GeoJSON data={{ type:'FeatureCollection', features: rawToRender } as any} style={{ color: '#ff5a1f', weight: 2 }} />
        )}
        {showMatched && matchedToRender.length > 0 && (
          <GeoJSON
            data={{ type:'FeatureCollection', features: matchedToRender } as any}
            style={{ color: '#1479ff', weight: 3 }}
            onEachFeature={(feature: any, layer: any) => {
              const details = feature?.properties?.details || {}
              // Summarize road classes if available
              const rc: Array<[number, number, string]> = details.road_class || []
              const way: Array<[number, number, number]> = details.osm_way_id || []
              const counts: Record<string, number> = {}
              for (let i = 0; i < rc.length; i++) {
                const v = rc[i][2]
                counts[v] = (counts[v] || 0) + (rc[i][1] - rc[i][0])
              }
              const top = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,5)
              const wayIds = way.slice(0,5).map(w => String(w[2]))
              const html = `
                <div style="font:12px system-ui">
                  <div style="font-weight:700;margin-bottom:4px">Matched details</div>
                  ${top.length ? `<div><b>Top road_class:</b> ${top.map(([k])=>k).join(', ')}</div>` : ''}
                  ${wayIds.length ? `<div><b>OSM way ids (sample):</b> ${wayIds.join(', ')}</div>` : ''}
                  ${(!top.length && !wayIds.length) ? '<div>No details available. Re-run map match to include debug details.</div>' : ''}
                </div>`
              layer.bindPopup(html)
            }}
          />
        )}
        {showSnapDebug && showMatched && matchedToRender.length > 0 && (
          <GeoJSON
            data={{ type:'FeatureCollection', features: matchedToRender.flatMap((f:any)=>{
              const snapped = f?.properties?.snapped_waypoints
              if (!snapped) return []
              const coords = snapped?.coordinates || []
              return coords.map((c:[number,number])=>({
                type:'Feature',
                properties:{},
                geometry:{ type:'Point', coordinates: c }
              }))
            }) } as any}
            pointToLayer={(feature: any, latlng: any) => L.circleMarker(latlng, { radius: 3, color: '#111', fillColor: '#0ff', fillOpacity: 0.9, weight: 1 })}
          />
        )}
        <FeatureGroup ref={drawGroupRef as any}>
          {drawReady && (
          <EditControl
            position="topright"
            draw={{
              marker: false,
              polyline: false,
              circle: false,
              circlemarker: false,
              polygon: false,
              rectangle: { showArea: false }
            }}
            edit={{ featureGroup: drawGroupRef.current as any, edit: false, remove: true }}
            onCreated={(e: any) => {
              const layer = e.layer as L.Rectangle
              const bounds = layer.getBounds()
              const selected = new Set<string>(selectedIds)
              const candidates = [...rawFeatures, ...matchedFeatures]
              for (const f of candidates) {
                if (f?.geometry?.type !== 'LineString') continue
                const coords = (f.geometry.coordinates || []) as [number, number][]
                for (let i = 0; i < coords.length; i++) {
                  const [x, y] = coords[i]
                  const latlng = L.latLng(y, x)
                  if (bounds.contains(latlng)) {
                    const id = f?.properties?.id
                    if (id) selected.add(id)
                    break
                  }
                }
              }
              setSelectedIds(selected)
            }}
          />)}
        </FeatureGroup>
        <FitToFeatures features={shownForFit} />
      {/* Map click inspector: show candidate edges around clicked point */}
      <MapClickInspector enabled={showSnapDebug} />
      </MapContainer>
      {loading && (
        <div style={{ position: 'absolute', top: 12, left: 12, background: '#000a', color: '#fff', padding: '6px 10px', borderRadius: 4 }}>
          Loading…
        </div>
      )}
      {/* Unified control + list drawer */}
      <SelectionOverlay
        openByDefault={false}
        activities={activities}
        selectedIds={selectedIds}
        onToggleId={(id) => {
          const next = new Set(selectedIds)
          if (next.has(id)) next.delete(id); else next.add(id)
          setSelectedIds(next)
        }}
        onSetSelectedIds={(next) => setSelectedIds(new Set(next))}
        availableTypes={allTypes}
        controls={{
          showRaw, setShowRaw,
          showMatched, setShowMatched,
          showBase, setShowBase,
          rawSelectedOnly, setRawSelectedOnly,
          matchedSelectedOnly, setMatchedSelectedOnly,
          type, setType,
          minDist, setMinDist,
          maxDist, setMaxDist,
          gpsAcc, setGpsAcc,
          showSnapDebug, setShowSnapDebug,
          onExport: async () => {
            if (selectedIds.size === 0) return
            const ids = Array.from(selectedIds)
            const res = await fetch(`${API_BASE}/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, format: 'geojson' }) })
            const blob = await res.blob()
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = 'export.geojson'
            a.click()
            URL.revokeObjectURL(url)
          },
          onMatch: async () => {
            if (selectedIds.size === 0) return
            const ids = Array.from(selectedIds)
            try {
              const body: any = { ids, profile: (type==='run'||type==='walk') ? 'foot' : 'bike' }
              if (gpsAcc !== '') body.gpsAccuracy = gpsAcc
              const res = await fetch(`${API_BASE}/mapmatch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
              const js = await res.json()
              alert(`Map-matched: ${js.matched} ok, ${js.failed} failed`)
              const feats: any[] = []
              for (const id of ids) {
                const gjRes = await fetch(`${API_BASE}/activities/${id}/geojson?variant=matched`)
                if (gjRes.ok) {
                  const fc = await gjRes.json()
                  if (fc?.features?.length) feats.push(...fc.features)
                }
              }
              if (feats.length) { setMatchedFeatures(feats); setShowMatched(true) }
            } catch (e) { console.error(e) }
          },
          onClear: () => setSelectedIds(new Set()),
          onRectangle: () => {
            const btn = document.querySelector('.leaflet-draw-draw-rectangle') as HTMLElement | null
            if (btn) btn.click()
          }
        }}
      />
    </div>
  )
}

type Controls = {
  showRaw: boolean; setShowRaw: (v:boolean)=>void
  showMatched: boolean; setShowMatched: (v:boolean)=>void
  showBase: boolean; setShowBase: (v:boolean)=>void
  rawSelectedOnly: boolean; setRawSelectedOnly: (v:boolean)=>void
  matchedSelectedOnly: boolean; setMatchedSelectedOnly: (v:boolean)=>void
  type: string; setType: (v:string)=>void
  minDist: number|''; setMinDist: (v:number|'')=>void
  maxDist: number|''; setMaxDist: (v:number|'')=>void
  gpsAcc: number|''; setGpsAcc: (v:number|'')=>void
  showSnapDebug: boolean; setShowSnapDebug: (v:boolean)=>void
  onExport: ()=>Promise<void>
  onMatch: ()=>Promise<void>
  onClear: ()=>void
  onRectangle: ()=>void
}

const SelectionOverlay: React.FC<{ openByDefault?: boolean, activities: Activity[], selectedIds: Set<string>, onToggleId: (id: string) => void, onSetSelectedIds: (ids: string[]) => void, availableTypes: string[], controls: Controls }> = ({ openByDefault = false, activities, selectedIds, onToggleId, onSetSelectedIds, availableTypes, controls }) => {
  const [open, setOpen] = useState(openByDefault)
  const [sortKey, setSortKey] = useState<'name' | 'start' | 'date' | 'type' | 'distance'>('date')
  const [sortAsc, setSortAsc] = useState<boolean>(true)
  const sorted = useMemo(() => {
    const copy = [...activities]
    const dir = sortAsc ? 1 : -1
    const by = (k: typeof sortKey, a: Activity, b: Activity) => {
      if (k === 'name') return ((a.name || '') as string).localeCompare(b.name || '')
      if (k === 'start') return ((a.start_loc || '') as string).localeCompare(b.start_loc || '')
      if (k === 'type') return (a.type || '').localeCompare(b.type || '')
      if (k === 'distance') return (a.distance_m || 0) - (b.distance_m || 0)
      const ad = a.start ? Date.parse(a.start) : 0
      const bd = b.start ? Date.parse(b.start) : 0
      return ad - bd
    }
    copy.sort((a, b) => dir * by(sortKey, a, b))
    return copy
  }, [activities, sortKey, sortAsc])

  const allChecked = sorted.length > 0 && sorted.every(a => selectedIds.has(a.id))
  const toggleSort = (k: typeof sortKey) => {
    if (k === sortKey) setSortAsc(!sortAsc); else { setSortKey(k); setSortAsc(true) }
  }
  return (
    <div style={{ position: 'absolute', right: 10, top: 60, zIndex: 1000 }}>
      <button className="btn" onClick={() => setOpen(!open)}>{open ? 'Hide Panel' : 'Show Panel'}</button>
      {open && (
        <div className="panel drawer" style={{ marginTop: 8, display: 'flex', flexDirection: 'column' }}>
          <div className="drawer-header">
            <span style={{ fontWeight: 700 }}>Routes</span>
            <span className="muted" style={{ marginLeft: 'auto' }}>{selectedIds.size} selected</span>
          </div>
          {/* unified controls */}
          <div className="toolbar" style={{ borderBottom: '1px solid var(--border)' }}>
            <label className="field"><input type='checkbox' checked={controls.showRaw} onChange={e=>controls.setShowRaw(e.target.checked)} /> Raw</label>
            <label className="field"><input type='checkbox' checked={controls.showMatched} onChange={e=>controls.setShowMatched(e.target.checked)} /> Snapped</label>
            <label className="field"><input type='checkbox' checked={controls.showBase} onChange={e=>controls.setShowBase(e.target.checked)} /> Basemap</label>
            <label className="field"><input type='checkbox' checked={controls.rawSelectedOnly} onChange={e=>controls.setRawSelectedOnly(e.target.checked)} /> Raw: Selected only</label>
            <label className="field"><input type='checkbox' checked={controls.matchedSelectedOnly} onChange={e=>controls.setMatchedSelectedOnly(e.target.checked)} /> Snapped: Selected only</label>
            <select className="field" value={controls.type} onChange={(e)=>controls.setType(e.target.value)}>
              <option value=''>All types</option>
              {availableTypes.map((t: string) => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase()+t.slice(1)}</option>
              ))}
            </select>
            <input className="field" type='number' placeholder='Min m' value={controls.minDist as any} onChange={(e)=>controls.setMinDist(e.target.value===''?'':Number(e.target.value))} style={{ width:100 }} />
            <input className="field" type='number' placeholder='Max m' value={controls.maxDist as any} onChange={(e)=>controls.setMaxDist(e.target.value===''?'':Number(e.target.value))} style={{ width:100 }} />
            <input className="field" type='number' placeholder='GPS acc m' value={controls.gpsAcc as any} onChange={(e)=>controls.setGpsAcc(e.target.value===''?'':Number(e.target.value))} style={{ width:110 }} />
            <label className="field"><input type='checkbox' checked={controls.showSnapDebug} onChange={(e)=>controls.setShowSnapDebug(e.target.checked)} /> Show snapped points</label>
            <button className="btn" onClick={controls.onExport}>Export</button>
            <button className="btn btn-primary" onClick={controls.onMatch}>Map Match</button>
            <button className="btn btn-ghost" onClick={controls.onClear}>Clear</button>
            <button className="btn" onClick={controls.onRectangle}>Rectangle</button>
          </div>
          <div className="row" style={{ fontWeight: 600, borderBottom: '1px solid var(--border)', gridTemplateColumns: '32px 1fr 160px 120px 80px 90px' }}>
            <input type='checkbox' checked={allChecked} onChange={(e) => {
              if (e.target.checked) onSetSelectedIds(sorted.map(a => a.id))
              else onSetSelectedIds([])
            }} />
            <button className="btn btn-ghost" onClick={() => toggleSort('name')}>Name {sortKey==='name' ? (sortAsc?'▲':'▼') : ''}</button>
            <button className="btn btn-ghost" onClick={() => toggleSort('start')}>Start {sortKey==='start' ? (sortAsc?'▲':'▼') : ''}</button>
            <button className="btn btn-ghost" onClick={() => toggleSort('date')}>Date {sortKey==='date' ? (sortAsc?'▲':'▼') : ''}</button>
            <button className="btn btn-ghost" onClick={() => toggleSort('type')}>Type {sortKey==='type' ? (sortAsc?'▲':'▼') : ''}</button>
            <button className="btn btn-ghost" onClick={() => toggleSort('distance')}>Distance {sortKey==='distance' ? (sortAsc?'▲':'▼') : ''}</button>
          </div>
          <div className="drawer-body">
            {sorted.map((a) => {
              const dateStr = a.start ? new Date(a.start).toLocaleDateString() : ''
              const checked = selectedIds.has(a.id)
              return (
                <label key={a.id} className="row" style={{ background: checked ? '#f7fbff' : 'transparent', gridTemplateColumns: '32px 1fr 160px 120px 80px 90px' }}>
                  <input type='checkbox' checked={checked} onChange={() => onToggleId(a.id)} />
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {a.name || a.id}
                    {a.source_file ? ` — ${a.source_file}` : ''}
                  </span>
                  <span className="muted">{a.start_loc || ''}</span>
                  <span>{dateStr}</span>
                  <span>{a.type}</span>
                  <span style={{ textAlign: 'right' }}>{a.distance_m}</span>
                </label>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}


