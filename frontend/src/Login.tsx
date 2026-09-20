import { useEffect, useMemo, useState } from 'react'
import { getDemoUsers, login, type DemoUsersResponse } from './api'

type Props = {
  onLoggedIn: () => void
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

export default function Login({ onLoggedIn }: Props) {
  const [email, setEmail] = useState('alex.employee@prism.local')
  const [password, setPassword] = useState('Prism2026!')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [demo, setDemo] = useState<DemoUsersResponse | null>(null)

  useEffect(() => {
    void getDemoUsers()
      .then(setDemo)
      .catch(() => setDemo(null))
  }, [])

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
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="brand-mark">Prism</div>
        <p className="login-kicker">Kohler Unified Enterprise AI · Track 3</p>
        <h1>Sign in</h1>
        <p className="login-lead">
          Role-gated knowledge bases. Access is enforced at retrieval, not just the UI.
        </p>
        <form className="login-form" onSubmit={(e) => void onSubmit(e)}>
          <label>
            Email
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
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
          <button type="submit" className="landing-cta" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        {demo && (
          <div className="demo-users">
            <h2>Pick a demo role</h2>
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
      </div>
    </div>
  )
}
