import { SUGGESTION_HINT, suggestionsForRole } from './suggestions'
import type { AuthUser } from './api'

type Props = {
  user: AuthUser
  onEnter: () => void
  onTryQuestion: (text: string) => void
  onLogout: () => void
}

const DOMAINS = [
  { id: 'hr', title: 'HR', blurb: 'Leave, probation, WFH, grievances' },
  { id: 'finance', title: 'Finance', blurb: 'Approvals, per diem, CapEx' },
  { id: 'customer_support', title: 'Support', blurb: 'Real Assist troubleshooting' },
  { id: 'privacy', title: 'Privacy', blurb: 'Collection, CCPA, rights' },
  { id: 'legal', title: 'Legal', blurb: 'Warranty, terms, Prop 65' },
  { id: 'uploaded', title: 'Your file', blurb: 'Session-only 6th domain' },
]

const STEPS = [
  { n: '1', title: 'Ask', body: 'One question across five Kohler domains — or drop a PDF.' },
  { n: '2', title: 'Route', body: 'Embedding anchors pick HR vs Finance vs Support. No extra LLM.' },
  { n: '3', title: 'Retrieve', body: 'Hybrid Chroma + BM25, fused, then one local generation call.' },
  { n: '4', title: 'Render', body: 'Same answer as prose, JSON, XML, Excel, or a draft email.' },
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
        <p className="landing-kicker">Kohler Unified Enterprise AI · Track 3</p>
        <h1>One query, any format.</h1>
        <p className="landing-lead">
          A local conversational agent over HR, Finance, Customer Support, Privacy, and Legal — plus a
          document you attach in this chat. Role-based login, cited sources, documented prompts, and
          browser voice (mic + speak). Answers stay on the machine. Reformats never re-ask the model.
        </p>
        <div className="landing-actions">
          <button type="button" className="landing-cta" onClick={onEnter}>
            Try the live demo
          </button>
          <span className="landing-meta">Runs on Ollama · 8GB VRAM · voice in Chrome/Edge</span>
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
        <h2>Try it — a few questions that show what Prism can do</h2>
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
        Kohler-MITWPU AI Research Lab, Track 3
      </footer>
    </div>
  )
}
