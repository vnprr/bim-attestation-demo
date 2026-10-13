// Mirrors backend/app/schemas.py. The frontend never talks to Solana directly.

export type Ruleset = { name: string; hash: string }

export type Milestone = {
  address: string
  investor: string
  contractor: string
  oracle: string
  arbiter: string
  amount: number
  ruleset_hash: string
  deadline: number
  dispute_window: number
  status: 'Open' | 'Approved' | 'Disputed' | 'Released' | 'Refunded'
  approved_at: number
  disputed_at: number
  asset_hash: string
  result_hash: string
  milestone_id: number
}

export type MilestoneView = {
  milestone: Milestone
  ruleset_name: string | null
  ruleset_file: string | null
  balances: { investor: number; contractor: number; milestone: number }
  now: number
  window_ends_at: number | null // Approved/Disputed: the payment is claimable after this
}

export type Tx = { signature: string; ok: boolean; error: string | null; logs: string[] }

export type Violation = { rule: string; global_id: string; element: string; reason: string }

export type QaReport = {
  ruleset_name: string
  result_hash: string
  result: { engine: string; asset_hash: string; ruleset_hash: string; passed: boolean; violations: Violation[] }
}

export type ClusterConfig = { cluster: string; explorer_query: string }

export type Health = { cluster: string; balances: Record<string, number>; low: string[] }

export type ActionResponse = { view: MilestoneView; tx: Tx | null; qa: QaReport | null; note: string | null }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  const body = await response.json().catch(() => null) // no JSON: the backend is not running behind the proxy
  if (!response.ok) throw new Error(errorText(response, body))
  return body
}

function errorText(response: Response, body: { detail?: string | { msg: string }[] } | null) {
  if (!body) return `Backend not reachable (${response.status}). Is uvicorn running on port 8080?`
  if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join('; ') // FastAPI validation error
  return body.detail ?? response.statusText
}

const post = <T>(path: string, body?: BodyInit, json = false) =>
  request<T>(path, { method: 'POST', body, headers: json ? { 'Content-Type': 'application/json' } : undefined })

const upload = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return form
}

export const api = {
  config: () => request<ClusterConfig>('/config'),
  health: () => request<Health>('/health'),
  rulesets: () => request<Ruleset[]>('/rulesets'),
  milestone: (address: string) => request<MilestoneView>(`/milestones/${address}`),
  create: (amount_sol: number, deadline_seconds: number, dispute_window_seconds: number, ruleset_hash: string) =>
    post<ActionResponse>(
      '/milestones',
      JSON.stringify({ amount_sol, deadline_seconds, dispute_window_seconds, ruleset_hash }),
      true,
    ),
  submit: (address: string, file: File) => post<ActionResponse>(`/milestones/${address}/submit`, upload(file)),
  claim: (address: string) => post<ActionResponse>(`/milestones/${address}/claim`),
  dispute: (address: string) => post<ActionResponse>(`/milestones/${address}/dispute`),
  resolve: (address: string, pay_contractor: boolean) =>
    post<ActionResponse>(`/milestones/${address}/resolve`, JSON.stringify({ pay_contractor }), true),
  refund: (address: string) => post<ActionResponse>(`/milestones/${address}/refund`),
  attackLenient: (address: string, file: File) =>
    post<ActionResponse>(`/milestones/${address}/attack/lenient-ruleset`, upload(file)),
}

export const sol = (lamports: number) => (lamports / 1e9).toLocaleString('en', { maximumFractionDigits: 4 })

export const short = (value: string) => `${value.slice(0, 6)}…${value.slice(-6)}`

/** "in 2 min 5 s" until a chain timestamp, or "passed". */
export function countdown(seconds: number) {
  if (seconds <= 0) return 'passed'
  const m = Math.floor(seconds / 60)
  return m > 0 ? `in ${m} min ${seconds % 60} s` : `in ${seconds} s`
}
