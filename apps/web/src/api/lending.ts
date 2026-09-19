/** Typed client for EnTIQ Lending (services/api/app/modules/lending). */
import { API_BASE, ApiError, tokenStore } from './client';

export type LendingStage = 'enquiry' | 'information' | 'assessment' | 'submitted' | 'approved' | 'conditions' | 'settled' | 'declined' | 'withdrawn';
export type LendingPurpose = 'equipment' | 'vehicle' | 'property' | 'working_capital' | 'refinance' | 'expansion' | 'other';
export const PIPELINE: LendingStage[] = ['enquiry', 'information', 'assessment', 'submitted', 'approved', 'conditions', 'settled'];

export interface ConditionOut { id: string; title: string; detail: string | null; kind: 'precedent' | 'subsequent'; owner_side: 'client' | 'practice' | 'lender'; due_on: string | null; overdue: boolean; status: 'open' | 'satisfied' | 'waived'; document_id: string | null; note: string | null; satisfied_at: string | null; satisfied_by_name: string | null }
export interface LendingEvent { id: string; kind: string; from_stage: string | null; to_stage: string | null; note: string | null; actor_label: string; at: string }
export interface ApplicationOut {
  id: string; client_id: string; client_name: string | null; contact_name: string | null; reference: string; purpose: LendingPurpose; description: string | null; amount_cents: number; term_months: number | null;
  rate_bps: number | null; repayment_cents: number | null; lender: string | null; stage: LendingStage; stage_index: number; owner_name: string | null; request_pack_id: string | null; readiness_pct: number;
  serviceability: Record<string, unknown>; dscr: number | null; decision_note: string | null; submitted_at: string | null; approved_at: string | null; settled_at: string | null; settlement_date: string | null;
  expected_settlement: string | null; closed_at: string | null; close_reason: string | null; conditions_open: number; conditions_blocking: number; created_at: string; updated_at: string;
}
export interface ApplicationDetail extends ApplicationOut { conditions: ConditionOut[]; events: LendingEvent[]; documents_outstanding: string[]; request_status: string | null }
export interface LendingOverview { active: number; pipeline_value_cents: number; settled_90d: number; settled_value_90d_cents: number; awaiting_client: number; conditions_open: number; by_stage: Record<string, number>; conversion_pct: number | null }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/lending${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
const qs = (o: Record<string, unknown>) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v)); const s = p.toString(); return s ? `?${s}` : ''; };

export const lending = {
  overview: () => req<LendingOverview>('GET', '/overview'),
  applications: {
    list: (f: { stage?: string; client_id?: string; open?: boolean } = {}) => req<ApplicationOut[]>('GET', `/applications${qs(f)}`),
    create: (b: { client_id: string; contact_id?: string | null; purpose?: LendingPurpose; description?: string | null; amount_cents: number; term_months?: number | null; rate_bps?: number | null; lender?: string | null; owner_membership_id?: string | null; expected_settlement?: string | null; send_request?: boolean }) => req<ApplicationDetail>('POST', '/applications', b),
    get: (id: string) => req<ApplicationDetail>('GET', `/applications/${id}`),
    patch: (id: string, b: Record<string, unknown>) => req<ApplicationDetail>('PATCH', `/applications/${id}`, b),
    openRequest: (id: string) => req<ApplicationDetail>('POST', `/applications/${id}/request`),
    assess: (id: string, b: { ebitda_cents?: number | null; existing_repayments_cents?: number | null; proposed_repayment_cents?: number | null; notes?: string | null; use_snapshot?: boolean }) => req<ApplicationDetail>('POST', `/applications/${id}/assess`, b),
    setStage: (id: string, stage: LendingStage, note?: string) => req<ApplicationDetail>('POST', `/applications/${id}/stage`, { stage, note: note ?? null }),
    addCondition: (id: string, b: { title: string; detail?: string | null; kind?: 'precedent' | 'subsequent'; owner_side?: 'client' | 'practice' | 'lender'; due_on?: string | null }) => req<ApplicationDetail>('POST', `/applications/${id}/conditions`, b),
    satisfyCondition: (id: string, conditionId: string, b: { note?: string | null; document_id?: string | null; waive?: boolean }) => req<ApplicationDetail>('POST', `/applications/${id}/conditions/${conditionId}/satisfy`, b),
  },
};

export const STAGE_LABEL: Record<LendingStage, string> = { enquiry: 'Enquiry', information: 'With client', assessment: 'Assessment', submitted: 'With lender', approved: 'Approved', conditions: 'Conditions', settled: 'Settled', declined: 'Declined', withdrawn: 'Withdrawn' };
export const PURPOSE_LABEL: Record<LendingPurpose, string> = { equipment: 'Equipment', vehicle: 'Vehicle', property: 'Property', working_capital: 'Working capital', refinance: 'Refinance', expansion: 'Expansion', other: 'Other' };
export function stageTone(s: LendingStage): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'settled' ? 'success' : s === 'declined' || s === 'withdrawn' ? 'error' : s === 'approved' || s === 'conditions' ? 'teal' : s === 'information' ? 'warn' : 'info'; }
export const fmtRate = (bps: number | null) => (bps == null ? '—' : `${(bps / 100).toFixed(2)}%`);
