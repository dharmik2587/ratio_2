import { useEffect, useRef, useState } from 'react'
import { Bot, RefreshCw, Send, TerminalSquare, User } from 'lucide-react'
import { navigatorQuery } from '../api'

const SUGGESTIONS = [
  'Why was this flagged?',
  'Why is this unresolved?',
  'What evidence is missing?',
  'What would increase confidence?',
  'Show all REVIEW_REQUIRED features',
  'Which regions have weak DEM support?',
  'What is the registration quality?',
]

export function Navigator({ analysisId, featureId, offline }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef(null)
  useEffect(() => { scrollRef.current?.scrollTo({ top: 1e9, behavior: 'smooth' }) }, [messages])

  async function ask(question) {
    if (!question.trim() || busy) return
    setBusy(true)
    setMessages(m => [...m, { role: 'user', text: question }])
    try {
      const result = await navigatorQuery(question, analysisId, featureId)
      setMessages(m => [...m, {
        role: 'assistant',
        text: result.explanation,
        tools: result.tools_called,
        decision: result.policy_decision,
        fallback: result.fallback_used,
        model: result.model_identifier,
      }])
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', error: e.message }])
    } finally {
      setBusy(false)
      setInput('')
    }
  }

  return <aside className="navigator">
    <div className="navigator-head">
      <div><Bot size={16} /><b>EVIDENCE NAVIGATOR</b></div>
      <span className={`nav-status ${offline ? 'off' : ''}`}>{offline ? 'DETERMINISTIC MODE' : 'CLAUDE ENABLED'}</span>
    </div>
    <div className="navigator-scroll" ref={scrollRef}>
      {messages.length === 0 && <>
        <div className="nav-empty">
          <Bot size={26} />
          <b>Ask about the evidence.</b>
          <span>The assistant answers from structured RATIO backend evidence only. It cannot modify decisions, thresholds, or weights.</span>
        </div>
        <div className="nav-suggestions">
          {SUGGESTIONS.map(s => <button key={s} onClick={() => ask(s)}>{s}</button>)}
        </div>
      </>}
      {messages.map((m, i) => m.role === 'user'
        ? <div className="nav-msg user" key={i}><User size={12} /><p>{m.text}</p></div>
        : <div className="nav-msg assistant" key={i}>
          <Bot size={12} />
          <div>
            {m.error ? <p className="nav-error">{m.error}</p> : <>
              <p>{m.text.executive_summary}</p>
              <dl>
                <div><dt>EVIDENCE</dt><dd>{m.text.evidence_explanation}</dd></div>
                <div><dt>RISK</dt><dd>{m.text.risk_assessment}</dd></div>
                <div><dt>RECOMMENDATION</dt><dd>{m.text.recommendation}</dd></div>
                <div><dt>LIMITATIONS</dt><dd><ul>{(m.text.limitations || []).map((l, j) => <li key={j}>{l}</li>)}</ul></dd></div>
              </dl>
            </>}
            <div className="nav-meta">
              {m.tools?.map(t => <code key={t}><TerminalSquare size={10} /> {t}</code>)}
              {m.decision && <code className="decision">{m.decision}</code>}
              {m.fallback && <code className="fallback">FALLBACK EXPLANATION</code>}
              <code>{m.model}</code>
            </div>
          </div>
        </div>)}
      {busy && <div className="nav-msg assistant"><Bot size={12} /><div><p className="busy"><RefreshCw className="spin" size={12} /> querying evidence tools…</p></div></div>}
    </div>
    <div className="navigator-input">
      <input value={input} placeholder="Ask about this feature's evidence…"
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') ask(input) }} />
      <button onClick={() => ask(input)} disabled={busy}><Send size={14} /></button>
    </div>
  </aside>
}
