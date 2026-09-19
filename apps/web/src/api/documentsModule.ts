/** Typed client for EnTIQ Documents (module 07) — filing, search and retention on top of the base attachment store. */
import { API_BASE, ApiError, tokenStore } from './client';

export interface FolderOut { id: string; client_id: string | null; parent_id: string | null; name: string; path: string; kind: string; depth: number; document_count: number }
export interface DocumentRow {
  id: string; client_id: string | null; client_name: string | null; module_key: string; kind: string; filename: string; content_type: string; size_bytes: number; sha256: string; description: string | null;
  uploaded_by_name: string | null; scan_status: string; retention_hold: boolean; visible_to_client: boolean; created_at: string;
  folder_id: string | null; folder_path: string | null; tags: string[]; text_source: 'none' | 'plain' | 'pdf' | 'ocr'; pages: number | null; retain_until: string | null; snippet: string | null;
}
export interface SearchIn { q?: string | null; client_id?: string | null; folder_id?: string | null; kind?: string | null; module_key?: string | null; visible_to_client?: boolean | null; retention_hold?: boolean | null; limit?: number }
export interface PolicyOut { id: string; name: string; kinds: string[]; years: number; trigger: string; action: 'review' | 'hold' | 'delete'; reference: string | null; is_active: boolean; documents: number }
export interface RetentionRow { document_id: string; filename: string; client_id: string | null; client_name: string | null; kind: string; policy_name: string | null; action: string; retain_until: string; due: boolean; retention_hold: boolean; created_at: string }
export interface DocsOverview { documents: number; bytes_total: number; unfiled: number; searchable: number; needs_ocr: number; on_hold: number; shared_with_clients: number; retention_due: number; by_module: Record<string, number>; by_kind: Record<string, number>; policies: number }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/documents-module${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

export const documentsModule = {
  overview: () => req<DocsOverview>('GET', '/overview'),
  folders: (clientId?: string) => req<FolderOut[]>('GET', `/folders${clientId ? `?client_id=${clientId}` : ''}`),
  createFolder: (b: { name: string; client_id?: string | null; parent_id?: string | null }) => req<FolderOut>('POST', '/folders', b),
  standardFolders: (clientId?: string) => req<FolderOut[]>('POST', `/folders/standard${clientId ? `?client_id=${clientId}` : ''}`),
  search: (b: SearchIn) => req<DocumentRow[]>('POST', '/search', b),
  file: (documentId: string, b: { folder_id?: string | null; tags?: string[]; kind?: string | null; reindex?: boolean }) => req<DocumentRow>('POST', `/${documentId}/file`, b),
  reindex: () => req<{ indexed: number }>('POST', '/reindex'),
  policies: () => req<PolicyOut[]>('GET', '/policies'),
  createPolicy: (b: { name: string; kinds?: string[]; years?: number; trigger?: string; action?: string; reference?: string | null }) => req<PolicyOut>('POST', '/policies', b),
  seedPolicies: () => req<PolicyOut[]>('POST', '/policies/defaults'),
  applyPolicies: () => req<{ indexed: number; held: number }>('POST', '/policies/apply'),
  retention: (days = 90) => req<RetentionRow[]>('GET', `/retention?days=${days}`),
};

export const TEXT_SOURCE_LABEL: Record<DocumentRow['text_source'], string> = { none: 'not searchable', plain: 'text indexed', pdf: 'PDF text indexed', ocr: 'needs OCR' };
