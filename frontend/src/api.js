async function expect(response) {
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      message = body.message || body.detail || message
    } catch {}
    const err = new Error(message)
    err.status = response.status
    err.code = null
    try {
      const body = await response.json()
      err.code = body.error || null
    } catch {}
    throw err
  }
  return response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function uploadImage(file) {
  const data = new FormData()
  data.append('file', file)
  return expect(await fetch('/api/images/upload', { method: 'POST', body: data }))
}
export async function createAnalysis(originalId, enhancedId, label) {
  return expect(await fetch('/api/analyses', json('POST', { original_image_id: originalId, enhanced_image_id: enhancedId, label })))
}
export async function getAnalysis(id) { return expect(await fetch(`/api/analyses/${id}`)) }
export async function getDatasets() { return expect(await fetch('/api/datasets')) }
export async function attachReference(id, datasetId) {
  return expect(await fetch(`/api/analyses/${id}/reference`, json('POST', { dataset_id: datasetId })))
}
export async function verifyPhysical(id, mission) {
  return expect(await fetch(`/api/analyses/${id}/verify`, json('POST', { mission_profile: mission })))
}
export async function saveAlignment(id, imagePoints, referencePoints, validationImagePoints, validationReferencePoints) {
  return expect(await fetch(`/api/analyses/${id}/align`, json('POST', {
    image_points: imagePoints, reference_points: referencePoints,
    validation_image_points: validationImagePoints || null,
    validation_reference_points: validationReferencePoints || null,
  })))
}
export async function requestExport(id) { return expect(await fetch(`/api/analyses/${id}/export`, { method: 'POST' })) }
export async function getPassport(id) { return expect(await fetch(`/api/analyses/${id}/passport`)) }
export async function getEvidenceReport(id) { return expect(await fetch(`/api/analyses/${id}/evidence-report`)) }
export async function getHealth() { return expect(await fetch('/api/health/phase3')) }

// Phase 3E evidence API
export async function getAnalysisSummary(id) { return expect(await fetch(`/api/evidence/analysis/${id}/summary`)) }
export async function getFeatureEvidence(fid, aid) {
  const params = aid ? `?analysis_id=${aid}` : ''
  return expect(await fetch(`/api/evidence/feature/${fid}/evidence${params}`))
}
export async function getRegistration(aid) { return expect(await fetch(`/api/evidence/registration?analysis_id=${aid}`)) }
export async function getRegionSummary(aid, region = 'ALL') { return expect(await fetch(`/api/evidence/region-summary/${aid}?region=${region}`)) }

// Phase 3C/3D
export async function runBenchmark() { return expect(await fetch('/api/benchmarks/run', { method: 'POST' })) }
export async function getBenchmarkSummary() { return expect(await fetch('/api/evidence/benchmark')) }
export async function runDrift() { return expect(await fetch('/api/drift/run', { method: 'POST' })) }
export async function getDriftReport() { return expect(await fetch('/api/evidence/drift')) }

// Phase 3F/3G
export async function requestExplanation(id, fid) {
  const params = fid ? `?feature_id=${fid}` : ''
  return expect(await fetch(`/api/analyses/${id}/explain${params}`, { method: 'POST' }))
}
export async function navigatorQuery(question, analysisId, featureId) {
  return expect(await fetch('/api/navigator/query', json('POST', { question, analysis_id: analysisId, feature_id: featureId })))
}
export async function navigatorAudit(limit = 20) { return expect(await fetch(`/api/navigator/audit?limit=${limit}`)) }

// Phase 3J
export async function getDemoCases() { return expect(await fetch('/api/demo/cases')) }
export async function runDemoCase(id) { return expect(await fetch(`/api/demo/run/${id}`, { method: 'POST' })) }
