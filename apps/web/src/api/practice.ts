/** Typed client for EnTIQ Practice (services/api/app/modules/practice). */
import { API_BASE, ApiError, tokenStore } from './client';

export type JobStatus = 'not_started' | 'in_progress' | 'waiting_client' | 'review' | 'complete' | 'cancelled';
export type Frequency = 'monthly' | 'quarterly' | 'biannual' | 'annual';
export interface ChecklistItem { key: string; label: string; done: boolean }
export interface JobOut {
  id: string; client_id: string; client_name: string | null; title: string; job_type: string; period_label: string | null; period_start: string | null; period_end: string | null; due_on: string | null; lodgement_due: string | null;
  status: JobStatus; priority: 'Low' | 'Normal' | 'High'; assignee_membership_id: string | null; assignee_name: string | null; reviewer_name: string | null; budget_minutes: number | null; actual_minutes: number; fee_cents: number | null;
  recurring_job_id: string | null; source: 'manual' | 'recurring' | 'onboarding'; checklist: ChecklistItem[]; notes: string | null; overdue: boolean; started_at: string | null; completed_at: string | null; created_at: string;
}
export interface JobIn { client_id: string; title: string; job_type: string; period_label?: string | null; period_start?: string | null; period_end?: string | null; due_on?: string | null; lodgement_due?: string | null; priority?: 'Low' | 'Normal' | 'High'; assignee_membership_id?: string | null; reviewer_membership_id?: string | null; budget_minutes?: number | null; fee_cents?: number | null; checklist?: ChecklistItem[] | null; notes?: string | null }
export interface RecurringOut { id: string; client_id: string; client_name: string | null; name_template: string; job_type: string; frequency: Frequency; month_offset: number; day_of_month: number; advance_days: number; assignee_name: string | null; budget_minutes: number | null; fee_cents: number | null; is_active: boolean; last_period_label: string | null; next_due_on: string | null; notes: string | null; created_at: string }
export interface RecurringIn { client_id: string; name_template?: string; job_type: string; frequency: Frequency; month_offset?: number; day_of_month?: number; advance_days?: number; assignee_membership_id?: string | null; budget_minutes?: number | null; fee_cents?: number | null; notes?: string | null }
export interface TimeOut { id: string; job_id: string; membership_id: string; member_name: string | null; worked_on: string; minutes: number; billable: boolean; note: string | null; created_at: string }
export interface DeadlineOut { on: string; kind: 'job' | 'statutory'; label: string; job_id: string | null; client_id: string | null; client_name: string | null; overdue: boolean; detail: string | null }
export interface TeamMember { membership_id: string; name: string; role: string; open_jobs: number; overdue_jobs: number; minutes_this_month: number; budget_minutes_open: number }
export interface PracticeOverview { open_jobs: number; overdue: number; due_7d: number; unassigned: number; waiting_client: number; in_review: number; completed_30d: number; by_type: Record<string, number>; minutes_this_month: number; recurring_active: number; upcoming: DeadlineOut[] }
export interface PracticeMeta { job_types: string[]; statuses: JobStatus[]; frequencies: Frequency[]; default_checklists: Record<string, string[]> }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/practice${path}`, {
    method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
const qs = (o: Record<string, unknown>) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v)); const s = p.toString(); return s ? `?${s}` : ''; };

export const practice = {
  overview: () => req<PracticeOverview>('GET', '/overview'),
  meta: () => req<PracticeMeta>('GET', '/meta'),
  jobs: {
    list: (f: { status?: string; client_id?: string; assignee?: string; job_type?: string; mine?: boolean; open?: boolean } = {}) => req<JobOut[]>('GET', `/jobs${qs(f)}`),
    create: (b: JobIn) => req<JobOut>('POST', '/jobs', b),
    get: (id: string) => req<JobOut>('GET', `/jobs/${id}`),
    patch: (id: string, b: Partial<JobIn>) => req<JobOut>('PATCH', `/jobs/${id}`, b),
    setStatus: (id: string, status: JobStatus, note?: string) => req<JobOut>('POST', `/jobs/${id}/status`, { status, note: note ?? null }),
    time: (id: string) => req<TimeOut[]>('GET', `/jobs/${id}/time`),
    addTime: (id: string, b: { worked_on: string; minutes: number; billable?: boolean; note?: string | null }) => req<TimeOut>('POST', `/jobs/${id}/time`, b),
  },
  recurring: {
    list: (client_id?: string) => req<RecurringOut[]>('GET', `/recurring${qs({ client_id })}`),
    create: (b: RecurringIn) => req<RecurringOut>('POST', '/recurring', b),
    toggle: (id: string) => req<RecurringOut>('POST', `/recurring/${id}/toggle`),
    generate: () => req<{ created: number }>('POST', '/recurring/generate'),
  },
  deadlines: (days = 90) => req<DeadlineOut[]>('GET', `/deadlines?days=${days}`),
  team: () => req<TeamMember[]>('GET', '/team'),
};

export const JOB_STATUS_LABEL: Record<JobStatus, string> = { not_started: 'Not started', in_progress: 'In progress', waiting_client: 'Waiting on client', review: 'In review', complete: 'Complete', cancelled: 'Cancelled' };
export function jobTone(s: JobStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' {
  return s === 'complete' ? 'success' : s === 'cancelled' ? 'neutral' : s === 'waiting_client' ? 'warn' : s === 'review' ? 'teal' : s === 'in_progress' ? 'info' : 'neutral';
}
export const fmtMinutes = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ''}` : `${m}m`);
