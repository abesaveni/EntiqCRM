/**
 * Client portal (module 14): the staff side (/client/*, bearer token) and the client's own surface (/portal/*, portal token).
 * The portal token lives in sessionStorage, separate from the staff token store, so a practice user can preview both.
 */
import { API_BASE, ApiError, tokenStore } from './client';
import type { PublicPack } from './requests';

export interface PortalContactOut { contact_id: string; client_id: string; client_name: string; name: string; email: string | null; role: string | null; has_portal_access: boolean; invited_at: string | null; last_login_at: string | null; active_sessions: number }
export interface ThreadMessage { id: string; from_client: boolean; author: string; body: string; created_at: string; read: boolean }
export interface StaffOverview { contacts_with_access: number; clients_with_access: number; logins_30d: number; unread_messages: number; shared_documents: number }
export interface PortalMe { contact_id: string; name: string; email: string | null; client_id: string; client_name: string; client_type: string; practice_name: string; practice_email: string | null; practice_phone: string | null; features: Record<'documents' | 'messages' | 'requests' | 'agreements' | 'jobs', boolean>; counts: Record<'shared_documents' | 'unread_messages' | 'open_requests' | 'awaiting_signature', number> }
export interface PortalDocument { id: string; filename: string; kind: string; size_bytes: number; content_type: string; uploaded_by: string; created_at: string }
export interface PortalRequest { id: string; title: string; purpose: string; status: string; due_on: string | null; overdue: boolean; items_total: number; items_done: number; outstanding: number }
export interface PortalAgreement { id: string; title: string; kind: string; status: string; my_status: string; sent_at: string | null; completed_at: string | null; expires_at: string | null }
export interface PortalJob { id: string; title: string; job_type: string; period_label: string | null; status: string; due_on: string | null; completed_at: string | null }
export interface PortalActivity { kind: string; summary: string; module_key: string; occurred_at: string }
export interface PortalHome { me: PortalMe; requests: PortalRequest[]; agreements: PortalAgreement[]; jobs: PortalJob[]; recent: PortalActivity[]; messages: ThreadMessage[] }
export interface PortalTokenOut { access_token: string; token_type: string; expires_at: string; practice_name: string; client_name: string }

const PORTAL_KEY = 'entiq.portal.session';
export const portalSession = {
  get: (): PortalTokenOut | null => { try { const raw = sessionStorage.getItem(PORTAL_KEY); return raw ? (JSON.parse(raw) as PortalTokenOut) : null; } catch { return null; } },
  set: (t: PortalTokenOut) => { try { sessionStorage.setItem(PORTAL_KEY, JSON.stringify(t)); } catch { /* private mode */ } },
  clear: () => { try { sessionStorage.removeItem(PORTAL_KEY); } catch { /* ignore */ } },
};

async function staffReq<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/client${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
async function portalReq<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const t = auth ? portalSession.get() : null;
  const res = await fetch(`${API_BASE}/portal${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined && !(body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) { if (res.status === 401) portalSession.clear(); throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data); }
  return data as T;
}
const fd = (file: File) => { const f = new FormData(); f.append('file', file, file.name); return f; };

export const clientPortalStaff = {
  overview: () => staffReq<StaffOverview>('GET', '/overview'),
  contacts: (clientId?: string) => staffReq<PortalContactOut[]>('GET', `/contacts${clientId ? `?client_id=${clientId}` : ''}`),
  invite: (contactId: string) => staffReq<PortalContactOut>('POST', `/contacts/${contactId}/invite`),
  revoke: (contactId: string) => staffReq<PortalContactOut>('POST', `/contacts/${contactId}/revoke`),
  thread: (clientId: string) => staffReq<ThreadMessage[]>('GET', `/clients/${clientId}/messages`),
  post: (clientId: string, body: string) => staffReq<ThreadMessage[]>('POST', `/clients/${clientId}/messages`, { body }),
};

export const portal = {
  requestLink: (email: string) => portalReq<{ sent: boolean }>('POST', '/auth/request-link', { email }, false),
  exchange: async (token: string) => { const t = await portalReq<PortalTokenOut>('POST', '/auth/exchange', { token }, false); portalSession.set(t); return t; },
  logout: async () => { try { await portalReq<void>('POST', '/logout'); } finally { portalSession.clear(); } },
  me: () => portalReq<PortalMe>('GET', '/me'),
  home: () => portalReq<PortalHome>('GET', '/home'),
  documents: () => portalReq<PortalDocument[]>('GET', '/documents'),
  download: async (d: PortalDocument) => {
    const t = portalSession.get();
    const res = await fetch(`${API_BASE}/portal/documents/${d.id}/download`, { headers: t ? { Authorization: `Bearer ${t.access_token}` } : {} });
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement('a'), { href: url, download: d.filename }); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  },
  upload: (file: File) => portalReq<PortalDocument>('POST', '/documents', fd(file)),
  messages: () => portalReq<ThreadMessage[]>('GET', '/messages'),
  post: (body: string) => portalReq<ThreadMessage[]>('POST', '/messages', { body }),
  resendAgreement: (id: string) => portalReq<{ sent: number }>('POST', `/agreements/${id}/resend`),
  request: (id: string) => portalReq<PublicPack>('GET', `/requests/${id}`),
  answer: (id: string, key: string, answer: boolean) => portalReq<PublicPack>('POST', `/requests/${id}/questions`, { key, answer }),
  uploadItem: (id: string, itemId: string, file: File) => portalReq<PublicPack>('POST', `/requests/${id}/items/${itemId}/upload`, fd(file)),
  notApplicable: (id: string, itemId: string, note: string) => portalReq<PublicPack>('POST', `/requests/${id}/items/${itemId}/not-applicable`, { note }),
  submit: (id: string) => portalReq<PublicPack>('POST', `/requests/${id}/submit`),
};
