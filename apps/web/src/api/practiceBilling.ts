/** Typed client for EnTIQ Billing (module 19) — the practice invoicing its own clients. */
import { API_BASE, ApiError, tokenStore } from './client';

export type InvoiceStatus = 'draft' | 'sent' | 'part_paid' | 'paid' | 'overdue' | 'void';
export interface LineOut { id: string; description: string; quantity: number; unit_cents: number; gst: boolean; amount_cents: number; module_key: string | null }
export interface PaymentOut { id: string; amount_cents: number; method: string; reference: string | null; received_on: string; recorded_by_name: string | null }
export interface InvoiceOut {
  id: string; client_id: string; client_name: string | null; contact_name: string | null; contact_email: string | null; number: string; status: InvoiceStatus; issued_on: string | null; due_on: string | null;
  period_label: string | null; subtotal_cents: number; gst_cents: number; total_cents: number; paid_cents: number; balance_cents: number; overdue: boolean; days_overdue: number; notes: string | null;
  fee_schedule_id: string | null; job_id: string | null; document_id: string | null; external_ref: string | null; reminders_sent: number; sent_at: string | null; paid_at: string | null; created_by_name: string | null; created_at: string;
}
export interface InvoiceDetail extends InvoiceOut { lines: LineOut[]; payments: PaymentOut[] }
export interface ScheduleOut { id: string; client_id: string; client_name: string | null; name: string; frequency: 'monthly' | 'quarterly' | 'annual'; amount_cents: number; gst: boolean; total_cents: number; day_of_month: number; terms_days: number; method: string; is_active: boolean; next_issue_on: string | null; last_invoice_period: string | null; source: string; annualised_cents: number }
export interface StatementRow { invoice_id: string; number: string; issued_on: string | null; due_on: string | null; total_cents: number; paid_cents: number; balance_cents: number; status: InvoiceStatus; days_overdue: number }
export interface ClientStatement { client_id: string; client_name: string; outstanding_cents: number; overdue_cents: number; current_cents: number; invoices: StatementRow[]; schedules: ScheduleOut[] }
export interface AgedRow { client_id: string; client_name: string; current_cents: number; d30_cents: number; d60_cents: number; d90_cents: number; total_cents: number; oldest_days: number }
export interface BillingOverview { outstanding_cents: number; overdue_cents: number; draft: number; sent: number; overdue_count: number; paid_30d_cents: number; invoiced_30d_cents: number; recurring_annualised_cents: number; avg_days_to_pay: number | null; aged: AgedRow[] }
export interface LineIn { description: string; quantity?: number; unit_cents: number; gst?: boolean; module_key?: string | null; ref_id?: string | null }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/practice-billing${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
const qs = (o: Record<string, unknown>) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v)); const s = p.toString(); return s ? `?${s}` : ''; };

export const practiceBilling = {
  overview: () => req<BillingOverview>('GET', '/overview'),
  invoices: {
    list: (f: { status?: string; client_id?: string; unpaid?: boolean } = {}) => req<InvoiceOut[]>('GET', `/invoices${qs(f)}`),
    create: (b: { client_id: string; contact_id?: string | null; lines: LineIn[]; period_label?: string | null; issued_on?: string | null; terms_days?: number; notes?: string | null; job_id?: string | null; send_now?: boolean }) => req<InvoiceDetail>('POST', '/invoices', b),
    get: (id: string) => req<InvoiceDetail>('GET', `/invoices/${id}`),
    send: (id: string) => req<InvoiceDetail>('POST', `/invoices/${id}/send`),
    remind: (id: string) => req<InvoiceDetail>('POST', `/invoices/${id}/remind`),
    pay: (id: string, b: { amount_cents: number; method?: string; reference?: string | null; received_on?: string | null }) => req<InvoiceDetail>('POST', `/invoices/${id}/payments`, b),
    void: (id: string, reason: string) => req<InvoiceDetail>('POST', `/invoices/${id}/void`, { reason }),
  },
  schedules: {
    list: (client_id?: string) => req<ScheduleOut[]>('GET', `/schedules${qs({ client_id })}`),
    create: (b: { client_id: string; name: string; frequency?: string; amount_cents: number; gst?: boolean; day_of_month?: number; terms_days?: number; method?: string; start_on?: string | null; notes?: string | null }) => req<ScheduleOut>('POST', '/schedules', b),
    toggle: (id: string) => req<ScheduleOut>('POST', `/schedules/${id}/toggle`),
    generate: (send = false) => req<{ created: number; invoices: InvoiceOut[] }>('POST', `/schedules/generate${send ? '?send=true' : ''}`),
  },
  statement: (clientId: string) => req<ClientStatement>('GET', `/clients/${clientId}/statement`),
};

export const INVOICE_STATUS_LABEL: Record<InvoiceStatus, string> = { draft: 'Draft', sent: 'Sent', part_paid: 'Part paid', paid: 'Paid', overdue: 'Overdue', void: 'Void' };
export function invoiceTone(s: InvoiceStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'paid' ? 'success' : s === 'overdue' ? 'error' : s === 'part_paid' ? 'warn' : s === 'sent' ? 'info' : 'neutral'; }
