/**
 * Session + entitlement state — backed by the platform spine (services/api).
 *
 * The store keeps the same shape the screens were built against, now filled from /me.
 * Entitlement is read from the server's `entitlements` map, never recomputed client-side:
 * one record (tenant_subscriptions), one source of truth, three enforcement points
 * (shell nav here, API middleware, billing meter).
 */
import { create } from 'zustand';
import type { ModuleKey } from '@entiq/modules';
import { api, ApiError, tokenStore, type LifecycleStatus as ApiLifecycle, type SessionOut, type TenantChoice } from '@/api/client';

export type LifecycleStatus = ApiLifecycle;
export type UserRole = 'owner' | 'admin' | 'staff';

export interface Tenant {
  id: string; name: string; slug: string; abn?: string; timezone: string;
  status: LifecycleStatus; trialEndsAt: string | null; currentPeriodEnd: string | null; createdAt: string;
  cardOnFile: boolean; cardBrand?: string; cardLast4?: string;
}
export interface SessionUser { id: string; name: string; email: string; role: UserRole; isOperator: boolean }
export interface Subscription { module: ModuleKey; status: LifecycleStatus; seats?: number; startedAt: string; requiredBy?: ModuleKey | null }
export interface Pricing { baseCents: number; gstBps: number; baseIncGstCents: number; trialDays: number }

export interface SignUpInput { practiceName: string; abn?: string; fullName: string; email: string; password: string; cardLast4: string; cardBrand?: string }

type Status = 'idle' | 'loading' | 'authenticated' | 'anonymous';

interface SessionState {
  status: Status;
  authenticated: boolean;
  tenant: Tenant | null;
  user: SessionUser | null;
  subscriptions: Subscription[];
  entitlements: Partial<Record<ModuleKey, boolean>>;
  grantedModules: ModuleKey[];
  permissions: string[];
  readOnly: boolean;
  pricing: Pricing;
  /** Set when login found more than one practice for this person. */
  pendingTenants: TenantChoice[] | null;
  pendingCreds: { email: string; password: string } | null;

  entitled: (key: ModuleKey) => boolean;
  can: (permission: string) => boolean;

