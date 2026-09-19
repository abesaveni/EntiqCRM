/** Typed client for EnTIQ Sign (services/api/app/modules/sign). Staff routes need a bearer token; the /s/{token} signer routes do not. */
import { API_BASE, ApiError, tokenStore } from './client';

export type AgreementStatus = 'draft' | 'sent' | 'partially_signed' | 'completed' | 'declined' | 'voided' | 'expired';
export type SignerStatus = 'pending' | 'sent' | 'viewed' | 'signed' | 'declined';
export type AgreementKind = 'engagement_letter' | 'declaration' | 'resolution' | 'agreement';

export interface SignerOut { id: string; name: string; email: string; contact_id: string | null; order: number; status: SignerStatus; viewed_at: string | null; signed_at: string | null; declined_at: string | null; decline_reason: string | null; signature_kind: 'typed' | 'drawn' | null; signature_sha256: string | null; identity_verified: boolean }
export interface SignEventOut { id: string; kind: string; at: string; signer_name: string | null; ip: string | null; detail: Record<string, unknown>; hash: string }
export interface AgreementOut {
  id: string; client_id: string | null; client_name: string | null; document_id: string; document_filename: string | null; document_sha256: string | null; title: string; kind: AgreementKind; message: string | null;
  status: AgreementStatus; require_identity: boolean; created_by_name: string | null; sent_at: string | null; completed_at: string | null; expires_at: string | null; voided_at: string | null; void_reason: string | null;
  sealed_sha256: string | null; chain_head: string | null; signers: SignerOut[]; created_at: string;
}
export interface AgreementDetail extends AgreementOut { events: SignEventOut[]; certificate: Record<string, unknown> | null }
export interface AgreementIn { title: string; document_id: string; client_id?: string | null; kind?: AgreementKind; message?: string | null; signers: Array<{ name: string; email: string; contact_id?: string | null }>; require_identity?: boolean; expires_in_days?: number; send_now?: boolean }
export interface SignOverview { awaiting: number; completed_30d: number; declined: number; expiring_7d: number }
export interface ChainCheck { ok: boolean; events: number; head?: string; matches_agreement?: boolean; first_break?: string }

export interface PublicSignerView {
  agreement_id: string; title: string; kind: AgreementKind; message: string | null; practice_name: string; document_filename: string; document_content_type: string; document_sha256: string;
  signer_name: string; signer_email: string; signer_status: SignerStatus; agreement_status: AgreementStatus; require_identity: boolean; identity_ok: boolean; expires_at: string | null; other_signers: Array<{ name: string; status: string }>;
}

async function req<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
  const t = auth ? tokenStore.get() : null;
  const res = await fetch(`${API_BASE}/sign${path}`, {
    method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}
const authHeaders = (): Record<string, string> => { const t = tokenStore.get(); return t ? { Authorization: `Bearer ${t.access_token}` } : {}; };

export const sign = {
  overview: () => req<SignOverview>('GET', '/overview'),
  agreements: {
    list: (f: { status?: string; client_id?: string } = {}) => { const p = new URLSearchParams(); if (f.status) p.set('status', f.status); if (f.client_id) p.set('client_id', f.client_id); const s = p.toString(); return req<AgreementOut[]>('GET', `/agreements${s ? `?${s}` : ''}`); },
    create: (b: AgreementIn) => req<AgreementDetail>('POST', '/agreements', b),
    get: (id: string) => req<AgreementDetail>('GET', `/agreements/${id}`),
    send: (id: string) => req<AgreementDetail>('POST', `/agreements/${id}/send`),
    remind: (id: string) => req<AgreementDetail>('POST', `/agreements/${id}/remind`),
    void: (id: string, reason: string) => req<AgreementDetail>('POST', `/agreements/${id}/void`, { reason }),
    verifyChain: (id: string) => req<ChainCheck>('GET', `/agreements/${id}/verify-chain`),
    certificate: async (a: AgreementOut): Promise<void> => {
      const res = await fetch(`${API_BASE}/sign/agreements/${a.id}/certificate.pdf`, { headers: authHeaders() });
      if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
      const url = URL.createObjectURL(await res.blob());
      const el = Object.assign(document.createElement('a'), { href: url, download: `certificate-${a.title.replace(/[^\w.-]+/g, '_')}.pdf` });
      document.body.appendChild(el); el.click(); el.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    },
  },
  /** Signer-facing, unauthenticated: the opaque token in the emailed link is the credential. */
  public: {
    view: (token: string) => req<PublicSignerView>('GET', `/public/${token}`, undefined, false),
    documentUrl: (token: string) => `${API_BASE}/sign/public/${token}/document`,
    sign: (token: string, b: { full_name: string; signature_kind: 'typed' | 'drawn'; signature_data: string; consent: boolean }) => req<PublicSignerView>('POST', `/public/${token}/sign`, b, false),
    decline: (token: string, reason: string) => req<PublicSignerView>('POST', `/public/${token}/decline`, { reason }, false),
  },
};

export const KIND_LABEL: Record<AgreementKind, string> = { engagement_letter: 'Engagement letter', declaration: 'Declaration', resolution: 'Resolution', agreement: 'Agreement' };
export const STATUS_LABEL: Record<AgreementStatus, string> = { draft: 'Draft', sent: 'Awaiting signature', partially_signed: 'Partially signed', completed: 'Completed', declined: 'Declined', voided: 'Voided', expired: 'Expired' };
export function agreementTone(s: AgreementStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' {
  return s === 'completed' ? 'success' : s === 'declined' || s === 'expired' ? 'error' : s === 'voided' ? 'neutral' : s === 'draft' ? 'neutral' : 'info';
}
export function signerTone(s: SignerStatus): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' {
  return s === 'signed' ? 'success' : s === 'declined' ? 'error' : s === 'viewed' ? 'teal' : s === 'sent' ? 'info' : 'neutral';
}
