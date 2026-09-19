/**
 * Typed client for the EnTIQ platform spine (services/api). Shapes mirror app/schemas.py.
 *
 * - Base URL `/api/v1`; Vite proxies to the FastAPI dev server (see vite.config.ts).
 * - Bearer access token + rotating refresh token, held in localStorage by the session store.
 * - One transparent refresh-and-retry on 401.
 * - 403 from the entitlement gate carries an `upsell` payload; it is surfaced as ApiError.upsell
 *   so the shell can render "Add <Module>" instead of an error.
 */
import type { ModuleKey, ModuleManifest } from '@entiq/modules';

export const API_BASE = '/api/v1';

// ------------------------------------------------------------------ types (mirror of schemas.py)
export type LifecycleStatus = 'trialing' | 'active' | 'past_due' | 'suspended' | 'cancelled' | 'retained';
export type Role = 'owner' | 'admin' | 'staff';

export interface TokenPair { access_token: string; refresh_token: string; token_type: 'bearer'; expires_at: string }
export interface UserOut { id: string; email: string; full_name: string; is_operator: boolean; email_verified: boolean }
export interface TenantOut {
  id: string; name: string; slug: string; abn: string | null; timezone: string; status: LifecycleStatus;
  trial_ends_at: string | null; current_period_end: string | null;
  card_on_file: boolean; card_brand: string | null; card_last4: string | null; created_at: string;
}
export interface SubscriptionOut {
  module_key: ModuleKey; status: LifecycleStatus; seats: number | null; started_at: string;
  trial_ends_at: string | null; current_period_end: string | null; required_by: ModuleKey | null;
}
export interface PricingOut { base_plan_cents: number; gst_rate_bps: number; base_plan_inc_gst_cents: number; currency: string; trial_days: number; require_card: boolean; free_mode: boolean }
export interface SessionOut {
  user: UserOut; tenant: TenantOut; role: Role; granted_modules: ModuleKey[]; permissions: string[];
  subscriptions: SubscriptionOut[]; entitlements: Record<ModuleKey, boolean>; read_only: boolean; pricing: PricingOut;
}
export interface TenantChoice { id: string; name: string; slug: string; role: Role; status: LifecycleStatus }
export interface LoginOut { requires_tenant_selection: boolean; tenants: TenantChoice[]; tokens: TokenPair | null; session: SessionOut | null }
export interface SubscribeOut { added: ModuleKey[]; subscriptions: SubscriptionOut[]; entitlements: Record<ModuleKey, boolean> }
export interface CatalogueItem { manifest: ModuleManifest; entitled: boolean; subscription: SubscriptionOut | null; purchasable: boolean; base: boolean }
export interface MemberOut {
  membership_id: string; user_id: string; email: string; full_name: string; role: Role; status: 'active' | 'invited' | 'disabled';
  job_title: string | null; modules: ModuleKey[]; joined_at: string | null; last_login_at: string | null;
}
export interface InviteOut { invitation_id: string; email: string; expires_at: string; accept_url: string | null }
export interface AuditOut { id: number; action: string; actor_user_id: string | null; target_type: string | null; target_id: string | null; detail: Record<string, unknown> | null; created_at: string; hash: string }

export interface UpsellPayload { name: string; shortName: string; outcome: string; pricing: ModuleManifest['pricing']; addPath: string }

export class ApiError extends Error {
  status: number;
  code: string | null;
  detail: unknown;
  upsell: UpsellPayload | null;
  module: ModuleKey | null;
  constructor(status: number, detail: unknown) {
    const d = (detail ?? {}) as Record<string, unknown>;
    const code = typeof d.error === 'string' ? d.error : typeof detail === 'string' ? detail : null;
    super(code ?? `HTTP ${status}`);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.upsell = (d.upsell as UpsellPayload) ?? null;
    this.module = (d.module as ModuleKey) ?? null;
  }
  get isReadOnly() { return this.status === 423; }
  get isNotSubscribed() { return this.status === 403 && (this.code === 'module_not_subscribed' || this.code === 'module_not_granted'); }
}

// ------------------------------------------------------------------ token storage
const TOKENS_KEY = 'entiq.tokens.v1';

