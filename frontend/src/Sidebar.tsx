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
  onRemovePrompt,
}: Props) {
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
        {savedPrompts.length === 0 ? (
          <div className="saved-prompts-empty">Save a question to reuse it.</div>
        ) : (
          <div className="saved-prompts-list">
            {savedPrompts.map((p) => (
              <div key={p.id} className="saved-prompt-row">
                <button
                  type="button"
                  className="saved-prompt-item"
                  title={p.body}
                  onClick={() => onUsePrompt(p)}
                >
                  <span className="saved-prompt-title">{p.title}</span>
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
