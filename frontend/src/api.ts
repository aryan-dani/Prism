const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export type SessionSummary = {
  id: string
  title: string | null
  updated_at?: string
  active_domain?: string | null
}

export type ChatResponse = {
  session_id: string
  reply: string
  domain: string | null
  is_clarification: boolean
  is_reformat: boolean
  confidence: string | null
  no_answer: boolean
  sources: Array<{ id: string; title: string; source_url: string; domain: string }>
  available_formats: string[]
  title: string | null
}

export type Health = {
  status: string
  chunks_indexed: number
  embed_model: string
  gen_model: string
  title_model: string
  domains: string[]
  ollama?: {
    reachable: boolean
    host: string
    models_required: string[]
    models_missing: string[]
    ok: boolean
    error?: string
  }
  uploads?: {
    chunks_indexed: number
    ttl_hours: number
    max_bytes: number
    allowed_suffixes: string[]
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json() as Promise<T>
}

export function getHealth() {
  return request<Health>('/api/health')
}

export function listSessions() {
  return request<SessionSummary[]>('/api/sessions')
}

export function createSession() {
  return request<{ id: string; title: string | null }>('/api/sessions', { method: 'POST' })
}

export function deleteSession(id: string) {
  return request<{ ok: boolean }>(`/api/sessions/${id}`, { method: 'DELETE' })
}

export type SessionDetail = {
  id: string
  title: string | null
  active_domain: string | null
  turns: Array<{
    role: string
    content: string
    domain?: string | null
    is_clarification?: boolean
    no_answer?: boolean
    confidence?: string | null
  }>
  last_answer: Record<string, unknown> | null
  available_formats?: string[]
  pending_clarification: Record<string, unknown> | null
  uploaded_docs?: UploadedDoc[]
}

export function getSession(id: string) {
  return request<SessionDetail>(`/api/sessions/${id}`)
}

/** Session-scoped uploaded document (ephemeral "uploaded" domain). */
export type UploadedDoc = {
  id: string
  filename: string
  content_type?: string
  bytes_size?: number
  chunk_count?: number
  turn_index?: number
  created_at?: string
}

export type UploadResponse = {
  doc_id: string
  filename: string
  status: string
  chunk_count: number
  uploaded_docs: UploadedDoc[]
}

export async function uploadDocument(sessionId: string, file: File): Promise<UploadResponse> {
  const body = new FormData()
  body.append('file', file, file.name)
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/upload`, { method: 'POST', body })
  if (!res.ok) {
    let detail = ''
    try {
      const j = (await res.json()) as { detail?: string }
      detail = j.detail ?? ''
    } catch {
      detail = await res.text()
    }
    throw new Error(detail || res.statusText)
  }
  return res.json() as Promise<UploadResponse>
}

export function deleteUpload(sessionId: string, docId: string) {
  return request<{ ok: boolean; uploaded_docs: UploadedDoc[] }>(
    `/api/sessions/${sessionId}/uploads/${docId}`,
    { method: 'DELETE' },
  )
}

export function chat(sessionId: string, message: string) {
  return request<ChatResponse>(`/api/sessions/${sessionId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}

const STATUS_LABELS: Record<string, string> = {
  received: 'Received…',
  checking_guards: 'Checking policy guards…',
  policy_lookup: 'Looking up policy rules…',
  format_check: 'Checking format request…',
  routing: 'Routing domain…',
  retrieving: 'Retrieving knowledge…',
  generating: 'Generating answer…',
  titling: 'Updating title…',
  done: 'Finishing…',
}

/** SSE chat: status stages then the same ChatResponse as /chat (no partial tokens). */
export async function chatStream(
  sessionId: string,
  message: string,
  onStatus?: (label: string, stage: string) => void,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) {
    throw new Error((await res.text()) || res.statusText)
  }
  if (!res.body) {
    throw new Error('No response body from chat stream')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: ChatResponse | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const block of parts) {
      const lines = block.split('\n')
      let event = 'message'
      const dataLines: string[] = []
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (!dataLines.length) continue
      const raw = dataLines.join('\n')
      let data: Record<string, unknown>
      try {
        data = JSON.parse(raw) as Record<string, unknown>
      } catch {
        continue
      }
      if (event === 'status') {
        const stage = String(data.stage ?? '')
        onStatus?.(STATUS_LABELS[stage] ?? `Working (${stage})…`, stage)
      } else if (event === 'result') {
        result = data as unknown as ChatResponse
      } else if (event === 'error') {
        throw new Error(String(data.message ?? 'Stream error'))
      }
    }
  }

  if (!result) {
    throw new Error('Stream ended without a result')
  }
  return result
}

export async function renderFormat(sessionId: string, format: string) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ format }),
  })
  if (!res.ok) throw new Error(await res.text())
  const type = res.headers.get('content-type') || ''
  if (type.includes('application/vnd.openxmlformats') || type.includes('octet-stream')) {
    const blob = await res.blob()
    return { binary: true as const, blob, filename: 'prism_answer.xlsx' }
  }
  return { binary: false as const, ...(await res.json()) }
}

export function downloadExcelUrl(sessionId: string) {
  return `${API_BASE}/api/sessions/${sessionId}/download/excel`
}