export const tokenStore = {
  get(): TokenPair | null {
    try { const raw = localStorage.getItem(TOKENS_KEY); return raw ? (JSON.parse(raw) as TokenPair) : null; } catch { return null; }
  },
  set(t: TokenPair | null) {
    try { t ? localStorage.setItem(TOKENS_KEY, JSON.stringify(t)) : localStorage.removeItem(TOKENS_KEY); } catch { /* storage unavailable */ }
  },
};

// ------------------------------------------------------------------ core fetch
let refreshing: Promise<TokenPair | null> | null = null;

async function refreshTokens(): Promise<TokenPair | null> {
  if (!refreshing) {
    refreshing = (async () => {
      const t = tokenStore.get();
      if (!t) return null;
      const r = await fetch(`${API_BASE}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: t.refresh_token }) });
      if (!r.ok) { tokenStore.set(null); return null; }
      const pair = (await r.json()) as TokenPair;
      tokenStore.set(pair);
      return pair;
    })().finally(() => { refreshing = null; });
  }
  return refreshing;
}

async function request<T>(method: string, path: string, body?: unknown, opts: { auth?: boolean; retry?: boolean } = {}): Promise<T> {
  const { auth = true, retry = true } = opts;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const t = tokenStore.get();
  if (auth && t) headers.Authorization = `Bearer ${t.access_token}`;

  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });

  if (res.status === 401 && auth && retry && t) {
    const pair = await refreshTokens();
    if (pair) return request<T>(method, path, body, { auth, retry: false });
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

// ------------------------------------------------------------------ endpoints
export const api = {
  health: () => request<{ ok: boolean; env: string }>('GET', '/health', undefined, { auth: false }),

  pricing: () => request<PricingOut>('GET', '/pricing', undefined, { auth: false }),
  auth: {
    signup: (b: { practice_name: string; abn?: string; full_name: string; email: string; password: string; payment_method?: { last4: string; brand?: string; payment_method_id?: string } }) =>
      request<LoginOut>('POST', '/auth/signup', b, { auth: false }),
    login: (b: { email: string; password: string; tenant_id?: string }) => request<LoginOut>('POST', '/auth/login', b, { auth: false }),
    logout: (refresh_token?: string) => request<void>('POST', '/auth/logout', refresh_token ? { refresh_token } : undefined),
    switchTenant: (tenant_id: string) => request<LoginOut>('POST', '/auth/switch-tenant', { tenant_id }),
    tenants: () => request<TenantChoice[]>('GET', '/auth/tenants'),
    acceptInvite: (b: { token: string; full_name: string; password: string }) => request<LoginOut>('POST', '/auth/accept-invite', b, { auth: false }),
  },

  me: () => request<SessionOut>('GET', '/me'),
  tenant: {
    get: () => request<TenantOut>('GET', '/tenant'),
    patch: (b: { name?: string; abn?: string; timezone?: string }) => request<TenantOut>('PATCH', '/tenant', b),
  },

  modules: () => request<CatalogueItem[]>('GET', '/modules'),
  subscriptions: {
    list: () => request<SubscriptionOut[]>('GET', '/subscriptions'),
    add: (module_key: ModuleKey, seats?: number) => request<SubscribeOut>('POST', '/subscriptions', { module_key, seats }),
    remove: (module_key: ModuleKey) => request<SubscribeOut>('DELETE', `/subscriptions/${module_key}`),
  },

  users: {
    list: () => request<MemberOut[]>('GET', '/users'),
    invite: (b: { email: string; role: 'admin' | 'staff'; modules: ModuleKey[]; job_title?: string }) => request<InviteOut>('POST', '/users/invite', b),
    setGrants: (membership_id: string, modules: ModuleKey[]) => request<MemberOut>('PATCH', `/users/${membership_id}/grants`, { modules }),
    patch: (membership_id: string, b: { role?: Role; status?: 'active' | 'disabled'; job_title?: string }) => request<MemberOut>('PATCH', `/users/${membership_id}`, b),
  },

  audit: { list: (limit = 100) => request<AuditOut[]>('GET', `/audit?limit=${limit}`) },

  /** Non-production only — the router is not mounted in production. */
  dev: {
    lifecycle: (status: LifecycleStatus, reason?: string) => request<SessionOut>('POST', '/dev/lifecycle', { status, reason }),
    probe: (module: ModuleKey) => request<{ module: ModuleKey; ok: boolean }>('GET', `/dev/probe/${module}`),
  },
};
