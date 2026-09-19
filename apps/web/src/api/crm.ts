/** Typed client for the CRM module (services/api/app/routers/crm.py). Shapes mirror schemas_crm.py. */
import type { ModuleKey } from '@entiq/modules';
import { API_BASE, ApiError, tokenStore } from './client';

export type ClientType = 'Company' | 'Trust' | 'Individual' | 'Partnership' | 'SMSF' | 'Other';
export type Stage = 'Lead' | 'Proposal' | 'Onboarding' | 'Active' | 'Review' | 'Dormant' | 'Lost';
export type Priority = 'Low' | 'Normal' | 'High';
export type TaskStatus = 'open' | 'done' | 'cancelled';
export type RiskLevel = 'Low' | 'Medium' | 'High';

export const STAGES: Stage[] = ['Lead', 'Proposal', 'Onboarding', 'Active', 'Review', 'Dormant', 'Lost'];
export const CLIENT_TYPES: ClientType[] = ['Company', 'Trust', 'Individual', 'Partnership', 'SMSF', 'Other'];
export const RELATIONSHIP_KINDS = [
  'director_of', 'secretary_of', 'shareholder_of', 'trustee_of', 'beneficiary_of', 'appointor_of', 'partner_of', 'member_of', 'owner_of',
  'bookkeeper_for', 'adviser_to', 'referrer_of', 'related_entity', 'spouse_of',
] as const;

export interface ContactOut {
  id: string; client_id: string; first_name: string; last_name: string | null; full_name: string; email: string | null; phone: string | null;
  role: string | null; is_primary: boolean; notes: string | null; has_portal_access: boolean; created_at: string;
}
export interface ClientOut {
  id: string; name: string; legal_name: string | null; client_type: ClientType; abn: string | null; abn_formatted: string | null; acn: string | null;
  stage: Stage; owner_membership_id: string | null; owner_name: string | null; risk_rating: RiskLevel | null; risk_assessed_at: string | null;
  since: string | null; email: string | null; phone: string | null; website: string | null;
  address_line1: string | null; address_line2: string | null; suburb: string | null; state: string | null; postcode: string | null; country: string;
  source: string | null; external_ref: string | null; tags: string[]; custom: Record<string, unknown>; archived_at: string | null;
  created_at: string; updated_at: string; contact_count: number; open_task_count: number; primary_contact: ContactOut | null;
}
export interface ClientPage { items: ClientOut[]; total: number; page: number; size: number }
export interface ClientIn {
  name: string; legal_name?: string | null; client_type?: ClientType; abn?: string | null; acn?: string | null; stage?: Stage; owner_membership_id?: string | null;
  since?: string | null; email?: string | null; phone?: string | null; website?: string | null; address_line1?: string | null; address_line2?: string | null;
  suburb?: string | null; state?: string | null; postcode?: string | null; country?: string; source?: string | null; tags?: string[]; custom?: Record<string, unknown>;
}
export interface ContactIn { first_name: string; last_name?: string | null; email?: string | null; phone?: string | null; role?: string | null; is_primary?: boolean; notes?: string | null }
export interface RelationshipOut { id: string; from_type: 'client' | 'contact'; from_id: string; from_label: string; to_type: 'client' | 'contact'; to_id: string; to_label: string; kind: string; percentage: number | null; notes: string | null; ended_at: string | null }
export interface TimelineOut { id: string; client_id: string | null; client_name: string | null; module_key: ModuleKey; kind: string; summary: string; detail: Record<string, unknown>; actor_label: string; ref_type: string | null; ref_id: string | null; occurred_at: string }
export interface TaskOut { id: string; client_id: string | null; client_name: string | null; title: string; description: string | null; due_at: string | null; priority: Priority; status: TaskStatus; assignee_membership_id: string | null; assignee_name: string | null; module_key: ModuleKey; done_at: string | null; created_at: string; overdue: boolean }
export interface TaskIn { title: string; description?: string | null; client_id?: string | null; due_at?: string | null; priority?: Priority; assignee_membership_id?: string | null }
export interface NoteOut { id: string; client_id: string; body: string; author_name: string | null; pinned: boolean; created_at: string; updated_at: string }
export interface PipelineColumn { stage: Stage; count: number; clients: ClientOut[] }
export interface HomeOut { overdue_tasks: number; due_this_week: number; elevated_risk: number; in_pipeline: number; total_clients: number; tasks: TaskOut[]; risks: ClientOut[]; recent: TimelineOut[] }
export interface SegmentOut { id: string; name: string; description: string | null; filters: ClientFilters; member_count: number; created_at: string }
export interface SearchHit { type: 'client' | 'contact'; id: string; client_id: string; label: string; sublabel: string | null }
export interface StaffOut { membership_id: string; name: string; email: string; role: string }
export interface DuplicateGroup { reason: 'abn' | 'name'; key: string; clients: ClientOut[] }
export interface ImportPreview { job_id: string; source: 'xero' | 'myob' | 'csv'; filename: string; columns: string[]; proposed_mapping: Record<string, string | null>; row_count: number; sample: Record<string, string>[]; warnings: string[] }
export interface ImportResult { job_id: string; status: string; row_count: number; created_count: number; updated_count: number; skipped_count: number; errors: string[] }

export interface ClientFilters { q?: string; stage?: Stage | ''; client_type?: ClientType | ''; owner?: string; risk?: 'elevated' | RiskLevel | ''; tag?: string; include_archived?: boolean; sort?: string }

