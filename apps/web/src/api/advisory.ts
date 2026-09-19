/** Typed client for EnTIQ Advisory (services/api/app/modules/advisory). */
import { API_BASE, ApiError, tokenStore } from './client';

export interface SnapshotOut {
  id: string; client_id: string; client_name: string | null; as_at: string; period_label: string | null; source: string; simulated: boolean; workpaper_id: string | null;
  revenue_cents: number | null; gross_profit_cents: number | null; expenses_cents: number | null; net_profit_cents: number | null; cash_cents: number | null; receivables_cents: number | null;
  payables_cents: number | null; inventory_cents: number | null; debt_cents: number | null; equity_cents: number | null; tax_provision_cents: number | null;
  kpis: Record<string, number>; health_score: number | null; health_band: 'good' | 'watch' | 'needs_action' | null; notes: string | null; created_by_name: string | null; created_at: string;
}
export interface AlertOut { id: string; client_id: string; client_name: string | null; snapshot_id: string | null; code: string; title: string; detail: string | null; severity: 'info' | 'watch' | 'action'; metric: string | null; value: number | null; benchmark: number | null; recommendation: string | null; status: string; auto: boolean; created_at: string }
export interface ActionOut { id: string; client_id: string; client_name: string | null; meeting_id: string | null; alert_id: string | null; title: string; detail: string | null; owner_side: 'practice' | 'client'; owner_name: string | null; due_on: string | null; overdue: boolean; status: 'open' | 'in_progress' | 'done' | 'cancelled'; visible_to_client: boolean; completed_at: string | null; task_id: string | null; created_at: string }
export interface AgendaItem { title: string; note: string | null; source: string; source_ref?: string | null; decision: string | null }
export interface MeetingOut { id: string; client_id: string; client_name: string | null; snapshot_id: string | null; title: string; kind: string; scheduled_for: string | null; status: 'scheduled' | 'prepared' | 'held' | 'published' | 'cancelled'; agenda: AgendaItem[]; summary: string | null; prepared_by_name: string | null; held_at: string | null; published_at: string | null; document_id: string | null; action_count: number; created_at: string }
export interface MeetingDetail extends MeetingOut { snapshot: SnapshotOut | null; alerts: AlertOut[]; actions: ActionOut[] }
export interface ClientAdvisory { client_id: string; client_name: string; latest: SnapshotOut | null; history: SnapshotOut[]; alerts: AlertOut[]; actions: ActionOut[]; meetings: MeetingOut[] }
export interface AdvisoryOverview { clients_with_snapshots: number; open_alerts: number; action_alerts: number; open_actions: number; overdue_actions: number; meetings_scheduled: number; meetings_held_90d: number; avg_health_score: number | null; attention: Array<{ client_id: string; client_name: string; health_score: number | null; health_band: string | null; alerts: string[]; as_at: string }> }
export interface SnapshotIn { client_id: string; as_at?: string | null; period_label?: string | null; workpaper_id?: string | null; revenue_cents?: number | null; gross_profit_cents?: number | null; expenses_cents?: number | null; net_profit_cents?: number | null; cash_cents?: number | null; receivables_cents?: number | null; payables_cents?: number | null; inventory_cents?: number | null; debt_cents?: number | null; equity_cents?: number | null; tax_provision_cents?: number | null; notes?: string | null }
export interface ActionIn { client_id: string; title: string; detail?: string | null; owner_side?: 'practice' | 'client'; owner_membership_id?: string | null; owner_label?: string | null; due_on?: string | null; visible_to_client?: boolean; alert_id?: string | null; meeting_id?: string | null }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/advisory${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
const qs = (o: Record<string, unknown>) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v)); const s = p.toString(); return s ? `?${s}` : ''; };

export const advisory = {
  overview: () => req<AdvisoryOverview>('GET', '/overview'),
  client: (clientId: string) => req<ClientAdvisory>('GET', `/clients/${clientId}`),
  snapshots: {
    list: (client_id?: string) => req<SnapshotOut[]>('GET', `/snapshots${qs({ client_id })}`),
    create: (b: SnapshotIn) => req<SnapshotOut>('POST', '/snapshots', b),
  },
  alerts: {
    list: (f: { status?: string; severity?: string; client_id?: string } = {}) => req<AlertOut[]>('GET', `/alerts${qs(f)}`),
    raise: (b: { client_id: string; title: string; detail?: string | null; severity?: string; recommendation?: string | null }) => req<AlertOut>('POST', '/alerts', b),
    dismiss: (id: string, reason: string) => req<AlertOut>('POST', `/alerts/${id}/dismiss`, { reason }),
  },
  actions: {
    list: (f: { status?: string; client_id?: string; mine?: boolean } = {}) => req<ActionOut[]>('GET', `/actions${qs(f)}`),
    create: (b: ActionIn) => req<ActionOut>('POST', '/actions', b),
    patch: (id: string, b: { status?: string; due_on?: string | null; owner_membership_id?: string | null; owner_label?: string | null; visible_to_client?: boolean }) => req<ActionOut>('PATCH', `/actions/${id}`, b),
  },
  meetings: {
    list: (f: { status?: string; client_id?: string } = {}) => req<MeetingOut[]>('GET', `/meetings${qs(f)}`),
    create: (b: { client_id: string; title?: string | null; kind?: string; scheduled_for?: string | null; snapshot_id?: string | null }) => req<MeetingDetail>('POST', '/meetings', b),
    get: (id: string) => req<MeetingDetail>('GET', `/meetings/${id}`),
    patch: (id: string, b: { title?: string; scheduled_for?: string | null; agenda?: AgendaItem[]; summary?: string | null }) => req<MeetingDetail>('PATCH', `/meetings/${id}`, b),
    prepare: (id: string) => req<MeetingDetail>('POST', `/meetings/${id}/prepare`),
    hold: (id: string, b: { summary: string; decisions?: Record<string, string>; actions?: ActionIn[] }) => req<MeetingDetail>('POST', `/meetings/${id}/hold`, b),
    publish: (id: string) => req<MeetingDetail>('POST', `/meetings/${id}/publish`),
  },
};

export const KPI_LABEL: Record<string, string> = {
  gross_margin_pct: 'Gross margin', net_margin_pct: 'Net margin', debtor_days: 'Debtor days', creditor_days: 'Creditor days', inventory_days: 'Inventory days',
  current_ratio: 'Current ratio', cash_runway_months: 'Cash runway', debt_to_equity: 'Debt to equity', cash_conversion_days: 'Cash conversion',
};
export const KPI_SUFFIX: Record<string, string> = { gross_margin_pct: '%', net_margin_pct: '%', debtor_days: ' days', creditor_days: ' days', inventory_days: ' days', cash_runway_months: ' mo', cash_conversion_days: ' days' };
export function healthTone(b: string | null): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return b === 'good' ? 'success' : b === 'watch' ? 'warn' : b === 'needs_action' ? 'error' : 'neutral'; }
export function severityTone(s: string): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'action' ? 'error' : s === 'watch' ? 'warn' : 'info'; }
