import type { RefObject } from 'react'
import type { UploadedDoc } from './api'
import { formatBytes } from './chatUtils'

const FORMATS = [
  { id: 'prose', label: 'Prose' },
  { id: 'json', label: 'JSON' },
  { id: 'xml', label: 'XML' },
  { id: 'excel', label: 'Excel' },
  { id: 'email', label: 'Email' },
] as const

const UPLOAD_ACCEPT = '.pdf,.txt,.md,.markdown,.csv,.json,.html,.htm,.docx'

type Props = {
  draft: string
  busy: boolean
  uploading: boolean
  savingPrompt: boolean
  listening: boolean
  dragOver: boolean
  activeId: string | null
  uploads: UploadedDoc[]
  formats: string[]
  panelFormat: string | null
  messageCount: number
  status: string
  speechSupported: boolean
  ttsSupported: boolean
  fileInputRef: RefObject<HTMLInputElement | null>
  draftTextareaRef: RefObject<HTMLTextAreaElement | null>
  onDraftChange: (v: string) => void
  onSend: () => void
  onFormat: (id: string) => void
  onAttachClick: () => void
  onFiles: (files: FileList | null) => void
  onRemoveUpload: (id: string) => void
  onToggleMic: () => void
  onSavePrompt: () => void
  onDragOver: (over: boolean) => void
  onDropFiles: (files: FileList) => void
}

export default function Composer({
  draft,
  busy,
  uploading,
  savingPrompt,
  listening,
  dragOver,
  activeId,
  uploads,
  formats,
  panelFormat,
  messageCount,
  status,
  speechSupported,
  ttsSupported,
  fileInputRef,
  draftTextareaRef,
  onDraftChange,
  onSend,
  onFormat,
  onAttachClick,
  onFiles,
  onRemoveUpload,
  onToggleMic,
  onSavePrompt,
  onDragOver,
  onDropFiles,
}: Props) {
  return (
    <div
      className={`composer-shell${dragOver ? ' drag-over' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        if (!dragOver) onDragOver(true)
      }}
      onDragLeave={() => onDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        onDragOver(false)
        onDropFiles(e.dataTransfer.files)
      }}
    >
      {uploads.length > 0 && (
        <div className="upload-row" aria-label="Attached documents">
          {uploads.map((u) => (
            <span key={u.id} className="upload-chip" title={`${u.chunk_count ?? 0} chunks · ${formatBytes(u.bytes_size)}`}>
              <span className="upload-icon" aria-hidden>
                ▤
              </span>
              <span className="upload-name">{u.filename}</span>
              <span className="upload-state">active</span>
              <button
                type="button"
                className="upload-remove"
                aria-label={`Remove ${u.filename}`}
                title="Remove and purge"
                onClick={() => onRemoveUpload(u.id)}
              >
                ×
              </button>
            </span>
          ))}
          <span className="upload-note">Local only · purged with this chat</span>
        </div>
      )}
      <div className="format-bar" role="toolbar" aria-label="Re-render last answer">
        {FORMATS.map((fmt) => (
          <button
            key={fmt.id}
            type="button"
            className={`format-btn format-${fmt.id}${
              (fmt.id === 'prose' && !panelFormat) || panelFormat === fmt.id ? ' is-active' : ''
            }`}
            disabled={busy || messageCount === 0 || !formats.includes(fmt.id)}
            aria-pressed={(fmt.id === 'prose' && !panelFormat) || panelFormat === fmt.id}
            onClick={() => onFormat(fmt.id)}
          >
            {fmt.label}
          </button>
        ))}
      </div>
      <form
        className={`composer${listening ? ' is-listening' : ''}`}
        onSubmit={(e) => {
          e.preventDefault()
          onSend()
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={UPLOAD_ACCEPT}
          multiple
          hidden
          onChange={(e) => onFiles(e.target.files)}
        />
        <button
          type="button"
          className="icon-btn attach"
          title="Attach a document for this chat only"
          aria-label="Attach document"
          disabled={busy || uploading || !activeId}
          onClick={onAttachClick}
        >
          {uploading ? '…' : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          )}
        </button>
        <textarea
          ref={draftTextareaRef}
          rows={1}
          value={draft}
          placeholder={
            listening
              ? 'Listening…'
              : uploads.length
                ? 'Ask about the attached file'
                : 'Ask a question, or drop a file'
          }
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              onSend()
            }
          }}
        />
        <div className="composer-actions">
          {speechSupported && (
            <button
              type="button"
              className={`icon-btn mic-btn${listening ? ' listening' : ''}`}
              title={listening ? 'Stop listening' : 'Dictate with microphone'}
              aria-label={listening ? 'Stop listening' : 'Dictate with microphone'}
              aria-pressed={listening}
              disabled={busy || !activeId}
              onClick={onToggleMic}
            >
              {listening ? (
                <span className="mic-dot" aria-hidden />
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" strokeWidth="2" />
                  <path d="M6 11a6 6 0 0 0 12 0M12 17v3M9 20h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              )}
            </button>
          )}
          <button
            type="button"
            className="icon-btn save-prompt-btn"
            title="Save this question for later"
            aria-label="Save prompt"
            disabled={busy || savingPrompt || !draft.trim()}
            onClick={onSavePrompt}
          >
            {savingPrompt ? '…' : 'Save'}
          </button>
          <button className="send" type="submit" disabled={busy || !draft.trim()}>
            Send
          </button>
        </div>
      </form>
      <div className="status-line">
        {listening ? (
          <span className="listening-hint">Listening. Click the mic to stop, or press Send.</span>
        ) : (
          <>
            {status ? <span>{status}</span> : null}
            {!status && (speechSupported || ttsSupported) ? (
              <span className="voice-hint">Voice in Chrome or Edge</span>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
