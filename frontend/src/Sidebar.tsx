import { useMemo, useRef, useState } from 'react'
import type { AuthUser, Health, SavedPrompt, SessionSummary } from './api'
import { displayTitle, domainLabel } from './chatUtils'

function DomainPip({ domain }: { domain?: string | null }) {
  const key = domain || 'none'
  return <span className={`domain-pip domain-${key}`} aria-hidden />
}

type Denial = { ts: string; email: string; role: string; query: string; reason: string }

type Props = {
  user: AuthUser
  health: Health | null
  denials: Denial[]
  sessions: SessionSummary[]
  filteredSessions: SessionSummary[]
  sessionQuery: string
  activeId: string | null
  savedPrompts: SavedPrompt[]
  shortcutMod: string
  onHome?: () => void
  onLogout?: () => void
  onNewChat: () => void
  onSessionQuery: (q: string) => void
  onSelectSession: (id: string) => void
  onRemoveSession: (id: string) => void
  onUsePrompt: (p: SavedPrompt) => void
  onRunPrompt: (p: SavedPrompt) => void
  onRenamePrompt: (id: string, title: string) => void
  onRemovePrompt: (id: string) => void
}

export default function Sidebar({
  user,
  health,
  denials,
  sessions,
  filteredSessions,
  sessionQuery,
  activeId,
  savedPrompts,
  shortcutMod,
  onHome,
  onLogout,
  onNewChat,
  onSessionQuery,
  onSelectSession,
  onRemoveSession,
  onUsePrompt,
  onRunPrompt,
  onRenamePrompt,
  onRemovePrompt,
}: Props) {
  const [promptQuery, setPromptQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [titleDraft, setTitleDraft] = useState('')
  const skipRenameBlur = useRef(false)

  const filteredPrompts = useMemo(() => {
    const q = promptQuery.trim().toLowerCase()
    if (!q) return savedPrompts
    return savedPrompts.filter(
      (p) => p.title.toLowerCase().includes(q) || p.body.toLowerCase().includes(q),
    )
  }, [savedPrompts, promptQuery])

  function commitRename(prompt: SavedPrompt) {
    const next = titleDraft.trim()
    setEditingId(null)
    if (!next || next === prompt.title) return
    onRenamePrompt(prompt.id, next)
  }
  return (
    <aside className="sidebar">
      <div className="brand">
        <button type="button" className="brand-home" onClick={onHome} title="Back to overview">
          <div className="brand-mark">Prism</div>
          <div className="brand-sub">Local enterprise knowledge · Ollama</div>
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

      <button className="new-chat" type="button" onClick={onNewChat}>
        New conversation
        <span className="new-chat-hint">{shortcutMod}+K</span>
      </button>

      <div className="sidebar-section">
        <p className="section-label">Sessions</p>
        <input
          className="session-search"
          type="search"
          value={sessionQuery}
          placeholder="Search sessions…"
          aria-label="Search sessions"
          onChange={(e) => onSessionQuery(e.target.value)}
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
                  onClick={() => onSelectSession(s.id)}
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
                  onClick={() => onRemoveSession(s.id)}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="saved-prompts" aria-label="Saved prompts">
        <p className="section-label">Saved prompts</p>
        <input
          className="session-search"
          type="search"
          value={promptQuery}
          placeholder="Search saved prompts…"
          aria-label="Search saved prompts"
          onChange={(e) => setPromptQuery(e.target.value)}
        />
        {filteredPrompts.length === 0 ? (
          <div className="saved-prompts-empty">
            {savedPrompts.length === 0 ? 'Save a question to reuse it.' : 'No saved prompts match that search'}
          </div>
        ) : (
          <div className="saved-prompts-list">
            {filteredPrompts.map((p) => (
              <div key={p.id} className="saved-prompt-row">
                {editingId === p.id ? (
                  <form
                    className="saved-prompt-rename"
                    onSubmit={(e) => {
                      e.preventDefault()
                      commitRename(p)
                    }}
                  >
                    <input
                      className="saved-prompt-title-input"
                      value={titleDraft}
                      autoFocus
                      aria-label="Rename saved prompt"
                      onChange={(e) => setTitleDraft(e.target.value)}
                      onBlur={() => {
                        if (skipRenameBlur.current) {
                          skipRenameBlur.current = false
                          return
                        }
                        commitRename(p)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') {
                          e.preventDefault()
                          skipRenameBlur.current = true
                          setEditingId(null)
                        }
                      }}
                    />
                  </form>
                ) : (
                  <>
                    <button
                      type="button"
                      className="saved-prompt-item"
                      title={`${p.body}\n\nClick to load. Double-click to rename.`}
                      onClick={() => onUsePrompt(p)}
                      onDoubleClick={() => {
                        setEditingId(p.id)
                        setTitleDraft(p.title)
                      }}
                    >
                      <span className="saved-prompt-title">{p.title}</span>
                    </button>
                    <div className="saved-prompt-actions">
                      <button
                        type="button"
                        className="saved-prompt-run"
                        title="Send this question now"
                        onClick={() => onRunPrompt(p)}
                      >
                        Run
                      </button>
                      <button
                        type="button"
                        className="session-delete"
                        aria-label={`Delete saved prompt ${p.title}`}
                        title="Delete"
                        onClick={() => onRemovePrompt(p.id)}
                      >
                        ×
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="sidebar-foot">
        {health && (
          <div className="sidebar-health">
            <span className={`health-pill ${health.status === 'ok' ? 'ok' : 'degraded'}`}>
              {health.status === 'ok'
                ? 'API ok'
                : !health.ollama?.reachable
                  ? 'Ollama down'
                  : health.ollama?.models_missing?.length
                    ? `Missing ${health.ollama.models_missing[0]}`
                    : 'Degraded'}
            </span>
            <span className="sidebar-health-meta">{health.chunks_indexed} chunks</span>
          </div>
        )}
        {denials.length > 0 && (
          <div className="denials-box" title="RBAC denials log (staff only)">
            <strong>Recent denials</strong>
            {denials.slice(0, 3).map((d, i) => (
              <div key={`${d.ts}-${i}`} className="denial-row">
                <span className="denial-meta">
                  {d.role} · {d.email.split('@')[0]}
                </span>
                <span className="denial-q">{d.query.slice(0, 64)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
