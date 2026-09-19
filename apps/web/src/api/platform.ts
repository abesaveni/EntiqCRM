/** Typed client for the platform layer: notifications, documents, billing, dev controls. Mirrors schemas_platform.py. */
import type { ModuleKey } from '@entiq/modules';
import { API_BASE, ApiError, tokenStore, type LifecycleStatus, type SessionOut } from './client';

export interface NotificationOut { id: string; kind: string; title: string; body: string | null; link: string | null; module_key: ModuleKey; read_at: string | null; created_at: string }
export interface DocumentOut {
  id: string; client_id: string | null; module_key: ModuleKey; kind: string; filename: string; content_type: string; size_bytes: number; sha256: string;
  description: string | null; uploaded_by_name: string | null; scan_status: 'clean' | 'infected' | 'unavailable' | 'pending'; retention_hold: boolean; visible_to_client: boolean; retention_until: string | null; created_at: string;
}
export interface BillingEventOut { id: number; module_key: ModuleKey | null; kind: string; amount_cents: number; gst_cents: number; total_cents: number; currency: string; status: string; detail: Record<string, unknown>; created_at: string }
export interface BillingLine { module_key: ModuleKey; name: string; status: LifecycleStatus; pricing_model: string; unit: string; indicative_monthly_cents: number | null; seats: number | null }
export interface BillingSummary {
  tenant_status: LifecycleStatus; base_plan_cents: number; base_plan_inc_gst_cents: number; gst_rate_bps: number; trial_ends_at: string | null; current_period_end: string | null;
  next_charge_at: string | null; next_charge_estimate_cents: number; card_on_file: boolean; card_last4: string | null; billing_mode: 'simulate' | 'stripe'; lines: BillingLine[]; recent: BillingEventOut[];
}
export interface OutboundOut { id: string; to_address: string; subject: string; template: string | null; status: 'queued' | 'sent' | 'failed' | 'skipped'; attempts: number; last_error: string | null; created_at: string; sent_at: string | null; body_text: string }
export interface LifecycleRun { stats: Record<string, unknown>; session: SessionOut }

function authHeaders(): Record<string, string> {
  const t = tokenStore.get();
  return t ? { Authorization: `Bearer ${t.access_token}` } : {};
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...authHeaders() }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

export const platform = {
  notifications: {
    list: (unread = false, limit = 30) => req<NotificationOut[]>('GET', `/notifications?unread=${unread}&limit=${limit}`),
    unreadCount: () => req<{ unread: number }>('GET', '/notifications/unread-count'),
    markRead: (id: string) => req<NotificationOut>('POST', `/notifications/${id}/read`),
    readAll: () => req<{ unread: number }>('POST', '/notifications/read-all'),
  },
  documents: {
    list: (clientId?: string, kind?: string) => req<DocumentOut[]>('GET', `/documents?${new URLSearchParams({ ...(clientId ? { client_id: clientId } : {}), ...(kind ? { kind } : {}) }).toString()}`),
    upload: async (file: File, opts: { clientId?: string; kind?: string; description?: string } = {}): Promise<DocumentOut> => {
      const fd = new FormData();
      fd.append('file', file, file.name);
      if (opts.clientId) fd.append('client_id', opts.clientId);
      if (opts.kind) fd.append('kind', opts.kind);
      if (opts.description) fd.append('description', opts.description);
      const res = await fetch(`${API_BASE}/documents`, { method: 'POST', headers: authHeaders(), body: fd });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
      return data as DocumentOut;
    },
    /** Downloads through fetch (the endpoint needs the bearer token) and hands the browser a blob URL. */
    download: async (doc: DocumentOut): Promise<void> => {
      const res = await fetch(`${API_BASE}/documents/${doc.id}/download`, { headers: authHeaders() });
      if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement('a'), { href: url, download: doc.filename });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    },
    remove: (id: string) => req<void>('DELETE', `/documents/${id}`),
    setHold: (id: string, hold: boolean, until?: string, reason?: string) => req<DocumentOut>('POST', `/documents/${id}/hold`, { hold, until: until ?? null, reason: reason ?? null }),
    share: (id: string, visible_to_client: boolean) => req<DocumentOut>('POST', `/documents/${id}/share`, { visible_to_client }),
  },
  billing: {
    summary: () => req<BillingSummary>('GET', '/billing/summary'),
    events: (limit = 50) => req<BillingEventOut[]>('GET', `/billing/events?limit=${limit}`),
  },
  dev: {
    runLifecycle: () => req<LifecycleRun>('POST', '/dev/run-lifecycle'),
    timeTravel: (b: { trial_ends_in_days?: number; status_changed_days_ago?: number }) => req<SessionOut>('POST', '/dev/time-travel', b),
    deliverOutbound: () => req<Record<string, number>>('POST', '/dev/deliver-outbound'),
    outbound: (limit = 20) => req<OutboundOut[]>('GET', `/dev/outbound?limit=${limit}`),
  },
};

export const fmtCents = (cents: number) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' }).format(cents / 100);
export const fmtBytes = (n: number) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);
