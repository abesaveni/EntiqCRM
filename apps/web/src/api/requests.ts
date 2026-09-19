/** Typed client for EnTIQ Requests (services/api/app/modules/requests). Staff routes need a bearer token; /r/{token} client routes do not. */
import { API_BASE, ApiError, tokenStore } from './client';

export type PackStatus = 'draft' | 'sent' | 'in_progress' | 'submitted' | 'reviewing' | 'complete' | 'cancelled';
export type ItemStatus = 'pending' | 'uploaded' | 'accepted' | 'rejected' | 'not_applicable';
export type Purpose = 'tax_return' | 'bas' | 'financials' | 'lending' | 'onboarding' | 'audit' | 'custom';
export type Category = 'identity' | 'financial' | 'tax' | 'bank' | 'payroll' | 'legal' | 'property' | 'other';

export interface Classification { detected?: string; confidence?: number; matches_item?: boolean; flags?: string[]; method?: string }
export interface ItemOut { id: string; key: string; label: string; description: string | null; category: Category; required: boolean; order: number; status: ItemStatus; document_id: string | null; document_filename: string | null; client_note: string | null; rejection_reason: string | null; classification: Classification; uploaded_at: string | null; reviewed_by_name: string | null; reviewed_at: string | null }
export interface QuestionOut { key: string; label: string; answer: boolean | null; adds: string[] }
export interface PackOut {
  id: string; client_id: string; client_name: string | null; contact_id: string | null; contact_name: string | null; contact_email: string | null; title: string; purpose: Purpose; period_label: string | null; message: string | null; status: PackStatus; due_on: string | null; overdue: boolean;
  items_total: number; items_required: number; items_done: number; items_uploaded: number; items_rejected: number; exceptions: number; created_by_name: string | null; sent_at: string | null; submitted_at: string | null; completed_at: string | null; reminder_count: number; last_reminded_at: string | null; token_expires_at: string | null; created_at: string; updated_at: string;
}
export interface PackDetail extends PackOut { items: ItemOut[]; questions: QuestionOut[]; request_url: string | null }
export interface ItemIn { key?: string | null; label: string; description?: string | null; category?: Category; required?: boolean }
export interface PackIn { client_id: string; contact_id?: string | null; title?: string | null; purpose?: Purpose; period_label?: string | null; message?: string | null; due_in_days?: number; use_template?: boolean; items?: ItemIn[]; send_now?: boolean }
export interface TemplateOut { purpose: Purpose; label: string; items: Array<{ key: string; label: string; category: Category; required: boolean; entity_types: string[]; conditional: boolean }>; questions: Array<{ key: string; label: string; adds: string[] }> }
export interface RequestsOverview { awaiting_client: number; awaiting_review: number; exceptions: number; overdue: number; completed_30d: number; avg_days_to_submit: number | null }
export interface PublicPack { practice_name: string; client_name: string; contact_name: string | null; title: string; purpose: Purpose; message: string | null; status: PackStatus; due_on: string | null; items: ItemOut[]; questions: QuestionOut[]; expires_at: string | null; can_submit: boolean; outstanding: string[] }

async function req<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const t = auth ? tokenStore.get() : null;
  const res = await fetch(`${API_BASE}/requests${path}`, {
    method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
async function upload<T>(path: string, file: File, auth: boolean): Promise<T> {
  const t = auth ? tokenStore.get() : null;
  const fd = new FormData(); fd.append('file', file, file.name);
  const res = await fetch(`${API_BASE}/requests${path}`, { method: 'POST', headers: t ? { Authorization: `Bearer ${t.access_token}` } : {}, body: fd });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

export const requests = {
  overview: () => req<RequestsOverview>('GET', '/overview'),
  templates: () => req<TemplateOut[]>('GET', '/templates'),
  packs: {
    list: (f: { status?: string; client_id?: string; open?: boolean } = {}) => { const p = new URLSearchParams(); if (f.status) p.set('status', f.status); if (f.client_id) p.set('client_id', f.client_id); if (f.open) p.set('open', 'true'); const s = p.toString(); return req<PackOut[]>('GET', `/packs${s ? `?${s}` : ''}`); },
    create: (b: PackIn) => req<PackDetail>('POST', '/packs', b),
    get: (id: string) => req<PackDetail>('GET', `/packs/${id}`),
    send: (id: string) => req<PackDetail>('POST', `/packs/${id}/send`),
    remind: (id: string) => req<PackDetail>('POST', `/packs/${id}/remind`),
    addItems: (id: string, items: ItemIn[], notify = true) => req<PackDetail>('POST', `/packs/${id}/items`, { items, notify }),
    review: (id: string, itemId: string, decision: 'accept' | 'reject', reason?: string) => req<PackDetail>('POST', `/packs/${id}/items/${itemId}/review`, { decision, reason: reason ?? null }),
    complete: (id: string) => req<PackDetail>('POST', `/packs/${id}/complete`),
    cancel: (id: string) => req<PackDetail>('POST', `/packs/${id}/cancel`),
  },
  /** Client-facing, unauthenticated: the emailed token is the credential. */
  public: {
    view: (token: string) => req<PublicPack>('GET', `/public/${token}`, undefined, false),
    answer: (token: string, key: string, answer: boolean) => req<PublicPack>('POST', `/public/${token}/questions`, { key, answer }, false),
    upload: (token: string, itemId: string, file: File) => upload<PublicPack>(`/public/${token}/items/${itemId}/upload`, file, false),
    notApplicable: (token: string, itemId: string, note: string) => req<PublicPack>('POST', `/public/${token}/items/${itemId}/not-applicable`, { note }, false),
    fileUrl: (token: string, itemId: string) => `${API_BASE}/requests/public/${token}/items/${itemId}/file`,
    submit: (token: string) => req<PublicPack>('POST', `/public/${token}/submit`, undefined, false),
  },
};

export const PACK_STATUS_LABEL: Record<PackStatus, string> = { draft: 'Draft', sent: 'Sent', in_progress: 'In progress', submitted: 'Submitted', reviewing: 'Reviewing', complete: 'Complete', cancelled: 'Cancelled' };
export const ITEM_STATUS_LABEL: Record<ItemStatus, string> = { pending: 'Awaiting', uploaded: 'Uploaded', accepted: 'Accepted', rejected: 'Needs another look', not_applicable: 'Not applicable' };
export const PURPOSE_LABEL: Record<Purpose, string> = { tax_return: 'Tax return', bas: 'Activity statement', financials: 'Financial statements', lending: 'Finance application', onboarding: 'Onboarding', audit: 'Audit evidence', custom: 'Custom' };
export function packTone(s: PackStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'complete' ? 'success' : s === 'cancelled' ? 'neutral' : s === 'submitted' || s === 'reviewing' ? 'warn' : s === 'draft' ? 'neutral' : 'info'; }
export function itemTone(s: ItemStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'accepted' ? 'success' : s === 'rejected' ? 'error' : s === 'uploaded' ? 'teal' : s === 'not_applicable' ? 'neutral' : 'neutral'; }
