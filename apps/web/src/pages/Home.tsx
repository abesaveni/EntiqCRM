import { Link } from 'react-router-dom';
import { formatDistanceToNow, isPast } from 'date-fns';
import { ArrowRight, AlertTriangle, CheckSquare, Clock, Sparkles } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Button } from '@entiq/ui/button';
import { getModule, purchasableModules } from '@entiq/modules';
import { useSession, isEntitled } from '@/state/session';
import { CLIENTS, TASKS, ACTIVITY } from '@/mock/data';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, riskTone } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

/** Role-based home — blueprint §2: work due, risks, approvals, recent activity, next best actions. */
export function Home() {
  const user = useSession((s) => s.user);
  const tenant = useSession((s) => s.tenant);
  const subscriptions = useSession((s) => s.subscriptions);

  const overdue = TASKS.filter((t) => !t.done && isPast(new Date(t.due)));
  const dueSoon = TASKS.filter((t) => !t.done && !isPast(new Date(t.due)));
  const risks = CLIENTS.filter((c) => c.risk === 'Medium' || c.risk === 'High');
  const pipeline = CLIENTS.filter((c) => ['Lead', 'Proposal', 'Onboarding'].includes(c.stage));
  const recent = [...ACTIVITY].sort((a, b) => +new Date(b.at) - +new Date(a.at)).slice(0, 7);
  const nextAdd = purchasableModules().filter((m) => m.status !== 'planned' && !isEntitled({ tenant, subscriptions }, m.key)).slice(0, 3);

  return (
    <div className="page">
      <PageHeader
        eyebrow={new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' })}
        title={`Good ${greeting()}, ${user?.name.split(' ')[0]}`}
        description="What needs you today, across every module you have."
      />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Overdue tasks" value={overdue.length} tone={overdue.length ? 'error' : 'neutral'} to="/tasks" />
        <Stat label="Due this week" value={dueSoon.length} to="/tasks" />
        <Stat label="Elevated-risk clients" value={risks.length} tone={risks.length ? 'warn' : 'neutral'} to="/clients?risk=elevated" />
        <Stat label="In pipeline" value={pipeline.length} to="/pipeline" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><CheckSquare className="size-4 text-primary" /> Work due</CardTitle>
            <Button asChild variant="ghost" size="sm"><Link to="/tasks">All tasks <ArrowRight className="ml-1 size-3.5" /></Link></Button>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {[...overdue, ...dueSoon].slice(0, 6).map((t) => {
                const c = CLIENTS.find((x) => x.id === t.clientId);
                const late = isPast(new Date(t.due));
                return (
                  <li key={t.id} className="flex items-center gap-3 px-6 py-2.5">
                    <span className={`size-2 shrink-0 rounded-full ${late ? 'bg-error' : t.priority === 'High' ? 'bg-warn' : 'bg-muted-foreground/40'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px]">{t.title}</div>
                      <div className="truncate text-[12px] text-muted-foreground">{c ? <Link to={`/clients/${c.id}`} className="hover:underline">{c.name}</Link> : 'Practice'} · {t.owner}</div>
                    </div>
                    <span className={`shrink-0 text-[12px] ${late ? 'font-medium text-error' : 'text-muted-foreground'}`}>
                      {late ? 'overdue ' : 'due '}{formatDistanceToNow(new Date(t.due), { addSuffix: !late })}
                    </span>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><AlertTriangle className="size-4 text-warn" /> Risks</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {risks.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 px-6 py-2.5">
                  <Link to={`/clients/${c.id}`} className="min-w-0 truncate text-[13px] hover:underline">{c.name}</Link>
                  <StatusPill tone={riskTone(c.risk)}>{c.risk}</StatusPill>
                </li>
              ))}
              {CLIENTS.filter((c) => c.stage === 'Review').map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 px-6 py-2.5">
                  <Link to={`/clients/${c.id}`} className="min-w-0 truncate text-[13px] hover:underline">{c.name}</Link>
                  <StatusPill tone="warn">Review due</StatusPill>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><Clock className="size-4 text-primary" /> Recent activity</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {recent.map((a) => {
                const c = CLIENTS.find((x) => x.id === a.clientId);
                const m = getModule(a.module);
                return (
                  <li key={a.id} className="flex items-start gap-3 px-6 py-2.5">
                    <ModuleIcon name={m.icon} className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px]">{a.summary}</div>
                      <div className="text-[12px] text-muted-foreground">
                        {c && <Link to={`/clients/${c.id}`} className="hover:underline">{c.name}</Link>} · {m.shortName} · {a.actor}
                      </div>
                    </div>
                    <span className="shrink-0 text-[12px] text-muted-foreground">{formatDistanceToNow(new Date(a.at), { addSuffix: true })}</span>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><Sparkles className="size-4 text-primary" /> Next best actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-[13px]">
            {overdue[0] && <Action to="/tasks" text={`Clear "${overdue[0].title}" — ${formatDistanceToNow(new Date(overdue[0].due))} overdue.`} />}
            {pipeline.find((c) => c.stage === 'Proposal') && <Action to="/pipeline" text="Follow up Greenline Logistics — proposal unanswered 2 days." />}
            {nextAdd.map((m) => (
              <Action key={m.key} to={`/hq/modules/${m.key}`} text={`Add ${m.shortName}: ${m.outcome}`} upsell />
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = 'neutral', to }: { label: string; value: number; tone?: 'neutral' | 'warn' | 'error'; to: string }) {
  const color = tone === 'error' ? 'text-error' : tone === 'warn' ? 'text-warn' : 'text-foreground';
  return (
    <Link to={to} className="rounded-[6px] border bg-card px-5 py-4 transition-colors hover:bg-secondary">
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div className={`mt-1 text-[26px] font-semibold leading-none tabular-nums ${color}`}>{value}</div>
    </Link>
  );
}

function Action({ to, text, upsell }: { to: string; text: string; upsell?: boolean }) {
  return (
    <Link to={to} className={`block rounded-[5px] border px-3 py-2 leading-[19px] transition-colors hover:bg-secondary ${upsell ? 'border-dashed border-warn/50 text-muted-foreground' : ''}`}>
      {text}
    </Link>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
}
