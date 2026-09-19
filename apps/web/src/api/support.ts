/** EnTIQ Support: tenant side (/hq/support) and operator side (/control/support). */
import { API_BASE, ApiError, tokenStore } from './client';

export type TicketStatus = 'open' | 'pending' | 'resolved' | 'closed';
export type Priority = 'low' | 'medium' | 'high' | 'urgent';
export type TicketCategory = 'question' | 'problem' | 'billing' | 'feature' | 'onboarding' | 'security';
export interface CommentOut { id: string; author_name: string; is_operator: boolean; internal: boolean; body: string; created_at: string }
export interface TicketOut { id: string; number: number; tenant_id: string; practice_name: string | null; subject: string; body: string; category: TicketCategory; priority: Priority; status: TicketStatus; module_key: string | null; created_by_name: string | null; assigned_operator_name: string | null; first_response_due_at: string | null; resolution_due_at: string | null; first_response_at: string | null; resolved_at: string | null; closed_at: string | null; sla_breached: boolean; sla_state: 'ok' | 'at_risk' | 'breached' | 'met'; satisfaction: number | null; comment_count: number; created_at: string; updated_at: string }
export interface TicketDetail extends TicketOut { comments: CommentOut[] }
export interface QueueStats { open: number; pending: number; unassigned: number; breached: number; at_risk: number; resolved_7d: number; median_first_response_minutes: number | null; by_category: Record<string, number> }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

export const support = {
  mine: (status?: string) => req<TicketOut[]>('GET', `/hq/support${status ? `?status=${status}` : ''}`),
  raise: (b: { subject: string; body: string; category: TicketCategory; priority: Priority; module_key?: string | null }) => req<TicketDetail>('POST', '/hq/support', b),
  get: (id: string) => req<TicketDetail>('GET', `/hq/support/${id}`),
  comment: (id: string, body: string) => req<TicketDetail>('POST', `/hq/support/${id}/comments`, { body }),
  close: (id: string, satisfaction?: number) => req<TicketDetail>('POST', `/hq/support/${id}/close`, { status: 'closed', satisfaction: satisfaction ?? null }),
  ops: {
    stats: () => req<QueueStats>('GET', '/control/support/stats'),
    queue: (status = 'open', mine = false) => req<TicketOut[]>('GET', `/control/support?status=${status}${mine ? '&mine=true' : ''}`),
    get: (id: string) => req<TicketDetail>('GET', `/control/support/${id}`),
    comment: (id: string, body: string, internal = false) => req<TicketDetail>('POST', `/control/support/${id}/comments`, { body, internal }),
    setStatus: (id: string, status: TicketStatus) => req<TicketDetail>('POST', `/control/support/${id}/status`, { status }),
    assign: (id: string, operator_user_id: string | null) => req<TicketDetail>('POST', `/control/support/${id}/assign`, { operator_user_id }),
    priority: (id: string, priority: Priority) => req<TicketDetail>('POST', `/control/support/${id}/priority`, { priority }),
    operators: () => req<Array<{ id: string; name: string }>>('GET', '/control/support/meta/operators'),
  },
};

export const TICKET_STATUS_LABEL: Record<TicketStatus, string> = { open: 'Open', pending: 'Waiting on you', resolved: 'Resolved', closed: 'Closed' };
export function ticketTone(s: TicketStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'resolved' ? 'success' : s === 'closed' ? 'neutral' : s === 'pending' ? 'warn' : 'info'; }
export function priorityToneOf(p: Priority): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return p === 'urgent' ? 'error' : p === 'high' ? 'warn' : p === 'medium' ? 'info' : 'neutral'; }
export function slaTone(s: TicketOut['sla_state']): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'breached' ? 'error' : s === 'at_risk' ? 'warn' : s === 'met' ? 'success' : 'neutral'; }
