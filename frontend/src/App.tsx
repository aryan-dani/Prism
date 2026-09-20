import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AuthError,
  chatStream,
  createSession,
  deleteSession,
  deleteUpload,
  downloadExcelBlob,
  getDenials,
  getHealth,
  getSession,
  listSessions,
  renderFormat,
  uploadDocument,
  type AuthUser,
  type ChatResponse,
  type Health,
  type SessionSummary,
  type UploadedDoc,
} from './api'
import AnswerBody from './AnswerBody'
import FormatPanel from './FormatPanel'
import { SUGGESTION_HINT, suggestionsForRole } from './suggestions'
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
  sustainabilityNote?: string | null
  workflow?: string | null
  promptDoc?: string | null
}

const FORMATS = [
  { id: 'prose', label: 'Prose' },
  { id: 'json', label: 'JSON' },
  { id: 'xml', label: 'XML' },
  { id: 'excel', label: 'Excel' },
  { id: 'email', label: 'Email' },
] as const

const UPLOAD_ACCEPT = '.pdf,.txt,.md,.markdown,.csv,.json,.html,.htm,.docx'

const WORKFLOW_LABELS: Record<string, string> = {
  rag_canonical: 'RAG + system prompt',
  rag_email: 'RAG → email render',
  policy_math: 'Deterministic policy_math',
  rbac_deny: 'RBAC denial',
  jailbreak_refuse: 'Jailbreak refuse',
  policy_override_refuse: 'Policy-override refuse',
  reformat: 'Reformat last answer',
  clarify: 'Clarification',
  session_memory: 'Session memory',
  session_email_recall: 'Session email recall',
  upload_rag: 'Uploaded-doc RAG',
}

function workflowLabel(id?: string | null): string {
  if (!id) return ''
  return WORKFLOW_LABELS[id] ?? id.replaceAll('_', ' ')
}

/** Browser Web Speech (Chrome/Edge). Absent → voice controls stay hidden. */
function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

