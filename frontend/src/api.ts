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
  turns: Array<{ role: string; content: string; domain?: string | null }>
  last_answer: Record<string, unknown> | null
  available_formats?: string[]
  pending_clarification: Record<string, unknown> | null
}

export function getSession(id: string) {
  return request<SessionDetail>(`/api/sessions/${id}`)
}

export function chat(sessionId: string, message: string) {
  return request<ChatResponse>(`/api/sessions/${sessionId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
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
