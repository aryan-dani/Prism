import { useMemo, useState, type MouseEvent } from 'react'

type Props = {
  format: string
  content: string
  onClose: () => void
}

export function parseEmailDraft(raw: string): { subject: string; body: string } {
  const text = raw.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').trim()
  const match = text.match(/^Subject:\s*(.*)\n+([\s\S]*)$/i)
  if (match) return { subject: match[1].trim(), body: match[2].trim() }
  return { subject: 'Prism answer', body: text }
}

export function mailtoHref(subject: string, body: string): string {
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

function pretty(format: string, content: string): string {
  if (format === 'json') {
    try {
      return JSON.stringify(JSON.parse(content), null, 2)
    } catch {
      return content
    }
  }
  return content
}

function titleFor(format: string): string {
  if (format === 'email') return 'Draft email'
  if (format === 'json') return 'JSON'
  if (format === 'xml') return 'XML'
  if (format === 'excel') return 'Excel downloaded'
  return format.toUpperCase()
}

export default function FormatPanel({ format, content, onClose }: Props) {
  const [copied, setCopied] = useState(false)
  const email = useMemo(
    () => (format === 'email' ? parseEmailDraft(content) : null),
    [format, content],
  )
  const display = useMemo(() => pretty(format, content), [format, content])
  const copyText = email ? `Subject: ${email.subject}\n\n${email.body}` : display
  const mailHref = email ? mailtoHref(email.subject, email.body) : ''

  async function copy() {
    try {
      await navigator.clipboard.writeText(copyText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  function openMail(e: MouseEvent<HTMLAnchorElement>) {
    if (!email) return
    if (mailHref.length <= 1800) return
    e.preventDefault()
    void navigator.clipboard.writeText(copyText)
    const clipped = `${email.body.slice(0, 1200)}\n\n[Draft truncated. Full text copied to clipboard.]`
    window.location.href = mailtoHref(email.subject, clipped)
  }

  return (
    <div className={`panel format-panel format-panel-${format}`}>
      <header className="format-panel-head">
        <div>
          <p className="format-panel-kicker">Same answer · no re-retrieval</p>
          <h3>{titleFor(format)}</h3>
        </div>
        <div className="format-panel-actions">
          {format !== 'excel' ? (
            <button type="button" className="format-panel-ghost" onClick={() => void copy()}>
              {copied ? 'Copied' : 'Copy'}
            </button>
          ) : null}
          <button type="button" className="format-panel-ghost" onClick={onClose} aria-label="Close format panel">
            Close
          </button>
        </div>
      </header>

      {format === 'email' && email ? (
        <>
          <dl className="email-meta">
            <div>
              <dt>To</dt>
              <dd>Choose a recipient in your mail app</dd>
            </div>
            <div>
              <dt>Subject</dt>
              <dd>{email.subject}</dd>
            </div>
          </dl>
          <div className="email-body">{email.body}</div>
          <div className="format-panel-cta">
            <a className="format-panel-primary" href={mailHref} onClick={openMail}>
              Open in Mail
            </a>
            <button type="button" className="format-panel-ghost" onClick={() => void copy()}>
              {copied ? 'Copied' : 'Copy draft'}
            </button>
          </div>
        </>
      ) : format === 'excel' ? (
        <p className="format-panel-note">
          Saved <code>prism_answer.xlsx</code>. Open it in Excel or Google Sheets.
        </p>
      ) : (
        <pre className="format-code">
          <code>{display}</code>
        </pre>
      )}
    </div>
  )
}