type SpeechRecognitionLike = {
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  lang: string
  onresult: ((ev: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null
  onerror: ((ev: { error?: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

function uid() {
  return crypto.randomUUID()
}

function domainLabel(d: string | null | undefined): string {
  if (!d) return ''
  if (d === 'uploaded') return 'Upload'
  if (d === 'customer_support') return 'Support'
  return d.replaceAll('_', ' ')
}

function DomainPip({ domain }: { domain?: string | null }) {
  const key = domain || 'none'
  return <span className={`domain-pip domain-${key}`} aria-hidden />
}

function formatBytes(n?: number): string {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

/** Keep sidebar/topbar titles human-readable when the titler returns junk. */
function displayTitle(raw: string | null | undefined, fallback = 'Untitled chat'): string {
  let t = (raw ?? '').trim()
  if (!t) return fallback
  if (t.startsWith('{') || t.startsWith('[') || t.includes('"entitlement') || t.includes('"risk_level"')) {
    return 'Structured answer request'
  }
  if (
    /generate short descriptive/i.test(t) ||
    /chat titles/i.test(t) ||
    /provide (a )?summary/i.test(t) ||
    /user request/i.test(t) ||
    /not enough info/i.test(t)
  ) {
    return fallback
  }
  if (!t.includes(' ') && (t.match(/[A-Z]/g)?.length ?? 0) >= 3) {
    t = t.replace(/([a-z])([A-Z])/g, '$1 $2')
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

function tidyTranscript(text: string): string {
  const squeezed = text.replace(/\s+/g, ' ').trim()
  if (!squeezed) return ''
  const sentences = squeezed.split(/(?<=[.!?])\s+/).filter(Boolean)
  const out: string[] = []
  for (const raw of sentences) {
    const s = raw.trim()
    const prev = out[out.length - 1]
    const norm = (v: string) => v.toLowerCase().replace(/[.!?]+$/g, '').trim()
    if (prev && norm(prev) === norm(s)) continue
    out.push(s)
  }
  return out.join(' ').replace(/\b(\w+)(?:\s+\1){1,}\b/gi, '$1')
}

function AnswerStateBanner({ m }: { m: Message }) {
  if (m.role !== 'assistant') return null
  if (m.isClarification) {
    return (
      <div className="answer-banner clarify-banner" role="status">
        Clarification needed. Pick a domain or rephrase so Prism can route correctly.
      </div>
    )
  }
  if (m.noAnswer) {
    return (
      <div className="answer-banner honesty-banner" role="status">
        No confident match in the knowledge base. Refusing to invent an answer.
      </div>
    )
  }
  return null
}

export default function App({
  user,
  onHome,
  onLogout,
  onAuthLost,
  seedQuestion,
}: {
  user: AuthUser
  onHome?: () => void
  onLogout?: () => void
  onAuthLost?: () => void
  seedQuestion?: string | null
}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [status, setStatus] = useState('Ready')
  const [panel, setPanel] = useState<{ format: string; content: string } | null>(null)
  const [formats, setFormats] = useState<string[]>(['prose'])
  const [uploads, setUploads] = useState<UploadedDoc[]>([])
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [sessionQuery, setSessionQuery] = useState('')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [denials, setDenials] = useState<
    Array<{ ts: string; email: string; role: string; query: string; reason: string }>
  >([])
  const [listening, setListening] = useState(false)
  const [speakingId, setSpeakingId] = useState<string | null>(null)
  const [showAllSources, setShowAllSources] = useState<Record<string, boolean>>({})
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const draftBaseRef = useRef('')

  const speechSupported = useMemo(() => typeof window !== 'undefined' && !!getSpeechRecognitionCtor(), [])
  const ttsSupported = useMemo(
    () => typeof window !== 'undefined' && typeof window.speechSynthesis !== 'undefined',
    [],
  )

  const roleDomains = useMemo(() => {
    if (user.role === 'customer') return ['customer_support', 'privacy', 'legal']
    return ['hr', 'finance', 'customer_support', 'privacy', 'legal']
  }, [user.role])

  const emptySuggestions = useMemo(() => suggestionsForRole(user.role), [user.role])

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId],
  )

  const filteredSessions = useMemo(() => {
    const q = sessionQuery.trim().toLowerCase()
    if (!q) return sessions
    return sessions.filter((s) => {
      const title = displayTitle(s.title).toLowerCase()
      const domain = domainLabel(s.active_domain).toLowerCase()
      return title.includes(q) || domain.includes(q) || s.id.toLowerCase().includes(q)
    })
  }, [sessions, sessionQuery])

  const shortcutMod = useMemo(
    () => (typeof navigator !== 'undefined' && /Mac|iPhone|iPad/i.test(navigator.platform) ? '⌘' : 'Ctrl'),
    [],
  )

  useEffect(() => {
    void bootstrap()
  }, [])

  useEffect(() => {
    if (seedQuestion) setDraft(seedQuestion)
  }, [seedQuestion])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, panel])

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.abort()
      } catch {
        /* ignore */
      }
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
    }
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'k') return
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        // Still allow Ctrl/Cmd+K from composer. It is the new-chat shortcut.
      }
      e.preventDefault()
      void startNewChat()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  async function bootstrap() {
    try {
      const [h, list] = await Promise.all([getHealth(), listSessions()])
      setHealth(h)
      setSessions(list)
      if (user.role === 'hr_staff' || user.role === 'finance_staff') {
        try {
          const d = await getDenials()
          setDenials(d.denials.slice(0, 8))
        } catch {
          setDenials([])
        }
      }
      if (list.length) {
        await loadSession(list[0].id, list)
      } else {
        await startNewChat(false)
      }
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthLost?.()
        return
      }
      setStatus(`API offline. Start backend: uv run uvicorn prism.api.main:app --port 8000`)
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
      setUploads(detail.uploaded_docs ?? [])
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
      setUploads([])
      setStatus(err instanceof Error ? err.message : 'Failed to load session')
    }
  }

  async function startNewChat(clearMessages = true) {
    const created = await createSession()
    await refreshSessions()
    setActiveId(created.id)
    setUploads([])
    if (clearMessages) {
      setMessages([])
      setPanel(null)
      setFormats(['prose'])
    }
    setStatus('New conversation')
  }

  async function attachFiles(files: FileList | File[] | null) {
    if (!files || !activeId || uploading) return
    const list = Array.from(files)
    if (!list.length) return
    setUploading(true)
    for (const file of list) {
      setStatus(`Indexing ${file.name} locally…`)
      try {
        const res = await uploadDocument(activeId, file)
        setUploads(res.uploaded_docs)
        setStatus(`Attached ${res.filename} · ${res.chunk_count} chunks · stays on this machine`)
      } catch (err) {
        setStatus(err instanceof Error ? `Upload failed: ${err.message}` : 'Upload failed')
      }
    }
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function removeUpload(docId: string) {
    if (!activeId) return
    try {
      const res = await deleteUpload(activeId, docId)
      setUploads(res.uploaded_docs)
      setStatus('Removed attached document. Its vectors were purged.')
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Failed to remove document')
    }
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
          sustainabilityNote: res.sustainability_note ?? null,
          workflow: res.workflow ?? null,
          promptDoc: res.prompt_doc ?? 'docs/prompts.md',
        },
      ])
      setFormats(res.available_formats.length ? res.available_formats : ['prose'])
      if (res.title) {
        setSessions((prev) =>
          prev.map((s) => (s.id === activeId ? { ...s, title: res.title } : s)),
        )
      }
      await refreshSessions()
      const wf = workflowLabel(res.workflow)
      setStatus(
        res.is_clarification
          ? 'Waiting for clarification'
          : res.no_answer
            ? `No confident answer · ${domainLabel(res.domain) || 'general'}${wf ? ` · ${wf}` : ''}`
            : `Answered · ${domainLabel(res.domain) || 'general'} · ${res.confidence ?? 'n/a'} confidence${wf ? ` · ${wf}` : ''}`,
      )
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthLost?.()
        return
      }
      setStatus(err instanceof Error ? err.message : 'Chat failed')
    } finally {
      setBusy(false)
    }
  }

  async function onFormat(format: string) {
    if (!activeId || busy) return
    if (format === 'prose') {
      setPanel(null)
      setStatus('Showing prose answer')
      return
    }
    if (panel?.format === format && format !== 'excel') {
      setPanel(null)
      return
    }
    if (format === 'excel') {
      try {
        const blob = await downloadExcelBlob(activeId)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'prism_answer.xlsx'
        a.click()
        URL.revokeObjectURL(url)
        setPanel({ format: 'excel', content: 'prism_answer.xlsx' })
        setStatus('Downloaded Excel')
      } catch (err) {
        if (err instanceof AuthError) onAuthLost?.()
        else setStatus(err instanceof Error ? err.message : 'Excel download failed')
      }
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
        setPanel({ format: res.format, content: res.filename })
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

  async function copyAnswer(m: Message) {
    const text = m.sustainabilityNote
      ? `${m.content.replace(m.sustainabilityNote, '').trim()}\n\n${m.sustainabilityNote}`.trim()
      : m.content
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(m.id)
      setStatus('Answer copied')
      window.setTimeout(() => setCopiedId((id) => (id === m.id ? null : id)), 1600)
    } catch {
      setStatus('Copy failed. Clipboard permission denied.')
    }
  }

  function stopSpeaking() {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    setSpeakingId(null)
  }

  function speakAnswer(m: Message) {
    if (!ttsSupported) {
      setStatus('Text-to-speech not supported in this browser. Try Chrome or Edge.')
      return
    }
    if (speakingId === m.id) {
      stopSpeaking()
      return
    }
    stopSpeaking()
    const text = m.content.replace(/\s+/g, ' ').trim()
    if (!text) return
    const utter = new SpeechSynthesisUtterance(text)
    utter.rate = 1
    utter.onend = () => setSpeakingId((id) => (id === m.id ? null : id))
    utter.onerror = () => setSpeakingId(null)
    setSpeakingId(m.id)
    window.speechSynthesis.speak(utter)
  }

  function toggleMic() {
    const Ctor = getSpeechRecognitionCtor()
    if (!Ctor) {
      setStatus('Voice input not supported here. Use Chrome or Edge.')
      return
    }
    if (listening && recognitionRef.current) {
      recognitionRef.current.stop()
      setListening(false)
      return
    }
    draftBaseRef.current = draft.trim()
    const rec = new Ctor()
    recognitionRef.current = rec
    rec.continuous = true
    rec.interimResults = true
    rec.maxAlternatives = 1
    rec.lang = 'en-IN'
    rec.onresult = (ev) => {
      let spoken = ''
      let interim = ''
      for (let i = 0; i < ev.results.length; i++) {
        const piece = ev.results[i][0]?.transcript?.trim() ?? ''
        if (!piece) continue
        if (ev.results[i].isFinal) spoken = spoken ? `${spoken} ${piece}` : piece
        else interim = interim ? `${interim} ${piece}` : piece
      }
      const combined = [draftBaseRef.current, tidyTranscript(spoken), interim]
        .filter(Boolean)
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim()
      setDraft(combined)
    }
    rec.onerror = (ev) => {
      setListening(false)
      if (ev.error === 'not-allowed') setStatus('Microphone permission denied')
      else if (ev.error !== 'aborted') setStatus(`Voice input error: ${ev.error ?? 'unknown'}`)
    }
    rec.onend = () => setListening(false)
    try {
      rec.start()
      setListening(true)
      setStatus('Listening… speak your question, then stop the mic or press Send')
    } catch {
      setStatus('Could not start microphone')
      setListening(false)
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <button type="button" className="brand-home" onClick={onHome} title="Back to overview">
            <div className="brand-mark">Prism</div>
            <div className="brand-sub">Kohler unified enterprise AI · local Ollama</div>
          </button>
          <div className="user-chip">
            <span className="role-badge">
              {user.name} · {user.role.replaceAll('_', ' ')}
            </span>
            <button type="button" className="logout-btn" onClick={onLogout}>
              Log out
            </button>
          </div>
        </div>
        <button className="new-chat" type="button" onClick={() => void startNewChat()}>
          New conversation
          <span className="new-chat-hint">{shortcutMod}+K</span>
        </button>
        <input
          className="session-search"
          type="search"
          value={sessionQuery}
          placeholder="Search sessions…"
          aria-label="Search sessions"
          onChange={(e) => setSessionQuery(e.target.value)}
        />
        <div className="session-list">
          {filteredSessions.length === 0 ? (
            <div className="session-empty">
              {sessions.length === 0 ? 'No conversations yet' : 'No sessions match that search'}
            </div>
          ) : (
            filteredSessions.map((s) => (
              <div key={s.id} className="session-row">
                <button
                  type="button"
                  className={`session-item ${s.id === activeId ? 'active' : ''}`}
                  onClick={() => void selectSession(s.id)}
                >
                  <div className="session-title">{displayTitle(s.title)}</div>
                  <div className="session-meta">
                    <DomainPip domain={s.active_domain} />
                    {domainLabel(s.active_domain) || 'New'}
                  </div>
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
            ))
          )}
        </div>
        <div className="sidebar-foot">
          {health && (
            <>
              <div>
                {health.chunks_indexed} chunks · {health.gen_model}
              </div>
              <div className={`health-pill ${health.status === 'ok' ? 'ok' : 'degraded'}`}>
                {health.status === 'ok'
                  ? 'API ok'
                  : !health.ollama?.reachable
                    ? 'Ollama not running'
                    : health.ollama?.models_missing?.length
                      ? `Ollama missing ${health.ollama.models_missing[0]}`
                      : 'API degraded'}
              </div>
            </>
          )}
          <div className="sidebar-credit">
            Built by Aryan Dani ·{' '}
            <a href="https://www.aryandani.com" target="_blank" rel="noreferrer">
              aryandani.com
            </a>
          </div>
          {denials.length > 0 && (
            <div className="denials-box" title="RBAC denials log (staff only)">
              <strong>Recent denials</strong>
              {denials.slice(0, 5).map((d, i) => (
                <div key={`${d.ts}-${i}`} className="denial-row">
                  <span className="denial-meta">
                    {d.role} · {d.email.split('@')[0]}
                  </span>
                  <span className="denial-q">{d.query.slice(0, 80)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{displayTitle(activeSession?.title, 'Ask across five domains')}</h1>
            <div className="chips" style={{ marginTop: 8 }}>
              {roleDomains.map((d) => (
                <span key={d} className="chip">
                  {domainLabel(d)}
                </span>
              ))}
              {uploads.length > 0 && (
                <span className="chip upload-domain" title="Session-scoped, purged when this chat is deleted">
                  + uploaded doc{uploads.length > 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
        </header>

        <section className="messages">
          {messages.length === 0 ? (
            <div className="empty">
              <h2>One query, any format</h2>
              <p>
                Ask across five domains, or drop a file. Same answer as prose, JSON, XML, Excel, or email.
                Every reply cites sources and the workflow id.
              </p>
              <div className="suggestions">
                {emptySuggestions.map((s) => (
                  <button key={s.text} type="button" className="suggestion" onClick={() => void sendMessage(s.text)}>
                    <span className="suggestion-domain">{s.domain.replaceAll('_', ' ')}</span>
                    {s.text}
                  </button>
                ))}
              </div>
              <p className="suggestion-hint">{SUGGESTION_HINT}</p>
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
                {m.role === 'assistant' ? (
                  <AnswerBody
                    text={
                      m.sustainabilityNote
                        ? m.content.replace(m.sustainabilityNote, '').trim()
                        : m.content
                    }
                  />
                ) : (
                  m.content
                )}
                {m.sustainabilityNote && (
                  <div className="water-callout" role="note">
                    <strong>Water conservation</strong>
                    {m.sustainabilityNote}
                  </div>
                )}
                {m.role === 'assistant' && (
                  <div className="meta-row">
                    {m.domain && (
                      <span className={`chip active${m.domain === 'uploaded' ? ' upload-domain' : ''}`}>
                        {domainLabel(m.domain)}
                      </span>
                    )}
                    {m.confidence && (
                      <span className={`chip conf ${confidenceTone(m.confidence)}`}>
                        {m.confidence} confidence
                      </span>
                    )}
                    {m.noAnswer && !m.isClarification && (
                      <span className="chip warn">no confident match</span>
                    )}
                    {m.isClarification && <span className="chip warn">needs clarification</span>}
                    {m.workflow && (
                      <span className="chip workflow" title={`Documented in ${m.promptDoc || 'docs/prompts.md'}`}>
                        {workflowLabel(m.workflow)}
                      </span>
                    )}
                    <button
                      type="button"
                      className={`copy-btn${copiedId === m.id ? ' copied' : ''}`}
                      onClick={() => void copyAnswer(m)}
                    >
                      {copiedId === m.id ? 'Copied' : 'Copy'}
                    </button>
                    {ttsSupported && (
                      <button
                        type="button"
                        className={`speak-btn${speakingId === m.id ? ' speaking' : ''}`}
                        onClick={() => speakAnswer(m)}
                        title={speakingId === m.id ? 'Stop speaking' : 'Speak answer'}
                        aria-label={speakingId === m.id ? 'Stop speaking' : 'Speak answer'}
                      >
                        {speakingId === m.id ? 'Stop' : 'Speak'}
                      </button>
                    )}
                  </div>
                )}
                {m.role === 'assistant' && (m.workflow || (m.sources && m.sources.length > 0)) && (
                  <div className="cite-block">
                    {m.sources && m.sources.length > 0 && (
                      <div className="sources">
                        <div className="sources-label">Sources</div>
                        <ul className="sources-list">
                          {(showAllSources[m.id] ? m.sources : m.sources.slice(0, 3)).map((s) => (
                            <li key={s.id}>
                              {s.domain ? (
                                <span className="source-domain">{domainLabel(s.domain)}</span>
                              ) : null}
                              {s.source_url.startsWith('http') ? (
                                <a href={s.source_url} target="_blank" rel="noreferrer">
                                  {s.title || s.source_url}
                                </a>
                              ) : (
                                <span>{s.title || s.source_url}</span>
                              )}
                            </li>
                          ))}
                        </ul>
                        {m.sources.length > 3 && (
                          <button
                            type="button"
                            className="sources-more"
                            onClick={() =>
                              setShowAllSources((prev) => ({ ...prev, [m.id]: !prev[m.id] }))
                            }
                          >
                            {showAllSources[m.id] ? 'Show fewer' : `Show all ${m.sources.length}`}
                          </button>
                        )}
                      </div>
                    )}
                    {m.workflow && (
                      <div className="prompt-cite">
                        Prompt / workflow: <code>{m.workflow}</code>
                        {' · '}
                        documented in <code>{m.promptDoc || 'docs/prompts.md'}</code>
                        {' '}(system prompt in <code>prism/core/answer.py</code>)
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
          {panel && (
            <FormatPanel format={panel.format} content={panel.content} onClose={() => setPanel(null)} />
          )}
          <div ref={bottomRef} />
        </section>

        <div
          className={`composer-shell${dragOver ? ' drag-over' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            if (!dragOver) setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            void attachFiles(e.dataTransfer.files)
          }}
        >
          {uploads.length > 0 && (
            <div className="upload-row" aria-label="Attached documents">
              {uploads.map((u) => (
                <span key={u.id} className="upload-chip" title={`${u.chunk_count ?? 0} chunks · ${formatBytes(u.bytes_size)}`}>
                  <span className="upload-icon" aria-hidden>
                    ▤
                  </span>
                  <span className="upload-name">{u.filename}</span>
                  <span className="upload-state">active</span>
                  <button
                    type="button"
                    className="upload-remove"
                    aria-label={`Remove ${u.filename}`}
                    title="Remove and purge"
                    onClick={() => void removeUpload(u.id)}
                  >
                    ×
                  </button>
                </span>
              ))}
              <span className="upload-note">Local only · purged with this chat</span>
            </div>
          )}
          <div className="format-bar" role="toolbar" aria-label="Re-render last answer">
            {FORMATS.map((fmt) => (
              <button
                key={fmt.id}
                type="button"
                className={`format-btn format-${fmt.id}${
                  (fmt.id === 'prose' && !panel) || panel?.format === fmt.id ? ' is-active' : ''
                }`}
                disabled={busy || messages.length === 0 || !formats.includes(fmt.id)}
                aria-pressed={(fmt.id === 'prose' && !panel) || panel?.format === fmt.id}
                onClick={() => void onFormat(fmt.id)}
              >
                {fmt.label}
              </button>
            ))}
          </div>
          <form
            className={`composer${listening ? ' is-listening' : ''}`}
            onSubmit={(e) => {
              e.preventDefault()
              void sendMessage(draft)
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={UPLOAD_ACCEPT}
              multiple
              hidden
              onChange={(e) => void attachFiles(e.target.files)}
            />
            <button
              type="button"
              className="icon-btn attach"
              title="Attach a document for this chat only"
              aria-label="Attach document"
              disabled={busy || uploading || !activeId}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? '…' : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              )}
            </button>
            <textarea
              rows={1}
              value={draft}
              placeholder={
                listening
                  ? 'Listening…'
                  : uploads.length
                    ? 'Ask about the attached file, or anything across the five domains'
                    : 'Ask about leave, expenses, warranties, privacy… or drop a file'
              }
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  if (listening && recognitionRef.current) {
                    recognitionRef.current.stop()
                    setListening(false)
                  }
                  void sendMessage(draft)
                }
              }}
            />
            <div className="composer-actions">
              {speechSupported && (
                <button
                  type="button"
                  className={`icon-btn mic-btn${listening ? ' listening' : ''}`}
                  title={listening ? 'Stop listening' : 'Dictate with microphone'}
                  aria-label={listening ? 'Stop listening' : 'Dictate with microphone'}
                  aria-pressed={listening}
                  disabled={busy || !activeId}
                  onClick={() => toggleMic()}
                >
                  {listening ? (
                    <span className="mic-dot" aria-hidden />
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                      <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" strokeWidth="2" />
                      <path d="M6 11a6 6 0 0 0 12 0M12 17v3M9 20h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  )}
                </button>
              )}
              <button className="send" type="submit" disabled={busy || !draft.trim()}>
                Send
              </button>
            </div>
          </form>
          <div className="status-line">
            {listening ? (
              <span className="listening-hint">Listening. Click the mic to stop, or press Send.</span>
            ) : (
              <>
                {status ? <span>{status}</span> : null}
                {!status && (speechSupported || ttsSupported) ? (
                  <span className="voice-hint">Voice in Chrome or Edge</span>
                ) : null}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
