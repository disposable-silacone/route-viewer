import React, { useState } from 'react'
import { Link } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export const Home: React.FC = () => {
  const [customerId, setCustomerId] = useState('amanda')
  const [sourceUri, setSourceUri] = useState('C:\\Users\\danie\\Downloads\\AmandaEarlyRawData\\SmallSet')
  const [result, setResult] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<string>('')
  const [tick, setTick] = useState<number>(0)
  React.useEffect(() => {
    if (!loading) return
    let cancelled = false
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/ingest/progress?t=${Date.now()}`, { cache: 'no-store', headers: { 'Cache-Control': 'no-cache' } as any })
        if (!res.ok) return
        const p = await res.json()
        if (cancelled) return
        const msg = `Scanned ${p.scanned}/${p.total} | Parsed ${p.parsed} (new ${p.new}, dup ${p.duplicates}, errors ${p.errors})`
        setProgress(msg)
        if (p.done) {
          clearInterval(id)
        }
      } catch {}
    }
    const id = setInterval(poll, 500)
    poll()
    return () => { cancelled = true; clearInterval(id) }
  }, [loading])

  async function handleIngest() {
    if (!sourceUri) return
    setLoading(true)
    setResult('')
    setProgress('Starting ingest...')
    try {
      const res = await fetch(`${API_BASE}/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sourceUri, customerId })
      })
      const json = await res.json()
      setResult(JSON.stringify(json, null, 2))
      setProgress('')
    } catch (err: any) {
      setResult(String(err))
      setProgress('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: '40px auto', fontFamily: 'system-ui, sans-serif' }}>
      <h1>Route Viewer</h1>
      <p>Enter a customer ID, a local path to a folder, .zip, or activity file (.gpx, .fit, .tcx, .gpx.gz, .fit.gz, .tcx.gz), then click Ingest.</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input
          style={{ width: 180, padding: 8 }}
          placeholder="customer id (e.g. amanda)"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
        />
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          style={{ flex: 1, padding: 8 }}
          placeholder="C:\\Users\\Dan\\Downloads\\garmin_export.zip"
          value={sourceUri}
          onChange={(e) => setSourceUri(e.target.value)}
        />
        <button onClick={handleIngest} disabled={loading || !sourceUri || !customerId}>
          {loading ? 'Ingesting…' : 'Ingest'}
        </button>
        <Link to="/map">
          <button>View on Map</button>
        </Link>
      </div>
      {progress && (
        <div style={{ marginTop: 8, color: '#1479ff' }}>{progress}</div>
      )}
      {result && (
        <pre style={{ marginTop: 16, background: '#111', color: '#eee', padding: 12, borderRadius: 6 }}>
          {result}
        </pre>
      )}
    </div>
  )
}


