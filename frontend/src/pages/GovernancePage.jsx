import { useEffect, useState } from 'react'
import { ShieldCheck, ShieldAlert, ShieldX, TrendingUp } from 'lucide-react'
import { getDriftReport, runDrift } from '../api'
import { BusyButton, ErrorBox } from '../components/ui'

const DECISION_ICON = { PASS: ShieldCheck, REVIEW: ShieldAlert, QUARANTINE: ShieldX }
const DECISION_COLOR = { PASS: 'pass', REVIEW: 'review', QUARANTINE: 'quarantine' }

export default function GovernancePage() {
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { getDriftReport().then(setReport).catch(() => setReport(null)) }, [])

  async function run() {
    setBusy(true); setError('')
    try {
      await runDrift()
      setReport(await getDriftReport())
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const versions = report ? Object.entries(report.versions).sort(([a], [b]) => a.localeCompare(b)) : []
  const baselineKey = report ? Object.keys(report.versions).sort()[0] : null

  return <main className="page">
    <div className="page-head">
      <div>
        <div className="eyebrow"><TrendingUp size={14} /> PHASE 3D · ENHANCEMENT / MODEL DRIFT MONITOR</div>
        <h1>Model governance</h1>
        <p className="lead">The same fixed benchmark runs through every registered enhancer version.
          Behavior changes are measured — not assumed. A new pipeline that changes detection rates is flagged
          REVIEW or QUARANTINE with the recorded metrics that triggered it.</p>
      </div>
      <div className="top-actions">
        <BusyButton className="primary" busy={busy} idle="RUN DRIFT MONITOR" busyText="RUNNING…" onClick={run} />
      </div>
    </div>
    <ErrorBox error={error} />
    {report && <>
      <div className="dataset-strip"><span>baseline: {report.baseline.version} · benchmark samples: {report.benchmark_samples} ·
        report {report.report_id} · data: {report.data_classification}</span></div>
      <div className="drift-grid">
        {versions.map(([key, v]) => {
          const isBaseline = key === baselineKey
          const comparison = report.comparisons[key]
          const decision = isBaseline ? 'PASS' : comparison?.decision || 'PASS'
          const Icon = DECISION_ICON[decision]
          return <section key={key} className={`drift-card ${DECISION_COLOR[decision]}`}>
            <div className="drift-head">
              <div><small>ENHANCER VERSION</small><b>{v.version}</b><span>{v.description}</span></div>
              <div className={`drift-decision ${DECISION_COLOR[decision]}`}>
                <Icon size={18} /><b>{decision}</b></div>
            </div>
            <div className="drift-metrics">
              {[['VISUAL-CHANGE RATE', v.visual_change_rate, '%'],
                ['SUSPICIOUS-REGION RATE', v.suspicious_region_rate, '%'],
                ['FALSE-POSITIVE RATE', v.false_positive_rate, '%'],
                ['FALSE-NEGATIVE RATE', v.false_negative_rate, '%'],
                ['MEAN REGION COUNT', v.region_count_mean, ''],
                ['MEAN CHANGED AREA', v.average_changed_area_pct, '%'],
                ['POLICY-BLOCK RATE', v.policy_block_rate, '%'],
                ['UNSUPPORTED-RISK MEAN', v.unsupported_risk_mean, '']].map(([label, value, unit]) =>
                <div key={label}><span>{label}</span>
                  <b>{value == null ? '—' : (Number(value) >= 0.01 || !unit
                    ? Number(value).toFixed(3) : (Number(value) * 100).toFixed(4))}{unit && value != null && Number(value) < 0.01 ? '‰' : unit}</b></div>)}
            </div>
            {comparison && <div className="drift-delta">
              {Object.entries(comparison.percentage_changes).filter(([, d]) => d != null).map(([metric, delta]) =>
                <code key={metric} className={Math.abs(delta) >= 20 ? 'hot' : ''}>
                  {metric.replaceAll('_', ' ')} {delta >= 0 ? '+' : ''}{delta.toFixed(1)}%
                </code>)}
              <div className="drift-reasons"><span>REASON CODES</span><em>{(comparison.reason_codes || ['within configured thresholds']).join(' · ')}</em></div>
            </div>}
          </section>
        })}
      </div>
      <div className="notice"><span><b>Drift decision basis:</b> configured absolute and percentage thresholds on recorded
        benchmark metrics. Percentage thresholds apply only when the baseline metric is ≥ 0.01 — a huge relative change on a
        near-zero baseline does not trigger a decision by itself.</span><strong>MEASURED, NOT CLAIMED</strong></div>
    </>}
    {!report && !busy && <div className="terrain-empty tall">No drift report yet. Run the drift monitor to generate one.</div>}
  </main>
}
