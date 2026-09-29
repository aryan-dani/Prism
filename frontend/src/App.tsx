import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AuthError,
  chatStream,
  createSavedPrompt,
  createSession,
  deleteSavedPrompt,
  deleteSession,
  deleteUpload,
  downloadExcelBlob,
  getDenials,
  getHealth,
  getSession,
  listSavedPrompts,
  listSessions,
  renameSavedPrompt,
  renderFormat,
  uploadDocument,
  type AuthUser,
  type Health,
  type SavedPrompt,
  type SessionSummary,
  type UploadedDoc,
} from './api'
import ChatHeader from './ChatHeader'
import Composer from './Composer'
import MessageList from './MessageList'
import Sidebar from './Sidebar'
import { suggestionsForRole } from './suggestions'
import {
  displayTitle,
  domainLabel,
  tidyTranscript,
  turnsToMessages,
  uid,
  workflowLabel,
  type Message,
} from './chatUtils'
import './index.css'

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
  const [savedPrompts, setSavedPrompts] = useState<SavedPrompt[]>([])
  const [savingPrompt, setSavingPrompt] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const draftTextareaRef = useRef<HTMLTextAreaElement>(null)
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
    const el = draftTextareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const next = Math.min(el.scrollHeight, 160)
    el.style.height = `${Math.max(next, 36)}px`
    el.classList.toggle('is-multiline', next > 48)
  }, [draft])

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
      e.preventDefault()
      void startNewChat()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  async function bootstrap() {
    try {
      const [h, list, prompts] = await Promise.all([getHealth(), listSessions(), listSavedPrompts()])
      setHealth(h)
      setSessions(list)
      setSavedPrompts(prompts)
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

  async function saveCurrentDraft() {
    const body = draft.trim()
    if (!body || savingPrompt) return
    setSavingPrompt(true)
    setStatus('Saving prompt…')
    try {
      const created = await createSavedPrompt(body)
      setSavedPrompts((prev) => [created, ...prev.filter((p) => p.id !== created.id)])
      setStatus(created.duplicate ? 'Already saved' : 'Prompt saved')
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthLost?.()
        return
      }
      setStatus(err instanceof Error ? err.message : 'Could not save prompt')
    } finally {
      setSavingPrompt(false)
    }
  }

  async function removeSavedPrompt(id: string) {
    try {
      await deleteSavedPrompt(id)
      setSavedPrompts((prev) => prev.filter((p) => p.id !== id))
      setStatus('Saved prompt removed')
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthLost?.()
        return
      }
      setStatus(err instanceof Error ? err.message : 'Could not delete prompt')
    }
  }

  function useSavedPrompt(prompt: SavedPrompt) {
    setDraft(prompt.body)
    setStatus(`Loaded “${prompt.title}”. Edit it, or press Send.`)
    window.requestAnimationFrame(() => draftTextareaRef.current?.focus())
  }

  function runSavedPrompt(prompt: SavedPrompt) {
    if (!activeId) {
      setStatus('Still opening a chat…')
      return
    }
    void sendMessage(prompt.body)
  }

  async function renamePrompt(id: string, title: string) {
    try {
      const updated = await renameSavedPrompt(id, title)
      setSavedPrompts((prev) => prev.map((p) => (p.id === id ? updated : p)))
      setStatus('Prompt renamed')
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthLost?.()
        return
      }
      setStatus(err instanceof Error ? err.message : 'Could not rename prompt')
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

  function stopListening() {
    if (listening && recognitionRef.current) {
      recognitionRef.current.stop()
      setListening(false)
    }
  }

  async function sendMessage(text: string) {
    const message = text.trim()
    if (!message || !activeId || busy) return
    stopListening()
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
      <Sidebar
        user={user}
        health={health}
        denials={denials}
        sessions={sessions}
        filteredSessions={filteredSessions}
        sessionQuery={sessionQuery}
        activeId={activeId}
        savedPrompts={savedPrompts}
        shortcutMod={shortcutMod}
        onHome={onHome}
        onLogout={onLogout}
        onNewChat={() => void startNewChat()}
        onSessionQuery={setSessionQuery}
        onSelectSession={(id) => void selectSession(id)}
        onRemoveSession={(id) => void removeSession(id)}
        onUsePrompt={useSavedPrompt}
        onRunPrompt={runSavedPrompt}
        onRenamePrompt={(id, title) => void renamePrompt(id, title)}
        onRemovePrompt={(id) => void removeSavedPrompt(id)}
      />

      <main className="main">
        <ChatHeader
          title={displayTitle(activeSession?.title, 'Ask across five domains')}
          roleDomains={roleDomains}
          uploadCount={uploads.length}
        />

        <MessageList
          messages={messages}
          emptySuggestions={emptySuggestions}
          copiedId={copiedId}
          speakingId={speakingId}
          showAllSources={showAllSources}
          ttsSupported={ttsSupported}
          onSendSuggestion={(text) => void sendMessage(text)}
          onCopy={(m) => void copyAnswer(m)}
          onSpeak={speakAnswer}
          onToggleSources={(id) =>
            setShowAllSources((prev) => ({ ...prev, [id]: !prev[id] }))
          }
          formatView={panel}
          onCloseFormat={() => setPanel(null)}
        />

        <Composer
          draft={draft}
          busy={busy}
          uploading={uploading}
          savingPrompt={savingPrompt}
          listening={listening}
          dragOver={dragOver}
          activeId={activeId}
          uploads={uploads}
          formats={formats}
          panelFormat={panel?.format ?? null}
          messageCount={messages.length}
          status={status}
          speechSupported={speechSupported}
          ttsSupported={ttsSupported}
          fileInputRef={fileInputRef}
          draftTextareaRef={draftTextareaRef}
          onDraftChange={setDraft}
          onSend={() => void sendMessage(draft)}
          onFormat={(id) => void onFormat(id)}
          onAttachClick={() => fileInputRef.current?.click()}
          onFiles={(files) => void attachFiles(files)}
          onRemoveUpload={(id) => void removeUpload(id)}
          onToggleMic={toggleMic}
          onSavePrompt={() => void saveCurrentDraft()}
          onDragOver={setDragOver}
          onDropFiles={(files) => void attachFiles(files)}
        />
      </main>
    </div>
  )
}
