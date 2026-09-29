import { useEffect, useRef } from 'react'
import AnswerBody from './AnswerBody'
import { SUGGESTION_HINT } from './suggestions'
import {
  confidenceTone,
  domainLabel,
  workflowLabel,
  type Message,
} from './chatUtils'

function AnswerStateBanner({ m }: { m: Message }) {
  if (m.role !== 'assistant') return null
  if (m.isClarification) {
    return (
      <div className="answer-banner clarify-banner" role="status">
        Clarification needed. Pick a domain or rephrase so Prism can route correctly.
      </div>
    )
  }
  if (m.noAnswer) {
    return (
      <div className="answer-banner honesty-banner" role="status">
        No confident match in the knowledge base. Refusing to invent an answer.
      </div>
    )
  }
  return null
}

type Suggestion = { text: string; domain: string }

type Props = {
  messages: Message[]
  emptySuggestions: Suggestion[]
  copiedId: string | null
  speakingId: string | null
  showAllSources: Record<string, boolean>
  ttsSupported: boolean
  onSendSuggestion: (text: string) => void
  onCopy: (m: Message) => void
  onSpeak: (m: Message) => void
  onToggleSources: (id: string) => void
}

export default function MessageList({
  messages,
  emptySuggestions,
  copiedId,
  speakingId,
  showAllSources,
  ttsSupported,
  onSendSuggestion,
  onCopy,
  onSpeak,
  onToggleSources,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <section className="messages">
      {messages.length === 0 ? (
        <div className="empty">
          <h2>One query, any format</h2>
          <p>
            Ask across five domains, or drop a file. Same answer as prose, JSON, XML, Excel, or email.
          </p>
          <div className="suggestions">
            {emptySuggestions.map((s) => (
              <button key={s.text} type="button" className="suggestion" onClick={() => onSendSuggestion(s.text)}>
                <span className="suggestion-domain">{s.domain.replaceAll('_', ' ')}</span>
                {s.text}
              </button>
            ))}
          </div>
          <p className="suggestion-hint">{SUGGESTION_HINT}</p>
        </div>
      ) : (
        messages.map((m) => (
          <div
            key={m.id}
            className={[
              'bubble',
              'anim-bubble-in',
              m.role,
              m.isClarification ? 'clarify' : '',
              m.noAnswer && !m.isClarification ? 'no-answer' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <AnswerStateBanner m={m} />
            {m.role === 'assistant' ? (
              <AnswerBody
                text={
                  m.sustainabilityNote
                    ? m.content.replace(m.sustainabilityNote, '').trim()
                    : m.content
                }
              />
            ) : (
              m.content
            )}
            {m.sustainabilityNote && (
              <div className="water-callout" role="note">
                <strong>Water conservation</strong>
                {m.sustainabilityNote}
              </div>
            )}
            {m.role === 'assistant' && (
              <div className="meta-row">
                {m.domain && (
                  <span className={`chip active${m.domain === 'uploaded' ? ' upload-domain' : ''}`}>
                    {domainLabel(m.domain)}
                  </span>
                )}
                {m.confidence && (
                  <span className={`chip conf ${confidenceTone(m.confidence)}`}>
                    {m.confidence} confidence
                  </span>
                )}
                {m.noAnswer && !m.isClarification && (
                  <span className="chip warn">no confident match</span>
                )}
                {m.isClarification && <span className="chip warn">needs clarification</span>}
                {m.workflow && (
                  <span className="chip workflow" title={`Documented in ${m.promptDoc || 'docs/prompts.md'}`}>
                    {workflowLabel(m.workflow)}
                  </span>
                )}
                <button
                  type="button"
                  className={`copy-btn${copiedId === m.id ? ' copied' : ''}`}
                  onClick={() => onCopy(m)}
                >
                  {copiedId === m.id ? 'Copied' : 'Copy'}
                </button>
                {ttsSupported && (
                  <button
                    type="button"
                    className={`speak-btn${speakingId === m.id ? ' speaking' : ''}`}
                    onClick={() => onSpeak(m)}
                    title={speakingId === m.id ? 'Stop speaking' : 'Speak answer'}
                    aria-label={speakingId === m.id ? 'Stop speaking' : 'Speak answer'}
                  >
                    {speakingId === m.id ? 'Stop' : 'Speak'}
                  </button>
                )}
              </div>
            )}
            {m.role === 'assistant' && (m.workflow || (m.sources && m.sources.length > 0)) && (
              <div className="cite-block">
                {m.sources && m.sources.length > 0 && (
                  <div className="sources">
                    <div className="sources-label">Sources</div>
                    <ul className="sources-list">
                      {(showAllSources[m.id] ? m.sources : m.sources.slice(0, 3)).map((s) => (
                        <li key={s.id}>
                          {s.domain ? (
                            <span className="source-domain">{domainLabel(s.domain)}</span>
                          ) : null}
                          {s.source_url.startsWith('http') ? (
                            <a href={s.source_url} target="_blank" rel="noreferrer">
                              {s.title || s.source_url}
                            </a>
                          ) : (
                            <span>{s.title || s.source_url}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                    {m.sources.length > 3 && (
                      <button
                        type="button"
                        className="sources-more"
                        onClick={() => onToggleSources(m.id)}
                      >
                        {showAllSources[m.id] ? 'Show fewer' : `Show all ${m.sources.length}`}
                      </button>
                    )}
                  </div>
                )}
                {m.workflow && (
                  <div className="prompt-cite">
                    Workflow <code>{m.workflow}</code>
                    {' · '}
                    <code>{m.promptDoc || 'docs/prompts.md'}</code>
                  </div>
                )}
              </div>
            )}
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </section>
  )
}
