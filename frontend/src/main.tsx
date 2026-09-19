import { StrictMode, useCallback, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import Landing from './Landing.tsx'
import Login from './Login.tsx'
import { clearAuth, getMe, getStoredToken, getStoredUser, type AuthUser } from './api'
import './index.css'

function Root() {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser())
  const [checking, setChecking] = useState(() => Boolean(getStoredToken()))
  const [view, setView] = useState<'landing' | 'chat'>(() =>
    window.location.hash === '#/chat' ? 'chat' : 'landing',
  )
  const [seedQuestion, setSeedQuestion] = useState<string | null>(null)

  const onLogout = useCallback(() => {
    clearAuth()
    setUser(null)
    setView('landing')
    window.location.hash = '#/'
  }, [])

  useEffect(() => {
    if (!getStoredToken()) {
      setChecking(false)
      return
    }
    void getMe()
      .then((me) => {
        setUser(me)
        setChecking(false)
      })
      .catch(() => {
        clearAuth()
        setUser(null)
        setChecking(false)
      })
  }, [])

  const enterChat = useCallback((question?: string) => {
    if (question) setSeedQuestion(question)
    window.location.hash = '#/chat'
    setView('chat')
  }, [])

  const backHome = useCallback(() => {
    setSeedQuestion(null)
    window.location.hash = '#/'
    setView('landing')
  }, [])

  if (checking) {
    return (
      <div className="login-page">
        <div className="login-card">Checking session…</div>
      </div>
    )
  }

  if (!user) {
    return (
      <Login
        onLoggedIn={() => {
          setUser(getStoredUser())
        }}
      />
    )
  }

  if (view === 'landing') {
    return (
      <Landing
        user={user}
        onEnter={() => enterChat()}
        onTryQuestion={(text) => enterChat(text)}
        onLogout={onLogout}
      />
    )
  }
  return (
    <App user={user} onHome={backHome} onLogout={onLogout} seedQuestion={seedQuestion} onAuthLost={onLogout} />
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
