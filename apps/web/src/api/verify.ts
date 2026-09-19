/** Typed client for EnTIQ Verify (services/api/app/modules/verify). Shapes mirror its schemas.py. */
import { API_BASE, ApiError, tokenStore } from './client';

export type VerificationStatus = 'pending' | 'in_progress' | 'verified' | 'failed' | 'expired' | 'cancelled';
export type ScreeningStatus = 'clear' | 'potential_match' | 'confirmed_match' | 'false_positive' | 'error';

export interface ProviderHealth { identity: { provider: string; live: boolean }; screening: { provider: string; live: boolean } }
export interface VerificationOut {
  id: string; client_id: string; contact_id: string | null; subject_type: 'individual' | 'entity'; subject_name: string; provider: string; simulated: boolean;
  status: VerificationStatus; verification_url: string | null; result: Record<string, unknown>; failure_reason: string | null; started_by_name: string | null;
  completed_at: string | null; expires_at: string | null; created_at: string;
}
export interface ScreeningMatch { id?: string; name?: string; score?: number; topics?: string[]; datasets?: string[]; schema?: string; countries?: string[] }
export interface ScreeningOut {
  id: string; client_id: string; client_name: string | null; contact_id: string | null; subject_type: 'individual' | 'entity'; subject_name: string; provider: string; simulated: boolean;
  status: ScreeningStatus; match_count: number; matches: ScreeningMatch[]; threshold: number; error: string | null; screened_at: string;
  review_decision: 'true_match' | 'false_positive' | null; reviewed_by_name: string | null; reviewed_at: string | null; review_notes: string | null;
}
export interface RiskFactor { factor: string; label: string; points: number; detail?: string }
export interface RiskOut { id: string; client_id: string; rating: 'Low' | 'Medium' | 'High'; score: number; method: string; factors: RiskFactor[]; assessed_by_name: string | null; assessed_at: string; next_review_at: string; notes: string | null }
export interface PartyStatus { contact_id: string; name: string; role: string | null; identity_status: 'verified' | 'in_progress' | 'failed' | 'none'; identity_simulated: boolean; screening_status: ScreeningStatus | 'none'; screening_simulated: boolean }
export interface ClientVerifyOut {
  client_id: string; client_name: string; client_type: string; risk: RiskOut | null; entity_screening: ScreeningOut | null; entity_verification: VerificationOut | null;
  parties: PartyStatus[]; verifications: VerificationOut[]; screenings: ScreeningOut[]; providers: ProviderHealth;
}
export interface VerifyOverview { verifications_pending: number; verifications_verified: number; screenings_to_review: number; reviews_due_30d: number; clients_unassessed: number; providers: ProviderHealth }
export interface ReviewDueOut { client_id: string; client_name: string; rating: string; next_review_at: string; overdue: boolean }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/verify${path}`, {
    method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
const qs = (o: Record<string, unknown>) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v)); const s = p.toString(); return s ? `?${s}` : ''; };

export const verify = {
  overview: () => req<VerifyOverview>('GET', '/overview'),
  client: (clientId: string) => req<ClientVerifyOut>('GET', `/clients/${clientId}`),
  verifications: {
    list: (f: { status?: string; client_id?: string; limit?: number } = {}) => req<VerificationOut[]>('GET', `/verifications${qs(f)}`),
    start: (clientId: string, b: { subject_type: 'individual' | 'entity'; contact_id?: string | null }) => req<VerificationOut>('POST', `/clients/${clientId}/verifications`, b),
    refresh: (id: string) => req<VerificationOut>('POST', `/verifications/${id}/refresh`),
    cancel: (id: string) => req<VerificationOut>('POST', `/verifications/${id}/cancel`),
  },
  screenings: {
    list: (f: { review_queue?: boolean; client_id?: string; limit?: number } = {}) => req<ScreeningOut[]>('GET', `/screenings${qs(f)}`),
    run: (clientId: string, b: { contact_id?: string | null; dob?: string | null } = {}) => req<ScreeningOut>('POST', `/clients/${clientId}/screen`, b),
    review: (id: string, b: { decision: 'true_match' | 'false_positive'; notes?: string | null }) => req<ScreeningOut>('POST', `/screenings/${id}/review`, b),
  },
  risk: {
    assess: (clientId: string, notes?: string) => req<RiskOut>('POST', `/clients/${clientId}/assess`, { notes: notes ?? null }),
    history: (clientId: string) => req<RiskOut[]>('GET', `/clients/${clientId}/risk-history`),
  },
  reviewsDue: (days = 30) => req<ReviewDueOut[]>('GET', `/reviews-due?days=${days}`),
};

export const SCREENING_LABEL: Record<ScreeningStatus | 'none', string> = { clear: 'Clear', potential_match: 'Potential match', confirmed_match: 'Confirmed match', false_positive: 'False positive', error: 'Error', none: 'Not screened' };
export const IDENTITY_LABEL: Record<PartyStatus['identity_status'], string> = { verified: 'Verified', in_progress: 'In progress', failed: 'Failed', none: 'Not verified' };
