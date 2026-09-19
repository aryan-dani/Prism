import { SUGGESTION_HINT, SUGGESTIONS } from './suggestions'

type Props = {
  onEnter: () => void
  onTryQuestion: (text: string) => void
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

export default function Landing({ onEnter, onTryQuestion }: Props) {
  return (
    <div className="landing">
      <header className="landing-bar">
        <div className="brand-mark">Prism</div>
        <button type="button" className="landing-cta ghost" onClick={onEnter}>
          Open chat
        </button>
      </header>

      <section className="landing-hero">
        <p className="landing-kicker">Kohler Unified Enterprise AI · Track 3</p>
        <h1>One query, any format.</h1>
        <p className="landing-lead">
          A local conversational agent over HR, Finance, Customer Support, Privacy, and Legal — plus a
          document you attach in this chat. Answers stay on the machine. Reformats never re-ask the model.
        </p>
        <div className="landing-actions">
          <button type="button" className="landing-cta" onClick={onEnter}>
            Try the live demo
          </button>
          <span className="landing-meta">Runs on Ollama · 8GB VRAM · no cloud LLM</span>
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
        <h2>Start with a question judges actually care about</h2>
        <div className="suggestions landing-suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s.text} type="button" className="suggestion" onClick={() => onTryQuestion(s.text)}>
              <span className="suggestion-domain">{s.domain.replaceAll('_', ' ')}</span>
              {s.text}
            </button>
          ))}
        </div>
        <p className="suggestion-hint">{SUGGESTION_HINT}</p>
      </section>
    </div>
  )
}
