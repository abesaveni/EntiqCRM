/** Typed client for EnTIQ Start (services/api/app/modules/start). Staff routes need a bearer token; the /onboard/{token} prospect routes do not. */
import { API_BASE, ApiError, tokenStore } from './client';

export type OnboardingStatus = 'draft' | 'invited' | 'in_progress' | 'awaiting_practice' | 'activated' | 'withdrawn';
export type StageStatus = 'pending' | 'active' | 'completed' | 'blocked' | 'skipped';
export type EntityType = 'Company' | 'Trust' | 'Individual' | 'Partnership' | 'SMSF' | 'Other';

export interface ServiceOut { id: string; name: string; category: string; description: string | null; basis: 'fixed' | 'monthly' | 'quarterly' | 'annual' | 'hourly'; amount_cents: number; gst: boolean; entity_types: EntityType[]; is_active: boolean; sort: number }
export interface StageOut { number: number; key: string; name: string; actor: 'prospect' | 'practice'; description: string; status: StageStatus; started_at: string | null; completed_at: string | null; completed_by: string | null; meta: Record<string, unknown> }
export interface GateOut { gate: 'kyc' | 'aml' | 'esign' | 'mandate'; label: string; status: 'Passed' | 'Pending' | 'Failed' | 'Error' | 'Not run'; simulated: boolean; detail: string | null; checked_at: string | null }
export interface DocRequest { key: string; label: string; required: boolean; document_id: string | null; uploaded_at: string | null; verified_by: string | null; verified_at: string | null }
export interface Question { key: string; label: string; type: 'text' | 'select' | 'bool'; options?: string[]; required: boolean }
export interface ProposalLine { service_id: string | null; name: string; basis: string; amount_cents: number; gst: boolean }
export interface Proposal { lines: ProposalLine[]; terms: string | null; issued_at: string; issued_by: string; valid_until: string; subtotal_cents: number; gst_cents: number; total_cents: number; accepted_at: string | null; accepted_by_name: string | null; declined_at: string | null }

export interface OnboardingOut {
  id: string; client_id: string; client_name: string; client_type: string; client_stage: string; primary_contact_name: string | null; primary_contact_email: string | null; owner_name: string | null;
  status: OnboardingStatus; current_stage: number; progress_pct: number; channel: string; invited_at: string | null; opened_at: string | null; activated_at: string | null; withdrawn_at: string | null; withdraw_reason: string | null;
  token_expires_at: string | null; proposal_total_cents: number | null; sign_agreement_id: string | null; risk_rating: string | null; created_at: string; updated_at: string;
}
export interface OnboardingDetail extends OnboardingOut { stages: StageOut[]; gates: GateOut[]; data: Record<string, any>; invite_url: string | null; notes: string | null }
export interface StartOverview { active: number; awaiting_prospect: number; awaiting_practice: number; activated_30d: number; withdrawn_30d: number; by_stage: Record<string, number>; median_days_to_activate: number | null }
export interface PublicView { practice_name: string; prospect_name: string; contact_name: string | null; status: OnboardingStatus; current_stage: number; stages: StageOut[]; data: Record<string, any>; questionnaire: Question[]; document_requests: DocRequest[]; services: ServiceOut[]; proposal: Proposal | null; expires_at: string | null }

export interface OnboardingIn { client_id?: string | null; prospect_name?: string; entity_type?: EntityType; contact_first_name?: string; contact_last_name?: string | null; contact_email?: string; owner_membership_id?: string | null; send_invitation?: boolean; invite_valid_days?: number; notes?: string | null }
export interface EntityDetailsIn { legal_name: string; trading_name?: string | null; entity_type: EntityType; abn?: string | null; acn?: string | null; tax_residency: 'australia' | 'foreign' | 'dual'; gst_registered?: boolean | null; industry?: string | null; address_line1?: string | null; suburb?: string | null; state?: string | null; postcode?: string | null; contact_name: string; contact_email: string; contact_phone?: string | null }
export interface PartyIn { name: string; role: 'Director' | 'Secretary' | 'Shareholder' | 'Trustee' | 'Beneficiary' | 'Appointor' | 'Partner' | 'Member' | 'Owner' | 'Other'; email?: string | null; phone?: string | null; ownership_pct?: number | null; is_beneficial_owner: boolean }
export interface MandateIn { method: 'direct_debit' | 'card' | 'invoice'; reference?: string | null; account_name?: string | null; accepted_terms: boolean }

