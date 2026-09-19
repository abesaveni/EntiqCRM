/** Typed client for EnTIQ Workpapers (services/api/app/modules/workpapers). */
import { API_BASE, ApiError, tokenStore } from './client';

export type PackStatus = 'draft' | 'in_progress' | 'in_review' | 'signed_off' | 'lodged' | 'archived';
export type WpItemStatus = 'not_started' | 'prepared' | 'queried' | 'reviewed' | 'signed_off' | 'n_a';
export type PackType = 'financial_statements' | 'tax_return' | 'bas' | 'smsf' | 'audit';

export interface WpItem {
  id: string; section: string; key: string; label: string; description: string | null; order: number; account_code: string | null; value_cents: number | null; prior_cents: number | null;
  variance_cents: number | null; variance_pct: number | null; status: WpItemStatus; evidence_state: 'missing' | 'attached' | 'verified'; document_id: string | null; document_filename: string | null;
  workings: string | null; query: string | null; prepared_by_name: string | null; prepared_at: string | null; reviewed_by_name: string | null; reviewed_at: string | null; material: boolean;
}
export interface WpIssue { id: string; item_id: string | null; item_label: string | null; kind: string; title: string; detail: string | null; severity: 'low' | 'medium' | 'high'; blocking: boolean; status: 'open' | 'resolved' | 'waived'; auto: boolean; raised_by_name: string | null; resolved_by_name: string | null; resolution: string | null; resolved_at: string | null; created_at: string }
export interface PackOut {
  id: string; client_id: string; client_name: string | null; job_id: string | null; title: string; pack_type: PackType; period_label: string | null; period_start: string | null; period_end: string | null;
  status: PackStatus; preparer_name: string | null; reviewer_name: string | null; prepared_at: string | null; reviewed_at: string | null; signed_off_at: string | null; signed_off_by_name: string | null;
  lodged_at: string | null; lodgement_ref: string | null; materiality_cents: number | null; ledger_source: string; ledger_synced_at: string | null; ledger_simulated: boolean; seal_sha256: string | null;
  items_total: number; items_done: number; evidence_attached: number; open_issues: number; blocking_issues: number; net_assets_cents: number | null; created_at: string; updated_at: string;
}
export interface PackDetail extends PackOut { items: WpItem[]; issues: WpIssue[]; sections: string[]; totals: Record<string, number>; notes: string | null }
export interface PackIn { client_id: string; job_id?: string | null; title?: string | null; pack_type?: PackType; period_label?: string | null; period_start?: string | null; period_end?: string | null; preparer_membership_id?: string | null; reviewer_membership_id?: string | null; materiality_cents?: number | null; use_template?: boolean }
export interface WpOverview { in_progress: number; in_review: number; signed_off_30d: number; lodged_30d: number; open_issues: number; blocking_issues: number; by_type: Record<string, number>; ledger_connections: number; ledger_live: boolean }
export interface LedgerConnectionOut { id: string; client_id: string | null; client_name: string | null; provider: string; status: string; simulated: boolean; external_name: string | null; external_tenant_id: string | null; scopes: string | null; last_sync_at: string | null; last_error: string | null; connected_by_name: string | null; created_at: string }
export interface SyncOut { pack: PackDetail; synced: number; simulated: boolean; source: string; message: string }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/workpapers${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
const qs = (o: Record<string, unknown>) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v)); const s = p.toString(); return s ? `?${s}` : ''; };

export const workpapers = {
  overview: () => req<WpOverview>('GET', '/overview'),
  templates: () => req<Record<string, Array<{ section: string; key: string; label: string }>>>('GET', '/templates'),
  packs: {
    list: (f: { status?: string; client_id?: string; mine?: boolean; open?: boolean } = {}) => req<PackOut[]>('GET', `/packs${qs(f)}`),
    create: (b: PackIn) => req<PackDetail>('POST', '/packs', b),
    get: (id: string) => req<PackDetail>('GET', `/packs/${id}`),
    addItem: (id: string, b: { section: string; label: string; description?: string | null; account_code?: string | null; value_cents?: number | null; prior_cents?: number | null }) => req<PackDetail>('POST', `/packs/${id}/items`, b),
    patchItem: (id: string, itemId: string, b: Partial<Pick<WpItem, 'label' | 'value_cents' | 'prior_cents' | 'account_code' | 'workings' | 'document_id' | 'status'>>) => req<PackDetail>('PATCH', `/packs/${id}/items/${itemId}`, b),
    checks: (id: string) => req<PackDetail>('POST', `/packs/${id}/checks`),
    raiseIssue: (id: string, b: { item_id?: string | null; kind?: string; title: string; detail?: string | null; severity?: string; blocking?: boolean }) => req<PackDetail>('POST', `/packs/${id}/issues`, b),
    resolveIssue: (id: string, issueId: string, resolution: string, waive = false) => req<PackDetail>('POST', `/packs/${id}/issues/${issueId}/resolve`, { resolution, waive }),
    submit: (id: string) => req<PackDetail>('POST', `/packs/${id}/submit`),
    signOff: (id: string, note?: string) => req<PackDetail>('POST', `/packs/${id}/sign-off`, { note: note ?? null }),
    reopen: (id: string) => req<PackDetail>('POST', `/packs/${id}/reopen`),
    lodge: (id: string, reference: string) => req<PackDetail>('POST', `/packs/${id}/lodge`, { reference }),
    sync: (id: string) => req<SyncOut>('POST', `/packs/${id}/sync`),
  },
  ledger: {
    connections: () => req<LedgerConnectionOut[]>('GET', '/ledger/connections'),
    connect: (client_id: string, provider: 'xero' | 'myob' = 'xero') => req<{ connection: LedgerConnectionOut; authorize_url: string | null; message: string }>('POST', '/ledger/connect', { client_id, provider }),
  },
};

export const PACK_TYPE_LABEL: Record<PackType, string> = { financial_statements: 'Financial statements', tax_return: 'Tax return', bas: 'Activity statement', smsf: 'SMSF', audit: 'Audit' };
export const WP_STATUS_LABEL: Record<PackStatus, string> = { draft: 'Draft', in_progress: 'In progress', in_review: 'In review', signed_off: 'Signed off', lodged: 'Lodged', archived: 'Archived' };
export const WP_ITEM_LABEL: Record<WpItemStatus, string> = { not_started: 'Not started', prepared: 'Prepared', queried: 'Query', reviewed: 'Reviewed', signed_off: 'Signed off', n_a: 'N/A' };
export function wpTone(s: PackStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'lodged' || s === 'signed_off' ? 'success' : s === 'in_review' ? 'teal' : s === 'in_progress' ? 'info' : 'neutral'; }
export function wpItemTone(s: WpItemStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'signed_off' ? 'success' : s === 'queried' ? 'warn' : s === 'reviewed' ? 'teal' : s === 'prepared' ? 'info' : 'neutral'; }
