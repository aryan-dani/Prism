import { useEffect, useState } from 'react'
import { getDemoUsers, login, type DemoUsersResponse } from './api'

type Props = {
  onLoggedIn: () => void
}

const ROLE_LABEL: Record<string, string> = {
  customer: 'Customer',
  general_employee: 'General Employee',
  hr_staff: 'HR Staff',
  finance_staff: 'Finance Staff',
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
          Role-gated knowledge bases. Access is enforced at retrieval — not just the UI.
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
            <h2>Demo accounts</h2>
            <p className="demo-pass">
              Shared password: <code>{demo.password}</code>
            </p>
            <table>
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Name</th>
                  <th>Email</th>
                </tr>
              </thead>
              <tbody>
                {demo.users.map((u) => (
                  <tr
                    key={u.email}
                    className="demo-row"
                    onClick={() => {
                      setEmail(u.email)
                      setPassword(demo.password)
                    }}
                    title="Click to fill"
                  >
                    <td>{ROLE_LABEL[u.role] ?? u.role}</td>
                    <td>{u.name}</td>
                    <td>
                      <code>{u.email}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="demo-hint">Click a row to fill the form. Smoke test: Alex Rao (General Employee).</p>
          </div>
        )}
      </div>
    </div>
  )
}
