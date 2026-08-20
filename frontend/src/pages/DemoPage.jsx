import { useEffect, useState } from 'react'
import { Bot, ChevronDown, FlaskConical, ShieldCheck, ShieldX, TerminalSquare } from 'lucide-react'
import { getDemoCases, navigatorQuery, runDemoCase } from '../api'
import { BusyButton, DataTag, ErrorBox } from '../components/ui'
import { EvidenceChain, EvidenceQuality } from '../components/EvidenceChain'

export default function DemoPage({ offline }) {
  const [cases, setCases] = useState([])
  const [active, setActive] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [advanced, setAdvanced] = useState(false)
  const [why, setWhy] = useState(null)

  useEffect(() => { getDemoCases().then(x => setCases(x.cases)).catch(e => setError(e.message)) }, [])

  async function verify(caseId) {
    setBusy(true); setError(''); setResult(null); setWhy(null); setAdvanced(false)
    try { setResult(await runDemoCase(caseId)) }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function askWhy() {
    if (!result) return
    setBusy(true)
    try {
      const featureId = result.feature?.feature_id
      const question = result.case === 'case7_evidence_navigator'
        ? result.question
        : `Why was ${featureId || 'this analysis'} decided ${result.policy?.decision?.replaceAll('_', ' ')}?`
      setWhy(await navigatorQuery(question, result.analysis_id, featureId))
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const selected = cases.find(c => c.id === active)

  return <main className="page demo-page">
    <div className="page-head">
      <div>
        <div className="eyebrow"><FlaskConical size={14} /> PHASE 3J · SIH DEMO MODE</div>
        <h1>Judge view — one-click scenarios</h1>
        <p className="lead">Every case runs the real deterministic pipeline server-side. Select a case, press
          VERIFY, and inspect the evidence chain. Then ask WHY — the navigator answers from structured evidence only.</p>
      </div>
    </div>
    <div className="demo-cases">
      {cases.map(c => <button key={c.id} className={`demo-case ${active === c.id ? 'on' : ''}`}
        onClick={() => setActive(c.id)}>
        <b>{c.title}</b><span>EXPECTED</span><em>{c.expected}</em><p>{c.description}</p></button>)}
    </div>
    <div className="action-row">
      <div className="scope"><FlaskConical size={16} />
        <span><b>Demo integrity:</b> no pre-scripted outcomes. The recorded values below come from the actual backend run.</span></div>
      <BusyButton className="primary" busy={busy} idle={`VERIFY ${selected ? selected.title.toUpperCase() : 'CASE'}`}
        busyText="RUNNING PIPELINE…" disabled={!selected} onClick={() => verify(active)} />
    </div>
    <ErrorBox error={error} />
    {result && <>
      {result.case === 'case6_model_drift' && <div className="demo-drift">
        <div className="decision-banner review"><div><small>MODEL DRIFT · BASELINE {result.baseline}</small>
          <strong>DRIFT REPORT {result.report_id}</strong><span>measured benchmark deltas per enhancer version</span></div></div>
        <div className="drift-grid">
          {result.comparisons.map(c => <section key={c.candidate} className={`drift-card ${c.decision.toLowerCase()}`}>
            <div className="drift-head"><div><small>ENHANCER VERSION</small><b>{c.candidate}</b></div>
              <div className={`drift-decision ${c.decision.toLowerCase()}`}>
                {c.decision === 'PASS' ? <ShieldCheck size={18} /> : <ShieldX size={18} />}<b>{c.decision}</b></div></div>
            <div className="drift-reasons"><span>REASON CODES</span><em>{c.reason_codes.join(' · ') || 'within configured thresholds'}</em></div>
            <div className="drift-delta">{Object.entries(c.percentage_changes).filter(([, d]) => d != null)
              .map(([m, d]) => <code key={m} className={Math.abs(d) >= 20 ? 'hot' : ''}>{m.replaceAll('_', ' ')} {d >= 0 ? '+' : ''}{d.toFixed(1)}%</code>)}</div>
          </section>)}
        </div>
      </div>}
      {(result.case === 'case7_evidence_navigator' || result.case === 'case8_claude_offline') && <div className="demo-navigator-result">
        <div className="decision-banner review"><div><small>EVIDENCE NAVIGATOR · {result.model_identifier}</small>
          <strong>{result.case === 'case8_claude_offline' ? 'CLAUDE OFFLINE — FALLBACK ACTIVE' : 'JUDGE QUESTION ANSWERED'}</strong>
          <span>question: “{result.question}”</span></div></div>
        <div className="explanation-panel">
          <div className="explanation-head"><small>TOOLS CALLED: {result.tools_called?.join(' · ')}</small>
            <b>Answer from structured evidence</b></div>
          {['executive_summary', 'risk_assessment', 'evidence_explanation', 'recommendation'].map(k =>
            <div key={k} className="explain-row"><span>{k.replaceAll('_', ' ').toUpperCase()}</span>
              <p>{result.explanation[k]}</p></div>)}
          <div className="explain-policy"><b>POLICY DECISION: {result.policy_decision}</b>
            <span>attached by the backend — the assistant cannot change it</span></div>
        </div>
      </div>}
      {result.policy && <>
        <div className={`decision-banner ${(result.policy.decision || '').toLowerCase()}`}>
          <div><small>MISSION DECISION · {result.policy.mission_profile?.replaceAll('_', ' ')}</small>
            <strong>{result.policy.decision?.replaceAll('_', ' ')}</strong>
            <span>{result.policy.reason_codes?.join(' · ')}</span></div>
          <div className="decision-actions">
            {result.dem_verification_status === 'NOT_REQUIRED' && <span className="blocked-chip ok">DEM VERIFICATION NOT REQUIRED — FAST PATH</span>}
            {result.case === 'case2_synthetic_fake_boulder' && <span className="blocked-chip">EXPORT BLOCKED — 409</span>}
            {result.analysis_id && <a className="secondary small" href={`/api/analyses/${result.analysis_id}/download`}>ANALYSIS JSON</a>}
          </div>
        </div>
      </>}
      {result.feature && <>
        <div className="demo-visuals">
          {result.analysis_id && ['annotated', 'difference_map'].map(name =>
            <div key={name} className="image-panel"><div className="panel-title">
              <div><small>{name === 'annotated' ? 'DETECTED REGIONS' : 'WEIGHTED CHANGE MAP'}</small></div></div>
              <div className="canvas"><img src={`/api/analyses/${result.analysis_id}/artifacts/${name}.png`} /></div></div>)}
          <div className="demo-summary">
            <EvidenceQuality feature={result.feature} />
            <div className="dataset-strip"><DataTag classification={result.verification?.dataset?.classification || 'DEMO'} />
              <span>{result.verification?.dataset?.mission} · {result.verification?.dataset?.product_id}</span>
              <em>{Number(result.verification?.dataset?.resolution_m_per_pixel).toFixed(2)} m/px</em></div>
            {result.feature.reference_resolution?.meters_per_pixel < 100 && <div className="hi-res-banner">
              <b>HIGH-RES LOCAL REFERENCE</b>
              <span>Resolution {result.feature.reference_resolution.meters_per_pixel} m/pixel · feature scale
                {result.feature.reference_resolution.feature_scale_m ? ` ${result.feature.reference_resolution.feature_scale_m.toFixed(0)} m` : ''} ·
                adequacy {result.feature.reference_resolution.status}</span></div>}
          </div>
        </div>
        <div className="phase2-grid">
          <div className="terrain-card">
            <div className="terrain-tabs">
              <button className="on">DEM PREVIEW</button>
            </div>
            {result.verification?.artifacts?.hillshade
              ? <img src={result.verification.artifacts.hillshade} />
              : <div className="terrain-empty">REFERENCE UNAVAILABLE</div>}
            <p>{result.verification?.dataset?.description}</p>
          </div>
          <EvidenceChain feature={result.feature} registration={result.registration}
            policy={result.policy} dataset={result.verification?.dataset} onAskWhy={askWhy} />
        </div>
        <button className="advanced-toggle" onClick={() => setAdvanced(v => !v)}>
          ADVANCED METRICS <ChevronDown size={14} className={advanced ? 'up' : ''} /></button>
        {advanced && <pre className="advanced-json">{JSON.stringify({
          feature: result.feature, registration: result.registration,
          policy: result.policy, dem_verification_status: result.dem_verification_status,
        }, null, 2)}</pre>}
        {why && <div className="demo-navigator-result">
          <div className="explanation-panel">
            <div className="explanation-head"><small>INTENT {why.intent} · TOOLS {why.tools_called?.join(' · ')} · {why.model_identifier}</small>
              <b>WHY — answered from structured evidence</b></div>
            <div className="nav-msg assistant"><Bot size={12} /><div><p>{why.explanation.executive_summary}</p>
              <dl><div><dt>RECOMMENDATION</dt><dd>{why.explanation.recommendation}</dd></div>
                <div><dt>LIMITATIONS</dt><dd><ul>{why.explanation.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></dd></div></dl>
              <div className="nav-meta">{why.tools_called?.map(t => <code key={t}><TerminalSquare size={10} /> {t}</code>)}
                {why.policy_decision && <code className="decision">{why.policy_decision}</code>}</div></div></div>
          </div>
        </div>}
      </>}
    </>}
  </main>
}
