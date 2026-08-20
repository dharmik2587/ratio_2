import { AlertTriangle, Check, X } from 'lucide-react'

const pct = (n, d = 3) => (n == null ? 'UNAVAILABLE' : Number(n).toFixed(d))

function Row({ step, title, ok, warn, value, detail, extra }) {
  return <div className={`chain-step ${ok === false ? 'bad' : ''} ${warn ? 'warn' : ''}`}>
    <div className="step-index">{String(step).padStart(2, '0')}</div>
    <div className="step-body">
      <div className="step-head">
        <b>{title}</b>
        {ok === false ? <X size={13} /> : warn ? <AlertTriangle size={13} /> : <Check size={13} />}
      </div>
      <div className="step-value">{value}</div>
      {detail && <div className="step-detail">{detail}</div>}
      {extra}
    </div>
  </div>
}

export function EvidenceChain({ feature, registration, policy, dataset, onAskWhy }) {
  if (!feature) return <div className="terrain-empty">NO FEATURE EVIDENCE</div>
  const resolution = feature.reference_resolution || {}
  const components = feature.support_components || {}
  const support = feature.physical_support
  const risk = feature.unsupported_risk
  const regOk = (feature.registration_quality || 0) >= 0.75 && registration?.status === 'REGISTRATION_SUCCESS'
  const refOk = (feature.reference_quality || 0) >= 0.6
  const resOk = resolution.status === 'REFERENCE_RESOLUTION_ADEQUATE'
  const supportOk = support != null && support >= 0.7
  const supportPartial = support != null && support >= 0.45 && support < 0.7
  const status = feature.status || 'UNKNOWN'
  const decision = policy?.decision || 'UNKNOWN'
  const decisionBad = ['NOT_SAFE', 'REVIEW_REQUIRED'].includes(decision)

  return <div className="evidence-chain">
    <div className="chain-title">
      <span>EVIDENCE CHAIN</span>
      <b>{feature.feature_id} — {status.replaceAll('_', ' ')}</b>
    </div>
    <Row step={1} title="WHAT CHANGED?" ok={feature.visual_change > 0}
      value={`VISUAL CHANGE ${pct(feature.visual_change)}`}
      detail="Weighted visual-change score from the frozen Phase-1 pipeline. Visual change is never physical support." />
    <Row step={2} title="IS THE INPUT COMPARABLE?" ok={(feature.comparison_quality || 0) >= 0.7}
      value={`COMPARISON QUALITY ${pct(feature.comparison_quality)}`}
      detail="Low-resolution visual correspondence only; not semantic or geographic identity." />
    <Row step={3} title="HOW WAS IT ALIGNED?" ok={regOk} warn={!regOk}
      value={`REGISTRATION ${registration?.quality_label || 'UNAVAILABLE'} · ${pct(feature.registration_quality)}`}
      detail={registration
        ? `${registration.method} · ${registration.validation_basis?.replaceAll('_', ' ')} · fit RMSE ${pct(registration.rmse_px)} px${registration.validation_point_count ? ` · independent validation ${pct(registration.validation_rmse_px)} px (${registration.validation_point_count} pt)` : ' · NO INDEPENDENT POINT'}`
        : 'No registration record'} />
    <Row step={4} title="WHAT DOES THE INDEPENDENT TERRAIN REFERENCE SHOW?" ok={resOk}
      warn={!resOk && status !== 'REFERENCE_UNAVAILABLE'}
      value={`REFERENCE ${pct(resolution.meters_per_pixel, 1)} M/PX · ${resolution.status || 'UNAVAILABLE'}`}
      detail={`Feature scale ${resolution.feature_scale_m != null ? `${Number(resolution.feature_scale_m).toFixed(0)} m` : 'unknown'} · resolution ratio ${resolution.resolution_ratio ?? '—'} · valid data ${pct(feature.valid_data_percentage, 1)} · ${feature.coverage_status || ''}`} />
    <Row step={5} title="HOW STRONG IS THE PHYSICAL SUPPORT?" ok={supportOk} warn={supportPartial}
      value={`PHYSICAL SUPPORT ${pct(support)}`}
      detail="Weighted mean over available components only; missing components are omitted, never zeroed."
      extra={<div className="component-grid">
        {Object.entries(components).map(([k, v]) =>
          <div key={k}><span>{k.replaceAll('_', ' ')}</span><b>{v == null ? 'UNAVAILABLE' : Number(v).toFixed(3)}</b></div>)}
      </div>} />
    <Row step={6} title="WHAT IS THE UNSUPPORTED RISK?" ok={risk != null && risk <= 0.4}
      warn={risk != null && risk > 0.4}
      value={`UNSUPPORTED RISK ${pct(risk)}`}
      detail="Deterministic engineering measure — NOT A PROBABILITY. Never treat as a calibrated risk probability." />
    <Row step={7} title="WHAT DOES THE MISSION POLICY REQUIRE?" ok={!decisionBad}
      value={`${policy?.mission_profile?.replaceAll('_', ' ') || 'MISSION'} → ${decision.replaceAll('_', ' ')}`}
      detail={(policy?.reason_codes || []).join(' · ') || 'no reason codes'} />
    <Row step={8} title="FINAL DECISION" ok={!decisionBad}
      value={<span className={`decision-chip ${decision.toLowerCase()}`}>{decision.replaceAll('_', ' ')}</span>}
      detail={decisionBad ? 'Export is blocked by the deterministic mission policy. The analysis report remains downloadable.' : 'All mandatory gates passed for this mission profile.'} />
    {onAskWhy && <button className="ask-why" onClick={onAskWhy}>WHY WAS THIS DECIDED?</button>}
  </div>
}

export function EvidenceQuality({ feature }) {
  if (!feature) return null
  const rows = [
    ['COMPARISON QUALITY', feature.comparison_quality, 'visual correspondence'],
    ['REGISTRATION QUALITY', feature.registration_quality, 'alignment quality'],
    ['REFERENCE QUALITY', feature.reference_quality, 'registration + coverage + resolution'],
    ['PHYSICAL SUPPORT', feature.physical_support, 'available terrain components'],
    ['UNSUPPORTED RISK', feature.unsupported_risk, 'deterministic, not a probability'],
  ]
  return <div className="quality-grid">
    {rows.map(([label, value, detail]) =>
      <div key={label} className="quality-cell">
        <small>{label}</small>
        <strong className={value == null ? 'dim' : ''}>{value == null ? '—' : Number(value).toFixed(3)}</strong>
        <span>{detail}</span>
      </div>)}
  </div>
}
