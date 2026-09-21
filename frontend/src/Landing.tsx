import { SUGGESTION_HINT, suggestionsForRole } from './suggestions'
import type { AuthUser } from './api'

type Props = {
  user: AuthUser
  onEnter: () => void
  onTryQuestion: (text: string) => void
  onLogout: () => void
}

const DOMAINS = [
  { id: 'hr', title: 'HR', blurb: 'Leave, probation, WFH' },
  { id: 'finance', title: 'Finance', blurb: 'Approvals, per diem' },
  { id: 'customer_support', title: 'Support', blurb: 'Live Assist repairs' },
  { id: 'privacy', title: 'Privacy', blurb: 'Collection, CCPA' },
  { id: 'legal', title: 'Legal', blurb: 'Warranty, Prop 65' },
  { id: 'uploaded', title: 'Your file', blurb: 'This chat only' },
]

const STEPS = [
  { n: '1', title: 'Ask', body: 'One question across five Kohler domains, or drop a PDF.' },
  { n: '2', title: 'Route', body: 'Anchors pick HR vs Finance vs Support. No extra LLM.' },
  { n: '3', title: 'Retrieve', body: 'Hybrid Chroma + BM25, then one local generation call.' },
  { n: '4', title: 'Render', body: 'Same answer as prose, JSON, XML, Excel, or email.' },
]

const STATS = [
  { n: '5', label: 'domains + upload' },
  { n: '39 / 39', label: 'stress harness' },
  { n: '8 GB', label: 'on-device VRAM' },
  { n: '0', label: 'cloud LLM calls' },
]

export default function Landing({ user, onEnter, onTryQuestion, onLogout }: Props) {
  const suggestions = suggestionsForRole(user.role)
  return (
    <div className="landing">
      <header className="landing-bar">
        <div className="brand-mark">Prism</div>
        <div className="landing-bar-right">
          <span className="role-badge" title={user.email}>
            {user.name} · {user.role.replaceAll('_', ' ')}
          </span>
          <button type="button" className="landing-cta ghost" onClick={onLogout}>
            Log out
          </button>
          <button type="button" className="landing-cta ghost" onClick={onEnter}>
            Open chat
          </button>
        </div>
      </header>

      <section className="landing-hero">
        <p className="landing-kicker">Unified Enterprise AI · Track 3</p>
        <h1>One query, any format.</h1>
        <p className="landing-lead">
          A local agent over HR, Finance, Support, Privacy, and Legal, plus the file you drop in
          chat. Role-gated retrieval, cited sources, and five output skins from one answer. Nothing
          leaves the laptop.
        </p>
        <div className="landing-actions">
          <button type="button" className="landing-cta" onClick={onEnter}>
            Try the live demo
          </button>
          <span className="landing-meta">Ollama on an RTX 5070 · voice in Chrome or Edge</span>
        </div>
        <div className="landing-stats" aria-label="Product proof">
          {STATS.map((s) => (
            <div key={s.label} className="landing-stat">
              <b>{s.n}</b>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-domains" aria-label="Knowledge domains">
        {DOMAINS.map((d) => (
          <article key={d.id} className={`landing-card domain-${d.id}`}>
            <h2>{d.title}</h2>
            <p>{d.blurb}</p>
          </article>
        ))}
      </section>

      <section className="landing-steps" aria-label="How it works">
        {STEPS.map((s) => (
          <article key={s.n} className="landing-step">
            <span className="landing-n">{s.n}</span>
            <h3>{s.title}</h3>
            <p>{s.body}</p>
          </article>
        ))}
      </section>

      <section className="landing-try">
        <h2>Try a question that has to be exact</h2>
        <div className="suggestions landing-suggestions">
          {suggestions.map((s) => (
            <button key={s.text} type="button" className="suggestion" onClick={() => onTryQuestion(s.text)}>
              <span className="suggestion-domain">{s.domain.replaceAll('_', ' ')}</span>
              {s.text}
            </button>
          ))}
        </div>
        <p className="suggestion-hint">{SUGGESTION_HINT}</p>
      </section>

      <footer className="landing-footer">
        Built by Aryan Dani ·{' '}
        <a href="https://www.aryandani.com" target="_blank" rel="noreferrer">
          aryandani.com
        </a>
        {' · '}
        MITWPU AI Research Lab, Track 3
      </footer>
    </div>
  )
}