async function req<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const t = auth ? tokenStore.get() : null;
  const res = await fetch(`${API_BASE}/start${path}`, {
    method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

export const start = {
  overview: () => req<StartOverview>('GET', '/overview'),
  onboardings: {
    list: (f: { status?: string; open?: boolean } = {}) => { const p = new URLSearchParams(); if (f.status) p.set('status', f.status); if (f.open === false) p.set('open', 'false'); const s = p.toString(); return req<OnboardingOut[]>('GET', `/onboardings${s ? `?${s}` : ''}`); },
    create: (b: OnboardingIn) => req<OnboardingDetail>('POST', '/onboardings', b),
    get: (id: string) => req<OnboardingDetail>('GET', `/onboardings/${id}`),
    invite: (id: string) => req<OnboardingDetail>('POST', `/onboardings/${id}/invite`),
    withdraw: (id: string, reason: string) => req<OnboardingDetail>('POST', `/onboardings/${id}/withdraw`, { reason }),
    stage2: (id: string, b: EntityDetailsIn) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/2`, b),
    stage3: (id: string, answers: Record<string, unknown>) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/3`, { answers }),
    verifyDoc: (id: string, key: string) => req<OnboardingDetail>('POST', `/onboardings/${id}/documents/${key}/verify`),
    stage4: (id: string) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/4`),
    stage5: (id: string, parties: PartyIn[], ownership_complete: boolean) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/5`, { parties, ownership_complete }),
    stage6: (id: string, service_ids: string[]) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/6`, { service_ids }),
    proposal: (id: string, b: { lines: ProposalLine[]; terms?: string | null; valid_days?: number }) => req<OnboardingDetail>('POST', `/onboardings/${id}/proposal`, b),
    stage7: (id: string, accepted_by_name: string, accept: boolean) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/7`, { accepted_by_name, accept }),
    stage8: (id: string, b: { document_id: string; title?: string | null; message?: string | null; require_identity?: boolean }) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/8`, b),
    runGates: (id: string) => req<OnboardingDetail>('POST', `/onboardings/${id}/gates/run`),
    mandate: (id: string, b: MandateIn) => req<OnboardingDetail>('POST', `/onboardings/${id}/mandate`, b),
    stage10: (id: string, b: { partner_signoff: boolean; margin_ok: boolean; risk_signoff: boolean; notes?: string | null }) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/10`, b),
    stage11: (id: string) => req<OnboardingDetail>('POST', `/onboardings/${id}/stages/11`),
  },
  services: {
    list: (includeInactive = false) => req<ServiceOut[]>('GET', `/services${includeInactive ? '?include_inactive=true' : ''}`),
    seedDefaults: () => req<ServiceOut[]>('POST', '/services/defaults'),
    create: (b: Omit<ServiceOut, 'id'>) => req<ServiceOut>('POST', '/services', b),
    update: (id: string, b: Omit<ServiceOut, 'id'>) => req<ServiceOut>('PUT', `/services/${id}`, b),
  },
  /** Prospect-facing, unauthenticated: the magic-link token is the credential. */
  public: {
    view: (token: string) => req<PublicView>('GET', `/public/${token}`, undefined, false),
    stage2: (token: string, b: EntityDetailsIn) => req<PublicView>('POST', `/public/${token}/stages/2`, b, false),
    stage3: (token: string, answers: Record<string, unknown>) => req<PublicView>('POST', `/public/${token}/stages/3`, { answers }, false),
    upload: async (token: string, key: string, file: File): Promise<PublicView> => {
      const fd = new FormData(); fd.append('file', file, file.name);
      const res = await fetch(`${API_BASE}/start/public/${token}/documents/${key}`, { method: 'POST', body: fd });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
      return data as PublicView;
    },
    stage4: (token: string) => req<PublicView>('POST', `/public/${token}/stages/4`, undefined, false),
    stage5: (token: string, parties: PartyIn[], ownership_complete: boolean) => req<PublicView>('POST', `/public/${token}/stages/5`, { parties, ownership_complete }, false),
    stage6: (token: string, service_ids: string[], notes?: string) => req<PublicView>('POST', `/public/${token}/stages/6`, { service_ids, notes: notes ?? null }, false),
    stage7: (token: string, accepted_by_name: string, accept: boolean) => req<PublicView>('POST', `/public/${token}/stages/7`, { accepted_by_name, accept }, false),
    mandate: (token: string, b: MandateIn) => req<PublicView>('POST', `/public/${token}/mandate`, b, false),
  },
};

export const STATUS_LABEL: Record<OnboardingStatus, string> = { draft: 'Draft', invited: 'Invited', in_progress: 'With prospect', awaiting_practice: 'With practice', activated: 'Activated', withdrawn: 'Withdrawn' };
export function onboardingTone(s: OnboardingStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' {
  return s === 'activated' ? 'success' : s === 'withdrawn' ? 'error' : s === 'awaiting_practice' ? 'warn' : s === 'draft' ? 'neutral' : 'info';
}
export function gateTone(s: GateOut['status']): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' {
  return s === 'Passed' ? 'success' : s === 'Pending' ? 'warn' : s === 'Failed' || s === 'Error' ? 'error' : 'neutral';
}
export const BASIS_LABEL: Record<ServiceOut['basis'], string> = { fixed: 'one-off', monthly: 'per month', quarterly: 'per quarter', annual: 'per year', hourly: 'per hour' };
