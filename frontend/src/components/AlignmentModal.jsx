import { useState } from 'react'
import { ShieldAlert, X } from 'lucide-react'
import { saveAlignment } from '../api'

export function AlignmentModal({ analysisId, imageSrc, dataset, onClose, onSaved }) {
  const [imagePoints, setImagePoints] = useState([])
  const [referencePoints, setReferencePoints] = useState([])
  const [vImage, setVImage] = useState(null)
  const [vReference, setVReference] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const fitDone = imagePoints.length === 3 && referencePoints.length === 3
  const phase = !fitDone
    ? (imagePoints.length === referencePoints.length ? 'image' : 'reference')
    : (!vImage ? 'vimage' : 'vreference')

  function point(event, type) {
    const paneMatches = (type === 'image' && (phase === 'image' || phase === 'vimage'))
      || (type === 'reference' && (phase === 'reference' || phase === 'vreference'))
    if (!paneMatches) return
    const r = event.currentTarget.getBoundingClientRect()
    const img = event.currentTarget.querySelector('img')
    const p = [(event.clientX - r.left) / r.width * img.naturalWidth,
               (event.clientY - r.top) / r.height * img.naturalHeight]
    if (type === 'image') {
      if (imagePoints.length < 3) setImagePoints(x => [...x, p])
      else setVImage(p)
    } else {
      if (referencePoints.length < 3) setReferencePoints(x => [...x, p])
      else setVReference(p)
    }
  }

  async function apply(withValidation) {
    setBusy(true); setError('')
    try {
      const result = await saveAlignment(analysisId, imagePoints, referencePoints,
        withValidation ? [vImage] : null, withValidation ? [vReference] : null)
      onSaved(result)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const dots = (points, w, h) => points.map((p, i) =>
    <i className="control-dot" key={i} style={{ left: `${p[0] / w * 100}%`, top: `${p[1] / h * 100}%` }}>{i + 1}</i>)

  return <div className="modal-backdrop">
    <div className="alignment-modal">
      <div className="modal-title">
        <div><small>MANUAL GEOREGISTRATION · PHASE 3B</small><h2>Three-point affine + independent validation point</h2></div>
        <button onClick={onClose}><X /></button>
      </div>
      <div className="alignment-instruction">
        <b>{!fitDone ? `CLICK FIT POINT ${imagePoints.length + 1} OF 3`
          : !vImage ? 'CLICK INDEPENDENT VALIDATION POINT (IMAGE)'
          : 'CLICK THE SAME VALIDATION POINT (REFERENCE)'}</b>
        <span>Three points determine the transform. The fourth point does NOT participate in the fit —
          it tests the transform. A zero fit RMSE is not proof of correctness; the independent point is.</span>
      </div>
      <div className="alignment-panes">
        <div className={phase !== 'image' && phase !== 'vimage' ? 'disabled' : ''} onClick={e => point(e, 'image')}>
          <span>IMAGE · FIT {imagePoints.length}/3 {vImage ? '· VALIDATION ✓' : ''}</span>
          <img src={imageSrc} />
          {dots(imagePoints, 512, 512)}
          {vImage && <i className="control-dot valid" style={{ left: `${vImage[0] / 512 * 100}%`, top: `${vImage[1] / 512 * 100}%` }}>V</i>}
        </div>
        <div className={phase !== 'reference' && phase !== 'vreference' ? 'disabled' : ''} onClick={e => point(e, 'reference')}>
          <span>REFERENCE · FIT {referencePoints.length}/3 {vReference ? '· VALIDATION ✓' : ''}</span>
          <img src={`/api/datasets/${dataset.id}/preview?kind=hillshade`} />
          {dots(referencePoints, dataset.reference_dimensions[0], dataset.reference_dimensions[1])}
          {vReference && <i className="control-dot valid" style={{
            left: `${vReference[0] / dataset.reference_dimensions[0] * 100}%`,
            top: `${vReference[1] / dataset.reference_dimensions[1] * 100}%` }}>V</i>}
        </div>
      </div>
      {error && <div className="error"><ShieldAlert size={16} />{error}</div>}
      <div className="modal-actions">
        <button className="secondary" onClick={() => { setImagePoints([]); setReferencePoints([]); setVImage(null); setVReference(null) }}>REDO</button>
        <button className="secondary" onClick={onClose}>CANCEL</button>
        {fitDone && vImage && vReference && <button className="secondary" disabled={busy}
          onClick={() => apply(true)}>{busy ? 'FITTING…' : 'ACCEPT WITH VALIDATION'}</button>}
        <button className="primary" disabled={busy || !fitDone || (vImage && !vReference)}
          onClick={() => apply(false)}>{busy ? 'FITTING…' : 'SHOW TRANSFORM & ACCEPT (3-POINT)'}</button>
      </div>
    </div>
  </div>
}
