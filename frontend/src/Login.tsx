import { useEffect, useMemo, useState } from 'react'
import { getDemoUsers, login, type DemoUsersResponse } from './api'

type Props = {
  onLoggedIn: () => void
  checking?: boolean
}

const ROLE_LABEL: Record<string, string> = {
  customer: 'Customer',
  general_employee: 'Employee',
  hr_staff: 'HR staff',
  finance_staff: 'Finance staff',
}

const ROLE_BLURB: Record<string, string> = {
  customer: 'Support, Privacy, Legal only',
  general_employee: 'Policies across all five domains',
  hr_staff: 'Plus named leave records',
  finance_staff: 'Plus CTC and compensation',
}

export default function Login({ onLoggedIn, checking = false }: Props) {
  const [email, setEmail] = useState('alex.employee@prism.local')
  const [password, setPassword] = useState('Prism2026!')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [demo, setDemo] = useState<DemoUsersResponse | null>(null)

  useEffect(() => {
    if (checking) return
    void getDemoUsers()
      .then(setDemo)
      .catch(() => setDemo(null))
  }, [checking])

  const roleCards = useMemo(() => {
    if (!demo) return []
    const preferred = new Map(demo.users.map((u) => [u.role, u]))
    const alex = demo.users.find((u) => u.email === 'alex.employee@prism.local')
    if (alex) preferred.set(alex.role, alex)
    return ['customer', 'general_employee', 'hr_staff', 'finance_staff']
      .map((role) => preferred.get(role))
      .filter((u): u is DemoUsersResponse['users'][number] => Boolean(u))
  }, [demo])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      onLoggedIn()
    } catch (err) {
      const raw = err instanceof Error ? err.message : 'Login failed'
      setError(
        /<\/?[a-z][\s\S]*>/i.test(raw) || /bad gateway/i.test(raw)
          ? 'API unreachable. Wait for the backend to finish starting, then try again.'
          : raw,
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-shell">
      <section className="login-brand anim-fade-up" aria-label="Prism">
        <p className="login-kicker">Unified Enterprise AI · Track 3</p>
        <div className="brand-mark login-brand-mark">Prism</div>
        <p className="login-brand-lead">
          One local front door for HR, Finance, Support, Privacy, and Legal. Role-gated retrieval.
          Nothing leaves the laptop.
        </p>
        <ul className="login-brand-points">
          <li>RBAC at retrieve, not just UI</li>
          <li>One answer, five output skins</li>
          <li>Zero cloud LLM calls</li>
        </ul>
      </section>

      <section className="login-panel anim-fade-up" style={{ animationDelay: '0.08s' }}>
        {checking ? (
          <div className="login-checking">
            <div className="brand-mark">Prism</div>
            <p>Checking session…</p>
          </div>
        ) : (
          <>
            <h1>Sign in</h1>
            <p className="login-lead">Access is enforced at retrieval, not just the UI.</p>
            <form className="login-form" onSubmit={(e) => void onSubmit(e)}>
              <label className="field">
                Email
                <input
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                Password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              {error && <div className="login-error">{error}</div>}
              <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </form>

            {demo && (
              <div className="demo-users">
                <p className="section-label">Demo roles</p>
                <p className="demo-pass">
                  Shared password: <code>{demo.password}</code>
                </p>
                <div className="role-grid">
                  {roleCards.map((u) => (
                    <button
                      key={u.role}
                      type="button"
                      className={`role-card${email === u.email ? ' is-selected' : ''}`}
                      onClick={() => {
                        setEmail(u.email)
                        setPassword(demo.password)
                      }}
                    >
                      <strong>{ROLE_LABEL[u.role] ?? u.role}</strong>
                      <span>{u.name}</span>
                      <em>{ROLE_BLURB[u.role] ?? u.email}</em>
                    </button>
                  ))}
                </div>
                <p className="demo-hint">Jury smoke test: Alex Rao, Employee.</p>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
