/**
 * Session + entitlement state.
 *
 * This is the FRONTEND model of what the platform spine will own server-side
 * (identity, tenant, tenant_subscriptions). It is deliberately shaped like the
 * eventual API so the swap from mock to live is a data-source change, not a
 * refactor. Persisted to localStorage so a demo survives reload.
 *
 * Commercial rules encoded here (decided 19 Sep 2026):
 *  - Base plan = Practice HQ + CRM, $99/mo + GST, 15-day trial, card at signup, $0 charged in trial.
 *  - Every other module is a separate subscription row.
 *  - Lifecycle: trialing → active → past_due → suspended → cancelled → retained.
 *    Access is granted in trialing/active/past_due; read-only in suspended; none after.
 *    Records are NEVER deleted on a billing event (AUSTRAC 7-year retention).
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { BASE_BUNDLE, PLATFORM_SERVICES, getModule, requiredClosure, type ModuleKey } from '@entiq/modules';

export type LifecycleStatus = 'trialing' | 'active' | 'past_due' | 'suspended' | 'cancelled' | 'retained';

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  abn?: string;
  status: LifecycleStatus;
  trialEndsAt: string; // ISO
  createdAt: string;
  cardOnFile: boolean;
  cardLast4?: string;
}

export type UserRole = 'owner' | 'admin' | 'staff';

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  /** EnTIQ operator — may open Control Centre. Never true for a practice user. */
  isOperator: boolean;
}

export interface Subscription {
  module: ModuleKey;
  status: LifecycleStatus;
  seats?: number;
  startedAt: string;
}

export interface SignUpInput {
  practiceName: string;
  abn?: string;
  fullName: string;
  email: string;
  cardLast4: string;
}

interface SessionState {
  authenticated: boolean;
  tenant: Tenant | null;
  user: SessionUser | null;
  subscriptions: Subscription[];

  signUp: (input: SignUpInput) => void;
  login: (email: string) => void;
  logout: () => void;

  subscribe: (module: ModuleKey, seats?: number) => ModuleKey[];
  unsubscribe: (module: ModuleKey) => void;

  /** Demo controls — simulate the lifecycle without a billing backend. */
  simulateTenantStatus: (status: LifecycleStatus) => void;
}

const ACCESS_STATES: LifecycleStatus[] = ['trialing', 'active', 'past_due'];
const READONLY_STATES: LifecycleStatus[] = ['suspended'];

const iso = (d: Date) => d.toISOString();
const daysFromNow = (n: number) => iso(new Date(Date.now() + n * 86_400_000));

function slugify(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

export const useSession = create<SessionState>()(
  persist(
    (set, get) => ({
      authenticated: false,
      tenant: null,
      user: null,
      subscriptions: [],

      signUp: (input) => {
        const now = new Date();
        set({
          authenticated: true,
          tenant: {
            id: `ten_${Math.random().toString(36).slice(2, 10)}`,
            name: input.practiceName,
            slug: slugify(input.practiceName),
            abn: input.abn,
            status: 'trialing',
            trialEndsAt: daysFromNow(15),
            createdAt: iso(now),
            cardOnFile: true,
            cardLast4: input.cardLast4,
          },
          user: {
            id: `usr_${Math.random().toString(36).slice(2, 10)}`,
            name: input.fullName,
            email: input.email,
            role: 'owner',
            isOperator: false,
          },
          // The base bundle is provisioned as a subscription row like any other module.
          subscriptions: BASE_BUNDLE.map((m) => ({ module: m, status: 'trialing', startedAt: iso(now) })),
        });
      },

      login: (email) => {
        // Mock: restore whatever tenant is persisted; if none, create a demo practice.
        const s = get();
        if (s.tenant) {
          set({ authenticated: true });
          return;
        }
        get().signUp({
          practiceName: 'Ashfield Partners',
          abn: '62 114 887 302',
          fullName: email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
          email,
          cardLast4: '4242',
        });
      },

      logout: () => set({ authenticated: false }),

      subscribe: (module, seats) => {
        const s = get();
        const now = iso(new Date());
        // Hard dependencies are provisioned with the module — you cannot buy Advisory without Workpapers.
        const closure = requiredClosure(module).filter(
          (k) => !BASE_BUNDLE.includes(k) && !PLATFORM_SERVICES.includes(k) && !s.subscriptions.some((x) => x.module === k),
        );
        const added: ModuleKey[] = [...closure, module].filter((k) => !s.subscriptions.some((x) => x.module === k));
        set({
          subscriptions: [
            ...s.subscriptions,
            ...added.map((m) => ({ module: m, status: 'active' as LifecycleStatus, seats: m === module ? seats : undefined, startedAt: now })),
          ],
        });
        return added;
      },

      unsubscribe: (module) => {
        if (BASE_BUNDLE.includes(module)) return; // the base plan is cancelled at tenant level, not per module
        set({ subscriptions: get().subscriptions.filter((x) => x.module !== module) });
      },

      simulateTenantStatus: (status) => {
        const t = get().tenant;
        if (!t) return;
        set({ tenant: { ...t, status } });
      },
    }),
    { name: 'entiq.session.v1' },
  ),
);

/* ---------------------------------------------------------------- selectors */

export function tenantHasAccess(t: Tenant | null): boolean {
  return !!t && ACCESS_STATES.includes(t.status);
}

export function tenantIsReadOnly(t: Tenant | null): boolean {
  return !!t && READONLY_STATES.includes(t.status);
}

/** Is the tenant entitled to `module` right now? Base bundle and platform services ride on tenant status. */
export function isEntitled(state: Pick<SessionState, 'tenant' | 'subscriptions'>, module: ModuleKey): boolean {
  const { tenant, subscriptions } = state;
  if (!tenant) return false;
  const tenantOk = ACCESS_STATES.includes(tenant.status) || READONLY_STATES.includes(tenant.status);
  if (!tenantOk) return false;
  if (BASE_BUNDLE.includes(module) || PLATFORM_SERVICES.includes(module)) return true;
  const sub = subscriptions.find((s) => s.module === module);
  return !!sub && (ACCESS_STATES.includes(sub.status) || READONLY_STATES.includes(sub.status));
}

export function useEntitled(module: ModuleKey): boolean {
  return useSession((s) => isEntitled(s, module));
}

export function trialDaysLeft(t: Tenant | null): number {
  if (!t) return 0;
  return Math.max(0, Math.ceil((new Date(t.trialEndsAt).getTime() - Date.now()) / 86_400_000));
}

/** Monthly bill ex-GST at today's subscriptions (indicative — metered modules show their unit, not a total). */
export function monthlyBaseExGst(): number {
  return getModule('crm').pricing.fromAud ?? 99;
}

export const GST_RATE = 0.1;
export const fmtAud = (n: number) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' }).format(n);
