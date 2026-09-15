import { useEffect, useMemo, useRef, useState } from 'react'
import {
  chatStream,
  createSession,
  deleteSession,
  downloadExcelUrl,
  getHealth,
  getSession,
  listSessions,
  renderFormat,
  type ChatResponse,
  type Health,
  type SessionSummary,
} from './api'
import './index.css'

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  domain?: string | null
  confidence?: string | null
  isClarification?: boolean
  noAnswer?: boolean
  sources?: ChatResponse['sources']
  availableFormats?: string[]
}

const SUGGESTIONS = [
  'An employee submits an expense claim for ₹15,000. Who needs to approve it?',
  'My toilet is occasionally leaking or running — what should I check?',
  'How many casual leave days can I carry forward?',
  'What personal information does Kohler collect?',
]

const FORMATS = ['prose', 'json', 'xml', 'excel', 'email'] as const

function uid() {
  return crypto.randomUUID()
}

/** Keep sidebar/topbar titles human-readable when the titler returns junk. */
function displayTitle(raw: string | null | undefined, fallback = 'Untitled chat'): string {
  const t = (raw ?? '').trim()
  if (!t) return fallback
  if (t.startsWith('{') || t.startsWith('[') || t.includes('"entitlement') || t.includes('"risk_level"')) {
    return 'Structured answer request'
  }
  if (/generate short descriptive/i.test(t) || /chat titles/i.test(t)) {
    return 'New conversation'
  }
  if (t.length > 72) return `${t.slice(0, 69)}…`
  return t
}

function turnsToMessages(
  turns: Array<{
    role: string
    content: string
    domain?: string | null
    is_clarification?: boolean
    no_answer?: boolean
    confidence?: string | null
  }>,
): Message[] {
  return turns
    .filter((t) => t.role === 'user' || t.role === 'assistant')
    .map((t) => ({
      id: uid(),
      role: t.role as 'user' | 'assistant',
      content: t.content,
      domain: t.domain,
      isClarification: Boolean(t.is_clarification),
      noAnswer: Boolean(t.no_answer),
      confidence: t.confidence ?? null,
    }))
}

function confidenceTone(confidence?: string | null): string {
  switch ((confidence || '').toLowerCase()) {
    case 'high':
      return 'ok'
    case 'medium':
      return 'mid'
    case 'low':
    case 'none':
      return 'warn'
    default:
      return ''
  }
}

