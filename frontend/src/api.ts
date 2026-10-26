// Calls to the BioValue AI API. Vite forwards /api to the FastAPI server on port 8765 (vite.config.ts).
import type {
  EvidenceLibrary, FieldError, Health, Inputs, Preview, ProjectInfo, RunWithInputs,
} from './types.ts'

export class ApiError extends Error {
  status: number
  fieldErrors: FieldError[]

  constructor(status: number, message: string, fieldErrors: FieldError[] = []) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

const UNREACHABLE = 'Cannot reach the BioValue AI server. Start it with: .venv/bin/python -m uvicorn backend.main:app --port 8765'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(0, UNREACHABLE)
  }
  const text = await response.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    // The dev proxy answers with plain text when the API is down.
    throw new ApiError(response.status, response.status >= 500 ? UNREACHABLE : text.slice(0, 200))
  }
  if (!response.ok) {
    const b = body as { message?: string; detail?: unknown; errors?: FieldError[] } | null
    // The dev proxy answers 502/503/504 with an empty body when the API server is down.
    if ([502, 503, 504].includes(response.status) && !b?.message && !b?.detail) throw new ApiError(response.status, UNREACHABLE)
    const detail = typeof b?.detail === 'string' ? b.detail : undefined
    throw new ApiError(response.status, b?.message ?? detail ?? `Request failed (${response.status})`, b?.errors ?? [])
  }
  return body as T
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  health: () => request<Health>('/api/health'),
  project: () => request<ProjectInfo>('/api/project'),
  evidence: () => request<EvidenceLibrary>('/api/evidence'),
  preview: (inputs: Inputs) => request<Preview>('/api/preview', post(inputs)),
  startRun: (inputs: Inputs) => request<{ run_id: string; status: string }>('/api/runs', post(inputs)),
  run: (runId: string) => request<RunWithInputs>(`/api/runs/${encodeURIComponent(runId)}`),
  latest: () => request<RunWithInputs>('/api/runs/latest'),
  reportUrl: (runId: string, format: 'md' | 'html') => `/api/runs/${encodeURIComponent(runId)}/report.${format}`,
}
