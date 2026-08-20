import { useEffect, useState } from 'react'
import { Activity, ArrowRight, CheckCircle2, Download, FlaskConical, Info, Layers3,
         RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react'
import { attachReference, createAnalysis, getAnalysis, getDatasets, getEvidenceReport,
         getPassport, requestExport, requestExplanation, uploadImage, verifyPhysical } from '../api'
import { BusyButton, DataTag, ErrorBox, FileDrop, ImagePanel, Metric, Notice, Stepper, pct } from '../components/ui'
import { AlignmentModal } from '../components/AlignmentModal'
import { EvidenceChain, EvidenceQuality } from '../components/EvidenceChain'
import { Navigator } from '../components/Navigator'

const MISSIONS = [
  ['SCIENTIFIC_VISUALIZATION', 'Scientific visualization'],
  ['MAPPING', 'Mapping'],
  ['HAZARD_ASSESSMENT', 'Hazard assessment'],
  ['ROUTE_PLANNING', 'Route planning'],
]

function UploadView({ onComplete, mission, onMission }) {
  const [original, setOriginal] = useState(null)
  const [enhanced, setEnhanced] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function verify() {
    setBusy(true); setError('')
    try {
      const [a, b] = await Promise.all([uploadImage(original), uploadImage(enhanced)])
      const made = await createAnalysis(a.id, b.id)
      const result = await getAnalysis(made.id)
      onComplete(result, { original: URL.createObjectURL(original), enhanced: URL.createObjectURL(enhanced) })
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <main className="upload-page">
    <div className="eyebrow"><FlaskConical size={14} /> NEW VERIFICATION RUN</div>
    <h1>Inspect what the enhancement <em>changed.</em></h1>
    <p className="lead">Compare an original sensor image with its enhanced counterpart. RATIO measures visual
      discrepancies, then demands independent terrain evidence before any mission decision.</p>
    <Stepper active={0} />
    <div className="pair">
      <FileDrop kicker="A · SENSOR EVIDENCE" title="Upload original image" file={original} onChange={setOriginal} />
      <div className="flow"><ArrowRight /></div>
      <FileDrop kicker="B · PROCESSED OUTPUT" title="Upload enhanced image" file={enhanced} onChange={setEnhanced} />
    </div>
    <ErrorBox error={error} />
    <div className="action-row">
      <div className="scope"><Info size={16} />
        <span><b>Stage 1 scope</b> Visual-change evidence only. Physical verification runs in the next step.</span></div>
      <label className="mission-select"><span>MISSION PROFILE</span>
        <select value={mission} onChange={e => onMission(e.target.value)}>
          {MISSIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select></label>
      <BusyButton className="primary" busy={busy} idle="VERIFY IMAGE PAIR" busyText="ANALYZING EVIDENCE…"
        disabled={!original || !enhanced} onClick={verify} />
    </div>
  </main>
}

function ComparisonGate({ data, onReset }) {
  const incompatible = data.comparison_status === 'INCOMPARABLE_IMAGES'
  const review = data.comparison_status === 'REVIEW_COMPARABILITY'
  const reason = data.compatibility.reason_code || (review ? 'UNCERTAIN_VISUAL_CORRESPONDENCE' : 'LOW_VISUAL_CORRESPONDENCE')
  return <main className="page">
    <div className="page-head">
      <div>
        <div className="eyebrow"><ShieldAlert size={14} /> COMPARISON GATE · {data.id.slice(0, 8).toUpperCase()}</div>
        <h1>{incompatible ? 'RATIO stopped analysis here.' : 'Image correspondence needs review.'}</h1>
        <p className="lead">RATIO does not assume that two images of the Moon represent the same observation.
          It first establishes visual correspondence; otherwise any difference map would be scientifically meaningless.</p>
      </div>
      <button className="secondary" onClick={onReset}><RefreshCw size={15} /> RETRY WITH BETTER INPUTS</button>
    </div>
    <div className={`comparison-gate ${incompatible ? 'blocked' : 'review'}`}>
      <div className="gate-status">
        <ShieldAlert size={26} />
        <div><b>COMPARISON GATE</b><small>STATUS</small></div>
        <strong>{incompatible ? 'LOW VISUAL CORRESPONDENCE' : 'CORRESPONDENCE UNCERTAIN'}</strong>
      </div>
      <div className="gate-metrics">
        <Metric label="COMPATIBILITY" value={data.compatibility.score.toFixed(3)} accent="amber" detail="visual correspondence estimate" />
        <Metric label="STATUS" value={data.compatibility.status} detail={reason} />
        <Metric label="REASON CODE" value={reason} detail="deterministic gate output" />
      </div>
      <div className="gate-narrative">
        <p>{incompatible
          ? 'RATIO stopped analysis because the two inputs could not be reliably treated as corresponding observations.'
          : 'RATIO could not establish sufficiently strong visual correspondence. Cropped or differently rendered scenes may require stronger registration capabilities.'}</p>
        <ul>
          <li className="stop">No visual-change metrics were generated.</li>
          <li className="stop">No terrain verification was attempted.</li>
          <li className="stop">No mission-policy decision was produced.</li>
        </ul>
      </div>
      <div className="gate-guidance">
        <b>Try one of these</b>
        <span>· Use an enhanced version derived from the original image</span>
        <span>· Use the same scene with a different resolution</span>
        <span>· Use a georegistered image pair</span>
      </div>
    </div>
    <div className="notice"><span><b>Scientific boundary:</b> compatibility estimates visual correspondence only.
      It does not prove semantic identity or geographic co-location.</span><strong>{incompatible ? 'NO CHANGE METRICS' : 'REVIEW REQUIRED'}</strong></div>
    <footer><span>RATIO 2.0 · COMPARISON GATE REPORT</span><span>RECORD SHA-256 {data.record_sha256.slice(0, 16)}…</span></footer>
  </main>
}

function Phase2Console({ analysis, previews, initialMission, offline }) {
  const [datasets, setDatasets] = useState([])
  const [datasetId, setDatasetId] = useState('')
  const [mission, setMission] = useState(initialMission)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [manual, setManual] = useState(false)
  const [registration, setRegistration] = useState(null)
  const [terrainView, setTerrainView] = useState('dem')
  const [featureId, setFeatureId] = useState(null)
  const [showNavigator, setShowNavigator] = useState(false)
  const [explanation, setExplanation] = useState(null)

  useEffect(() => {
    getDatasets().then(x => {
      setDatasets(x.datasets)
      if (x.datasets.length) setDatasetId(x.datasets[0].id)
    }).catch(e => setError(e.message))
  }, [])
  const dataset = datasets.find(x => x.id === datasetId)
  const feature = result?.features?.find(x => x.feature_id === (featureId || result.features[0]?.feature_id))

  async function run() {
    setBusy(true); setError(''); setResult(null)
    try {
      if (analysis.features.length) {
        if (!datasetId) throw new Error('Select an independent terrain reference.')
        // Do not re-attach after manual alignment: attaching rewrites the
        // registration record and would discard the 3+1 point fit.
        if (!registration) {
          const attached = await attachReference(analysis.id, datasetId)
          setRegistration(attached.registration)
        }
      }
      const verified = await verifyPhysical(analysis.id, mission)
      setResult(verified)
      setFeatureId(verified.features[0]?.feature_id || null)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function openManual() {
    setError('')
    try {
      const attached = await attachReference(analysis.id, datasetId)
      setRegistration(attached.registration)
      setManual(true)
    } catch (e) { setError(e.message) }
  }
  async function download(kind) {
    try {
      const body = kind === 'passport' ? await getPassport(analysis.id)
        : kind === 'evidence' ? await getEvidenceReport(analysis.id)
        : await requestExport(analysis.id)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' }))
      a.download = `ratio-${kind}-${analysis.id}.json`
      a.click(); URL.revokeObjectURL(a.href)
    } catch (e) { setError(e.message) }
  }
  async function explain() {
    setError('')
    try { setExplanation(await requestExplanation(analysis.id, feature?.feature_id)) }
    catch (e) { setError(e.message) }
  }

  return <section className="phase2">
    <div className="phase2-head">
      <div><small>PHASE 2 + 3 · INDEPENDENT TERRAIN VERIFICATION</small>
        <h2>Make visual information earn mission trust.</h2></div>
      <span className="deterministic">DETERMINISTIC ENGINE · EXPLANATION LAYER SEPARATE</span>
    </div>
    <div className="verification-controls">
      <label><span>MISSION PROFILE</span>
        <select value={mission} onChange={e => setMission(e.target.value)}>
          {MISSIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select></label>
      <label className="dataset-control"><span>INDEPENDENT REFERENCE</span>
        <select value={datasetId} disabled={!analysis.features.length}
          onChange={e => { setDatasetId(e.target.value); setRegistration(null); setResult(null) }}>
          {!analysis.features.length && <option>Not required — no significant change</option>}
          {datasets.map(d => <option value={d.id} key={d.id}>
            {d.classification} · {d.product_id} · {Number(d.resolution_m_per_pixel).toFixed(1)} m/px</option>)}
        </select></label>
      {analysis.features.length > 0 && <button className="secondary" disabled={!dataset}
        onClick={openManual}>MANUAL 3+1 POINT</button>}
      <BusyButton className="primary" busy={busy} idle="VERIFY PHYSICAL EVIDENCE" busyText="VERIFYING TERRAIN…" onClick={run} />
    </div>
    {dataset && analysis.features.length > 0 && <div className="dataset-strip">
      <DataTag classification={dataset.classification} />
      <span>{dataset.mission} · {dataset.instrument}</span>
      <em>{Number(dataset.resolution_m_per_pixel).toFixed(2)} m/px</em>
      {dataset.note && <em className="note">{dataset.note}</em>}
    </div>}
    <ErrorBox error={error} />
    {result && <>
      <div className={`decision-banner ${result.policy.decision.toLowerCase()}`}>
        <div><small>MISSION DECISION · {result.mission_profile.replaceAll('_', ' ')}</small>
          <strong>{result.policy.decision.replaceAll('_', ' ')}</strong>
          <span>{result.policy.reason_codes.join(' · ')}</span></div>
        <div className="decision-actions">
          <button onClick={() => download('passport')}>PASSPORT</button>
          <button onClick={() => download('evidence')}>EVIDENCE REPORT</button>
          <button onClick={explain}>EXPLAIN</button>
          <button onClick={() => setShowNavigator(v => !v)} className={showNavigator ? 'on' : ''}>NAVIGATOR</button>
          <button onClick={() => download('export')}>MISSION EXPORT</button>
        </div>
      </div>
      {result.no_significant_change
        ? <div className="fast-path"><ShieldCheck /><div><b>NO SIGNIFICANT CHANGE</b>
            <span>DEM verification was not required. Phase 1 retained no meaningful suspicious region.</span></div></div>
        : <div className="phase2-grid">
          <div className="terrain-card">
            <div className="terrain-tabs">
              <button className={terrainView === 'dem' ? 'on' : ''} onClick={() => setTerrainView('dem')}>DEM</button>
              <button className={terrainView === 'hillshade' ? 'on' : ''} onClick={() => setTerrainView('hillshade')}>HILLSHADE</button>
            </div>
            {result.artifacts[terrainView]
              ? <img src={result.artifacts[terrainView]} />
              : <div className="terrain-empty">REFERENCE UNAVAILABLE</div>}
            <p>Hillshade is a visualization derivative. Observed illumination comparison remains unavailable unless acquisition geometry is supplied.</p>
            <div className="feature-pills">{result.features.map(f =>
              <button key={f.feature_id} className={feature?.feature_id === f.feature_id ? 'on' : ''}
                onClick={() => setFeatureId(f.feature_id)}>{f.feature_id}</button>)}
            </div>
            <EvidenceQuality feature={feature} />
          </div>
          <EvidenceChain feature={feature} registration={registration || result.registration} policy={result.policy}
            dataset={result.dataset} onAskWhy={() => setShowNavigator(true)} />
        </div>}
      {showNavigator && <Navigator analysisId={analysis.id} featureId={feature?.feature_id} offline={offline} />}
      {explanation && <div className="explanation-panel">
        <div className="explanation-head"><small>EXPLANATION REPORT · {explanation.model_identifier}
          {explanation.fallback_used ? ' · DETERMINISTIC FALLBACK' : ''}</small>
          <b>Why does RATIO say this?</b></div>
        {['executive_summary', 'risk_assessment', 'evidence_explanation', 'recommendation'].map(k =>
          <div key={k} className="explain-row"><span>{k.replaceAll('_', ' ').toUpperCase()}</span>
            <p>{explanation.report[k]}</p></div>)}
        <div className="explain-row"><span>LIMITATIONS</span>
          <ul>{explanation.report.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></div>
        <div className="explain-policy"><b>POLICY DECISION: {explanation.policy_decision}</b>
          <span>attached by the backend, never by the language model</span></div>
      </div>}
    </>}
    {manual && dataset && <AlignmentModal analysisId={analysis.id} imageSrc={previews.original} dataset={dataset}
      onClose={() => setManual(false)} onSaved={r => { setRegistration(r); setManual(false) }} />}
  </section>
}

function AnalysisView({ data, previews, onReset, initialMission, offline }) {
  const [selected, setSelected] = useState(data.features[0]?.id || null)
  const [mode, setMode] = useState('difference_map')
  const feature = data.features.find(f => f.id === selected)
  return <div className="analysis-page">
    <div className="analysis-top">
      <div><div className="eyebrow"><Activity size={14} /> ANALYSIS COMPLETE · {data.id.slice(0, 8).toUpperCase()}</div>
        <h1>Visual evidence workspace</h1></div>
      <div className="top-actions">
        <button className="secondary" onClick={onReset}><RefreshCw size={15} /> NEW ANALYSIS</button>
        <a className="primary small" href={`/api/analyses/${data.id}/download`}><Download size={15} /> EXPORT JSON</a>
      </div>
    </div>
    <Stepper active={1} />
    {data.dimensions.resize_applied && <div className="normalization-banner"><RefreshCw size={16} />
      <span><b>Resolution normalization applied.</b> Images had different dimensions and were normalized for comparison:
        {data.dimensions.enhanced_dimensions.join('×')} → {data.dimensions.analysis_dimensions.join('×')} using
        {data.dimensions.resize_method.replaceAll('_', ' ')}.</span></div>}
    <Notice><span><b>Interpretation boundary:</b> these signals identify change, not hallucination.
      Physical support is unresolved until a terrain reference is evaluated.</span><strong>VISUAL-ONLY</strong></Notice>
    <div className="metric-grid">
      <Metric label="SUSPICIOUS AREA" value={pct(data.metrics.suspicious_area_pct, 2)} accent="amber" detail="of image pixels" />
      <Metric label="CANDIDATE REGIONS" value={data.metrics.region_count} detail="connected components" />
      <Metric label="GLOBAL SSIM" value={data.metrics.global_ssim.toFixed(3)} detail="1.0 = identical" />
      <Metric label="MEAN VISUAL SCORE" value={data.metrics.mean_visual_score.toFixed(3)} detail="normalized [0–1]" />
    </div>
    <div className="workspace">
      <div className="viewers">
        <ImagePanel tag="SOURCE A" label="Original sensor image" src={previews.original} />
        <ImagePanel tag="EVIDENCE VIEW" label={mode === 'difference_map' ? 'Weighted change map' : 'Detected regions'} src={data.artifacts[mode]}>
          <div className="tabs">
            <button className={mode === 'difference_map' ? 'on' : ''} onClick={() => setMode('difference_map')}>HEATMAP</button>
            <button className={mode === 'annotated' ? 'on' : ''} onClick={() => setMode('annotated')}>REGIONS</button>
          </div>
        </ImagePanel>
      </div>
      <aside className="evidence">
        <div className="aside-head"><div><small>REGION INSPECTOR</small><b>{feature ? feature.id : 'NO CANDIDATES'}</b></div><Layers3 size={20} /></div>
        {feature ? <>
          <div className="score-ring" style={{ '--score': `${feature.visual_score * 360}deg` }}>
            <div><strong>{feature.visual_score.toFixed(2)}</strong><span>VISUAL SCORE</span></div></div>
          <div className="bars">
            {[['Residual', feature.residual_score], ['SSIM change', feature.ssim_change],
              ['Edge mismatch', feature.edge_mismatch], ['Frequency', feature.frequency_change]].map(([n, v]) =>
              <div key={n}><span>{n}<b>{v.toFixed(3)}</b></span><em><i style={{ width: `${v * 100}%` }} /></em></div>)}
          </div>
          <dl>
            <div><dt>BOUNDING BOX</dt><dd>{feature.bbox.join(' · ')}</dd></div>
            <div><dt>REGION AREA</dt><dd>{feature.area_px.toLocaleString()} px</dd></div>
            <div><dt>PHYSICAL SUPPORT</dt><dd className="unresolved">UNRESOLVED UNTIL PHASE 2</dd></div>
          </dl>
        </> : <div className="empty"><CheckCircle2 /><b>No suspicious regions</b>
          <span>At the configured threshold, no connected visual-change region was retained.</span></div>}
      </aside>
    </div>
    <section className="regions">
      <div className="section-title"><div><small>DETECTED COMPONENTS</small><h2>Suspicious change regions</h2></div>
        <span>{data.features.length} TOTAL</span></div>
      {data.features.length
        ? <div className="table">
          <div className="tr th"><span>ID</span><span>LOCATION (X,Y,W,H)</span><span>AREA</span><span>VISUAL SCORE</span><span>STATUS</span></div>
          {data.features.map(f => <button className={`tr ${selected === f.id ? 'selected' : ''}`} key={f.id} onClick={() => setSelected(f.id)}>
            <span><b>{f.id}</b></span><span>{f.bbox.join(', ')}</span><span>{pct(f.area_pct, 2)}</span>
            <span><i className="mini"><em style={{ width: `${f.visual_score * 100}%` }} /></i>{f.visual_score.toFixed(3)}</span>
            <span className="tag">SUSPICIOUS CHANGE</span></button>)}
        </div>
        : <div className="table-empty">No region exceeds the configured detection threshold.</div>}
    </section>
    <Phase2Console analysis={data} previews={previews} initialMission={initialMission} offline={offline} />
    <footer><span>RATIO 2.0 · PROTOTYPE · NOT FLIGHT CERTIFIED</span>
      <span>RECORD SHA-256 {data.record_sha256.slice(0, 16)}…</span></footer>
  </div>
}

export default function AnalysisPage({ mission, onMission, offline }) {
  const [result, setResult] = useState(null)
  const [previews, setPreviews] = useState(null)
  useEffect(() => () => {
    if (previews) { URL.revokeObjectURL(previews.original); URL.revokeObjectURL(previews.enhanced) }
  }, [previews])
  if (result) {
    return result.comparison_status === 'COMPARABLE'
      ? <AnalysisView data={result} previews={previews} initialMission={mission} offline={offline}
          onReset={() => { setResult(null); setPreviews(null) }} />
      : <ComparisonGate data={result} onReset={() => { setResult(null); setPreviews(null) }} />
  }
  return <UploadView mission={mission} onMission={onMission} onComplete={(r, p) => { setResult(r); setPreviews(p) }} />
}
