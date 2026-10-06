export type Role = 'Viewer' | 'Operator' | 'Manager'

export interface Identity {
  apiKey: string
  userId: string
  role: Role
}

const IDENTITY_KEY = 'planogram.identity'

export function loadIdentity(): Identity {
  try {
    const saved = localStorage.getItem(IDENTITY_KEY)
    if (saved) return JSON.parse(saved) as Identity
  } catch {
    // fall through to defaults
  }
  return { apiKey: 'dev-key', userId: 'dev-user', role: 'Manager' }
}

let identity = loadIdentity()

export function setIdentity(next: Identity): void {
  identity = next
  try {
    localStorage.setItem(IDENTITY_KEY, JSON.stringify(next))
  } catch {
    // identity is only remembered for convenience
  }
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    const detail = (body as { detail?: unknown } | null)?.detail
    super(typeof detail === 'string' ? detail : JSON.stringify(detail ?? body))
    this.status = status
    this.body = body
  }
}

async function request(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {
    'X-API-Key': identity.apiKey,
    'X-User-Id': identity.userId,
    'X-User-Role': identity.role,
  }
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const response = await fetch(`/api${path}`, { method, headers, body: payload })
  if (!response.ok) {
    const text = await response.text()
    let errorBody: unknown = text
    try {
      errorBody = JSON.parse(text)
    } catch {
      // keep text body
    }
    throw new ApiError(response.status, errorBody)
  }
  return response
}

export const api = {
  async get<T>(path: string): Promise<T> {
    return (await request('GET', path)).json() as Promise<T>
  },
  async post<T>(path: string, body?: unknown): Promise<T> {
    const response = await request('POST', path, body)
    return (response.status === 204 ? undefined : response.json()) as Promise<T>
  },
  async patch<T>(path: string, body: unknown): Promise<T> {
    return (await request('PATCH', path, body)).json() as Promise<T>
  },
  async del(path: string): Promise<void> {
    await request('DELETE', path)
  },
  /** Images need the auth headers, so they are fetched and shown through object URLs. */
  async blobUrl(path: string): Promise<string> {
    return URL.createObjectURL(await (await request('GET', path)).blob())
  },
}

export interface Store {
  id: string
  name: string
}

export interface Fixture {
  id: string
  store_id: string
  name: string
  bay_count: number
  bays: number[]
}

export interface ReferenceImage {
  id: string
  sku: string
  url: string
}

export interface Product {
  sku: string
  name: string
  reference_images: ReferenceImage[]
}

export interface ShelfPhoto {
  id: string
  store_id: string
  fixture_id: string
  bay: number
  uploaded_by: string
  uploaded_at: string
  width: number
  height: number
  image_url: string | null
}

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

export interface Block {
  id: string
  sku: string | null
  facings: number
  box: Box | null
  unknown: boolean
}

export interface Shelf {
  number: number
  blocks: Block[]
}

export interface BayLayout {
  bay: number
  shelf_photo_id: string | null
  shelves: Shelf[]
}

export type PlanogramStatus = 'Draft' | 'Approved' | 'Superseded'

export interface Planogram {
  id: string
  fixture_id: string
  status: PlanogramStatus
  created_at: string
  approved_by: string | null
  approved_at: string | null
  superseded_at: string | null
  bays: BayLayout[]
}

export interface Job {
  id: string
  kind: 'extraction' | 'compliance_check'
  status: 'queued' | 'running' | 'done' | 'failed'
  shelf_photo_id: string
  submitted_by: string
  submitted_at: string
  result_id: string | null
  result_url: string | null
  error: string | null
}

export interface ImportReport {
  created: string[]
  updated: string[]
  failed: { row: number; sku: string; reason: string }[]
}

export type DeviationKind = 'Gap' | 'Missing' | 'Wrong Facing Count' | 'Misplaced' | 'Unexpected'

export interface Position {
  bay: number
  shelf: number
  order: number
  facings: number
}

export interface Deviation {
  kind: DeviationKind
  sku: string | null
  facings: number
  planned: Position | null
  observed: Position | null
  box: Box
  confidence: number
}

export interface UnverifiedArea {
  shelf: number
  box: Box
  confidence: number
}

export interface ComplianceCheck {
  id: string
  shelf_photo_id: string
  planogram_id: string
  store_id: string
  fixture_id: string
  bay: number
  submitted_by: string
  submitted_at: string
  /** null when no planned Facing could be verified. */
  compliance_score: number | null
  coverage: number
  deviations: Deviation[]
  unverified: UnverifiedArea[]
}