function AnswerStateBanner({ m }: { m: Message }) {
  if (m.role !== 'assistant') return null
  if (m.isClarification) {
    return (
      <div className="answer-banner clarify-banner" role="status">
        Clarification needed — pick a domain or rephrase so Prism can route correctly.
      </div>
    )
  }
  if (m.noAnswer) {
    return (
      <div className="answer-banner honesty-banner" role="status">
        No confident match in the knowledge base — refusing to invent an answer.
      </div>
    )
  }
  return null
}

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [status, setStatus] = useState('Ready')
  const [panel, setPanel] = useState<{ format: string; content: string } | null>(null)
  const [formats, setFormats] = useState<string[]>(['prose'])
  const bottomRef = useRef<HTMLDivElement>(null)

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId],
  )

  useEffect(() => {
    void bootstrap()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, panel])

  async function bootstrap() {
    try {
      const [h, list] = await Promise.all([getHealth(), listSessions()])
      setHealth(h)
      setSessions(list)
      if (list.length) {
        await loadSession(list[0].id, list)
      } else {
        await startNewChat(false)
      }
    } catch (err) {
      setStatus(`API offline — start backend: uv run uvicorn prism.api.main:app --port 8000`)
      console.error(err)
    }
  }

  async function refreshSessions() {
    const list = await listSessions()
    setSessions(list)
    return list
  }

  async function loadSession(id: string, knownList?: SessionSummary[]) {
    setActiveId(id)
    setPanel(null)
    setStatus('Loading conversation…')
    try {
      const detail = await getSession(id)
      setMessages(turnsToMessages(detail.turns))
      setFormats(
        detail.available_formats?.length
          ? detail.available_formats
          : detail.turns.length
            ? ['prose', 'json', 'xml', 'email']
            : ['prose'],
      )
      if (knownList) setSessions(knownList)
      else await refreshSessions()
      setStatus(detail.turns.length ? 'Conversation loaded' : 'Ready')
    } catch (err) {
      setMessages([])
      setFormats(['prose'])
      setStatus(err instanceof Error ? err.message : 'Failed to load session')
    }
  }

  async function startNewChat(clearMessages = true) {
    const created = await createSession()
    await refreshSessions()
    setActiveId(created.id)
    if (clearMessages) {
      setMessages([])
      setPanel(null)
      setFormats(['prose'])
    }
    setStatus('New conversation')
  }

  async function selectSession(id: string) {
    if (id === activeId) return
    await loadSession(id)
  }

  async function removeSession(id: string) {
    await deleteSession(id)
    const list = await listSessions()
    setSessions(list)
    if (activeId === id) {
      if (list[0]) {
        await loadSession(list[0].id, list)
      } else {
        await startNewChat()
      }
    }
  }

  async function sendMessage(text: string) {
    const message = text.trim()
    if (!message || !activeId || busy) return
    setBusy(true)
    setDraft('')
    setPanel(null)
    setMessages((prev) => [...prev, { id: uid(), role: 'user', content: message }])
    setStatus('Thinking…')
    try {
      const res = await chatStream(activeId, message, (label) => setStatus(label))
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: 'assistant',
          content: res.reply,
          domain: res.domain,
          confidence: res.confidence,
          isClarification: res.is_clarification,
          noAnswer: res.no_answer,
          sources: res.sources,
          availableFormats: res.available_formats,
        },
      ])
      setFormats(res.available_formats.length ? res.available_formats : ['prose'])
      await refreshSessions()
      setStatus(
        res.is_clarification
          ? 'Waiting for clarification'
          : res.no_answer
            ? `No confident answer · ${res.domain ?? 'general'}`
            : `Answered · ${res.domain ?? 'general'} · ${res.confidence ?? 'n/a'} confidence`,
      )
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Chat failed')
    } finally {
      setBusy(false)
    }
  }

  async function onFormat(format: string) {
    if (!activeId || busy) return
    if (format === 'excel') {
      window.open(downloadExcelUrl(activeId), '_blank')
      return
    }
    setBusy(true)
    setStatus(`Rendering ${format}…`)
    try {
      const res = await renderFormat(activeId, format)
      if (res.binary) {
        const url = URL.createObjectURL(res.blob)
        const a = document.createElement('a')
        a.href = url
        a.download = res.filename
        a.click()
        URL.revokeObjectURL(url)
      } else {
        setPanel({ format: res.format, content: String(res.content) })
      }
      setStatus(`Rendered as ${format}`)
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Render failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">Prism</div>
          <div className="brand-sub">Kohler unified enterprise AI · local Ollama</div>
        </div>
        <button className="new-chat" type="button" onClick={() => void startNewChat()}>
          New conversation
        </button>
        <div className="session-list">
          {sessions.map((s) => (
            <div key={s.id} className="session-row">
              <button
                type="button"
                className={`session-item ${s.id === activeId ? 'active' : ''}`}
                onClick={() => void selectSession(s.id)}
              >
                <div className="session-title">{displayTitle(s.title)}</div>
                <div className="session-meta">{s.active_domain?.replaceAll('_', ' ') || 'no domain yet'}</div>
              </button>
              <button
                type="button"
                className="session-delete"
                aria-label="Delete session"
                title="Delete"
                onClick={() => void removeSession(s.id)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
        {health && (
          <div className="sidebar-foot">
            <div>
              {health.chunks_indexed} chunks · {health.gen_model}
            </div>
            <div className={`health-pill ${health.status === 'ok' ? 'ok' : 'degraded'}`}>
              API {health.status}
              {health.ollama && !health.ollama.ok ? ' · Ollama incomplete' : ''}
            </div>
          </div>
        )}
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{displayTitle(activeSession?.title, 'Ask across five domains')}</h1>
            <div className="chips" style={{ marginTop: 8 }}>
              {(health?.domains ?? ['hr', 'finance', 'customer_support', 'privacy', 'legal']).map((d) => (
                <span key={d} className="chip">
                  {d.replaceAll('_', ' ')}
                </span>
              ))}
            </div>
          </div>
        </header>

        <section className="messages">
          {messages.length === 0 ? (
            <div className="empty">
              <h2>One query, any format</h2>
              <p>
                Prism reasons across HR, Finance, Customer Support, Privacy, and Legal — then re-renders the same
                answer as prose, JSON, XML, Excel, or a draft email.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="suggestion" onClick={() => void sendMessage(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={[
                  'bubble',
                  m.role,
                  m.isClarification ? 'clarify' : '',
                  m.noAnswer && !m.isClarification ? 'no-answer' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                <AnswerStateBanner m={m} />
                {m.content}
                {m.role === 'assistant' && (
                  <div className="meta-row">
                    {m.domain && <span className="chip active">{m.domain.replaceAll('_', ' ')}</span>}
                    {m.confidence && (
                      <span className={`chip conf ${confidenceTone(m.confidence)}`}>
                        {m.confidence} confidence
                      </span>
                    )}
                    {m.noAnswer && !m.isClarification && (
                      <span className="chip warn">no confident match</span>
                    )}
                    {m.isClarification && <span className="chip warn">needs clarification</span>}
                  </div>
                )}
                {m.sources && m.sources.length > 0 && (
                  <div className="sources">
                    Sources:{' '}
                    {m.sources.slice(0, 4).map((s, i) => (
                      <span key={s.id}>
                        {i > 0 ? ' · ' : ''}
                        {s.source_url.startsWith('http') ? (
                          <a href={s.source_url} target="_blank" rel="noreferrer">
                            {s.title || s.source_url}
                          </a>
                        ) : (
                          s.title || s.source_url
                        )}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
          {panel && (
            <div className="panel">
              <strong>{panel.format.toUpperCase()}</strong>
              {'\n'}
              {panel.content}
            </div>
          )}
          <div ref={bottomRef} />
        </section>

        <div className="composer-shell">
          <div className="format-bar">
            {FORMATS.map((fmt) => (
              <button
                key={fmt}
                type="button"
                className="format-btn"
                disabled={busy || messages.length === 0 || !formats.includes(fmt)}
                onClick={() => void onFormat(fmt)}
              >
                {fmt}
              </button>
            ))}
          </div>
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault()
              void sendMessage(draft)
            }}
          >
            <textarea
              value={draft}
              placeholder="Ask about leave policy, expense approvals, toilet troubleshooting, privacy, warranties…"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void sendMessage(draft)
                }
              }}
            />
            <button className="send" type="submit" disabled={busy || !draft.trim()}>
              {busy ? '…' : 'Send'}
            </button>
          </form>
          <div className="status-line">{status}</div>
        </div>
      </main>
    </div>
  )
}
