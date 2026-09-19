import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CreditCard, Users, Plug, ShieldCheck } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Button } from '@entiq/ui/button';
import { getModule, purchasableModules } from '@entiq/modules';
import { useSession, trialDaysLeft, fmtAud, monthlyBaseExGst, GST_RATE } from '@/state/session';
import { INTEGRATIONS } from '@/mock/data';
import { api, type MemberOut } from '@/api/client';
import { platform, fmtCents, type BillingSummary } from '@/api/platform';
import { fmtDate } from '@/api/crm';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, lifecycleTone } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

export function HqOverview() {
  const tenant = useSession((s) => s.tenant)!;
  const entitled = useSession((s) => s.entitled);
  const entitlements = useSession((s) => s.entitlements);
  void entitlements;
  const [members, setMembers] = useState<MemberOut[] | null>(null);
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  useEffect(() => {
    void api.users.list().then(setMembers).catch(() => setMembers([]));
    void platform.billing.summary().then(setBilling).catch(() => setBilling(null));
  }, []);
  const owned = purchasableModules().filter((m) => entitled(m.key));
  const base = monthlyBaseExGst();
  const attention = INTEGRATIONS.filter((i) => i.status === 'attention' || i.status === 'not_connected');

  return (
    <div className="page">
      <PageHeader
        eyebrow="Practice HQ"
        title={tenant.name}
        description="Subscriptions, users, access, integrations and settings — the one administration centre for this practice."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex-row items-center justify-between pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><CreditCard className="size-4 text-primary" /> Plan</CardTitle>
            <StatusPill tone={lifecycleTone(tenant.status)}>{tenant.status.replace('_', ' ')}</StatusPill>
          </CardHeader>
          <CardContent className="space-y-3 text-[13px]">
            <div className="flex items-baseline justify-between"><span className="text-muted-foreground">Base plan</span><span className="font-medium">{fmtAud(base)} + GST / mo</span></div>
            <div className="flex items-baseline justify-between"><span className="text-muted-foreground">Includes</span><span className="font-medium">Practice HQ · CRM · Billing</span></div>
            <div className="flex items-baseline justify-between"><span className="text-muted-foreground">Add-on modules</span><span className="font-medium">{owned.length}</span></div>
            {billing && <div className="flex items-baseline justify-between"><span className="text-muted-foreground">Next charge</span><span className="font-medium">{billing.next_charge_at ? `${fmtCents(billing.next_charge_estimate_cents)} on ${fmtDate(billing.next_charge_at)}` : '—'}</span></div>}
            {tenant.status === 'trialing' && (
              <div className="rounded-[5px] bg-accent px-3 py-2 text-accent-foreground">
                {trialDaysLeft(tenant)} days left. First charge {fmtAud(base * (1 + GST_RATE))} on day 16 to card ····{tenant.cardLast4}.
              </div>
            )}
            {billing?.billing_mode === 'simulate' && <div className="text-[12px] text-muted-foreground">Billing is in simulate mode — charges are recorded, not taken, until Stripe is connected.</div>}
            {billing && billing.recent.length > 0 && (
              <ul className="divide-y rounded-[5px] border text-[12px]">
                {billing.recent.slice(0, 4).map((e) => <li key={e.id} className="flex items-center justify-between px-3 py-1.5"><span className="text-muted-foreground">{e.kind.replace('.', ' · ')}{e.module_key ? ` · ${e.module_key}` : ''}</span><span className="tabular-nums">{e.total_cents ? fmtCents(e.total_cents) : '—'}</span></li>)}
              </ul>
            )}
            <Button asChild variant="outline" size="sm" className="w-full"><Link to="/hq/modules">Modules &amp; subscription <ArrowRight className="ml-1 size-3.5" /></Link></Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><Users className="size-4 text-primary" /> Users</CardTitle>
            <span className="text-[12px] text-muted-foreground">{members ? `${members.length} people` : '…'}</span>
          </CardHeader>
          <CardContent className="space-y-3 text-[13px]">
            <div className="flex items-baseline justify-between"><span className="text-muted-foreground">Active</span><span className="font-medium">{members?.filter((m) => m.status === 'active').length ?? '–'}</span></div>
            <div className="flex items-baseline justify-between"><span className="text-muted-foreground">Invited, not yet joined</span><span className="font-medium">{members?.filter((m) => m.status === 'invited').length ?? '–'}</span></div>
            <div className="flex items-baseline justify-between"><span className="text-muted-foreground">Last access review</span><span className="font-medium text-warn">Overdue</span></div>
            <Button asChild variant="outline" size="sm" className="w-full"><Link to="/hq/users">Users &amp; access <ArrowRight className="ml-1 size-3.5" /></Link></Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><Plug className="size-4 text-primary" /> Integrations</CardTitle>
            {attention.length > 0 && <StatusPill tone="warn">{attention.length} need attention</StatusPill>}
          </CardHeader>
          <CardContent className="space-y-2 text-[13px]">
            {INTEGRATIONS.slice(0, 4).map((i) => (
              <div key={i.key} className="flex items-center justify-between">
                <span>{i.name}</span>
                <StatusPill tone={i.status === 'connected' ? 'success' : i.status === 'attention' ? 'warn' : 'neutral'}>
                  {i.status === 'connected' ? 'Connected' : i.status === 'attention' ? 'Attention' : 'Not connected'}
                </StatusPill>
              </div>
            ))}
            <Button asChild variant="outline" size="sm" className="mt-1 w-full"><Link to="/hq/integrations">Integration hub <ArrowRight className="ml-1 size-3.5" /></Link></Button>
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><ShieldCheck className="size-4 text-primary" /> Your modules</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {['hq', 'crm', 'billing'].map((k) => {
              const m = getModule(k as any);
              return (
                <div key={k} className="flex items-center gap-3 rounded-[5px] border bg-secondary/40 px-3 py-2.5">
                  <ModuleIcon name={m.icon} className="size-4 text-primary" />
                  <div className="min-w-0 flex-1"><div className="truncate text-[13px] font-medium">{m.shortName}</div><div className="text-[11px] text-muted-foreground">Base plan</div></div>
                </div>
              );
            })}
            {owned.map((m) => (
              <div key={m.key} className="flex items-center gap-3 rounded-[5px] border px-3 py-2.5">
                <ModuleIcon name={m.icon} className="size-4 text-primary" />
                <div className="min-w-0 flex-1"><div className="truncate text-[13px] font-medium">{m.shortName}</div><div className="text-[11px] text-muted-foreground">{m.pricing.unit}</div></div>
              </div>
            ))}
            <Link to="/hq/modules" className="flex items-center justify-center gap-2 rounded-[5px] border border-dashed px-3 py-2.5 text-[13px] text-muted-foreground hover:bg-secondary">
              + Add a module
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
