import { domainLabel } from './chatUtils'

type Props = {
  title: string
  roleDomains: string[]
  uploadCount: number
}

export default function ChatHeader({ title, roleDomains, uploadCount }: Props) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <div className="chips chips-top">
          {roleDomains.map((d) => (
            <span key={d} className="chip">
              {domainLabel(d)}
            </span>
          ))}
          {uploadCount > 0 && (
            <span className="chip upload-domain" title="Session-scoped, purged when this chat is deleted">
              + uploaded doc{uploadCount > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
