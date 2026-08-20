import { useEffect, useState } from 'react'
import { Download, FlaskConical } from 'lucide-react'
import { getBenchmarkSummary, runBenchmark } from '../api'
import { BusyButton, DataTag, ErrorBox } from '../components/ui'

function download(url, name) {
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
}

export default function BenchmarksPage() {
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getBenchmarkSummary().then(setReport).catch(() => setReport(null))
  }, [])

  async function run() {
    setBusy(true); setError('')
    try {
      await runBenchmark()
      setReport(await getBenchmarkSummary())
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return <main className="page">
    <div className="page-head">
      <div>
        <div className="eyebrow"><FlaskConical size={14} /> PHASE 3C · SYNTHETIC HAZARD TEST RANGE</div>
        <h1>Synthetic benchmark &amp; false-positive controls</h1>
        <p className="lead">Controlled hazards and benign perturbations run through the frozen RATIO pipeline.
          Scene-level split: development / validation / held-out. No ML is trained — metrics are recorded, not optimized.</p>
      </div>
      <div className="top-actions">
        <button className="secondary" onClick={() => download('/api/benchmarks/report.html', 'benchmark_report.html')}>
          <Download size={15} /> HTML REPORT</button>
        <BusyButton className="primary" busy={busy} idle="RUN BENCHMARK" busyText="RUNNING…" onClick={run} />
      </div>
    </div>
    <ErrorBox error={error} />
    {report && <>
      <div className="dataset-strip"><DataTag classification={report.data_classification} />
        <span>generated {report.generated_at} · report {report.report_id}</span>
        <em>real-data samples use the NASA SVS rendering composite (not calibrated science imagery)</em>
      </div>
      <div className="bench-grid">
        {Object.entries(report.splits).map(([split, s]) =>
          <section key={split} className="bench-split">
            <div className="split-head"><b>{split.toUpperCase().replaceAll('_', ' ')}</b>
              <span>{s.total_samples} samples</span></div>
            <div className="metric-grid">
              <div className="metric"><small>HAZARD DETECTION</small>
                <strong>{((1 - (s.aggregates.false_negative_rate || 1)) * 100).toFixed(1)}%</strong>
                <span>region-level recall</span></div>
              <div className="metric"><small>FALSE-POSITIVE RATE</small>
                <strong>{(s.aggregates.false_positive_rate * 100).toFixed(4)}%</strong>
                <span>benign pixels flagged</span></div>
              <div className="metric"><small>UNSUPPORTED-CANDIDATE RATE</small>
                <strong>{((s.aggregates.unsupported_candidate_rate || 0) * 100).toFixed(1)}%</strong>
                <span>samples producing a candidate</span></div>
              <div className="metric"><small>MEAN SUSPICIOUS AREA</small>
                <strong>{(s.aggregates.average_suspicious_area_pct || 0).toFixed(3)}%</strong>
                <span>of image pixels</span></div>
            </div>
            <div className="table">
              <div className="tr th"><span>HAZARD CLASS</span><span>SAMPLES</span><span>DETECTED</span>
                <span>MISSED</span><span>FALSE ALARMS</span><span>AVG IOU</span><span>MEDIAN IOU</span><span>AVG PRECISION</span></div>
              {Object.entries(s.classes).map(([name, c]) =>
                <div className="tr" key={name}><span><b>{name.replaceAll('_', ' ')}</b></span>
                  <span>{c.number_of_samples}</span><span>{c.detected}</span><span>{c.missed}</span>
                  <span>{c.false_alarms}</span><span>{c.average_iou ?? '—'}</span><span>{c.median_iou ?? '—'}</span>
                  <span>{c.average_pixel_precision ?? '—'}</span></div>)}
            </div>
          </section>)}
      </div>
      <div className="notice"><span><b>Interpretation:</b> the false-positive controls verify that RATIO distinguishes
        VISUAL CHANGE from an UNSUPPORTED-TERRAIN CANDIDATE — benign processing is rarely flagged, injected hazards are usually detected.</span>
        <strong>{report.data_classification}</strong></div>
    </>}
    {!report && !busy && <div className="terrain-empty tall">No benchmark report yet. Run the benchmark to generate one.</div>}
  </main>
}