/** The importable fields, in the order the mapping UI shows them. */
export const IMPORT_FIELDS: Array<{ key: string; label: string; required?: boolean }> = [
  { key: 'name', label: 'Client / organisation name', required: true }, { key: 'legal_name', label: 'Legal name' }, { key: 'abn', label: 'ABN' }, { key: 'acn', label: 'ACN' },
  { key: 'first_name', label: 'Contact first name' }, { key: 'last_name', label: 'Contact last name' }, { key: 'contact_name', label: 'Contact full name' },
  { key: 'email', label: 'Email' }, { key: 'phone', label: 'Phone' }, { key: 'mobile', label: 'Mobile' }, { key: 'website', label: 'Website' },
  { key: 'address_line1', label: 'Address line 1' }, { key: 'address_line2', label: 'Address line 2' }, { key: 'suburb', label: 'Suburb / city' },
  { key: 'state', label: 'State' }, { key: 'postcode', label: 'Postcode' }, { key: 'country', label: 'Country' }, { key: 'external_ref', label: 'External reference / ID' },
];

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/crm${path}`, {
    method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

function qs(params: object): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params as Record<string, unknown>)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const crm = {
  home: () => req<HomeOut>('GET', '/home'),
  search: (q: string) => req<SearchHit[]>('GET', `/search${qs({ q })}`),
  staff: () => req<StaffOut[]>('GET', '/staff'),

  clients: {
    list: (f: ClientFilters & { page?: number; size?: number } = {}) => req<ClientPage>('GET', `/clients${qs(f)}`),
    get: (id: string) => req<ClientOut>('GET', `/clients/${id}`),
    create: (b: ClientIn) => req<ClientOut>('POST', '/clients', b),
    patch: (id: string, b: Partial<ClientIn>) => req<ClientOut>('PATCH', `/clients/${id}`, b),
    setStage: (id: string, stage: Stage, reason?: string) => req<ClientOut>('POST', `/clients/${id}/stage`, { stage, reason }),
    archive: (id: string) => req<ClientOut>('DELETE', `/clients/${id}`),
    timeline: (id: string, limit = 50) => req<TimelineOut[]>('GET', `/clients/${id}/timeline${qs({ limit })}`),
    contacts: (id: string) => req<ContactOut[]>('GET', `/clients/${id}/contacts`),
    addContact: (id: string, b: ContactIn) => req<ContactOut>('POST', `/clients/${id}/contacts`, b),
    relationships: (id: string) => req<RelationshipOut[]>('GET', `/clients/${id}/relationships`),
    notes: (id: string) => req<NoteOut[]>('GET', `/clients/${id}/notes`),
    addNote: (id: string, body: string, pinned = false) => req<NoteOut>('POST', `/clients/${id}/notes`, { body, pinned }),
  },
  contacts: {
    directory: (q?: string) => req<ContactOut[]>('GET', `/contacts${qs({ q })}`),
    patch: (id: string, b: Partial<ContactIn>) => req<ContactOut>('PATCH', `/contacts/${id}`, b),
    archive: (id: string) => req<void>('DELETE', `/contacts/${id}`),
  },
  relationships: {
    add: (b: { from_type: 'client' | 'contact'; from_id: string; to_type: 'client' | 'contact'; to_id: string; kind: string; percentage?: number | null; notes?: string | null }) => req<RelationshipOut>('POST', '/relationships', b),
    end: (id: string) => req<void>('DELETE', `/relationships/${id}`),
  },
  tasks: {
    list: (f: { status?: TaskStatus | 'all'; client_id?: string; assignee?: string; mine?: boolean } = {}) => req<TaskOut[]>('GET', `/tasks${qs(f)}`),
    create: (b: TaskIn) => req<TaskOut>('POST', '/tasks', b),
    patch: (id: string, b: Partial<TaskIn> & { status?: TaskStatus }) => req<TaskOut>('PATCH', `/tasks/${id}`, b),
    complete: (id: string) => req<TaskOut>('POST', `/tasks/${id}/complete`),
  },
  notes: { remove: (id: string) => req<void>('DELETE', `/notes/${id}`) },
  pipeline: () => req<PipelineColumn[]>('GET', '/pipeline'),
  segments: {
    list: () => req<SegmentOut[]>('GET', '/segments'),
    create: (b: { name: string; description?: string; filters: ClientFilters }) => req<SegmentOut>('POST', '/segments', b),
    members: (id: string, page = 1, size = 50) => req<ClientPage>('GET', `/segments/${id}/members${qs({ page, size })}`),
    remove: (id: string) => req<void>('DELETE', `/segments/${id}`),
  },
  duplicates: () => req<DuplicateGroup[]>('GET', '/duplicates'),
  import: {
    preview: async (file: File): Promise<ImportPreview> => {
      const t = tokenStore.get();
      const fd = new FormData();
      fd.append('file', file, file.name);
      const res = await fetch(`${API_BASE}/crm/import/preview`, { method: 'POST', headers: t ? { Authorization: `Bearer ${t.access_token}` } : {}, body: fd });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
      return data as ImportPreview;
    },
    commit: (jobId: string, b: { mapping?: Record<string, string | null>; default_stage?: Stage; update_existing?: boolean }) => req<ImportResult>('POST', `/import/${jobId}/commit`, b),
    status: (jobId: string) => req<ImportResult>('GET', `/import/${jobId}`),
  },
};

export const fmtDate = (iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }) =>
  iso ? new Date(iso).toLocaleDateString('en-AU', opts) : '—';
