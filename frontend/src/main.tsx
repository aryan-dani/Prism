import { StrictMode, useCallback, useState } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import Landing from './Landing.tsx'
import './index.css'

function Root() {
  const [view, setView] = useState<'landing' | 'chat'>(() =>
    window.location.hash === '#/chat' ? 'chat' : 'landing',
  )
  const [seedQuestion, setSeedQuestion] = useState<string | null>(null)

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

  if (view === 'landing') {
    return (
      <Landing
        onEnter={() => enterChat()}
        onTryQuestion={(text) => enterChat(text)}
      />
    )
  }
  return <App onHome={backHome} seedQuestion={seedQuestion} />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