  bootstrap: () => Promise<void>;
  signUp: (input: SignUpInput) => Promise<void>;
  login: (email: string, password: string) => Promise<'ok' | 'select_tenant'>;
  selectTenant: (tenantId: string) => Promise<void>;
  switchTenant: (tenantId: string) => Promise<void>;
  acceptInvite: (token: string, fullName: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;

  subscribe: (module: ModuleKey, seats?: number) => Promise<ModuleKey[]>;
  unsubscribe: (module: ModuleKey) => Promise<void>;
  /** Non-production: walk the lifecycle without a billing backend. */
  simulateLifecycle: (status: LifecycleStatus) => Promise<void>;
}

const DEFAULT_PRICING: Pricing = { baseCents: 9900, gstBps: 1000, baseIncGstCents: 10890, trialDays: 15 };

function mapSession(s: SessionOut) {
  return {
    tenant: {
      id: s.tenant.id, name: s.tenant.name, slug: s.tenant.slug, abn: s.tenant.abn ?? undefined, timezone: s.tenant.timezone,
      status: s.tenant.status, trialEndsAt: s.tenant.trial_ends_at, currentPeriodEnd: s.tenant.current_period_end, createdAt: s.tenant.created_at,
      cardOnFile: s.tenant.card_on_file, cardBrand: s.tenant.card_brand ?? undefined, cardLast4: s.tenant.card_last4 ?? undefined,
    } satisfies Tenant,
    user: { id: s.user.id, name: s.user.full_name, email: s.user.email, role: s.role, isOperator: s.user.is_operator } satisfies SessionUser,
    subscriptions: s.subscriptions.map((x) => ({ module: x.module_key, status: x.status, seats: x.seats ?? undefined, startedAt: x.started_at, requiredBy: x.required_by })) satisfies Subscription[],
    entitlements: s.entitlements,
    grantedModules: s.granted_modules,
    permissions: s.permissions,
    readOnly: s.read_only,
    pricing: { baseCents: s.pricing.base_plan_cents, gstBps: s.pricing.gst_rate_bps, baseIncGstCents: s.pricing.base_plan_inc_gst_cents, trialDays: s.pricing.trial_days } satisfies Pricing,
  };
}

const EMPTY = {
  tenant: null, user: null, subscriptions: [], entitlements: {}, grantedModules: [], permissions: [], readOnly: false, pricing: DEFAULT_PRICING,
  pendingTenants: null, pendingCreds: null,
};

export const useSession = create<SessionState>()((set, get) => {
  const apply = (s: SessionOut) => set({ ...mapSession(s), status: 'authenticated', authenticated: true, pendingTenants: null, pendingCreds: null });
  const clear = () => { tokenStore.set(null); set({ ...EMPTY, status: 'anonymous', authenticated: false }); };

  return {
    status: 'idle',
    authenticated: false,
    ...EMPTY,

    entitled: (key) => get().entitlements[key] === true,
    can: (permission) => get().permissions.includes(permission),

    bootstrap: async () => {
      if (get().status !== 'idle') return;
      if (!tokenStore.get()) { set({ status: 'anonymous' }); return; }
      set({ status: 'loading' });
      try { apply(await api.me()); } catch { clear(); }
    },

    signUp: async (input) => {
      const out = await api.auth.signup({
        practice_name: input.practiceName, abn: input.abn, full_name: input.fullName, email: input.email, password: input.password,
        payment_method: { last4: input.cardLast4, brand: input.cardBrand ?? 'card' },
      });
      if (out.tokens && out.session) { tokenStore.set(out.tokens); apply(out.session); }
    },

    login: async (email, password) => {
      const out = await api.auth.login({ email, password });
      if (out.requires_tenant_selection) {
        set({ pendingTenants: out.tenants, pendingCreds: { email, password } });
        return 'select_tenant';
      }
      if (out.tokens && out.session) { tokenStore.set(out.tokens); apply(out.session); }
      return 'ok';
    },

    selectTenant: async (tenantId) => {
      const creds = get().pendingCreds;
      if (!creds) throw new Error('No pending login');
      const out = await api.auth.login({ ...creds, tenant_id: tenantId });
      if (out.tokens && out.session) { tokenStore.set(out.tokens); apply(out.session); }
    },

    switchTenant: async (tenantId) => {
      const out = await api.auth.switchTenant(tenantId);
      if (out.tokens && out.session) { tokenStore.set(out.tokens); apply(out.session); }
    },

    acceptInvite: async (token, fullName, password) => {
      const out = await api.auth.acceptInvite({ token, full_name: fullName, password });
      if (out.tokens && out.session) { tokenStore.set(out.tokens); apply(out.session); }
    },

    logout: async () => {
      const t = tokenStore.get();
      try { if (t) await api.auth.logout(t.refresh_token); } catch { /* already gone */ }
      clear();
    },

    refresh: async () => { try { apply(await api.me()); } catch (e) { if (e instanceof ApiError && e.status === 401) clear(); else throw e; } },

    subscribe: async (module, seats) => {
      const out = await api.subscriptions.add(module, seats);
      await get().refresh();
      return out.added;
    },

    unsubscribe: async (module) => { await api.subscriptions.remove(module); await get().refresh(); },

    simulateLifecycle: async (status) => { apply(await api.dev.lifecycle(status, 'demo control')); },
  };
});

/* ---------------------------------------------------------------- selectors & helpers */

export function useEntitled(module: ModuleKey): boolean {
  return useSession((s) => s.entitlements[module] === true);
}

const ACCESS: LifecycleStatus[] = ['trialing', 'active', 'past_due'];

export function tenantHasAccess(t: Tenant | null): boolean { return !!t && ACCESS.includes(t.status); }
export function tenantIsReadOnly(t: Tenant | null): boolean { return !!t && t.status === 'suspended'; }

export function trialDaysLeft(t: Tenant | null): number {
  if (!t?.trialEndsAt) return 0;
  return Math.max(0, Math.ceil((new Date(t.trialEndsAt).getTime() - Date.now()) / 86_400_000));
}

/** Base plan, ex GST, in dollars — from the server's pricing when a session exists. */
export function monthlyBaseExGst(): number { return useSession.getState().pricing.baseCents / 100; }
export const GST_RATE = 0.1;
export const fmtAud = (n: number) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' }).format(n);

/** Human text for an API failure, for forms. */
export function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    const d = (e.detail ?? {}) as Record<string, unknown>;
    switch (e.code) {
      case 'email_in_use': return 'That email already has an EnTIQ account. Sign in instead.';
      case 'weak_password': return `Password needs ${(d.needs as string[] | undefined)?.join(', ') ?? 'to be stronger'}.`;
      case 'invalid_credentials': return 'Email or password is incorrect.';
      case 'account_locked': return 'Too many attempts. Try again in 15 minutes.';
      case 'invalid_or_expired_invitation': return 'This invitation link is invalid or has expired.';
      case 'tenant_read_only': return 'This practice is read-only until payment is restored.';
      case 'already_a_member': return 'That person is already a member of this practice.';
      default: return e.code ? e.code.replace(/_/g, ' ') : `Request failed (${e.status})`;
    }
  }
  return e instanceof Error ? e.message : 'Something went wrong.';
}
