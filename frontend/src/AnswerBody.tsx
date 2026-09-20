import type { ReactNode } from 'react'

function normalizeMoney(text: string): string {
  return text
    .replace(/\u20B9|\uFFFD/g, 'Rs. ')
    .replace(/(^|[\s:(])\?(\d)/g, '$1Rs. $2')
    .replace(/\s+Rs\.\s+/g, ' Rs. ')
    .replace(/Rs\.\s+/g, 'Rs. ')
}

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((c) => c.trim())
}

function looksLikeSep(line: string): boolean {
  const t = line.trim()
  if (!t.includes('|') || !/-{3,}/.test(t)) return false
  return splitRow(t).every((c) => /^:?-{3,}:?$/.test(c) || c === '')
}

function looksLikeRow(line: string): boolean {
  const t = line.trim()
  return t.includes('|') && t.length > 2 && !looksLikeSep(t)
}

function inline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i}>{part.slice(1, -1)}</code>
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

function splitInlineBullets(line: string): string[] {
  const body = line.replace(/^\s*[-*]\s+/, '')
  return body.split(/\s+-\s+/).map((s) => s.trim()).filter(Boolean)
}

function peelTableFromBullets(items: string[]): { items: string[]; headerLine: string | null } {
  const last = items[items.length - 1]
  if (!last?.includes('|')) return { items, headerLine: null }
  const pipe = last.indexOf('|')
  const before = last.slice(0, pipe)
  const matched = before.match(/^(.*?)([A-Za-z][A-Za-z /()-]{1,40})$/)
  if (!matched) return { items, headerLine: last }
  const kept = matched[1].trim()
  const header = `${matched[2].trim()} ${last.slice(pipe)}`.trim()
  const next = kept ? [...items.slice(0, -1), kept] : items.slice(0, -1)
  return { items: next, headerLine: header }
}

function renderTable(header: string[], rows: string[][], key: number): ReactNode {
  return (
    <div key={key} className="answer-table-wrap">
      <table>
        <thead>
          <tr>
            {header.map((h, hi) => (
              <th key={hi}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {header.map((_, ci) => (
                <td key={ci}>{inline(row[ci] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function parseBlocks(raw: string): ReactNode[] {
  const lines = normalizeMoney(raw).replace(/\r\n/g, '\n').split('\n')
  const out: ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    if (!lines[i].trim()) {
      i += 1
      continue
    }

    const tableAhead = looksLikeSep(lines[i + 1] ?? '')
    if (tableAhead && (looksLikeRow(lines[i]) || /^\s*[-*]\s+/.test(lines[i]))) {
      let headerLine = lines[i]
      if (/^\s*[-*]\s+/.test(headerLine) || headerLine.includes(' - ')) {
        const peeled = peelTableFromBullets(splitInlineBullets(headerLine))
        if (peeled.items.length) {
          out.push(
            <ul key={key++}>
              {peeled.items.map((item, ii) => (
                <li key={ii}>{inline(item)}</li>
              ))}
            </ul>,
          )
        }
        if (peeled.headerLine) headerLine = peeled.headerLine
      }
      const header = splitRow(headerLine)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && looksLikeRow(lines[i]) && !/^\s*[-*]\s+/.test(lines[i])) {
        rows.push(splitRow(lines[i]))
        i += 1
      }
      out.push(renderTable(header, rows, key++))
      continue
    }

    if (/^\s*[-*]\s+/.test(lines[i])) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i]) && !looksLikeSep(lines[i + 1] ?? '')) {
        items.push(...splitInlineBullets(lines[i]))
        i += 1
      }
      out.push(
        <ul key={key++}>
          {items.map((item, ii) => (
            <li key={ii}>{inline(item)}</li>
          ))}
        </ul>,
      )
      continue
    }

    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !(looksLikeRow(lines[i]) && looksLikeSep(lines[i + 1] ?? ''))
    ) {
      para.push(lines[i].trim())
      i += 1
    }
    out.push(<p key={key++}>{inline(para.join(' '))}</p>)
  }

  return out
}

export default function AnswerBody({ text }: { text: string }) {
  return <div className="answer-body">{parseBlocks(text)}</div>
}
