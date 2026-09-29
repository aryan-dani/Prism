import type { ChatResponse } from './api'

export type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  domain?: string | null
  confidence?: string | null
  isClarification?: boolean
  noAnswer?: boolean
  sources?: ChatResponse['sources']
  availableFormats?: string[]
  sustainabilityNote?: string | null
  workflow?: string | null
  promptDoc?: string | null
}

export const WORKFLOW_LABELS: Record<string, string> = {
  rag_canonical: 'RAG + system prompt',
  rag_email: 'RAG → email render',
  policy_math: 'Deterministic policy_math',
  rbac_deny: 'RBAC denial',
  jailbreak_refuse: 'Jailbreak refuse',
  policy_override_refuse: 'Policy-override refuse',
  reformat: 'Reformat last answer',
  clarify: 'Clarification',
  session_memory: 'Session memory',
  session_email_recall: 'Session email recall',
  upload_rag: 'Uploaded-doc RAG',
}

export function workflowLabel(id?: string | null): string {
  if (!id) return ''
  return WORKFLOW_LABELS[id] ?? id.replaceAll('_', ' ')
}

export function uid() {
  return crypto.randomUUID()
}

export function domainLabel(d: string | null | undefined): string {
  if (!d) return ''
  if (d === 'uploaded') return 'Upload'
  if (d === 'customer_support') return 'Support'
  return d.replaceAll('_', ' ')
}

export function formatBytes(n?: number): string {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

/** Keep sidebar/topbar titles human-readable when the titler returns junk. */
export function displayTitle(raw: string | null | undefined, fallback = 'Untitled chat'): string {
  let t = (raw ?? '').trim()
  if (!t) return fallback
  if (t.startsWith('{') || t.startsWith('[') || t.includes('"entitlement') || t.includes('"risk_level"')) {
    return 'Structured answer request'
  }
  if (
    /generate short descriptive/i.test(t) ||
    /chat titles/i.test(t) ||
    /provide (a )?summary/i.test(t) ||
    /user request/i.test(t) ||
    /not enough info/i.test(t)
  ) {
    return fallback
  }
  if (!t.includes(' ') && (t.match(/[A-Z]/g)?.length ?? 0) >= 3) {
    t = t.replace(/([a-z])([A-Z])/g, '$1 $2')
  }
  if (t.length > 72) return `${t.slice(0, 69)}…`
  return t
}

export function turnsToMessages(
  turns: Array<{
    role: string
    content: string
    domain?: string | null
    is_clarification?: boolean
    no_answer?: boolean
    confidence?: string | null
  }>,
): Message[] {
  return turns
    .filter((t) => t.role === 'user' || t.role === 'assistant')
    .map((t) => ({
      id: uid(),
      role: t.role as 'user' | 'assistant',
      content: t.content,
      domain: t.domain,
      isClarification: Boolean(t.is_clarification),
      noAnswer: Boolean(t.no_answer),
      confidence: t.confidence ?? null,
    }))
}

export function confidenceTone(confidence?: string | null): string {
  switch ((confidence || '').toLowerCase()) {
    case 'high':
      return 'ok'
    case 'medium':
      return 'mid'
    case 'low':
    case 'none':
      return 'warn'
    default:
      return ''
  }
}

export function tidyTranscript(text: string): string {
  const squeezed = text.replace(/\s+/g, ' ').trim()
  if (!squeezed) return ''
  const sentences = squeezed.split(/(?<=[.!?])\s+/).filter(Boolean)
  const out: string[] = []
  for (const raw of sentences) {
    const s = raw.trim()
    const prev = out[out.length - 1]
    const norm = (v: string) => v.toLowerCase().replace(/[.!?]+$/g, '').trim()
    if (prev && norm(prev) === norm(s)) continue
    out.push(s)
  }
  return out.join(' ').replace(/\b(\w+)(?:\s+\1){1,}\b/gi, '$1')
}
