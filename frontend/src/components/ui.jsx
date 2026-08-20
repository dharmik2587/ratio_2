import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, CheckCircle2, Hexagon, Info, ShieldAlert, UploadCloud, X } from 'lucide-react'

export const pct = (n, d = 1) => `${Number(n || 0).toFixed(d)}%`

export function Header({ page, onPage, offline }) {
  const items = [
    ['analysis', 'ANALYSIS'],
    ['benchmarks', 'BENCHMARKS'],
    ['governance', 'MODEL GOVERNANCE'],
    ['demo', 'SIH DEMO'],
  ]
  return <header>
    <div className="brand"><div className="mark"><Hexagon size={24} /><span>R</span></div>
      <div><b>RATIO</b><small>EVIDENCE VERIFICATION CONSOLE</small></div></div>
    <nav>{items.map(([id, label]) =>
      <span key={id} className={page === id ? 'active' : ''} onClick={() => onPage(id)}>{label}</span>)}
    </nav>
    <div className="system"><i className={offline ? 'off' : ''} /> {offline ? 'CLAUDE OFFLINE' : 'SYSTEM NOMINAL'} <span>PHASE 3</span></div>
  </header>
}

export function Stepper({ active }) {
  const items = ['INPUT PAIR', 'VISUAL EVIDENCE', 'TERRAIN EVIDENCE', 'MISSION DECISION', 'EXPORT']
  return <div className="stepper">{items.map((x, i) =>
    <div className={i <= active ? 'on' : ''} key={x}><b>{String(i + 1).padStart(2, '0')}</b><span>{x}</span>{i < items.length - 1 && <em />}</div>)}
  </div>
}

export function FileDrop({ title, kicker, file, onChange }) {
  const [drag, setDrag] = useState(false)
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  return <div className={`file-card ${drag ? 'drag' : ''} ${file ? 'loaded' : ''}`}
    onDragOver={e => { e.preventDefault(); setDrag(true) }}
    onDragLeave={() => setDrag(false)}
    onDrop={e => { e.preventDefault(); setDrag(false); onChange(e.dataTransfer.files[0]) }}>
    <div className="file-head"><span>{kicker}</span>{file && <button onClick={() => onChange(null)}><X size={14} /></button>}</div>
    {file ? <>
      <img src={preview} />
      <div className="file-meta"><CheckCircle2 size={16} />
        <div><b>{file.name}</b><span>{(file.size / 1024).toFixed(1)} KB · READY</span></div></div>
    </> : <label><input type="file" accept="image/png,image/jpeg,image/tiff,image/webp"
        onChange={e => onChange(e.target.files[0])} />
        <UploadCloud size={28} /><b>{title}</b><span>Drop a PNG, JPEG, TIFF or WebP</span><small>MAXIMUM 20 MB</small></label>}
  </div>
}

export function Metric({ label, value, accent, detail }) {
  return <div className="metric"><small>{label}</small><strong className={accent || ''}>{value}</strong><span>{detail}</span></div>
}

export function ImagePanel({ label, tag, src, children }) {
  return <section className="image-panel">
    <div className="panel-title"><div><small>{tag}</small><b>{label}</b></div>{children}</div>
    <div className="canvas"><img src={src} /><span className="coords">PIXEL SPACE · TOP-LEFT ORIGIN</span></div>
  </section>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="error"><ShieldAlert size={18} />{String(error)}</div>
}

export function Notice({ children, tone = 'warn' }) {
  return <div className={`notice ${tone}`}><Info size={17} />{children}</div>
}

export function DataTag({ classification }) {
  const map = {
    REAL: 'real', 'REAL LUNAR-DERIVED DEMONSTRATION DATA': 'real',
    SYNTHETIC_DEMO: 'synthetic', SYNTHETIC_BENCHMARK: 'synthetic', SYNTHETIC: 'synthetic',
    TEST_DATA: 'test', DEMO: 'test', MIXED: 'mixed',
  }
  return <b className={map[classification] || 'test'}>{classification}</b>
}

export function BusyButton({ busy, idle, busyText, disabled, onClick, className = 'primary' }) {
  return <button className={className} disabled={disabled || busy} onClick={onClick}>
    {busy ? <>{busyText}</> : <>{idle}{!busy && <ArrowRight size={18} />}</>}</button>
}
